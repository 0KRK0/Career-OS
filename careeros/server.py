"""Career OS local server: http://127.0.0.1:8765 (only reachable from this computer)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import yaml
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import agents, answers, brain, db, learn, opps, prepare
from .config import CONFIG_DIR, LOG_DIR, ROOT, WEB_DIR, companies, cover_letter_name, profile, save_profile, save_settings, settings

app = FastAPI(title="Career OS", docs_url="/api/docs")
_filler: subprocess.Popen | None = None
_brain_cache: dict = {"t": 0, "v": {}}


@app.on_event("startup")
def _startup() -> None:
    db.conn()
    db.repair_v4()
    agents.ensure_defaults()
    if os.environ.get("CAREEROS_NO_SCHEDULER") != "1":
        agents.start_scheduler()


# ---------------- status ----------------

def filler_alive() -> bool:
    hb = db.kv_get("filler_heartbeat", 0) or 0
    return bool(hb) and time.time() - float(hb) < 15


def _filler_watch() -> None:
    """Start the autofill browser when the scheduler queued applications for it."""
    while True:
        time.sleep(15)
        try:
            if db.kv_get("filler_wanted") and db.q1("SELECT id FROM fill_requests WHERE status='pending' LIMIT 1"):
                db.kv_set("filler_wanted", False)
                ensure_filler()
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=_filler_watch, daemon=True, name="filler-watch").start()


@app.get("/api/status")
def status():
    if time.time() - _brain_cache["t"] > 30:
        _brain_cache.update(t=time.time(), v=brain.status())
    s = settings()
    b = dict(_brain_cache["v"], active=brain.active_count(), auth_error=(db.kv_get("brain_auth") or {}).get("msg", ""))
    lim = db.kv_get("brain_limited") or {}
    from datetime import datetime, timedelta, timezone
    b["limited"] = bool(lim) and lim.get("at", "") >= (datetime.now(timezone.utc) - timedelta(hours=5)).replace(microsecond=0).isoformat()
    done = db.kv_get("scout_slots_done", {}) or {}
    return {
        "brain": b, "filler": filler_alive(), "stats": opps.stats(),
        "scout_times": s.get("scout_times"), "slots_done_today": done.get("done", []) if done.get("date") == time.strftime("%Y-%m-%d") else [],
        "email_enabled": bool((s.get("email") or {}).get("enabled") and (s.get("email") or {}).get("app_password")),
        "email_last_check": db.kv_get("email_last_check"),
        "cv_ok": Path(s.get("cv_path") or "").exists(), "resume_ok": Path(s.get("resume_path") or "").exists(),
        "books": len(learn.books()), "running_agents": [a["name"] for a in agents.all_agents() if a["running"]],
        "unseen": db.q1("SELECT COUNT(*) n FROM notifications WHERE seen=0")["n"],
    }


@app.get("/api/notifications")
def notifications(unseen: int = 0):
    rows = db.q("SELECT * FROM notifications " + ("WHERE seen=0 " if unseen else "") + "ORDER BY id DESC LIMIT 50")
    return rows


@app.post("/api/notifications/seen")
def notifications_seen():
    db.x("UPDATE notifications SET seen=1 WHERE seen=0")
    return {"ok": True}


# ---------------- opportunities (Apply) ----------------

@app.get("/api/opps")
def list_opps(status: str | None = None, kind: str | None = None, country: str | None = None, track: str | None = None,
              q: str | None = None, min_score: int = 0, limit: int = 300, order: str = "score",
              posted_days: int = 0, sponsor_only: int = 0, offset: int = 0):
    return opps.listing(status, kind, country, track, q, min_score, limit, order, posted_days, bool(sponsor_only), offset)


@app.get("/api/facets")
def get_facets(min_score: int = 0):
    return opps.facets(min_score)


@app.put("/api/filters")
def put_filters(body: dict = Body(...)):
    """The Apply filter panel + automation switches; saved so they're there next time."""
    new = {}
    if "filters" in body and settings().get("remember_filters", True):
        new["filters"] = body["filters"]
    for k in ("auto_prepare", "auto_open_autofill", "ai_fill_unknown", "remember_filters", "scout_times", "min_score"):
        if k in body:
            new[k] = body[k]
    if "toast" in body:
        new["notify"] = {"toast": bool(body["toast"])}
    if "email_enabled" in body:
        new["email"] = {"enabled": bool(body["email_enabled"])}
    if new:
        save_settings(new)
    return {"ok": True}


@app.get("/api/opps/{oid}")
def get_opp(oid: int):
    o = opps.get(oid)
    if not o:
        raise HTTPException(404)
    o["prepared"] = opps.prepared(oid)
    o["events"] = db.q("SELECT * FROM events WHERE opp_id=? ORDER BY id DESC", (oid,))
    o["emails"] = db.q("SELECT sender,subject,received_at,category,snippet FROM emails WHERE opp_id=? ORDER BY received_at DESC", (oid,))
    d = opps.app_dir(oid)
    o["files"] = [p.name for p in d.iterdir() if p.is_file()]
    return o


@app.post("/api/opps")
def add_opp(body: dict = Body(...)):
    url = (body.get("url") or "").strip()
    if not url and not body.get("title"):
        raise HTTPException(400, "url or title required")
    title, org = body.get("title") or "", body.get("org") or ""
    if url and not title:
        try:
            r = httpx.get(url, timeout=12, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 career-os"})
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else url
        except httpx.HTTPError:
            title = url
    if url and not org:
        org = re.sub(r"^www\.|\.(com|co\.uk|io|ai|org|net)$", "", httpx.URL(url).host or "")
    oid, _ = opps.upsert({"source": "manual", "ext_id": url or f"manual:{title}:{org}", "title": title, "org": org,
                          "location": body.get("location", ""), "url": url, "apply_url": url,
                          "deadline": body.get("deadline", ""), "kind": body.get("kind") or None,
                          "description": body.get("description", "")})
    if body.get("status"):
        db.set_status(oid, body["status"], "added manually")
    return {"id": oid}


@app.patch("/api/opps/{oid}")
def patch_opp(oid: int, body: dict = Body(...)):
    o = opps.get(oid)
    if not o:
        raise HTTPException(404)
    if "status" in body and body["status"] != o["status"]:
        db.set_status(oid, body["status"], body.get("status_note", ""))
    allowed = ["notes", "contact", "deadline", "followup_at", "title", "org", "location", "kind", "apply_url"]
    upd = {k: v for k, v in body.items() if k in allowed}
    if upd:
        db.x(f"UPDATE opportunities SET {','.join(k + '=?' for k in upd)}, updated_at=? WHERE id=?",
             (*upd.values(), db.now(), oid))
        if "notes" in upd:
            db.event(oid, "note", upd["notes"][:300])
    return {"ok": True}


@app.post("/api/opps/bulk")
def bulk(body: dict = Body(...)):
    ids = [int(i) for i in body.get("ids", [])]
    st = body.get("status")
    for i in ids:
        db.set_status(i, st, "bulk")
    return {"ok": True, "n": len(ids)}


_prep_threads: dict[int, threading.Thread] = {}


@app.post("/api/opps/{oid}/prepare")
def prepare_opp(oid: int):
    if oid in _prep_threads and _prep_threads[oid].is_alive():
        return {"ok": True, "already": True}

    def work():
        try:
            prepare.prepare(oid, log=lambda m: db.event(oid, "prepare", m))
        except Exception as e:  # noqa: BLE001
            db.event(oid, "prepare", f"failed: {e}")
    t = threading.Thread(target=work, daemon=True)
    _prep_threads[oid] = t
    t.start()
    return {"ok": True}


@app.get("/api/opps/{oid}/file/{name}")
def opp_file(oid: int, name: str):
    p = opps.app_dir(oid) / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p))


@app.put("/api/opps/{oid}/cover")
def save_cover(oid: int, body: dict = Body(...)):
    d = opps.app_dir(oid)
    text = body.get("text", "")
    (d / "cover_letter.txt").write_text(text, encoding="utf-8")
    pj = opps.prepared(oid)
    pj["cover_letter"] = text
    (d / "prepared.json").write_text(json.dumps(pj, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = prepare.render_pdf(prepare._letter_html(text, profile()), d / cover_letter_name())
    db.event(oid, "cover", "cover letter edited")
    return {"ok": ok}


def ensure_filler() -> None:
    global _filler
    if filler_alive() or (_filler and _filler.poll() is None):
        return
    log = open(LOG_DIR / "filler.out.log", "a", encoding="utf-8")
    _filler = subprocess.Popen([sys.executable, "-m", "careeros.filler"], cwd=str(ROOT), stdout=log, stderr=log,
                               creationflags=0x08000000 if sys.platform == "win32" else 0)


@app.post("/api/fill")
def fill(body: dict = Body(...)):
    """Queue applications for autofill. body: {ids:[..]} or {url:'...'}"""
    ids = [int(i) for i in body.get("ids", [])]
    n = 0
    for i in ids:
        o = opps.get(i)
        if not o:
            continue
        url = o.get("apply_url") or o.get("url")
        if not url:
            continue
        db.x("INSERT INTO fill_requests(opp_id,url,status,created_at) VALUES(?,?,?,?)", (i, url, "pending", db.now()))
        n += 1
    if body.get("url"):
        oid = add_opp({"url": body["url"]})["id"]
        db.x("INSERT INTO fill_requests(opp_id,url,status,created_at) VALUES(?,?,?,?)", (oid, body["url"], "pending", db.now()))
        n += 1
    if n:
        ensure_filler()
    return {"queued": n}


# ---------------- Track ----------------

@app.get("/api/track")
def track():
    rows = opps.listing(status=",".join(opps.ACTIVE_PIPELINE + ["filling", "rejected", "withdrawn"]), limit=1000, order="updated")
    now = time.time()
    for r in rows:
        r["days_since_submit"] = opps.days_between(r["submitted_at"]) if r.get("submitted_at") else None
        r["days_since_contact"] = opps.days_between(r["last_contact_at"]) if r.get("last_contact_at") else None
    upcoming = db.q("SELECT id,title,org,deadline,status,score FROM opportunities WHERE deadline!='' AND deadline>=date('now') "
                    "AND status IN ('new','shortlisted','preparing','ready','filling') ORDER BY deadline LIMIT 40")
    return {"pipeline": rows, "deadlines": upcoming,
            "emails": db.q("SELECT e.*, o.org, o.title FROM emails e LEFT JOIN opportunities o ON o.id=e.opp_id "
                           "WHERE e.category!='' ORDER BY e.received_at DESC LIMIT 60")}


@app.get("/api/answers")
def get_answers():
    return {"answers": db.q("SELECT * FROM answers ORDER BY updated_at DESC"),
            "corrections": db.q("SELECT c.*, o.org, o.title FROM corrections c LEFT JOIN opportunities o ON o.id=c.opp_id "
                                "ORDER BY c.id DESC LIMIT 200")}


@app.put("/api/answers/{aid}")
def put_answer(aid: int, body: dict = Body(...)):
    db.x("UPDATE answers SET value=?, source='you', updated_at=? WHERE id=?", (body.get("value", ""), db.now(), aid))
    return {"ok": True}


@app.post("/api/answers")
def add_answer(body: dict = Body(...)):
    label = body.get("label", "")
    db.x("INSERT INTO answers(key,label,value,source,uses,updated_at) VALUES(?,?,?,?,0,?) ON CONFLICT(key) DO UPDATE SET "
         "value=excluded.value, updated_at=excluded.updated_at", (answers.norm_label(label), label, body.get("value", ""), "you", db.now()))
    return {"ok": True}


@app.delete("/api/answers/{aid}")
def del_answer(aid: int):
    db.x("DELETE FROM answers WHERE id=?", (aid,))
    return {"ok": True}


# ---------------- Agents ----------------

@app.get("/api/agents")
def get_agents():
    return {"agents": agents.all_agents(),
            "health": db.q("SELECT * FROM source_health ORDER BY ok, key"),
            "runs": db.q("SELECT id,agent_name,started_at,finished_at,status,found FROM runs ORDER BY id DESC LIMIT 40")}


@app.get("/api/runs/{rid}")
def get_run(rid: int):
    return db.q1("SELECT * FROM runs WHERE id=?", (rid,))


@app.post("/api/agents/{aid}/run")
def run_agent(aid: int):
    return {"started": agents.run_agent(aid)}


@app.post("/api/agents/run-scouts")
def run_scouts():
    def cycle():
        agents.run_all_scouts(slot_index=None, wait=True)
        opps.rescore_all()
        p = agents.agent_by_kind("prepare")
        if p and p["enabled"]:
            agents.run_agent(p["id"], wait=True)
    threading.Thread(target=cycle, daemon=True).start()
    return {"ok": True}


@app.patch("/api/agents/{aid}")
def patch_agent(aid: int, body: dict = Body(...)):
    for k in ("enabled", "on_schedule"):
        if k in body:
            db.x(f"UPDATE agents SET {k}=? WHERE id=?", (1 if body[k] else 0, aid))
    if "config" in body:
        db.x("UPDATE agents SET config=? WHERE id=?", (json.dumps(body["config"]), aid))
    if "name" in body:
        db.x("UPDATE agents SET name=? WHERE id=?", (body["name"], aid))
    return {"ok": True}


@app.post("/api/agents")
def new_agent(body: dict = Body(...)):
    kind = body.get("kind", "research")
    name = body.get("name") or f"Research · {body.get('field', 'jobs')} ({body.get('country', 'worldwide')})"
    cfg = body.get("config") or {k: body[k] for k in ("field", "country", "kinds", "extra") if body.get(k)}
    if kind == "research":
        cfg.setdefault("slots", 1)
    aid = db.x("INSERT INTO agents(name,kind,config,enabled,on_schedule,created_at) VALUES(?,?,?,?,?,?)",
               (name, kind, json.dumps(cfg), 1, 1, db.now()))
    return {"id": aid}


@app.delete("/api/agents/{aid}")
def del_agent(aid: int):
    db.x("DELETE FROM agents WHERE id=?", (aid,))
    return {"ok": True}


# ---------------- Learn ----------------

@app.get("/api/learn")
def get_learn():
    return learn.tracks()


@app.post("/api/learn/progress")
def learn_progress(body: dict = Body(...)):
    learn.save_progress(body["module_id"], body.get("status"), body.get("notes"))
    return {"ok": True}


@app.post("/api/learn/test")
def learn_test(body: dict = Body(...)):
    try:
        return learn.make_test(body["module_id"], int(body.get("n", 6)), body.get("difficulty", "interview level"))
    except brain.BrainError as e:
        raise HTTPException(503, str(e))


@app.post("/api/learn/grade")
def learn_grade(body: dict = Body(...)):
    try:
        return learn.grade(int(body["test_id"]), body.get("answers", {}))
    except brain.BrainError as e:
        raise HTTPException(503, str(e))


@app.post("/api/learn/run")
def learn_run(body: dict = Body(...)):
    row = db.q1("SELECT payload FROM tests WHERE id=?", (int(body["test_id"]),))
    q = next((q for q in json.loads(row["payload"]) if q["id"] == body["qid"]), None)
    if not q:
        raise HTTPException(404)
    return {"results": learn.run_code(body.get("code", ""), q.get("tests") or [], q.get("function_name") or "solve")}


@app.post("/api/learn/mock")
def learn_mock(body: dict = Body(...)):
    try:
        return learn.mock_turn(body.get("track_id", ""), body.get("module_id", ""), body.get("message", ""), body.get("session"))
    except brain.BrainError as e:
        raise HTTPException(503, str(e))


@app.get("/books/{rel:path}")
def book(rel: str):
    base = Path(settings().get("books_dir") or "").resolve()
    p = (base / rel).resolve()
    if base not in p.parents or not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), media_type="application/pdf" if p.suffix.lower() == ".pdf" else None,
                        headers={"Content-Disposition": f'inline; filename="{p.name}"'})


# ---------------- Settings ----------------

@app.get("/api/settings")
def get_settings():
    s = settings()
    if s["email"].get("app_password"):
        s["email"]["app_password"] = "••••••••"
    return {"settings": s,
            "profile_yaml": (CONFIG_DIR / "profile.yaml").read_text(encoding="utf-8") if (CONFIG_DIR / "profile.yaml").exists() else "",
            "companies_yaml": (CONFIG_DIR / "companies.yaml").read_text(encoding="utf-8") if (CONFIG_DIR / "companies.yaml").exists() else ""}


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    new = body.get("settings") or {}
    if (new.get("email") or {}).get("app_password", "").startswith("••"):
        new["email"].pop("app_password")
    if new:
        save_settings(new)
    if body.get("profile_yaml") is not None:
        try:
            save_profile(yaml.safe_load(body["profile_yaml"]) or {})
        except yaml.YAMLError as e:
            raise HTTPException(400, f"profile.yaml: {e}")
    if body.get("companies_yaml") is not None:
        try:
            yaml.safe_load(body["companies_yaml"])
            (CONFIG_DIR / "companies.yaml").write_text(body["companies_yaml"], encoding="utf-8")
        except yaml.YAMLError as e:
            raise HTTPException(400, f"companies.yaml: {e}")
    if "country_weights" in new or "tracks_enabled" in new:
        threading.Thread(target=opps.rescore_all, daemon=True).start()
    return {"ok": True}


@app.post("/api/settings/test-email")
def test_email():
    from . import mail
    try:
        return {"ok": mail.test_login() == "ok"}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=400)


# ---------------- Setup wizard (any user) ----------------

@app.get("/api/onboarding")
def onboarding():
    from . import universal
    from .config import onboarded
    p = profile() if (CONFIG_DIR / "profile.yaml").exists() else {}
    return {"onboarded": onboarded(), "profile": p, "settings": {k: settings().get(k) for k in ("cv_path", "resume_path", "books_dir", "scout_times", "profile_dir")},
            "catalog": {"roles": list(universal.ROLES.keys()), "countries": list(universal.COUNTRIES.keys()) + list(universal.REGIONS.keys()),
                        "kinds": ["job", "internship", "graduate", "apprenticeship", "fellowship", "scholarship", "parttime", "competition"],
                        "sectors": universal.SECTORS, "role_sectors": universal.ROLE_SECTORS,
                        "levels": ["student", "early", "mid", "senior"]},
            "claude": brain.status(), "has_facts": (CONFIG_DIR / "career-facts.md").exists()}


def _deep(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@app.post("/api/onboarding/save")
def onboarding_save(body: dict = Body(...)):
    if body.get("profile"):
        cur = profile() if (CONFIG_DIR / "profile.yaml").exists() else {}
        new = _deep(cur, body["profile"])
        edu = (new.get("education") or [{}])[0] if new.get("education") else {}
        # keep the flat fields the form filler uses in sync with the first education entry
        for flat, key in (("school", "school"), ("discipline", "field"), ("degree", "level"), ("grad_year", "end")):
            if edu.get(key):
                new[flat] = str(edu[key])
        if new.get("first_name") and new.get("last_name") and not new.get("full_name"):
            new["full_name"] = f"{new['first_name']} {new['last_name']}"
        save_profile(new)
    if body.get("settings"):
        save_settings(body["settings"])
    return {"ok": True, "profile": profile()}


@app.get("/api/onboarding/preview")
def onboarding_preview():
    from . import universal
    if not (CONFIG_DIR / "profile.yaml").exists():
        return {"agents": [], "tracks": []}
    p = profile()
    ag = [a["name"] for a in universal.generate_agents(p) if a["kind"] in ("ats", "feeds", "research", "discover", "programs")]
    core = set(universal.degree_tracks(p))
    titles = {t["id"]: t["title"] for t in learn._tracks_raw()["tracks"]}
    tr = [{"title": titles.get(t, t), "core": t in core} for t in universal.default_learn_tracks(p)]
    tr += [{"title": c, "core": False} for c in universal.custom_tracks_needed(p)]
    return {"agents": ag, "tracks": tr, "sectors": universal.sectors_for(p)}


@app.post("/api/onboarding/cv")
def onboarding_cv(body: dict = Body(...)):
    """Import a CV (upload as base64, a path on this PC, or pasted text) -> profile + your fact sheet."""
    from . import cvimport
    try:
        return cvimport.import_cv(filename=body.get("filename"), data_b64=body.get("data"), path=body.get("path"),
                                  text=body.get("text"), overwrite=bool(body.get("overwrite", True)))
    except brain.BrainError as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------- Career folder + "About me" (Claude's understanding of you) ----------------

@app.get("/api/aboutme")
def aboutme_get():
    from . import aboutme
    f = aboutme.folder()
    return {"profile_dir": str(f) if f else "", "exists": bool(f and f.exists()),
            "work_dir": str(aboutme.work_dir() or ""), "md": aboutme.about_md(), "questions": aboutme.questions(),
            "files": aboutme.files(), "history_chars": len(aboutme.history(10**7)),
            "job": db.kv_get("aboutme_job") or {}, "claude": brain.status(),
            "cv_path": settings().get("cv_path", ""),
            "suggest": str(Path.home() / "Documents" / "My career")}


@app.put("/api/aboutme")
def aboutme_put(body: dict = Body(...)):
    from . import aboutme
    if not aboutme.work_dir():
        raise HTTPException(400, "Choose your career folder first.")
    aboutme._write("about-me.md", body.get("md", ""))
    return {"ok": True}


@app.post("/api/aboutme/folder")
def aboutme_folder(body: dict = Body(...)):
    from . import aboutme
    path = (body.get("path") or "").strip()
    if not path:
        raise HTTPException(400, "Type or pick a folder.")
    try:
        return aboutme.set_folder(path)
    except OSError as e:
        raise HTTPException(400, f"Can't use that folder: {e}")


@app.post("/api/aboutme/pick")
def aboutme_pick():
    """Open a native 'choose folder' dialog on this PC (the app runs locally)."""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Choose (or create) your career folder")
        root.destroy()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"No folder dialog here ({e.__class__.__name__}) - type the path instead."}
    return {"ok": bool(path), "path": path or ""}


@app.post("/api/aboutme/open")
def aboutme_open():
    from . import aboutme
    f = aboutme.folder()
    if not f or not f.exists():
        raise HTTPException(400, "No career folder yet.")
    if sys.platform == "win32":
        os.startfile(str(f))  # noqa: S606
    return {"ok": True}


@app.post("/api/aboutme/build")
def aboutme_build():
    from . import aboutme
    f = aboutme.folder()
    if not f or not f.exists():
        raise HTTPException(400, "Choose your career folder first.")
    if not brain.available():
        raise HTTPException(503, "Connect Claude Code first (Settings → Claude) - it's what reads your folder.")
    job = db.kv_get("aboutme_job") or {}
    if job.get("status") == "running" and time.time() - _ts(job.get("at")) < 2700:
        return {"ok": True, "already": True}
    db.kv_set("aboutme_job", {"status": "running", "detail": "Starting…", "at": db.now()})
    threading.Thread(target=lambda: _safe(aboutme.build), daemon=True).start()
    return {"ok": True}


@app.post("/api/aboutme/answers")
def aboutme_answers(body: dict = Body(...)):
    from . import aboutme
    ans = body.get("answers") or {}
    if not brain.available():
        # no Claude: keep the answers verbatim so nothing is lost
        block = "\n".join(f"- **{q}** {a}" for q, a in ans.items() if str(a).strip())
        if block:
            aboutme._write("about-me.md", (aboutme.about_md() or "# About me\n") + "\n\n## In my own words\n" + block + "\n")
            aboutme._write("open-questions.md", "\n".join(f"- {q}" for q in aboutme.questions() if not str(ans.get(q, "")).strip()) + "\n")
        return {"ok": True, "md": aboutme.about_md(), "questions": aboutme.questions(), "merged": False}
    try:
        r = aboutme.merge_answers(ans)
    except brain.BrainError as e:
        raise HTTPException(503, str(e))
    return {"ok": True, "md": r["about_me_md"], "questions": r["questions"], "merged": True}


def _ts(s) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


@app.post("/api/onboarding/finish")
def onboarding_finish():
    from . import universal
    p = profile()
    p["onboarded"] = True
    save_profile(p)
    universal.apply_goals_to_settings(p)
    agents.ensure_defaults()
    res = agents.sync_agents()
    opps.rescore_all()
    for subject in universal.custom_tracks_needed(p):
        threading.Thread(target=lambda s=subject: _safe(learn.create_track, s), daemon=True).start()
    run_scouts()
    total = db.q1("SELECT COUNT(*) n FROM agents WHERE enabled=1")["n"]
    return {"ok": True, "agents": res, "agents_total": total}


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None


@app.post("/api/agents/sync")
def agents_sync():
    return agents.sync_agents()


# ---------------- Learn (AI) ----------------

@app.post("/api/learn/select")
def learn_select(body: dict = Body(...)):
    learn.select([str(i) for i in body.get("selected", [])])
    return {"ok": True}


@app.post("/api/learn/track")
def learn_new_track(body: dict = Body(...)):
    subject = (body.get("subject") or "").strip()
    if not subject:
        raise HTTPException(400, "subject required")
    threading.Thread(target=lambda: _safe(learn.create_track, subject), daemon=True).start()
    return {"ok": True}


@app.post("/api/learn/deepen")
def learn_deepen(body: dict = Body(...)):
    threading.Thread(target=lambda: _safe(learn.deepen, body["track_id"], int(body["level"])), daemon=True).start()
    return {"ok": True}


@app.post("/api/learn/refresh")
def learn_refresh(body: dict = Body(...)):
    threading.Thread(target=lambda: _safe(learn.refresh, body["track_id"]), daemon=True).start()
    return {"ok": True}


@app.post("/api/learn/teach")
def learn_teach(body: dict = Body(...)):
    try:
        return learn.teach(body.get("track_id", ""), body.get("module_id", ""), body.get("message", ""),
                           body.get("session"), int(body.get("level") or 0))
    except brain.BrainError as e:
        raise HTTPException(503, str(e))


# ---------------- Claude connection + usage meter ----------------

FREE_FEATURES = ["Company job-board scouts (Greenhouse, Lever, Ashby, Workday…)", "Careers-page crawler", "Open job feeds",
                 "Match scoring & filters", "Autofill + learning from your edits", "Gmail tracking & follow-up drafts",
                 "Deadline pop-ups", "Your library & progress"]
PLAN_FEATURES = ["Company & programme finders", "Research agents", "Cover letters", "Drafted form answers",
                 "AI teacher, tests & mock interviews", "Learn builder", "CV import",
                 "About me (reading your career folder)", "Ask Claude chat in the application browser"]


@app.get("/api/usage")
def usage(days: int = 14):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    iso = lambda d: d.replace(microsecond=0).isoformat()
    def agg(since):
        rows = db.q("SELECT purpose, COUNT(*) calls, SUM(input_tokens+output_tokens) tokens, SUM(cache_tokens) cache, "
                    "SUM(web_searches) web, SUM(api_equiv_usd) usd, SUM(duration_ms) ms FROM usage WHERE at>=? GROUP BY purpose "
                    "ORDER BY tokens DESC", (iso(since),))
        return {"by_purpose": rows, "tokens": sum(r["tokens"] or 0 for r in rows), "calls": sum(r["calls"] for r in rows),
                "web": sum(r["web"] or 0 for r in rows), "usd": round(sum(r["usd"] or 0 for r in rows), 2)}
    day_rows = db.q("SELECT substr(at,1,10) d, purpose, SUM(input_tokens+output_tokens) tokens FROM usage WHERE at>=? "
                    "GROUP BY d, purpose ORDER BY d", (iso(now - timedelta(days=days)),))
    lim = db.kv_get("brain_limited") or {}
    paused = bool(lim) and lim.get("at", "") >= iso(now - timedelta(hours=5))
    return {"window": agg(now - timedelta(hours=5)), "today": agg(now.replace(hour=0, minute=0, second=0)),
            "week": agg(now - timedelta(days=7)), "month": agg(now - timedelta(days=30)), "days": day_rows,
            "limit": {"paused": paused, "at": lim.get("at"), "msg": lim.get("msg"), "estimate_tokens": lim.get("window_tokens")},
            "brain": brain.status(), "extra_cost": 0, "free": FREE_FEATURES, "plan": PLAN_FEATURES,
            "api_key_blocked": True, "max_parallel": settings().get("max_parallel_agents", 2)}


@app.get("/api/ai")
def ai_info():
    """Which AI app does the thinking, and the choices."""
    return {"provider": brain.provider(), "status": brain.status(),
            "choices": [{"id": k, "name": v["name"], "app": v["app"], "plan": v["plan"], "installed": bool(__import__("careeros.config", fromlist=["cli_exe"]).cli_exe(k))}
                        for k, v in brain.PROVIDERS.items()]}


@app.put("/api/ai")
def ai_set(body: dict = Body(...)):
    p = (body.get("provider") or "").lower()
    if p not in brain.PROVIDERS:
        raise HTTPException(400, "Unknown AI")
    cur = settings().get("llm") or {}
    save_settings({"llm": {"provider": p, "cmd": body.get("cmd", "") if p == cur.get("provider") else "", "model": body.get("model", "")}})
    db.kv_set("brain_auth", None)
    _brain_cache["t"] = 0
    return {"ok": True, "status": brain.status()}


@app.post("/api/claude/{action}")   # kept name; works for whichever AI you chose
def claude_action(action: str):
    """install / login open a real terminal window on this PC; test makes one tiny call."""
    i = brain.info()
    exe = brain.cli_exe() or brain.info()["app"].split()[0].lower()
    if action == "test":
        try:
            r = brain.ask("Reply with exactly the word OK.", max_turns=1, timeout=180, purpose="Connection test")
            _brain_cache["t"] = 0
            return {"ok": "ok" in r["text"].lower(), "reply": r["text"][:200]}
        except brain.BrainError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    prov = brain.provider()
    login_cmd = f'"{exe}"' + ("".join(" " + a for a in i.get("login_args", [])))
    if sys.platform != "win32":
        cmd = {"install": i["install_unix"], "login": login_cmd}[action]
        return {"ok": False, "manual": f"Open a terminal and run: {cmd}" + (f"  - {i['login_hint']}" if action == "login" else "")}
    if action == "install":
        if prov != "claude" and not shutil.which("npm"):
            import webbrowser
            webbrowser.open("https://nodejs.org/en/download")
            return {"ok": False, "manual": f"{i['app']} needs Node.js first. The Node.js download page opened - install the LTS version, then press Install again."}
        subprocess.Popen(["cmd", "/c", "start", f"Install {i['app']}", "powershell", "-NoExit", "-ExecutionPolicy", "Bypass",
                          "-Command", f"{i['install_win']}; Write-Host ''; Write-Host 'Done. Now go back to Career OS and press Sign in.' -ForegroundColor Green"])
    elif action == "login":
        # a small .cmd file avoids Windows quoting problems with paths like C:\Users\me\.local\bin\claude.exe
        esc = lambda t: re.sub(r"([&|<>^])", r"^\1", t)
        lines = ["@echo off", f"title Sign in to {i['name']}"] + [f"set {k}=" for k in i["strip"]] + [
            "echo.", f"echo   {esc(i['login_hint'])}", "echo   When you're done, close this window, go back to Career OS and press Test.", "echo.",
            f'"{exe}"' + "".join(" " + a for a in i.get("login_args", []))]
        bat = ROOT / "data" / "signin.cmd"
        bat.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        subprocess.Popen(["cmd", "/c", "start", "", "cmd", "/k", str(bat)])
    else:
        raise HTTPException(404)
    _brain_cache["t"] = 0
    return {"ok": True}


# ---------------- Job boards + the Extra agent ----------------

@app.get("/api/boards")
def boards_get():
    from . import boards
    ag = agents.agent_by_kind("boards")
    return {"catalogue": boards.catalogue(), "boards": boards.boards(), "leads": boards.leads(120),
            "login_open": boards.login_open(), "agent": {"id": ag["id"], "running": ag["running"], "last_run": ag["last_run"],
                                                          "last_status": ag["last_status"]} if ag else None,
            "settings": {"times": boards.times(), "searches_per_board": 4, "show_window": False, "add_untraced": True,
                         **(settings().get("extra") or {})}, "ai": brain.available(), "ai_name": brain.name()}


@app.put("/api/extra/settings")
def extra_settings(body: dict = Body(...)):
    cur = settings().get("extra") or {}
    keep = {k: body[k] for k in ("times", "searches_per_board", "show_window", "add_untraced") if k in body}
    if "times" in keep:
        keep["times"] = sorted(t for t in keep["times"] if re.match(r"^\d{2}:\d{2}$", t or ""))[:4] or ["08:40", "18:40"]
    save_settings({"extra": {**cur, **keep}})
    return {"ok": True}


@app.post("/api/boards")
def boards_add(body: dict = Body(...)):
    from . import boards
    try:
        return boards.add_board(body.get("site") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/boards/{bid}")
def boards_patch(bid: int, body: dict = Body(...)):
    from . import boards
    boards.update_board(bid, body)
    return {"ok": True}


@app.delete("/api/boards/{bid}")
def boards_delete(bid: int):
    from . import boards
    boards.delete_board(bid)
    return {"ok": True}


@app.post("/api/boards/{bid}/login")
def boards_login(bid: int):
    from . import boards
    try:
        return boards.open_login(bid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/boards/run")
def boards_run():
    from . import boards
    boards.ensure_agent()
    ag = agents.agent_by_kind("boards")
    return {"ok": agents.run_agent(ag["id"]), "id": ag["id"]}


# ---------------- Where we search: sources, sectors, companies ----------------

@app.get("/api/sources")
def get_sources():
    from . import discover
    comp = companies()
    jobs = {r["org"].lower(): r["n"] for r in db.q("SELECT org, COUNT(*) n FROM opportunities GROUP BY org")}
    match = {r["org"].lower(): r["n"] for r in db.q("SELECT org, COUNT(*) n FROM opportunities WHERE score>=? AND status IN ('new','shortlisted') GROUP BY org",
                                                    (int(settings().get("min_score") or 55),))}
    health = {r["key"]: r for r in db.q("SELECT * FROM source_health")}
    groups = []
    for key, lst in comp.items():
        if key.startswith("_") or not isinstance(lst, list):
            continue
        rows = []
        for c in lst:
            h = health.get(f"{c.get('ats')}:{c['name']}") or health.get(f"page:{c['name']}") or {}
            nm = c["name"].replace(" — early careers", "").lower()
            rows.append({"name": c["name"], "ats": c.get("ats"), "url": c.get("url") or "", "jobs": jobs.get(nm, 0), "matches": match.get(nm, 0),
                         "ok": h.get("ok"), "detail": h.get("detail", ""), "checked": h.get("checked_at", "")})
        groups.append({"key": key, "title": discover.sector_title(key), "companies": rows})
    feeds = [{"name": s, "what": w} for s, w in (("Arbeitnow", "EU tech jobs"), ("Himalayas", "remote jobs"), ("Remotive", "remote jobs"), ("Jobicy", "remote jobs"))]
    by_source = db.q("SELECT source, COUNT(*) n FROM opportunities GROUP BY source ORDER BY n DESC")
    ag = agents.all_agents()
    return {"groups": groups, "feeds": feeds, "by_source": by_source,
            "finders": [{"id": a["id"], "name": a["name"], "kind": a["kind"], "last_run": a["last_run"], "last_status": a["last_status"],
                         "found": a["last_found"], "running": a["running"], "config": a["config"]} for a in ag if a["kind"] in ("discover", "programs", "research")],
            "total_jobs": db.q1("SELECT COUNT(*) n FROM opportunities")["n"], "scout_times": settings().get("scout_times"),
            "sectors_catalog": __import__("careeros.universal", fromlist=["SECTORS"]).SECTORS}


@app.post("/api/companies")
def add_company(body: dict = Body(...)):
    from . import discover
    try:
        return discover.add_company(body.get("name", "").strip(), body.get("url", "").strip())
    except brain.BrainError as e:
        raise HTTPException(503, str(e))


@app.post("/api/sectors")
def add_sector(body: dict = Body(...)):
    """Start a Company finder for any sector (top N employers → their careers pages)."""
    sector = (body.get("sector") or "").strip()
    if not sector:
        raise HTTPException(400, "sector required")
    n = int(body.get("n") or 100)
    name = f"Company finder · {sector}"
    row = db.q1("SELECT id FROM agents WHERE name=?", (name,))
    aid = row["id"] if row else db.x("INSERT INTO agents(name,kind,config,enabled,on_schedule,created_at) VALUES(?,?,?,?,?,?)",
                                     (name, "discover", json.dumps({"sector": sector, "n": n}), 1, 1, db.now()))
    return {"id": aid, "started": agents.run_agent(aid)}


@app.post("/api/prepare-top")
def prepare_top(body: dict = Body(default={})):
    """Draft cover letters for the best N matches right now (uses Claude)."""
    a = agents.agent_by_kind("prepare")
    if not a:
        raise HTTPException(404, "no Writer agent")
    cfg = dict(a["config"], top=int(body.get("n") or 10))
    db.x("UPDATE agents SET config=? WHERE id=?", (json.dumps(cfg), a["id"]))
    return {"started": agents.run_agent(a["id"])}


@app.get("/api/count-opps")
def count_opps(status: str | None = None, kind: str | None = None, country: str | None = None, track: str | None = None,
               q: str | None = None, min_score: int = 0, posted_days: int = 0, sponsor_only: int = 0):
    return {"n": opps.listing(status, kind, country, track, q, min_score, 0, "score", posted_days, bool(sponsor_only), count=True),
            "total": db.q1("SELECT COUNT(*) n FROM opportunities")["n"]}


# ---------------- static UI ----------------

@app.get("/", response_class=HTMLResponse)
def index():
    return brain.tr((WEB_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/static/app.js")
def app_js():
    """The UI mentions 'Claude'; show the name of the AI you actually use."""
    from fastapi.responses import Response
    return Response(brain.tr((WEB_DIR / "app.js").read_text(encoding="utf-8")), media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
