"""Learn: tracks, progress, your local books, and the examiner (Claude) that tests you."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import brain, db
from .config import CONTENT_DIR, DATA_DIR, candidate_summary, save_settings, settings


LEVELS = ["Foundations", "Core", "Advanced", "Expert", "Frontier"]
TRACKS_DIR = DATA_DIR / "tracks"          # your own tracks (any subject) + AI-added modules/resources
TRACKS_DIR.mkdir(parents=True, exist_ok=True)
EXTRA_FILE = TRACKS_DIR / "_extra.json"   # {"modules": {track_id: [module...]}, "resources": {module_id: [res...]}}


def _load_extra() -> dict:
    try:
        return json.loads(EXTRA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"modules": {}, "resources": {}}


def _save_extra(x: dict) -> None:
    EXTRA_FILE.write_text(json.dumps(x, indent=1, ensure_ascii=False), encoding="utf-8")


def _kind_of(url: str, title: str = "") -> str:
    u, t = (url or "").lower(), (title or "").lower()
    if "arxiv.org" in u or "arxiv" in t:
        return "Paper"
    if "ocw.mit.edu" in u or "course" in t or "cs229" in u or "cs224n" in u or ".courses." in u or "/courses/" in u:
        return "Course"
    if "youtube.com" in u or "video" in t or "lectures" in t:
        return "Video"
    if u.endswith(".pdf") or "book" in t or "pdf" in t:
        return "Book"
    if "docs" in u or "developer." in u or "documentation" in t:
        return "Docs"
    if "leetcode" in u or "codeforces" in u or "cses" in u or "puzzle" in t or "drill" in t:
        return "Practice"
    return "Web"


def _tracks_raw() -> dict:
    """Built-in catalog + your own tracks + AI-added modules, merged."""
    data = json.loads((CONTENT_DIR / "tracks.json").read_text(encoding="utf-8"))
    for f in sorted(TRACKS_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
            t["category"] = "custom"
            data["tracks"].append(t)
        except (OSError, ValueError):
            pass
    extra = _load_extra()
    for t in data["tracks"]:
        t["modules"] = list(t.get("modules") or []) + list(extra.get("modules", {}).get(t["id"], []))
        for m in t["modules"]:
            m.setdefault("level", 2)
            m.setdefault("resources", [])
            m.setdefault("topics", [])
            m.setdefault("books", [])
            m["resources"] = m["resources"] + extra.get("resources", {}).get(m["id"], [])
            for r in m["resources"]:
                r.setdefault("kind", _kind_of(r.get("u", ""), r.get("t", "")))
        t["modules"].sort(key=lambda m: m["level"])
    return data


def books() -> list[dict]:
    d = Path(settings().get("books_dir") or "")
    if not str(d) or not d.exists() or str(d) == ".":
        return []
    out = []
    for p in sorted(d.rglob("*")):
        if p.suffix.lower() in (".pdf", ".epub", ".djvu") and p.is_file():
            out.append({"name": p.name, "rel": str(p.relative_to(d)).replace("\\", "/"),
                        "size_mb": round(p.stat().st_size / 1e6, 1)})
    return out


def _book_matches(keys: list[str], lib: list[dict]) -> list[dict]:
    found = []
    for k in keys or []:
        rx = re.compile(re.escape(k).replace(r"\ ", r"[\s_\-]*"), re.I)
        for b in lib:
            if rx.search(b["name"]) and b not in found:
                found.append(b)
    return found


def selected_ids() -> list[str]:
    sel = (settings().get("learn") or {}).get("selected") or []
    if not sel:
        from .universal import default_learn_tracks
        sel = default_learn_tracks()
    return sel


def tracks() -> dict:
    data = _tracks_raw()
    lib = books()
    prog = {r["module_id"]: r for r in db.q("SELECT * FROM learn_progress")}
    used = set()
    from .universal import degree_tracks
    core_ids = set(degree_tracks())
    for t in data["tracks"]:
        done = 0
        for m in t["modules"]:
            m["local_books"] = _book_matches(m.get("books"), lib)
            used.update(b["rel"] for b in m["local_books"])
            p = prog.get(m["id"]) or {}
            m["status"] = p.get("status") or "todo"
            m["notes"] = p.get("notes") or ""
            done += m["status"] == "done"
        t["done"] = done
        t["total"] = len(t["modules"])
        t["for_degree"] = t["id"] in core_ids
        lv = []
        for i, name in enumerate(LEVELS, start=1):
            ms = [m for m in t["modules"] if m["level"] == i]
            lv.append({"n": i, "name": name, "total": len(ms), "done": sum(m["status"] == "done" for m in ms)})
        t["levels"] = lv
    data["levels"] = LEVELS
    data["selected"] = [i for i in selected_ids() if any(t["id"] == i for t in data["tracks"])]
    data["library"] = lib
    data["unmapped_books"] = [b for b in lib if b["rel"] not in used]
    data["test_history"] = db.q("SELECT id,module_id,score,created_at FROM tests WHERE score IS NOT NULL ORDER BY id DESC LIMIT 50")
    data["jobs"] = db.kv_get("learn_jobs", {}) or {}
    return data


def module(module_id: str) -> tuple[dict, dict] | tuple[None, None]:
    for t in _tracks_raw()["tracks"]:
        for m in t["modules"]:
            if m["id"] == module_id:
                return t, m
    return None, None


def track(track_id: str) -> dict | None:
    return next((t for t in _tracks_raw()["tracks"] if t["id"] == track_id), None)


def select(ids: list[str]) -> None:
    save_settings({"learn": {"selected": ids}})


# ---------------- AI: new subjects, deeper levels, fresh sources, the teacher ----------------

def _job(key: str, status: str, detail: str = "") -> None:
    jobs = db.kv_get("learn_jobs", {}) or {}
    jobs[key] = {"status": status, "detail": detail[:300], "at": db.now()}
    db.kv_set("learn_jobs", jobs)


RES_RULES = """Only FREE, legally open resources: open textbooks on authors' sites, university open courseware,
official documentation, arXiv / open-access papers, reputable free video lectures. Never pirated copies, never
paywalled links. Verify every URL with WebFetch before including it. Prefer the newest good material."""

TRACK_PROMPT = """Design a complete learning track for: "{subject}".
Learner: {candidate}
It must take someone from total beginner to research frontier, across 5 levels:
1 Foundations, 2 Core, 3 Advanced, 4 Expert, 5 Frontier (current research, key papers, open problems).
Give 2-3 modules per level. {rules}
Return ONLY JSON:
{{"id": "<short-kebab-id>", "title": "<name>", "why": "<one sentence: why it matters for the learner's goals>",
  "modules": [{{"id": "<track-id>-<n>", "title": "...", "level": 1-5, "hours": <int>,
    "topics": ["...", "..."], "resources": [{{"t": "title - author/source", "u": "https://...", "kind": "Book|Course|Video|Paper|Docs|Practice|Web"}}],
    "checkpoint": "what 'done' means, concretely"}}]}}"""

DEEPEN_PROMPT = """Add 2-3 new modules at level {level} ({level_name}) to the learning track "{title}".
Existing modules (don't repeat them): {existing}
Learner: {candidate}
{rules}
Return ONLY JSON: {{"modules": [{{"id": "{tid}-l{level}-<n>", "title": "...", "level": {level}, "hours": <int>,
  "topics": [...], "resources": [{{"t": "...", "u": "https://...", "kind": "..."}}], "checkpoint": "..."}}]}}"""

REFRESH_PROMPT = """Refresh the reading lists of the learning track "{title}".
Modules: {modules}
For each module, find up to 2 NEW free resources not already listed (e.g. a better open textbook,
a recent open course, or - for Expert/Frontier modules - important papers from the last 2 years).
{rules}
Return ONLY JSON: {{"<module id>": [{{"t": "...", "u": "https://...", "kind": "..."}}], ...}}"""

TEACH_PROMPT = """You are the learner's personal tutor for "{track}" (focus: {focus}; level: {level}).
Learner: {candidate}

Teach like a great 1-to-1 tutor, not a textbook:
- SHORT: about 120 words (never more than 180 unless they say "more" / "in detail").
- One idea at a time: a plain-words explanation, then ONE tiny worked example. Math in plain text.
- Then stop and check: end with one short question for them to try, or "Say *next* when ready."
- Don't list everything up front. No long intros, no summaries of what you'll cover.
- "simpler" -> simpler with an everyday example; "deeper" -> the next level up (up to research level).
- Only when they ask for sources / papers / links / the latest: search the web and cite links. {rules}
- Their own PDFs are in {books_dir} ({books}); open one only if they ask about their books.

Learner says: {message}"""

STYLE_REMINDER = "(Tutor style: short - about 120 words - one idea + one tiny example, then one check question.)\n\n"
WEB_RX = re.compile(r"paper|source|link|latest|newest|recent|resource|read next|reading list|course|video|arxiv|cite|reference|up.to.date|news", re.I)
BOOK_RX = re.compile(r"my (book|pdf|library|copy)|in my books", re.I)


def create_track(subject: str) -> str:
    brain.set_purpose("Learn builder", "")
    key = "track:" + re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:40]
    _job(key, "running", f"Building a track for {subject}")
    try:
        data, _ = brain.ask_json(TRACK_PROMPT.format(subject=subject, candidate=candidate_summary(), rules=RES_RULES),
                                 tools=["WebSearch", "WebFetch"], max_turns=60, timeout=1800)
        tid = re.sub(r"[^a-z0-9-]+", "-", (data.get("id") or key.split(":", 1)[1]).lower()).strip("-")[:40] or "custom"
        data["id"] = tid
        data["title"] = data.get("title") or subject
        data.setdefault("why", "")
        (TRACKS_DIR / f"{tid}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        sel = selected_ids()
        if tid not in sel:
            select(sel + [tid])
        _job(key, "done", f"{data['title']} is ready ({len(data.get('modules', []))} modules)")
        return tid
    except Exception as e:  # noqa: BLE001
        _job(key, "error", str(e))
        raise


def deepen(track_id: str, level: int) -> int:
    brain.set_purpose("Learn builder", "")
    t = track(track_id)
    key = f"deepen:{track_id}:{level}"
    _job(key, "running", f"Adding {LEVELS[level - 1]} modules to {t['title']}")
    try:
        data, _ = brain.ask_json(DEEPEN_PROMPT.format(
            level=level, level_name=LEVELS[level - 1], title=t["title"], tid=track_id,
            existing="; ".join(m["title"] for m in t["modules"]), candidate=candidate_summary(), rules=RES_RULES),
            tools=["WebSearch", "WebFetch"], max_turns=40, timeout=1500)
        mods = [dict(m, level=level) for m in (data.get("modules") or []) if m.get("title")]
        x = _load_extra()
        x.setdefault("modules", {}).setdefault(track_id, []).extend(mods)
        _save_extra(x)
        _job(key, "done", f"{len(mods)} new {LEVELS[level - 1]} modules")
        return len(mods)
    except Exception as e:  # noqa: BLE001
        _job(key, "error", str(e))
        raise


def refresh(track_id: str) -> int:
    brain.set_purpose("Learn builder", "")
    t = track(track_id)
    key = f"refresh:{track_id}"
    _job(key, "running", f"Looking for newer free sources for {t['title']}")
    try:
        mods = [{"id": m["id"], "title": m["title"], "level": LEVELS[m["level"] - 1],
                 "have": [r.get("u") for r in m["resources"]]} for m in t["modules"]]
        data, _ = brain.ask_json(REFRESH_PROMPT.format(title=t["title"], modules=json.dumps(mods, ensure_ascii=False),
                                                       rules=RES_RULES),
                                 tools=["WebSearch", "WebFetch"], max_turns=60, timeout=1800)
        x = _load_extra()
        n = 0
        for mid, res in (data or {}).items():
            have = {r.get("u") for m in t["modules"] if m["id"] == mid for r in m["resources"]}
            new = [r for r in res if isinstance(r, dict) and r.get("u") and r["u"] not in have]
            if new:
                x.setdefault("resources", {}).setdefault(mid, []).extend(new)
                n += len(new)
        _save_extra(x)
        _job(key, "done", f"{n} new sources added")
        return n
    except Exception as e:  # noqa: BLE001
        _job(key, "error", str(e))
        raise


def teach(track_id: str, module_id: str, message: str, session: str | None, level: int = 0) -> dict:
    """A short, tutor-style reply. Web search only when you ask for sources/papers (much faster otherwise)."""
    brain.set_purpose("AI teacher", "")
    tools = []
    if WEB_RX.search(message or ""):
        tools += ["WebSearch", "WebFetch"]
    books_dir = settings().get("books_dir") or ""
    if BOOK_RX.search(message or "") and books_dir:
        tools += ["Read", "Glob"]
    turns = 8 if tools else 2
    if session:
        try:
            r = brain.ask(STYLE_REMINDER + message, resume=session, tools=tools or None, max_turns=turns, timeout=420,
                          add_dirs=[books_dir] if "Read" in tools else None, fast=True)
            return {"reply": r["text"], "session": r["session_id"]}
        except brain.AuthError:
            raise
        except brain.BrainError:
            pass  # the old conversation is gone (or the AI app can't resume) - start a fresh one
    t = track(track_id) or {"title": track_id, "modules": []}
    _, m = module(module_id) if module_id else (None, None)
    lib = books()
    prompt = TEACH_PROMPT.format(
        track=t["title"], focus=(m or {}).get("title", "the whole track"),
        level=LEVELS[(level or (m or {}).get("level", 1)) - 1], candidate=candidate_summary(), rules=RES_RULES,
        books_dir=books_dir or "(none)", books=", ".join(b["name"] for b in lib[:40]) or "none",
        message=message or "Give me a 3-line orientation: what this is, why it matters for my goals, and the first thing to learn.")
    r = brain.ask(prompt, tools=tools or None, max_turns=turns, timeout=420, add_dirs=[books_dir] if "Read" in tools else None, fast=True)
    return {"reply": r["text"], "session": r["session_id"]}


def save_progress(module_id: str, status: str | None = None, notes: str | None = None) -> None:
    cur = db.q1("SELECT * FROM learn_progress WHERE module_id=?", (module_id,)) or {}
    db.x("INSERT INTO learn_progress(module_id,status,notes,updated_at) VALUES(?,?,?,?) ON CONFLICT(module_id) DO UPDATE "
         "SET status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at",
         (module_id, status if status is not None else cur.get("status", "todo"),
          notes if notes is not None else cur.get("notes", ""), db.now()))


TEST_PROMPT = """You are a demanding interviewer/examiner for the track "{track}" at the level of
top-firm interviews (Jane Street/Optiver for quant, Google/Meta for SWE, DeepMind/Anthropic for ML).
Module: {module}
Topics: {topics}
Candidate's own notes (may be empty): {notes}
Difficulty: {difficulty}

Create a test of {n} questions mixing types. Keep it tight so it's quick to write and answer:
prompts of 1-3 lines, explanations of one sentence, reference answers of 1-3 sentences, at most ONE code
question with 3 small tests. Return ONLY JSON:
{{"questions": [
  {{"id": "q1", "type": "mcq", "prompt": "...", "options": ["...","...","...","..."], "answer_index": 0, "explanation": "..."}},
  {{"id": "q2", "type": "short", "prompt": "...", "reference_answer": "...", "rubric": "what a full-marks answer must contain"}},
  {{"id": "q3", "type": "code", "prompt": "... (Python)", "function_name": "solve", "starter_code": "def solve(...):\\n    pass",
    "tests": [{{"args": [..], "expected": ..}}], "reference_answer": "short explanation of optimal approach + complexity"}}
]}}
Rules: at least one 'short' question; include 'code' questions only if the topic is programmable
(DSA/SWE/quant-dev/ML); code tests must be JSON-serialisable args/expected and deterministic;
questions must be correct - double-check answers."""

GRADE_PROMPT = """Grade these answers strictly but fairly, like a top-firm interviewer.
Module: {module}
For each item give a score 0-10 and one or two sentences of feedback, pointing at the exact gap.
Items:
{items}
Return ONLY JSON: {{"results": [{{"id": "...", "score": 0-10, "feedback": "..."}}], "overall_feedback": "2-3 sentences: strongest area, weakest area, what to study next"}}"""


def make_test(module_id: str, n: int = 5, difficulty: str = "interview level") -> dict:
    brain.set_purpose("Tests & grading", "")
    t, m = module(module_id)
    if not m:
        raise ValueError("unknown module")
    notes = (db.q1("SELECT notes FROM learn_progress WHERE module_id=?", (module_id,)) or {}).get("notes", "")
    prompt = TEST_PROMPT.format(track=t["title"], module=m["title"], topics="; ".join(m["topics"]),
                                notes=(notes or "")[:2000], difficulty=difficulty, n=n)
    data, _ = brain.ask_json(prompt, max_turns=2, timeout=400, fast=True)
    qs = data.get("questions", []) if isinstance(data, dict) else []
    tid = db.x("INSERT INTO tests(module_id,payload,created_at) VALUES(?,?,?)", (module_id, json.dumps(qs), db.now()))
    public = []
    for q in qs:
        pq = {k: v for k, v in q.items() if k not in ("answer_index", "reference_answer", "rubric", "explanation", "tests")}
        if q.get("type") == "code":
            pq["n_tests"] = len(q.get("tests") or [])
        public.append(pq)
    return {"test_id": tid, "module": m["title"], "questions": public}


HARNESS = r"""
import json, sys, io, contextlib
src = open(sys.argv[1], encoding='utf-8').read()
tests = json.load(open(sys.argv[2], encoding='utf-8'))
fn_name = sys.argv[3]
ns = {}
out = []
try:
    exec(compile(src, 'solution.py', 'exec'), ns)
    fn = ns[fn_name]
except Exception as e:
    print(json.dumps([{'ok': False, 'error': 'compile: ' + repr(e)}])); sys.exit(0)
for t in tests:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            got = fn(*t.get('args', []))
        exp = t.get('expected')
        ok = got == exp or (isinstance(got, float) and isinstance(exp, (int, float)) and abs(got - exp) < 1e-6) \
             or (isinstance(got, tuple) and list(got) == exp)
        out.append({'ok': bool(ok), 'args': t.get('args'), 'expected': exp, 'got': repr(got)[:200]})
    except Exception as e:
        out.append({'ok': False, 'args': t.get('args'), 'error': repr(e)[:200]})
print(json.dumps(out))
"""


def run_code(code: str, tests: list, fn_name: str, timeout: int = 8) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        (dp / "sol.py").write_text(code, encoding="utf-8")
        (dp / "tests.json").write_text(json.dumps(tests), encoding="utf-8")
        (dp / "h.py").write_text(HARNESS, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, str(dp / "h.py"), str(dp / "sol.py"), str(dp / "tests.json"), fn_name],
                               capture_output=True, text=True, timeout=timeout, cwd=d,
                               creationflags=0x08000000 if sys.platform == "win32" else 0)
        except subprocess.TimeoutExpired:
            return [{"ok": False, "error": f"timed out after {timeout}s (too slow or infinite loop)"}]
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return [{"ok": False, "error": (r.stderr or r.stdout)[-500:]}]


def grade(test_id: int, answers: dict) -> dict:
    brain.set_purpose("Tests & grading", "")
    row = db.q1("SELECT * FROM tests WHERE id=?", (test_id,))
    if not row:
        raise ValueError("no such test")
    qs = json.loads(row["payload"])
    _, m = module(row["module_id"])
    results, to_ai = {}, []
    for q in qs:
        a = answers.get(q["id"], "")
        if q["type"] == "mcq":
            ok = str(a) != "" and int(a) == int(q.get("answer_index", -1))
            results[q["id"]] = {"id": q["id"], "score": 10 if ok else 0,
                                "feedback": ("Correct. " if ok else f"Answer: option {int(q.get('answer_index', 0)) + 1}. ") + q.get("explanation", "")}
        elif q["type"] == "code":
            runs = run_code(a or "", q.get("tests") or [], q.get("function_name") or "solve") if a else []
            passed = sum(1 for r in runs if r.get("ok"))
            total = max(1, len(q.get("tests") or []))
            results[q["id"]] = {"id": q["id"], "score": round(10 * passed / total, 1), "tests": runs,
                                "feedback": f"{passed}/{total} tests passed."}
            to_ai.append({"id": q["id"], "type": "code-quality", "question": q["prompt"], "answer": a[:4000],
                          "reference": q.get("reference_answer", ""), "tests_passed": f"{passed}/{total}"})
        else:
            to_ai.append({"id": q["id"], "type": "short", "question": q["prompt"], "answer": a[:4000],
                          "reference": q.get("reference_answer", ""), "rubric": q.get("rubric", "")})
    overall = ""
    if to_ai and brain.available():
        data, _ = brain.ask_json(GRADE_PROMPT.format(module=m["title"] if m else row["module_id"],
                                                     items=json.dumps(to_ai, ensure_ascii=False, indent=1)),
                                 max_turns=2, timeout=400, fast=True)
        for r in (data or {}).get("results", []):
            rid = r.get("id")
            if rid in results and "tests" in results[rid]:
                results[rid]["feedback"] += " " + r.get("feedback", "")
                results[rid]["score"] = round(0.7 * results[rid]["score"] + 0.3 * float(r.get("score", 0)), 1)
            else:
                results[rid] = {"id": rid, "score": float(r.get("score", 0)), "feedback": r.get("feedback", "")}
        overall = (data or {}).get("overall_feedback", "")
    for q in qs:
        if q["type"] != "mcq" and q.get("reference_answer"):
            results.setdefault(q["id"], {"id": q["id"], "score": 0, "feedback": ""})["reference"] = q["reference_answer"]
    scores = [r["score"] for r in results.values()]
    pct = round(10 * sum(scores) / max(1, len(scores)), 1)
    db.x("UPDATE tests SET answers=?, grade=?, score=? WHERE id=?",
         (json.dumps(answers), json.dumps({"results": list(results.values()), "overall": overall}), pct, test_id))
    if pct >= 80:
        save_progress(row["module_id"], status="done")
    elif (db.q1("SELECT status FROM learn_progress WHERE module_id=?", (row["module_id"],)) or {}).get("status") in (None, "todo"):
        save_progress(row["module_id"], status="learning")
    return {"score": pct, "results": list(results.values()), "overall": overall}


MOCK_SYSTEM = """You are running a live mock interview for the role/track "{track}" (module focus: {module}).
Act exactly like a strong interviewer at a top firm: one question at a time, push on vague answers,
give hints only when asked, keep your turns short. The candidate's background:
{facts}
Start now with a brief greeting and your first question."""


def mock_turn(track_id: str, module_id: str, message: str, session: str | None) -> dict:
    brain.set_purpose("Mock interviews", "")
    if not session:
        data = next((t for t in _tracks_raw()["tracks"] if t["id"] == track_id), {"title": track_id})
        _, m = module(module_id) if module_id else (None, None)
        prompt = MOCK_SYSTEM.format(track=data["title"], module=(m or {}).get("title", "general"),
                                    facts=brain.me_context(short=True)[:4000])
        if message:
            prompt += f"\n\nCandidate says: {message}"
        r = brain.ask(prompt, max_turns=2, timeout=300, fast=True)
    else:
        r = brain.ask(message, resume=session, max_turns=2, timeout=300, fast=True)
    return {"reply": r["text"], "session": r["session_id"]}
