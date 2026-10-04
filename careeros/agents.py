"""Agents: each is a small worker with its own job (a scout for a group of companies,
a research agent for one field x country, the email tracker, the deadline watcher...).
Run as many as you like; AI-powered ones share a slot limit so your plan
isn't hammered (Settings -> max parallel agents)."""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import date, datetime, timedelta

import httpx

from . import brain, db, opps, sources
from .config import companies, save_companies, settings
from .notify import notify

_running: dict[int, dict] = {}
_run_lock = threading.Lock()

SCOUT_KINDS = ("ats", "pages", "feeds", "adzuna", "reed", "research")

RESEARCH_PROMPT = """You are one research agent in a job-search team working for the candidate below.
Today is {today}.
Your beat: **{field}** in **{country}**.
Look for: {kinds}.
{extra}

Candidate: {candidate}

Use WebSearch and WebFetch. Prefer the official application page. Only include opportunities
that are OPEN NOW (deadline after today, or rolling) - verify on the page, don't guess.
Match the candidate's level; skip roles far above it. Max {limit} items, best first.

Return ONLY a JSON array:
[{{"title": "...", "org": "...", "kind": "job|internship|graduate|fellowship|scholarship|parttime|competition",
  "location": "city, country", "country_code": "UK|IN|US|DE|...|REMOTE",
  "url": "official page to apply", "deadline": "YYYY-MM-DD or null if rolling/unknown",
  "pay": "stipend/salary if stated else ''", "sponsorship": "yes|no|unknown",
  "eligibility": "one line on who can apply", "why_fit": "one line"}}]"""


def ensure_defaults() -> None:
    """Create the agent line-up for this person (from their goals) if it isn't there yet."""
    from .config import onboarded
    if not onboarded():
        return  # the setup wizard creates everything when it finishes
    if not db.kv_get("goal_weights_v1"):
        # scoring used to fall back to built-in country weights; now it always comes from your own goals
        from .config import CONFIG_DIR, _read_yaml, save_settings
        from .universal import goal_weights
        raw = _read_yaml(CONFIG_DIR / "settings.yaml")
        add = {k: v for k, v in goal_weights().items() if not raw.get(k)}
        if add:
            save_settings(add)
            threading.Thread(target=opps.rescore_all, daemon=True).start()
        db.kv_set("goal_weights_v1", True)
    if not db.kv_get("seeded_v1"):
        from .config import CONTENT_DIR
        seed = CONTENT_DIR / "seed.json"
        if seed.exists():
            mine = set(settings().get("tracks_enabled") or [])
            for it in json.loads(seed.read_text(encoding="utf-8")):
                if it.get("for_tracks") and not mine & set(it["for_tracks"]):
                    continue  # e.g. AI-safety fellowships only for people aiming at AI / research roles
                it = {k: v for k, v in it.items() if k != "for_tracks"}
                opps.upsert(dict(it, source="seed", ext_id=it["url"], apply_url=it["url"]))
        db.kv_set("seeded_v1", True)
    if not db.kv_get("agents_v2"):
        # upgrade from v1: replace the old fixed line-up with agents generated from your goals
        for r in db.q("SELECT id, config FROM agents"):
            if not json.loads(r["config"] or "{}").get("auto"):
                db.x("DELETE FROM agents WHERE id=?", (r["id"],))
        db.kv_set("agents_v2", True)
    if not db.q1("SELECT id FROM agents LIMIT 1") or not db.kv_get("agents_v4"):
        sync_agents()  # v3 added the Company finders
        db.kv_set("agents_v3", True)
        db.kv_set("agents_v4", True)


def sync_agents() -> dict:
    """(Re)generate agents from the goals. Agents you created or edited by hand are left alone."""
    from .universal import generate_agents
    wanted = generate_agents()
    names = {a["name"] for a in wanted}
    removed = 0
    for r in db.q("SELECT id, name, config FROM agents"):
        cfg = json.loads(r["config"] or "{}")
        if cfg.get("auto") and r["name"] not in names:
            db.x("DELETE FROM agents WHERE id=?", (r["id"],))
            removed += 1
    added = 0
    for a in wanted:
        if db.q1("SELECT id FROM agents WHERE name=?", (a["name"],)):
            continue
        cfg = dict(a.get("config") or {}, auto=True)
        enabled = a.get("enabled", cfg.pop("enabled", 1))
        db.x("INSERT INTO agents(name,kind,config,enabled,on_schedule,created_at) VALUES(?,?,?,?,?,?)",
             (a["name"], a["kind"], json.dumps(cfg), enabled, a.get("on_schedule", 1), db.now()))
        added += 1
    return {"added": added, "removed": removed}


def all_agents() -> list[dict]:
    rows = db.q("SELECT * FROM agents ORDER BY id")
    for r in rows:
        r["config"] = json.loads(r["config"] or "{}")
        r["running"] = r["id"] in _running
        r["live_log"] = "\n".join(_running[r["id"]]["log"][-40:]) if r["id"] in _running else ""
    return rows


class Run:
    def __init__(self, agent: dict):
        self.agent = agent
        self.lines: list[str] = []
        self.found = 0
        self.run_id = db.x("INSERT INTO runs(agent_id,agent_name,started_at,status) VALUES(?,?,?,?)",
                           (agent["id"], agent["name"], db.now(), "running"))

    def log(self, msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        self.lines.append(line)
        if len(self.lines) % 10 == 0:
            db.x("UPDATE runs SET log=? WHERE id=?", ("\n".join(self.lines[-400:]), self.run_id))


def _ingest(items: list[dict], run: Run) -> int:
    new = 0
    for it in items:
        if not it.get("title"):
            continue
        try:
            _, is_new = opps.upsert(it)
            new += int(is_new)
        except Exception as e:  # noqa: BLE001
            run.log(f"  skip bad item: {e}")
    return new


def _run_ats(agent: dict, run: Run) -> int:
    comp = companies()
    groups = agent["config"].get("groups") or [k for k in comp if not k.startswith("_")]
    total = 0
    with sources._client() as c:
        for g in groups:
            for co in comp.get(g, []) or []:
                if co.get("ats") not in sources.ATS and co.get("ats") != "workday":
                    continue  # custom career pages are read by the "Career pages" scout
                jobs = sources.fetch_company(co, c, run.log)
                n = _ingest(jobs, run)
                if jobs:
                    run.log(f"  {co['name']}: {len(jobs)} open, {n} new")
                total += n
                time.sleep(0.25)
    return total


def _run_feeds(agent: dict, run: Run) -> int:
    cfg, total = agent["config"], 0
    with sources._client() as c:
        for name, fn in (("arbeitnow", lambda: sources.arbeitnow(c)),
                         ("himalayas", lambda: sources.himalayas(c)),
                         ("remotive", lambda: sources.remotive(c, cfg.get("remotive") or [])),
                         ("jobicy", lambda: sources.jobicy(c, cfg.get("jobicy") or []))):
            if not cfg.get(name):
                continue
            try:
                items = fn()
                n = _ingest(items, run)
                run.log(f"  {name}: {len(items)} fetched, {n} new")
                total += n
            except Exception as e:  # noqa: BLE001
                run.log(f"  {name} failed: {str(e)[:150]}")
    return total


def _run_adzuna(agent: dict, run: Run) -> int:
    s = settings()["adzuna"]
    if not (s.get("app_id") and s.get("app_key")):
        run.log("  Adzuna keys missing - get free keys at developer.adzuna.com and add them in Settings")
        return 0
    with sources._client() as c:
        items = sources.adzuna(c, s["app_id"], s["app_key"], agent["config"]["countries"], agent["config"]["queries"])
    n = _ingest(items, run)
    run.log(f"  adzuna: {len(items)} fetched, {n} new")
    return n


def _run_reed(agent: dict, run: Run) -> int:
    key = settings()["reed"].get("api_key")
    if not key:
        run.log("  Reed key missing - free key at reed.co.uk/developers, add it in Settings")
        return 0
    with sources._client() as c:
        items = sources.reed(c, key, agent["config"]["queries"])
    n = _ingest(items, run)
    run.log(f"  reed: {len(items)} fetched, {n} new")
    return n


def _run_research(agent: dict, run: Run) -> int:
    cfg = agent["config"]
    from .config import candidate_summary
    prompt = RESEARCH_PROMPT.format(today=date.today().isoformat(), field=cfg.get("field", ""), candidate=candidate_summary(),
                                    country=cfg.get("country", "worldwide"), kinds=cfg.get("kinds", "jobs"),
                                    extra=cfg.get("extra", ""), limit=int(cfg.get("limit", 15)))
    data, _ = brain.ask_json(prompt, tools=["WebSearch", "WebFetch"], max_turns=int(cfg.get("max_turns", 40)),
                             timeout=1500, log=run.log)
    if not isinstance(data, list):
        run.log("  no list returned")
        return 0
    items = []
    today = date.today().isoformat()
    for d in data:
        if not isinstance(d, dict) or not d.get("url"):
            continue
        dl = d.get("deadline") or ""
        if dl and len(str(dl)) >= 10 and str(dl)[:10] < today:
            continue
        items.append({
            "source": "research", "ext_id": d["url"].strip(), "title": d.get("title", ""), "org": d.get("org", ""),
            "kind": d.get("kind") or "job", "location": d.get("location", ""),
            "country": (d.get("country_code") or "").upper().replace("GB", "UK") or None,
            "url": d["url"], "apply_url": d["url"], "deadline": (str(dl)[:10] if dl else ""),
            "salary": d.get("pay", ""), "sponsorship": d.get("sponsorship") if d.get("sponsorship") in ("yes", "no") else None,
            "eligibility": d.get("eligibility", ""),
            "description": f"{d.get('eligibility', '')}\nWhy it fits: {d.get('why_fit', '')}",
        })
    n = _ingest(items, run)
    run.log(f"  research: {len(items)} opportunities, {n} new")
    return n


def _run_pages(agent: dict, run: Run) -> int:
    from . import discover
    comp = companies()
    entries = [co for g in agent["config"].get("groups") or [] for co in (comp.get(g) or []) if co.get("ats") == "page"]
    run.log(f"  opening {len(entries)} careers pages in a headless browser…")
    jobs = discover.crawl_pages(entries, log=run.log)
    save_companies(comp)  # keeps any page we discovered runs on a real job system
    n = _ingest(jobs, run)
    run.log(f"  {len(jobs)} matching roles found on careers pages, {n} new")
    return n


def _run_discover(agent: dict, run: Run) -> int:
    from . import discover
    cfg = agent["config"]
    res = discover.find_companies(cfg.get("sector", ""), int(cfg.get("n", 100)), log=run.log)
    return res.get("added", 0)


def _run_programs(agent: dict, run: Run) -> int:
    from . import discover
    cfg = agent["config"]
    items = discover.find_programs(cfg.get("kind", "graduate"), int(cfg.get("n", 100)), log=run.log)
    return _ingest(items, run)


def _run_sources_fix(agent: dict, run: Run) -> int:
    broken = db.q("SELECT key, detail FROM source_health WHERE ok=0")
    if not broken:
        run.log("  all company boards healthy")
        return 0
    names = [b["key"] for b in broken][:25]
    prompt = ("These company job boards failed. For each, find the company's CURRENT public job board on "
              "Greenhouse (boards-api.greenhouse.io/v1/boards/<slug>/jobs), Lever (api.lever.co/v0/postings/<slug>), "
              "Ashby (api.ashbyhq.com/posting-api/job-board/<slug>), SmartRecruiters or Workable, by checking the "
              "company's careers page links. Verify with WebFetch.\n" + "\n".join(names) +
              '\nReturn ONLY JSON: [{"key": "<as given>", "ats": "greenhouse|lever|ashby|smartrecruiters|workable|none", "slug": "..."}]')
    data, _ = brain.ask_json(prompt, tools=["WebSearch", "WebFetch"], max_turns=40, timeout=1500, log=run.log)
    comp = companies()
    fixed = 0
    for d in data if isinstance(data, list) else []:
        ats_old, _, name = (d.get("key") or "").partition(":")
        for g, lst in comp.items():
            if g.startswith("_"):
                continue
            for co in lst or []:
                if co["name"] == name and co["ats"] == ats_old:
                    if d.get("ats") in sources.ATS and d.get("slug"):
                        co["ats"], co["slugs"] = d["ats"], [d["slug"]]
                        co.pop("slug", None)
                        fixed += 1
                        run.log(f"  fixed {name} -> {d['ats']}:{d['slug']}")
                    elif d.get("ats") == "none":
                        co["disabled_reason"] = "no public ATS board"
    comp = {g: ([c for c in lst if not c.get("disabled_reason")] if isinstance(lst, list) else lst) for g, lst in comp.items()}
    save_companies(comp)
    db.x("DELETE FROM source_health WHERE ok=0")
    return fixed


def _run_prepare(agent: dict, run: Run) -> int:
    from . import prepare
    s = settings()
    n = int(agent["config"].get("top") or s.get("auto_prepare_top") or 10)
    rows = db.q("SELECT id,title,org FROM opportunities WHERE status IN ('new','shortlisted') AND score>=? "
                "AND kind NOT IN ('scholarship') ORDER BY CASE status WHEN 'shortlisted' THEN 0 ELSE 1 END, score DESC LIMIT ?",
                (int(s.get("min_score") or 55) + 10, n))
    done = 0
    for r in rows:
        run.log(f"  preparing #{r['id']} {r['title']} @ {r['org']}")
        try:
            prepare.prepare(r["id"], log=run.log)
            done += 1
        except Exception as e:  # noqa: BLE001
            run.log(f"   failed: {str(e)[:150]}")
            if "limit" in str(e).lower():
                break
    if done:
        notify(f"ready:{db.now()[:13]}", f"{done} applications ready for you",
               "Cover letters drafted. Open Career OS → Apply → 'Autofill ready ones', check and submit.", "#apply")
    return done


def _run_email(agent: dict, run: Run) -> int:
    from . import mail
    r = mail.check(log=run.log)
    if r.get("skipped"):
        run.log(f"  {r['skipped']} - add your Gmail app password in Settings")
        return 0
    return int(r.get("updated", 0)) + int(r.get("new_tracked", 0))


def _run_deadlines(agent: dict, run: Run) -> int:
    s = settings()
    expired = opps.expire_old()
    if expired:
        run.log(f"  {expired} passed their deadline")
    n = 0
    for days in sorted((s.get("notify") or {}).get("deadline_days") or [7, 3, 1]):
        lim = (date.today() + timedelta(days=days)).isoformat()
        rows = db.q("SELECT id,title,org,deadline FROM opportunities WHERE deadline!='' AND deadline>=? AND deadline<=? "
                    "AND status IN ('new','shortlisted','preparing','ready','filling') AND score>=?",
                    (date.today().isoformat(), lim, int(s.get("min_score") or 40)))
        for r in rows:
            left = (date.fromisoformat(r["deadline"][:10]) - date.today()).days
            notify(f"dl:{r['id']}:{days}", f"Deadline in {left} day(s): {r['org']}",
                   f"{r['title']} closes {r['deadline']}. Open Career OS to apply.", "#apply")
            n += 1
    run.log(f"  {n} deadline alerts checked")
    return n


def _run_boards(agent, run) -> int:
    from . import boards
    return boards.run(agent, run)


RUNNERS = {"pages": _run_pages, "discover": _run_discover, "programs": _run_programs, "ats": _run_ats, "feeds": _run_feeds, "adzuna": _run_adzuna, "reed": _run_reed,
           "research": _run_research, "sources_fix": _run_sources_fix, "prepare": _run_prepare,
           "email": _run_email, "deadlines": _run_deadlines, "boards": _run_boards}


def run_agent(agent_id: int, wait: bool = False) -> bool:
    agent = next((a for a in all_agents() if a["id"] == agent_id), None)
    if not agent:
        return False
    with _run_lock:
        if agent_id in _running:
            return False
        _running[agent_id] = {"log": []}

    def work():
        label = {"research": "Research agents", "discover": "Company finders", "programs": "Programme finders",
                 "prepare": "Cover letters", "sources_fix": "Board fixer", "boards": "Extra · job boards"}.get(agent["kind"], "Other agents")
        brain.set_purpose(label, agent["name"])
        run = Run(agent)
        run.lines = _running[agent_id]["log"]
        status, found = "ok", 0
        run.log(f"▶ {agent['name']}")
        try:
            found = RUNNERS[agent["kind"]](agent, run)
            run.log(f"✓ done - {found} new/updated")
        except brain.LimitError as e:
            status = "limited"
            run.log(f"⏸ {str(e)[:300]}")
        except brain.BrainError as e:
            status = "needs_claude" if not brain.available() or isinstance(e, brain.AuthError) else "error"
            run.log(f"✗ {str(e)[:300]}")
        except Exception as e:  # noqa: BLE001
            status = "error"
            run.log(f"✗ {str(e)[:300]}")
            if not isinstance(e, (brain.BrainError, httpx.HTTPError)):
                run.log(traceback.format_exc()[-800:])
        finally:
            db.x("UPDATE runs SET finished_at=?, status=?, found=?, log=? WHERE id=?",
                 (db.now(), status, found, "\n".join(run.lines[-400:]), run.run_id))
            db.x("UPDATE agents SET last_run=?, last_status=?, last_found=? WHERE id=?",
                 (db.now(), status, found, agent_id))
            with _run_lock:
                _running.pop(agent_id, None)

    t = threading.Thread(target=work, daemon=True, name=f"agent-{agent_id}")
    t.start()
    if wait:
        t.join()
    return True


def run_all_scouts(slot_index: int | None = None, wait: bool = False) -> list[int]:
    """Start every enabled scout. Research agents with slots=1 only run in the first slot of the day."""
    started = []
    for a in all_agents():
        if not a["enabled"] or a["kind"] not in SCOUT_KINDS or not a["on_schedule"]:
            continue
        # research agents (slots=1) use Claude + web search: once a day is plenty
        if a["config"].get("slots") and slot_index is not None and a["last_run"] \
                and a["last_run"][:10] == datetime.utcnow().date().isoformat():
            continue
        if run_agent(a["id"]):
            started.append(a["id"])
    if wait:
        while any(i in _running for i in started):
            time.sleep(1)
    return started


def _tick_extra(now, today: str) -> None:
    """The Extra agent runs on its own times, independent of the scouts."""
    from . import boards
    a = agent_by_kind("boards")
    if not a or not a["enabled"] or not a["on_schedule"] or a["running"]:
        return
    if not _has_table("boards") or not db.q1("SELECT id FROM boards WHERE enabled=1"):
        return
    done = db.kv_get("extra_slots_done", {}) or {}
    if done.get("date") != today:
        done = {"date": today, "done": []}
    due = [t for t in boards.times() if now.strftime("%H:%M") >= t and t not in done["done"]]
    if due:
        done["done"] += due
        db.kv_set("extra_slots_done", done)
        run_agent(a["id"])


def _has_table(name: str) -> bool:
    return bool(db.q1("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def agent_by_kind(kind: str) -> dict | None:
    return next((a for a in all_agents() if a["kind"] == kind), None)


# ---------------- scheduler ----------------

def _scheduler_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            tick()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        stop.wait(30)


def tick() -> None:
    from .config import onboarded
    if not onboarded():
        return  # nothing runs until the setup wizard is finished
    s = settings()
    now = datetime.now()
    today = now.date().isoformat()
    slots = sorted(s.get("scout_times") or ["07:30", "17:30"])
    done_slots = db.kv_get("scout_slots_done", {})
    if done_slots.get("date") != today:
        done_slots = {"date": today, "done": []}
    due = [i for i, hm in enumerate(slots) if now.strftime("%H:%M") >= hm and hm not in done_slots["done"]]
    if due:
        idx = due[-1]
        for i in due:
            done_slots["done"].append(slots[i])
        db.kv_set("scout_slots_done", done_slots)

        def cycle():
            run_all_scouts(slot_index=idx, wait=True)
            opps.rescore_all()
            prep = agent_by_kind("prepare")
            if prep and prep["enabled"] and settings().get("auto_prepare", True):
                run_agent(prep["id"], wait=True)
        threading.Thread(target=cycle, daemon=True, name="scout-cycle").start()

    _tick_extra(now, today)
    em = agent_by_kind("email")
    if em and em["enabled"] and em["on_schedule"] and (s.get("email") or {}).get("enabled"):
        every = int(s["email"].get("check_every_minutes") or 60)
        if not em["last_run"] or (datetime.utcnow() - datetime.fromisoformat(em["last_run"][:19])).total_seconds() > every * 60:
            run_agent(em["id"])

    # Company & programme finders: first run as soon as possible, then weekly (companies don't change daily);
    # if Claude wasn't connected or it failed, try again an hour later
    for a in all_agents():
        if any(x["kind"] in ("discover", "programs") and x["running"] for x in all_agents()):
            break  # one finder at a time - they use Claude + web search
        if a["kind"] in ("discover", "programs") and a["enabled"] and a["on_schedule"] and not a["running"]:
            age = (datetime.utcnow() - datetime.fromisoformat(a["last_run"][:19])).total_seconds() if a["last_run"] else None
            if age is None or age > 7 * 86400 or (a["last_status"] in ("needs_claude", "error") and age > 3600):
                run_agent(a["id"])

    # Claude agents that hit the Pro usage limit: retry once the limit has had time to reset (~5h window)
    for a in all_agents():
        if a["enabled"] and a["last_status"] == "limited" and a["last_run"] and not a["running"]:
            if (datetime.utcnow() - datetime.fromisoformat(a["last_run"][:19])).total_seconds() > 3 * 3600:
                run_agent(a["id"])

    dl = agent_by_kind("deadlines")
    if dl and dl["enabled"] and (not dl["last_run"] or
                                 (datetime.utcnow() - datetime.fromisoformat(dl["last_run"][:19])).total_seconds() > 3600):
        run_agent(dl["id"])

    digest = (s.get("notify") or {}).get("daily_digest")
    if digest and now.strftime("%H:%M") >= digest and db.kv_get("digest_date") != today:
        db.kv_set("digest_date", today)
        st = opps.stats()
        ready = st["by_status"].get("ready", 0) + st["by_status"].get("filling", 0)
        soon = db.q1("SELECT COUNT(*) n FROM opportunities WHERE deadline!='' AND deadline<=? AND deadline>=? "
                     "AND status IN ('new','shortlisted','ready','filling')",
                     ((date.today() + timedelta(days=7)).isoformat(), today))["n"]
        notify(f"digest:{today}", f"Career OS: {ready} ready to submit",
               f"{st['new_today']} new matches today · {soon} deadlines this week. 20 minutes now = done for today.", "#apply")
        if ready and s.get("auto_open_autofill", True):
            open_ready_in_autofill()


def open_ready_in_autofill(limit: int = 15) -> int:
    """Queue the ready applications for the autofill browser (the server process starts it)."""
    rows = db.q("SELECT id, apply_url, url FROM opportunities WHERE status='ready' ORDER BY "
                "CASE WHEN deadline='' THEN 1 ELSE 0 END, deadline, score DESC LIMIT ?", (limit,))
    for r in rows:
        if not db.q1("SELECT id FROM fill_requests WHERE opp_id=? AND status='pending'", (r["id"],)):
            db.x("INSERT INTO fill_requests(opp_id,url,status,created_at) VALUES(?,?,?,?)",
                 (r["id"], r["apply_url"] or r["url"], "pending", db.now()))
    if rows:
        db.kv_set("filler_wanted", True)
    return len(rows)


_stop = threading.Event()


def start_scheduler() -> None:
    ensure_defaults()
    threading.Thread(target=_scheduler_loop, args=(_stop,), daemon=True, name="scheduler").start()
