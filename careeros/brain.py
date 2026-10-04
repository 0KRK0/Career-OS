"""The 'brain': your AI's command-line app run headless - Claude Code (`claude -p`), OpenAI Codex CLI
(`codex exec`, signed in with ChatGPT) or Gemini CLI (`gemini -p`, signed in with Google).
It uses your own subscription's limits: no API keys, no per-token billing.

API-key variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY...) are removed from the
environment so an agent can never fall back to paid API billing."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from .config import DATA_DIR, cli_exe, llm_provider, settings

_sem_lock = threading.Lock()
_sem: threading.BoundedSemaphore | None = None
_sem_size = 0
_active = 0
_active_lock = threading.Lock()

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
WORKDIR = DATA_DIR / "agent-workdir"
WORKDIR.mkdir(parents=True, exist_ok=True)


def _semaphore() -> threading.BoundedSemaphore:
    global _sem, _sem_size
    n = max(1, int(settings().get("max_parallel_agents") or 2))
    with _sem_lock:
        if _sem is None or n != _sem_size:
            _sem, _sem_size = threading.BoundedSemaphore(n), n
        return _sem


def active_count() -> int:
    return _active


PROVIDERS = {
    "claude": {"name": "Claude", "app": "Claude Code", "plan": "Claude Pro or Max",
               "install_win": "irm https://claude.ai/install.ps1 | iex", "install_unix": "curl -fsSL https://claude.ai/install.sh | bash",
               "login_hint": "When Claude opens, type /login and choose 'Claude account with subscription' (Pro/Max) - NOT an API key.",
               "strip": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"]},
    "codex": {"name": "ChatGPT", "app": "Codex CLI", "plan": "ChatGPT Plus, Pro or Team",
              "install_win": "npm install -g @openai/codex", "install_unix": "npm install -g @openai/codex",
              "login_args": ["login"],
              "login_hint": "Choose 'Sign in with ChatGPT' in the browser that opens - NOT an API key.",
              "strip": ["OPENAI_API_KEY", "CODEX_API_KEY"]},
    "gemini": {"name": "Gemini", "app": "Gemini CLI", "plan": "a Google account (free tier) or Google AI Pro",
               "install_win": "npm install -g @google/gemini-cli", "install_unix": "npm install -g @google/gemini-cli",
               "login_hint": "Choose 'Login with Google', finish in the browser, then type /quit.",
               "strip": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"]},
}


# the quicker model for interactive things (you're waiting on screen). Settings → llm.fast_model overrides ("" = same as main).
FAST_DEFAULT = {"claude": "sonnet", "gemini": "flash", "codex": ""}


def provider() -> str:
    return llm_provider()


def info(p: str | None = None) -> dict:
    return PROVIDERS[p or provider()]


def name() -> str:
    return info()["name"]


def tr(text: str) -> str:
    """Show the right AI's name in messages written for Claude."""
    p = provider()
    if p == "claude":
        return text
    i = info(p)
    return text.replace("Claude Code", i["app"]).replace("Claude", i["name"])


def available() -> bool:
    return cli_exe() is not None


def status() -> dict:
    exe = cli_exe()
    i = info()
    out = {"available": bool(exe), "path": exe or "", "version": "", "active": _active,
           "provider": provider(), "name": i["name"], "app": i["app"], "plan": i["plan"],
           "max_parallel": int(settings().get("max_parallel_agents") or 2)}
    try:
        from . import db
        out["auth_error"] = (db.kv_get("brain_auth") or {}).get("msg", "")
    except Exception:  # noqa: BLE001
        out["auth_error"] = ""
    if exe:
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20,
                               creationflags=CREATE_NO_WINDOW, env=_env())
            out["version"] = (r.stdout or r.stderr).strip().splitlines()[0][:80] if (r.stdout or r.stderr).strip() else ""
        except Exception as e:  # noqa: BLE001
            out["version"] = f"error: {e}"[:80]
    return out


def _env() -> dict:
    env = dict(os.environ)
    for p in PROVIDERS.values():          # never let any AI fall back to pay-per-use API billing
        for k in p["strip"]:
            env.pop(k, None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


_ctx = threading.local()


def set_purpose(purpose: str, detail: str = "") -> None:
    """Label the Claude calls made on this thread (for the usage meter)."""
    _ctx.purpose, _ctx.detail = purpose, detail


def _record(data: dict | None, ok: bool, purpose: str | None, detail: str | None) -> None:
    try:
        from . import db
        u = (data or {}).get("usage") or {}
        stu = u.get("server_tool_use") or {}
        db.x("INSERT INTO usage(at,purpose,detail,ok,input_tokens,output_tokens,cache_tokens,web_searches,turns,duration_ms,api_equiv_usd) "
             "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
             (db.now(), purpose or getattr(_ctx, "purpose", "other"), (detail or getattr(_ctx, "detail", ""))[:120], 1 if ok else 0,
              int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
              int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0),
              int(stu.get("web_search_requests") or 0) + int(stu.get("web_fetch_requests") or 0),
              int((data or {}).get("num_turns") or 0), int((data or {}).get("duration_ms") or 0),
              float((data or {}).get("total_cost_usd") or 0)))
    except Exception:  # noqa: BLE001
        pass


class BrainError(RuntimeError):
    pass


class LimitError(BrainError):
    """Your plan's usage limit is reached; agents pause until it resets."""


class AuthError(BrainError):
    """The AI app is installed but not signed in (or its sign-in expired)."""


def auth_msg() -> str:
    i = info()
    return (f"{i['app']} isn't signed in (or its sign-in expired). In Career OS press 'Sign in' on the red bar "
            f"(or Settings → AI), sign in with your {i['plan']} subscription - not an API key - then press Test.")


_AUTH_RX = re.compile(r"\b401\b|failed to authenticate|authentication_error|invalid api key|oauth token|not logged in|"
                      r"please run /login|/login|invalid x-api-key|credit balance|unauthori[sz]ed|please (log|sign) in|"
                      r"login required|no credentials|auth(entication)? (required|failed)", re.I)
_LIMIT_RX = re.compile(r"usage limit|rate.?limit|limit reached|quota|\b429\b|too many requests|try again (in|at|later)", re.I)


def _fail(msg: str, status: int | None = None) -> None:
    """Turn an error from the AI app into the right exception."""
    from . import db
    msg = str(msg or "")
    if status in (401, 403) or _AUTH_RX.search(msg):
        db.kv_set("brain_auth", {"at": db.now(), "msg": msg[:300]})
        raise AuthError(auth_msg())
    if status == 429 or _LIMIT_RX.search(msg):
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(hours=5)).replace(microsecond=0).isoformat()
        win = db.q1("SELECT SUM(input_tokens+output_tokens) t FROM usage WHERE at >= ? AND ok=1", (since,))["t"] or 0
        db.kv_set("brain_limited", {"at": db.now(), "msg": msg[:200], "window_tokens": win})
        raise LimitError(f"{name()} plan limit reached - agents pause and retry after it resets. ({msg[:200]})")
    raise BrainError(f"{info()['app']} error: {msg[:600]}")


def _run(cmd: list[str], prompt: str, timeout: int, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=str(cwd), env=_env(), creationflags=CREATE_NO_WINDOW)


def _drop(cmd: list[str], flag: str, has_value: bool = False) -> list[str]:
    if flag not in cmd:
        return cmd
    i = cmd.index(flag)
    return cmd[:i] + cmd[i + (2 if has_value else 1):]


def _claude(exe, prompt, tools, max_turns, timeout, resume, add_dirs, model):
    cmd = [exe, "-p", "--output-format", "json"]
    for d in add_dirs or []:
        if d and Path(d).exists():
            cmd += ["--add-dir", str(d)]
    cmd += ["--allowedTools", ",".join(tools)] if tools else ["--disallowedTools", "Bash,Edit,Write,NotebookEdit"]
    if max_turns:
        cmd += ["--max-turns", str(max_turns)]
    if resume:
        cmd += ["--resume", resume]
    if model:
        cmd += ["--model", model]
    r = _run(cmd, prompt, timeout, WORKDIR)
    if r.returncode != 0 and "unknown option" in (r.stderr or "") and "--max-turns" in cmd:
        r = _run(_drop(cmd, "--max-turns", True), prompt, timeout, WORKDIR)
    out = (r.stdout or "").strip()
    try:
        data = json.loads(out.splitlines()[-1] if out and not out.startswith("{") else out)
    except (ValueError, IndexError):
        _fail((r.stderr or out)[:600] or f"no output (exit {r.returncode})")
    ok = not data.get("is_error") and data.get("subtype") in (None, "success")
    _record(data, ok, None, None)
    if not ok:
        msg = data.get("result") or data.get("subtype") or r.stderr
        if data.get("is_error") or not data.get("result"):
            _fail(msg, data.get("api_error_status"))
    return {"text": data.get("result") or "", "session_id": data.get("session_id", ""), "raw": data}


def _codex(exe, prompt, tools, timeout, resume, add_dirs, model):
    import tempfile
    fd, last = tempfile.mkstemp(prefix="codex-", suffix=".txt", dir=str(WORKDIR))
    os.close(fd)
    cmd = [exe, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--output-last-message", last]
    if model:
        cmd += ["--model", model]
    if tools and any(t in tools for t in ("WebSearch", "WebFetch")):
        cmd += ["--search"]
    cmd += (["resume", resume, "-"] if resume else ["-"])
    r = _run(cmd, prompt, timeout, WORKDIR)
    if r.returncode != 0 and "--search" in cmd and re.search(r"unexpected argument|unknown (option|argument)|unrecognized", r.stderr or "", re.I):
        r = _run(_drop(cmd, "--search"), prompt, timeout, WORKDIR)
    sid, usage, text, err = "", {}, "", ""
    for line in (r.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type", "")
        if t in ("thread.started", "session.created"):
            sid = ev.get("thread_id") or ev.get("session_id") or sid
        elif t == "turn.completed":
            u = ev.get("usage") or {}
            for k in ("input_tokens", "output_tokens", "cached_input_tokens"):
                usage[k] = usage.get(k, 0) + int(u.get(k) or 0)
        elif t == "item.completed" and (ev.get("item") or {}).get("type") in ("agent_message", "assistant_message"):
            text = ev["item"].get("text") or text
        elif t in ("error", "turn.failed"):
            err = (ev.get("error") or {}).get("message") if isinstance(ev.get("error"), dict) else ev.get("message") or str(ev)
    try:
        text = Path(last).read_text(encoding="utf-8").strip() or text
    except OSError:
        pass
    finally:
        try:
            os.unlink(last)
        except OSError:
            pass
    data = {"usage": {"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
                      "cache_read_input_tokens": usage.get("cached_input_tokens", 0)}}
    _record(data, bool(text) and not err, None, None)
    if not text:
        _fail(err or (r.stderr or "")[-600:] or f"no answer (exit {r.returncode})")
    return {"text": text, "session_id": sid, "raw": data}


def _gemini(exe, prompt, tools, timeout, add_dirs, model):
    cmd = [exe, "--output-format", "json", "--approval-mode", "default"]
    if model:
        cmd += ["--model", model]
    dirs = [str(d) for d in add_dirs or [] if d and Path(d).exists()]
    if dirs:
        cmd += ["--include-directories", ",".join(dirs)]
    cmd += ["-p", "Follow the instructions above."]
    r = _run(cmd, prompt, timeout, WORKDIR)
    out = (r.stdout or "").strip()
    data = {}
    try:
        data = json.loads(out[out.index("{"):]) if "{" in out else {}
    except ValueError:
        data = {}
    tok = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
    for m in ((data.get("stats") or {}).get("models") or {}).values():
        t = m.get("tokens") or {}
        tok["input_tokens"] += int(t.get("prompt") or t.get("input") or 0)
        tok["output_tokens"] += int(t.get("candidates") or t.get("output") or 0)
        tok["cache_read_input_tokens"] += int(t.get("cached") or 0)
    text = data.get("response") or ""
    _record({"usage": tok}, bool(text), None, None)
    if not text:
        e = data.get("error") or {}
        _fail((e.get("message") if isinstance(e, dict) else str(e)) or (r.stderr or out)[-600:] or f"no answer (exit {r.returncode})",
              e.get("code") if isinstance(e, dict) and isinstance(e.get("code"), int) else None)
    return {"text": text, "session_id": "", "raw": {"usage": tok}}


def ask(prompt: str, tools: list[str] | None = None, max_turns: int | None = None,
        timeout: int = 900, resume: str | None = None, log=None, add_dirs: list[str] | None = None,
        purpose: str | None = None, detail: str | None = None, fast: bool = False) -> dict:
    """Run one headless turn of your AI app. fast=True uses the quicker model (teacher, tests, chat). Returns {'text', 'session_id', 'raw'}.
    tools use Claude's names (WebSearch, WebFetch, Read, Glob, Grep); other apps get the nearest equivalent."""
    global _active
    exe = cli_exe()
    i = info()
    if not exe:
        raise BrainError(f"{i['app']} not found. Install it in Settings → AI and sign in with your {i['plan']} subscription.")
    p = provider()
    if resume and p == "gemini":
        raise BrainError("This AI app can't continue a conversation - starting fresh.")
    llm = settings().get("llm") or {}
    model = (llm.get("model") or (settings().get("claude_model") if p == "claude" else "") or "").strip()
    if fast:
        model = (llm.get("fast_model") if "fast_model" in llm else FAST_DEFAULT.get(p, "")) or model
    saved = (getattr(_ctx, "purpose", "other"), getattr(_ctx, "detail", ""))
    if purpose or detail:
        set_purpose(purpose or saved[0], detail or saved[1])
    sem = _semaphore()
    if log:
        log("  waiting for a free agent slot..." if _active >= _sem_size else f"  thinking ({i['app']})...")
    with sem:
        with _active_lock:
            _active += 1
        try:
            if p == "codex":
                res = _codex(exe, prompt, tools, timeout, resume, add_dirs, model)
            elif p == "gemini":
                res = _gemini(exe, prompt, tools, timeout, add_dirs, model)
            else:
                res = _claude(exe, prompt, tools, max_turns, timeout, resume, add_dirs, model)
        except subprocess.TimeoutExpired as e:
            raise BrainError(f"{i['app']} timed out after {timeout}s") from e
        finally:
            with _active_lock:
                _active -= 1
            _ctx.purpose, _ctx.detail = saved
    try:
        from . import db
        if db.kv_get("brain_auth"):
            db.kv_set("brain_auth", None)   # signed in again - clear the warning
        db.kv_set("brain_last_ok", db.now())
    except Exception:  # noqa: BLE001
        pass
    return res


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply."""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidates = [m.group(1)] if m else []
    candidates.append(text)
    for c in candidates:
        c = c.strip()
        try:
            return json.loads(c)
        except ValueError:
            pass
        for open_ch, close_ch in (("[", "]"), ("{", "}")):
            start = c.find(open_ch)
            while start != -1:
                depth, in_str, esc = 0, False, False
                for i in range(start, len(c)):
                    ch = c[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == "\\":
                            esc = True
                        elif ch == '"':
                            in_str = False
                        continue
                    if ch == '"':
                        in_str = True
                    elif ch == open_ch:
                        depth += 1
                    elif ch == close_ch:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(c[start:i + 1])
                            except ValueError:
                                break
                start = c.find(open_ch, start + 1)
    raise ValueError("no JSON found in reply")


def ask_json(prompt: str, **kw):
    res = ask(prompt, **kw)
    try:
        return extract_json(res["text"]), res
    except ValueError:
        # one repair attempt (in the same session when the AI app supports it)
        if res.get("session_id") and provider() != "gemini":
            fix = ask("Your last reply was not valid JSON. Reply again with ONLY the JSON, nothing else.",
                      resume=res["session_id"], max_turns=2, timeout=300)
        else:
            fix = ask(prompt + "\n\nIMPORTANT: reply with ONLY the JSON, no other text.", **kw)
        return extract_json(fix["text"]), fix


def me_context(short: bool = False) -> str:
    """What Claude knows about you: its understanding (about-me.md in your career folder) first,
    then the checked fact sheet, then the CV text."""
    from .config import read_text
    try:
        from .aboutme import about_md
        about = about_md()
    except Exception:  # noqa: BLE001
        about = ""
    facts = read_text("career-facts.md")
    if short:
        return (about[:6000] + "\n\n" + facts) if about else facts
    cv = read_text("cv.md")
    parts = []
    if about:
        parts.append("---- CLAUDE'S UNDERSTANDING OF THE CANDIDATE (about-me.md) ----\n" + about[:14000])
    parts.append("---- CHECKED FACTS & RULES ----\n" + facts)
    if cv:
        parts.append("---- MASTER CV ----\n" + cv[:12000])
    return "\n\n".join(parts)
