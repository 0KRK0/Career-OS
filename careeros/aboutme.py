"""Your career folder + Claude's understanding of you.

You choose one folder (e.g. D:\\My career). Your CV and any documents about you live there.
Claude Code reads that folder and writes what it understood into it:

  <career folder>/career-os/about-me.md          who you are, your story, projects, goals, voice
  <career folder>/career-os/open-questions.md    things it wants to ask you
  <career folder>/career-os/answers-history.md   answers you've given on real forms (reused for consistency)

Everything Claude writes for you (cover letters, form answers) starts from about-me.md,
so it answers like someone who actually knows you - not by matching labels."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import brain, db
from .config import CONFIG_DIR, candidate_summary, save_settings, settings


def folder() -> Path | None:
    p = (settings().get("profile_dir") or "").strip()
    return Path(p) if p else None


def work_dir() -> Path | None:
    f = folder()
    if not f:
        return None
    d = f / "career-os"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return d


def _read(name: str) -> str:
    d = work_dir()
    if d and (d / name).exists():
        return (d / name).read_text(encoding="utf-8", errors="replace")
    return ""


def _write(name: str, text: str) -> None:
    d = work_dir()
    if d:
        (d / name).write_text(text, encoding="utf-8")


def about_md() -> str:
    return _read("about-me.md")


def questions() -> list[str]:
    return [l[2:].strip() for l in _read("open-questions.md").splitlines() if l.startswith("- ")]


def history(limit_chars: int = 6000) -> str:
    h = _read("answers-history.md")
    return h[-limit_chars:] if h else ""


def files(limit: int = 60) -> list[dict]:
    f = folder()
    if not f or not f.exists():
        return []
    out = []
    for p in sorted(f.rglob("*")):
        if not p.is_file() or "career-os" in p.parts or p.name.startswith("."):
            continue
        if p.suffix.lower() in (".pdf", ".docx", ".doc", ".md", ".txt", ".rtf", ".odt", ".tex", ".json", ".html"):
            out.append({"name": str(p.relative_to(f)).replace("\\", "/"), "kb": round(p.stat().st_size / 1024)})
        if len(out) >= limit:
            break
    return out


def set_folder(path: str) -> dict:
    p = Path(path.strip().strip('"'))
    p.mkdir(parents=True, exist_ok=True)
    save_settings({"profile_dir": str(p)})
    work_dir()
    return {"ok": True, "profile_dir": str(p)}


BUILD_PROMPT = """You are building a deep, honest understanding of a job candidate so that you can later
fill in applications and write for them the way a trusted friend who knows them well would.

Their career folder is: {folder}
Use Glob/Read to look at it (and subfolders). Prioritise: CVs/resumes, cover letters, personal
statements, READMEs of their projects, transcripts, certificates, notes, anything "about me".
Read at most ~40 files; skip images, binaries, code files and duplicates.
Also here is what we already know (profile + checked facts):
{known}

Write about-me.md in markdown with these sections:
# About me (Claude's understanding)
## Snapshot  (5 lines: who they are right now)
## Story  (their path so far, in order, in plain words)
## Experience  (each role: what they actually did, results with the exact numbers written in their documents)
## Projects  (each project: what it is, what they built, tech, links, honest status/limitations)
## Education
## Skills  (grouped; only skills evidenced in the documents)
## Achievements & publications
## Goals & motivations  (what they want and why - only what documents/answers state; otherwise leave for questions)
## Constraints  (work rights, locations, availability - as stated)
## Voice  (how they write: tone, typical phrasing; 2-3 short verbatim samples from their own writing)
## Do not claim  (things that are unverified, lapsed, in progress, or that they asked never to say)
## Sources  (which files each part came from)

Never invent. If something is unknown, don't guess - add a question instead.
Then list 6-10 short questions whose answers would most improve applications (motivations, why AI/quant,
preferred teams, availability, research interests, stories for behavioural questions, etc.).

Return ONLY JSON: {{"about_me_md": "...", "questions": ["...", "..."]}}"""

MERGE_PROMPT = """Here is your current understanding of the candidate (about-me.md):
{about}

They just answered these questions in their own words:
{answers}

Update about-me.md: fold the answers into the right sections (keep their wording where it helps the
Voice section), keep everything else, never invent. Then list any NEW follow-up questions (0-5).
Return ONLY JSON: {{"about_me_md": "...", "questions": ["..."]}}"""


def build(log=print) -> dict:
    brain.set_purpose("About me", "")
    f = folder()
    if not f or not f.exists():
        raise ValueError("Choose your career folder first.")
    known = (CONFIG_DIR / "career-facts.md").read_text(encoding="utf-8") if (CONFIG_DIR / "career-facts.md").exists() else ""
    known = candidate_summary() + "\n\n" + known[:12000]
    _job("running", "Reading your career folder…")
    try:
        data, _ = brain.ask_json(BUILD_PROMPT.format(folder=str(f), known=known), tools=["Read", "Glob", "Grep"],
                                 add_dirs=[str(f)], max_turns=60, timeout=2400, log=log)
    except Exception as e:  # noqa: BLE001
        _job("error", str(e))
        raise
    md = (data or {}).get("about_me_md", "")
    if md:
        _write("about-me.md", md)
    qs = [q for q in (data or {}).get("questions", []) if q]
    _write("open-questions.md", "\n".join(f"- {q}" for q in qs) + "\n")
    _job("done", f"Understanding written ({len(md.split())} words), {len(qs)} questions for you")
    return {"about_me_md": md, "questions": qs}


def merge_answers(ans: dict) -> dict:
    brain.set_purpose("About me", "")
    pairs = "\n".join(f"Q: {q}\nA: {a}" for q, a in ans.items() if str(a).strip())
    if not pairs:
        return {"about_me_md": about_md(), "questions": questions()}
    data, _ = brain.ask_json(MERGE_PROMPT.format(about=about_md() or candidate_summary(), answers=pairs), max_turns=3, timeout=900)
    md = (data or {}).get("about_me_md") or about_md()
    _write("about-me.md", md)
    left = [q for q in questions() if q not in ans or not str(ans[q]).strip()]
    qs = left + [q for q in (data or {}).get("questions", []) if q]
    _write("open-questions.md", "\n".join(f"- {q}" for q in qs) + "\n")
    return {"about_me_md": md, "questions": qs}


def add_questions(qs: list[str]) -> None:
    cur = questions()
    new = [q for q in qs if q and q not in cur]
    if new:
        _write("open-questions.md", "\n".join(f"- {q}" for q in cur + new) + "\n")


def record_answers(fields: list[dict], org: str, title: str) -> int:
    """Keep your own long-form answers (what you finally submitted) so future forms stay consistent."""
    items = [(f["label"], f["value"]) for f in fields
             if f.get("kind") in ("textarea", "text") and len((f.get("value") or "").strip()) >= 60 and f.get("label")]
    if not items:
        return 0
    block = f"\n## {date.today().isoformat()} · {title} — {org}\n" + "".join(f"\n**{l.strip()}**\n{v.strip()}\n" for l, v in items)
    _write("answers-history.md", (_read("answers-history.md") or "# Answers you've given\n") + block)
    return len(items)


def _job(status: str, detail: str) -> None:
    db.kv_set("aboutme_job", {"status": status, "detail": detail, "at": db.now()})
