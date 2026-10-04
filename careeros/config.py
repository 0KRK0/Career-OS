"""Paths, settings and profile loading. Everything personal lives in config/*.yaml
(git-ignored) and data/ (git-ignored). Only *.example.yaml files are committed."""
from __future__ import annotations

import copy
import os
import shutil
import threading
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
CONTENT_DIR = Path(__file__).resolve().parent / "content"
WEB_DIR = ROOT / "web"
APPS_DIR = DATA_DIR / "applications"
LOG_DIR = DATA_DIR / "logs"
BROWSER_PROFILE = DATA_DIR / "browser-profile"
DB_PATH = DATA_DIR / "careeros.db"

for d in (DATA_DIR, APPS_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS: dict = {
    "port": 8765,
    "books_dir": "",
    "profile_dir": "",  # your career folder: CV + documents about you; Claude writes its understanding there
    "cv_path": "",
    "resume_path": "",
    # countries where the 1-page resume is uploaded instead of the 2-page CV
    "use_resume_for_countries": [],
    "browser_channel": "chrome",  # "chrome", "msedge" or "" for Playwright's bundled Chromium
    # the AI that does the thinking - a command-line app signed in with YOUR subscription (no API keys)
    "llm": {"provider": "claude", "cmd": "", "model": ""},   # provider: claude | codex | gemini
    "claude_cmd": "claude",   # older setting, still honoured for Claude
    "claude_model": "",
    "max_parallel_agents": 2,
    "scout_times": ["07:30", "17:30"],  # Apply runs twice a day
    "min_score": 55,
    "auto_prepare_top": 12,  # after each scout run, draft cover letters for the best N new matches
    # neutral until you pick countries in the setup wizard (then country_weights_goal takes over)
    "country_weights": {"REMOTE": 8, "OTHER": 6},
    "tracks_enabled": [],  # filled from your target roles
    "blocked_autofill_domains": ["linkedin.com", "indeed.com", "naukri.com", "glassdoor.com"],
    "ai_fill_unknown": True,
    # automation switches (all on by default; change them in the Apply filter panel or Settings)
    "auto_prepare": True,          # draft cover letters for the best new matches after each scan
    "auto_open_autofill": True,    # at the daily digest time, open the autofill browser with ready applications
    "remember_filters": True,
    "filters": {},                 # the Apply filter panel's saved view
    "learn": {"selected": []},     # Learn tracks shown in your sidebar (empty = picked from your degree + roles)
    "notify": {"toast": True, "deadline_days": [7, 3, 1], "daily_digest": "20:00"},
    "email": {
        "enabled": False,
        "imap_host": "imap.gmail.com",
        "address": "",
        "app_password": "",
        "check_every_minutes": 60,
        "lookback_days": 45,
        "followup_after_days": 14,
        "create_drafts": True,
    },
    "adzuna": {"app_id": "", "app_key": ""},
    "reed": {"api_key": ""},
}

_lock = threading.RLock()


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


def _apply_update_file() -> None:
    """An update can ship config/settings.update.yaml: its keys are added only where you haven't set them,
    so updating never overwrites your own settings. The file is removed once applied."""
    up = CONFIG_DIR / "settings.update.yaml"
    if not up.exists():
        return
    cur = _read_yaml(CONFIG_DIR / "settings.yaml")
    add = {k: v for k, v in (_read_yaml(up) or {}).items() if not cur.get(k)}
    if add:
        _write_yaml(CONFIG_DIR / "settings.yaml", _deep_merge(cur, add))
    try:
        up.unlink()
    except OSError:
        pass


def settings() -> dict:
    with _lock:
        _apply_update_file()
        return _deep_merge(DEFAULT_SETTINGS, _read_yaml(CONFIG_DIR / "settings.yaml"))


def save_settings(new: dict) -> dict:
    with _lock:
        # store only what you changed; untouched options keep following the defaults
        merged = _deep_merge(_read_yaml(CONFIG_DIR / "settings.yaml"), new)
        _write_yaml(CONFIG_DIR / "settings.yaml", merged)
        return settings()


def profile() -> dict:
    with _lock:
        p = _read_yaml(CONFIG_DIR / "profile.yaml")
        if not p:
            p = _read_yaml(CONFIG_DIR / "profile.example.yaml")
        return p


def save_profile(p: dict) -> None:
    with _lock:
        _write_yaml(CONFIG_DIR / "profile.yaml", p)


def companies() -> dict:
    """Your company list. Starts as a copy of companies.default.yaml; finders then add to your copy."""
    mine = CONFIG_DIR / "companies.yaml"
    if not mine.exists() and (CONFIG_DIR / "companies.default.yaml").exists():
        with _lock:
            shutil.copy(CONFIG_DIR / "companies.default.yaml", mine)
    return _read_yaml(mine)


def save_companies(c: dict) -> None:
    with _lock:
        _write_yaml(CONFIG_DIR / "companies.yaml", c)


def read_text(name: str) -> str:
    """Read a personal text file from config/ (career-facts.md, cv.md, resume.md)."""
    p = CONFIG_DIR / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    ex = CONFIG_DIR / (Path(name).stem + ".example" + Path(name).suffix)
    return ex.read_text(encoding="utf-8") if ex.exists() else ""


LLM_CLI = {"claude": "claude", "codex": "codex", "gemini": "gemini"}


def llm_provider() -> str:
    p = ((settings().get("llm") or {}).get("provider") or "claude").lower()
    return p if p in LLM_CLI else "claude"


def cli_exe(provider: str | None = None) -> str | None:
    """Find the AI's command-line app (Claude Code, OpenAI Codex CLI or Gemini CLI)."""
    provider = provider or llm_provider()
    s = settings()
    cmd = (s.get("llm") or {}).get("cmd") if provider == llm_provider() else ""
    cmd = cmd or (s.get("claude_cmd") if provider == "claude" else "") or LLM_CLI[provider]
    found = shutil.which(cmd)
    if found:
        return found
    home = Path.home()
    name = LLM_CLI[provider]
    for cand in (home / ".local" / "bin" / f"{name}.exe", home / ".local" / "bin" / name,
                 home / "AppData" / "Roaming" / "npm" / f"{name}.cmd", Path(os.environ.get("APPDATA", "")) / "npm" / f"{name}.cmd"):
        if str(cand) and cand.exists():
            return str(cand)
    return None


def claude_exe() -> str | None:   # kept for older code paths
    return cli_exe()


# ---------------- profile helpers (make everything work for any user) ----------------

def onboarded() -> bool:
    p = _read_yaml(CONFIG_DIR / "profile.yaml")
    return bool(p.get("onboarded"))


def file_stub() -> str:
    """'Jane_Doe' - used for generated file names (cover letters)."""
    import re as _re
    name = (profile().get("full_name") or "Candidate").strip()
    return _re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "Candidate"


def cover_letter_name() -> str:
    return f"{file_stub()}_Cover_Letter.pdf"


def goals() -> dict:
    g = profile().get("goals") or {}
    return {"roles": g.get("roles") or [], "countries": g.get("countries") or [],
            "kinds": g.get("kinds") or ["job", "internship", "graduate", "fellowship", "scholarship"],
            "level": g.get("level") or "early", "salary_goal": g.get("salary_goal") or ""}


def candidate_summary() -> str:
    """A short, factual summary of the candidate for agent prompts. Built from profile.yaml."""
    p = profile()
    if p.get("summary"):
        return str(p["summary"]).strip()
    parts = []
    edu = (p.get("education") or [{}])[0] if p.get("education") else {}
    deg = " ".join(x for x in [edu.get("level") or p.get("degree"), edu.get("field") or p.get("discipline")] if x)
    school = edu.get("school") or p.get("school")
    if deg or school:
        parts.append(f"Education: {deg}{' at ' + school if school else ''}{' (ends ' + str(edu.get('end') or p.get('grad_year')) + ')' if (edu.get('end') or p.get('grad_year')) else ''}.")
    if p.get("current_title") or p.get("current_company"):
        parts.append(f"Most recent role: {p.get('current_title', '')} at {p.get('current_company', '')}; "
                     f"{p.get('years_experience', '?')} years' experience.")
    if p.get("location"):
        parts.append(f"Based in {p['location']}.")
    wr = p.get("work_rights") or {}
    free = wr.get("no_sponsorship_needed_in") or []
    if free:
        parts.append(f"Can work without sponsorship in: {', '.join(free)}.")
    if str(p.get("requires_sponsorship", "")).lower().startswith("y"):
        parts.append("Needs visa sponsorship elsewhere - include roles that sponsor or where it's unknown; skip roles that refuse sponsorship or require citizenship.")
    if wr.get("notes"):
        parts.append(f"Work-rights notes: {wr['notes']}.")
    g = goals()
    if g["roles"]:
        parts.append(f"Target roles: {', '.join(g['roles'])}. Level: {g['level']}.")
    return " ".join(parts) or "No profile yet."
