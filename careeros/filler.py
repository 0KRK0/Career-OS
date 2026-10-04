"""Autofill session. One visible browser window (its own profile in data/browser-profile,
so you stay signed in to Workday/Greenhouse accounts between runs). Each application
opens in its own tab, gets filled, and waits for YOU to review and click Submit.

Run:  python -m careeros.filler          (the app starts this for you)
"""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from . import answers, brain, db, opps
from .config import BROWSER_PROFILE, LOG_DIR, cover_letter_name, profile, settings

INJECT = brain.tr((Path(__file__).parent / "inject.js").read_text(encoding="utf-8"))
LOG = LOG_DIR / "filler.log"


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


FORM_PROMPT = """You are filling in an application form for the candidate - like a careful, trusted assistant
who knows them well. FIRST read and understand the whole page, THEN decide every field.

=== WHO THE CANDIDATE IS (your understanding + checked facts: the only source of truth) ===
{about}

=== THEIR PAST ANSWERS ON OTHER FORMS (reuse their wording where it fits; stay consistent) ===
{history}

=== WHAT THEY TOLD AUTOFILL BEFORE (short answers they gave or corrected) ===
{learned}

=== THE OPPORTUNITY ===
{job}
{prepared}

=== THE PAGE AS SHOWN ({url}) ===
{page}

=== LINKS ON THE PAGE ===
{links}

=== FIELDS (id, type, label, help text, options, required, current value, suggestion from their profile) ===
{fields}

How to decide:
- Follow the page's instructions (e.g. "apply through this other form instead", "1-2 paragraphs",
  "include a % estimate", word limits). If the page says the real application is elsewhere, put that
  link in open_links and say so in warnings.
- Write long answers in the candidate's own first-person voice, specific to THIS opportunity, using their
  real experience and projects. Respect the requested length. Spell the way the job's country does (American English for US/Canada roles, British English for most others) unless their About me says otherwise.
- If they already typed something in a field, keep it (don't rewrite) unless it's clearly for a different question.
- Keep suggestions from their profile unless the page shows they're wrong for this question.
- NEVER invent facts, numbers, dates, grades, references, people, or experience they don't have.
  When only the candidate can decide or know (salary, notice/start date if unknown, referees' names and
  emails, legal declarations, a personal estimate like "% likely to accept"), use action "needs_you" with a
  short note saying exactly what's needed - you may add a suggested draft in "value" for estimates/opinions,
  and it will be shown to them for approval.
- Eligibility / work-rights questions: answer truthfully from their constraints.
- Checkboxes and choices that are consents, acknowledgements, confirmations, declarations or marketing
  preferences: do NOT decide - list them in "consents" with one line explaining what ticking means.
  Choices that are just facts (e.g. "Have you applied before?") you may fill if you know the answer.
- For select/radio fields, "value" must be one of the listed options, copied exactly.

Return ONLY JSON:
{{"understanding": "2-3 sentences: what this page is and what it wants from them",
  "warnings": ["instructions they must not miss"],
  "open_links": [{{"url": "https://...", "why": "short"}}],
  "fields": [{{"id": "<id>", "action": "fill|needs_you|skip", "value": "...", "note": "one short line (why / what's needed)"}}],
  "consents": [{{"id": "<id>", "what": "what ticking/choosing means", "value": "the option to choose, or 'checked'"}}],
  "questions_for_candidate": ["things worth learning about them for next time"]}}"""

POLISH_PROMPT = """Polish the candidate's own draft answers on an application form. Keep their meaning, facts and
voice (first person, plain, confident, no buzzwords), fix grammar and flow, make them specific and complete for
the question, and respect any length hint. Never add facts that aren't in what they wrote or in their profile.
Spell the way the job's country does (American English for US/Canada roles, British English for most others) unless their About me says otherwise.

=== WHO THEY ARE ===
{about}

=== OPPORTUNITY ===
{job}

=== THEIR DRAFTS (id, question, help text, their text) ===
{drafts}

Return ONLY JSON: {{"<id>": "<polished text>", ...}}"""


CHAT_FIRST = """You are Claude, sitting beside {name} in their job-application browser (Career OS) - like a friend
who knows them well, looking at the same screen. Answer what they ask: about this page, the role, the company,
how to answer a question, whether something is a good idea. Be direct and short unless they ask for more.

Rules: never invent facts about them (only what's below); never tell them to claim things that aren't true;
you can't click anything - they submit and tick consents themselves. You may use WebSearch/WebFetch for facts
about the company or role, and say where facts came from. Spell the way the job's country does (American English for US/Canada roles, British English for most others) unless their About me says otherwise.

If they want text for a form field (e.g. "help me answer this"), write it in their voice from their real
experience and put it in "fill" with that field's id, so they can press Insert. Respect length hints.

=== WHO THEY ARE ===
{about}

=== THEIR PAST ANSWERS ON OTHER FORMS ===
{history}

=== THE OPPORTUNITY ===
{job}
"""

CHAT_TURN = """=== THE PAGE NOW ({url}) ===
{page}

=== FORM FIELDS (id, type, label, help, current value) ===
{fields}

=== THE FIELD THEY'RE ON ===
{focus}

=== THEIR MESSAGE ===
{text}

Return ONLY JSON: {{"reply": "your answer (plain text, **bold** allowed)", "fill": [{{"id": "<field id>", "value": "..."}}]}}
("fill" is usually empty - only when they asked for text for a field.)"""


class Tab:
    def __init__(self, page, oid: int | None, url: str):
        self.page, self.oid, self.url = page, oid, url
        self.job = opps.get(oid) if oid else None
        self.prepared = opps.prepared(oid) if oid else {}
        self.ai_future: Future | None = None
        self.polish_future: Future | None = None
        self.ai_done_url = ""
        self.ai_done_at = 0.0
        self.pending_submit = None
        self.chat_future: Future | None = None
        self.chat_session = ""
        self.chat_url = ""
        self.last_snapshot: list[dict] = []
        self.submitted = False
        self.needs_fill = True
        self.last_fill = 0.0
        self.frames: dict[str, object] = {}     # "frameNo" -> frame
        self.consents: list[dict] = []
        self.polish_backup: dict[str, tuple] = {}
        self.info: dict = {}


TABS: dict = {}


def blocked(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in settings().get("blocked_autofill_domains") or [])


def _cv_path(tab: Tab) -> str | None:
    s = settings()
    country = (tab.job or {}).get("country", "")
    cv = s.get("resume_path") if country in (s.get("use_resume_for_countries") or []) else s.get("cv_path")
    if not Path(cv or "").exists():
        cv = s.get("cv_path") if Path(s.get("cv_path") or "").exists() else s.get("resume_path")
    return cv if cv and Path(cv).exists() else None


def file_kind(field: dict) -> str:
    """'cv', 'cover', 'other' or '' (unknown) - from the label, the input's name/id, then the text around it."""
    own = " ".join(str(field.get(k) or "") for k in ("label", "name", "elid")).lower()
    for text in (own, (field.get("help") or "")[:160].lower()):
        if re.search(r"cover", text):
            return "cover"
        if re.search(r"resume|r\u00e9sum\u00e9|\bcv\b|curriculum", text):
            return "cv"
        if re.search(r"transcript|portfolio|writing sample|certificate|photo|id document|passport|other|additional|supporting", text):
            return "other"
    return ""


def file_for(field: dict, tab: Tab, cv_taken: bool = False) -> str | None:
    k = file_kind(field)
    if k == "cover":
        if tab.oid:
            p = opps.app_dir(tab.oid) / cover_letter_name()
            return str(p) if p.exists() else None
        return None
    if k == "cv" or (k == "" and not cv_taken):
        return _cv_path(tab)
    return None


def _collect(tab: Tab) -> list[dict]:
    """All fields in all frames, ids made unique as '<frame>:<idx>'."""
    out = []
    tab.frames = {}
    for i, fr in enumerate(tab.page.frames):
        try:
            fs = fr.evaluate("() => window.__careeros ? window.__careeros.collect() : []")
        except Exception:  # noqa: BLE001
            continue
        if not fs:
            continue
        tab.frames[str(i)] = fr
        for f in fs:
            f["fid"] = f"{i}:{f['idx']}"
            out.append(f)
    return out


def _apply(tab: Tab, plan: list[dict]) -> int:
    """plan items carry 'fid' + JS fields; combobox/upload handled with real key presses."""
    n = 0
    by_frame: dict[str, list[dict]] = {}
    for p in plan:
        fno, idx = p["fid"].split(":", 1)
        by_frame.setdefault(fno, []).append(dict(p, idx=idx))
    for fno, items in by_frame.items():
        fr = tab.frames.get(fno)
        if not fr:
            continue
        simple = [p for p in items if p["kind"] not in ("combobox", "file")]
        try:
            n += fr.evaluate("plan => window.__careeros.apply(plan)", simple) or 0
        except Exception as e:  # noqa: BLE001
            log(f"    apply failed: {str(e)[:100]}")
        for p in [p for p in items if p["kind"] == "combobox" and p.get("source") not in ("none", "needs")]:
            try:
                loc = fr.locator(f'[data-careeros-idx="{p["idx"]}"]').first
                loc.click(timeout=3000)
                loc.press_sequentially(str(p["value"])[:60], delay=15)
                fr.wait_for_timeout(700)
                loc.press("Enter")
                fr.evaluate("([i,v,s]) => window.__careeros.markFilled(i,v,s)", [p["idx"], p["value"], p["source"]])
                n += 1
            except Exception as e:  # noqa: BLE001
                log(f"    combobox '{str(p['value'])[:30]}' failed: {str(e)[:80]}")
        for p in [p for p in items if p["kind"] == "file"]:
            try:
                fr.locator(f'[data-careeros-idx="{p["idx"]}"]').first.set_input_files(p["path"], timeout=5000)
                fr.evaluate("([i,v,s]) => window.__careeros.markFilled(i,v,s)", [p["idx"], Path(p["path"]).name, "profile"])
                n += 1
            except Exception as e:  # noqa: BLE001
                log(f"    upload failed: {str(e)[:100]}")
    return n


NOT_SELF = answers.NOT_SELF


def _quick_plan(fields: list[dict], tab: Tab) -> tuple[list[dict], dict]:
    """Instant, obvious fills (name, email, phone, links, CV upload). Everything else waits for Claude,
    which also receives these as suggestions."""
    plan, suggestions = [], {}
    files = [f for f in fields if f["kind"] == "file"]
    cv_taken = any(file_kind(f) == "cv" for f in files)  # an explicit CV box exists: unnamed boxes stay empty
    for f in fields:
        k = f["kind"]
        if f.get("filled"):
            continue
        if k == "file":
            if not f.get("value"):
                path = file_for(f, tab, cv_taken)
                if path:
                    plan.append({"fid": f["fid"], "kind": "file", "path": path, "source": "profile"})
                    if file_kind(f) == "":
                        cv_taken = True
            continue
        val, src = answers.match(f, tab.job, tab.prepared)
        if not val:
            continue
        suggestions[f["fid"]] = {"value": val if val != "__DECLINE__" else "Prefer not to say / decline", "from": src}
        obvious = src in ("profile", "learned") and k in ("text", "select", "combobox") and \
            re.search(r"name|e-?mail|phone|mobile|linkedin|github|website|portfolio|city|country|location|post ?code|school|university|degree|discipline|major", f.get("label") or "", re.I) \
            and not answers.JOB_SPECIFIC.search(f.get("label") or "") and not NOT_SELF.search(f.get("label") or "")
        if not obvious or f.get("value") and k != "select":
            continue
        if k in ("select",):
            opt = answers.choose_option(f.get("options") or [], val)
            if opt >= 0 and not (f.get("value") and not re.match(r"^(select|choose|please|--)", f["value"], re.I)):
                plan.append({"fid": f["fid"], "kind": k, "value": f["options"][opt], "option": opt, "source": src})
        else:
            plan.append({"fid": f["fid"], "kind": k, "value": val, "source": src})
    return plan, suggestions


def _job_text(tab: Tab, info: dict) -> str:
    j = tab.job or {}
    if j:
        return f"{j.get('title', '')} at {j.get('org', '')} ({j.get('location', '')})\n{(j.get('description') or '')[:4000]}"
    return f"(Not from the tracker) Page title: {info.get('title', '')} - work it out from the page."


def _page_info(tab: Tab) -> dict:
    page = tab.page
    try:
        info = page.evaluate("() => window.__careeros ? window.__careeros.pageInfo() : {}") or {}
    except Exception:  # noqa: BLE001
        info = {}
    for fr in page.frames:  # text inside embedded forms (e.g. Greenhouse / Airtable iframes)
        if fr != page.main_frame:
            try:
                txt = fr.evaluate("() => document.body ? document.body.innerText.slice(0, 6000) : ''")
                if txt and txt.strip():
                    info["text"] = (info.get("text", "") + "\n\n[embedded form]\n" + txt)[:18000]
            except Exception:  # noqa: BLE001
                pass
    return info


def fill_tab(tab: Tab, pool: ThreadPoolExecutor, manual: bool = False) -> None:
    """manual=True when you press 'Read & fill this page'; automatic runs happen when a page loads."""
    page = tab.page
    if blocked(page.url):
        status(tab, "Autofill is off on this site (account-ban risk).\nOpen the company's own careers page and I'll fill that.")
        return
    if tab.ai_future and not tab.ai_future.done():
        if manual:
            status(tab, "…Claude is still reading this page — one moment…")
        return
    fields = _collect(tab)
    tab.last_fill = time.time()
    use_claude = settings().get("ai_fill_unknown", True) and brain.available()
    if not fields:
        if manual and use_claude:  # no form, but the page may say where/how to apply
            status(tab, "…No form fields here. Claude is reading the page to see how to apply…")
            tab.ai_future = pool.submit(ask_form_agent, tab, [], {}, _page_info(tab))
            tab.ai_done_url = page.url
        else:
            status(tab, "No form here yet.\nClick the site's Apply button (or sign in), then press 'Read & fill this page'.")
        return
    plan, suggestions = _quick_plan(fields, tab)
    n = _apply(tab, plan)
    if tab.oid:
        db.x("UPDATE opportunities SET status='filling', updated_at=? WHERE id=? AND status NOT IN "
             "('submitted','responded','assessment','interviewing','offer','rejected')", (db.now(), tab.oid))
    same_page = tab.ai_done_url and tab.ai_done_url.split("#")[0] == page.url.split("#")[0] and time.time() - tab.ai_done_at < 900
    if use_claude and (manual or not same_page):
        info = _page_info(tab)
        status(tab, f"…Filled {n} obvious field(s). Claude is reading the whole page — instructions, links, consents — and your About me, then it fills the rest…")
        fresh = _collect(tab)
        tab.ai_future = pool.submit(ask_form_agent, tab, fresh, suggestions, info)
        tab.ai_done_url, tab.ai_done_at = page.url, time.time()
    elif use_claude:
        status(tab, f"Filled {n} obvious field(s). Claude already read this page.\nPress 'Read & fill this page' to have it read again (e.g. after new questions appear).")
    else:
        red = [{"fid": f["fid"], "kind": f["kind"], "value": "", "source": "none"} for f in fields
               if not f.get("value") and not f.get("filled") and f["kind"] not in ("file", "checkbox")]
        _apply(tab, red)
        status(tab, f"Filled {n} of {len(fields)} fields.\n{len(red)} red field(s) need you.\n"
                    + ("" if brain.available() else "Connect Claude Code (Settings) so it can read the page and write the rest.\n")
                    + "Check everything, then click the site's Submit yourself.")


def ask_form_agent(tab: Tab, fields: list[dict], suggestions: dict, info: dict) -> dict:
    brain.set_purpose("Form answers", (tab.job or {}).get("org", "") or info.get("title", ""))
    from . import aboutme
    rows = []
    for f in fields:
        if f["kind"] in ("file", "password") or answers.SENSITIVE.search(f.get("label") or ""):
            continue
        rows.append({"id": f["fid"], "type": f["kind"], "label": f.get("label", "")[:300], "help": f.get("help", "")[:300],
                     "options": (f.get("options") or [])[:40], "required": f.get("required"),
                     "current": (f.get("value") or "")[:600], "suggestion": suggestions.get(f["fid"])})
    learned = db.q("SELECT label, value FROM answers ORDER BY uses DESC, updated_at DESC LIMIT 60")
    prep = tab.prepared or {}
    prompt = FORM_PROMPT.format(
        about=brain.me_context()[:26000], history=aboutme.history() or "(none yet)",
        learned="\n".join(f"- {a['label']}: {a['value']}" for a in learned) or "(none yet)",
        job=_job_text(tab, info),
        prepared=("Approved pitch: " + prep.get("pitch", "") + "\nWhy this company: " + prep.get("why_company", "")) if prep else "",
        url=info.get("url", tab.page.url), page=info.get("text", "")[:14000],
        links="\n".join(f"- {l['text']}: {l['href']}" for l in (info.get("links") or [])[:60]),
        fields="\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    data, _ = brain.ask_json(prompt, max_turns=3, timeout=600)
    return data if isinstance(data, dict) else {}


def apply_agent(tab: Tab, data: dict, ctx, pool) -> None:
    from . import aboutme
    fields = {f["fid"]: f for f in _collect(tab)}
    plan, filled, needs = [], 0, 0
    for it in data.get("fields") or []:
        f = fields.get(it.get("id"))
        if not f or f["kind"] == "file":
            continue
        act, val, note = it.get("action"), it.get("value") or "", it.get("note") or ""
        k = f["kind"]
        if act == "skip":
            continue
        if act == "needs_you":
            needs += 1
            if val and k in ("text", "textarea") and not f.get("value"):
                plan.append({"fid": f["fid"], "kind": k, "value": val, "source": "ai", "note": "Suggested draft — please check: " + note})
            else:
                # if we pre-filled it (not you), clear it: Claude decided it isn't ours to answer
                clear = bool(f.get("value")) and f.get("source") not in ("", "none", None) and k in ("text", "textarea")
                plan.append({"fid": f["fid"], "kind": k, "value": "", "source": "needs", "clear": clear, "note": note or "Only you can answer this"})
            continue
        if not val:
            continue
        if f.get("value") and f.get("source") in ("", "none") and k in ("text", "textarea"):
            continue  # you typed it - leave it
        if k in ("select", "radio"):
            opt = answers.choose_option(f.get("options") or [], val)
            if opt < 0:
                continue
            plan.append({"fid": f["fid"], "kind": k, "value": f["options"][opt], "option": opt, "source": "ai", "note": note if len(note) < 140 else ""})
        elif k == "checkbox":
            continue  # checkboxes go through consents
        else:
            plan.append({"fid": f["fid"], "kind": k, "value": val, "source": "ai", "note": note if k == "textarea" else ""})
        filled += 1
    _apply(tab, plan)
    tab.consents = [c for c in (data.get("consents") or []) if c.get("id") in fields]
    opened = []
    for l in (data.get("open_links") or [])[:2]:
        url = (l or {}).get("url", "")
        if not url.startswith("http") or url.split("#")[0] == tab.page.url.split("#")[0]:
            continue
        try:
            pg = ctx.new_page()
            TABS[pg] = Tab(pg, tab.oid, url)
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            opened.append({"url": url, "why": l.get("why", "")})
            log(f"  opened linked form: {url}")
        except Exception as e:  # noqa: BLE001
            log(f"  could not open {url}: {str(e)[:100]}")
    if data.get("questions_for_candidate"):
        aboutme.add_questions(data["questions_for_candidate"][:5])
    tab.info = {"understanding": data.get("understanding", ""), "warnings": data.get("warnings") or [], "opened": opened,
                "consents": len(tab.consents), "consentList": [c.get("what", "") for c in tab.consents][:8],
                "canUndo": bool(tab.polish_backup)}
    info(tab)
    status(tab, f"Claude filled {filled} field(s) after reading the page." + (f"\n{needs} need you (red, with a note)." if needs else "")
           + (f"\n{len(tab.consents)} acknowledgement(s) left for you to confirm." if tab.consents else "")
           + "\nRead the amber answers, change anything, then click the site's Submit yourself.")


def do_consents(tab: Tab) -> None:
    fields = {f["fid"]: f for f in _collect(tab)}
    plan = []
    for c in tab.consents:
        f = fields.get(c.get("id"))
        if not f:
            continue
        v = c.get("value") or "checked"
        if f["kind"] in ("select", "radio"):
            opt = answers.choose_option(f.get("options") or [], v)
            if opt >= 0:
                plan.append({"fid": f["fid"], "kind": f["kind"], "value": f["options"][opt], "option": opt, "source": "profile", "force": True})
        elif f["kind"] == "checkbox":
            plan.append({"fid": f["fid"], "kind": "checkbox", "value": "checked", "source": "profile"})
        elif f["kind"] == "combobox":
            plan.append({"fid": f["fid"], "kind": "combobox", "value": v, "source": "profile"})
    _apply(tab, plan)
    tab.consents = []
    tab.info["consents"] = 0
    tab.info["consentList"] = []
    info(tab)
    status(tab, f"Ticked {len(plan)} acknowledgement(s) you approved. Check them before you submit.")


def ask_polish(tab: Tab, drafts: list[dict]) -> dict:
    brain.set_purpose("Form answers", "polish")
    j = tab.job or {}
    prompt = POLISH_PROMPT.format(about=brain.me_context(short=True)[:14000],
                                  job=f"{j.get('title', '')} at {j.get('org', '')}" if j else tab.page.title(),
                                  drafts="\n".join(json.dumps({"id": d["fid"], "question": d.get("label"), "help": d.get("help", "")[:200],
                                                               "text": d.get("value")}, ensure_ascii=False) for d in drafts))
    data, _ = brain.ask_json(prompt, max_turns=3, timeout=400, fast=True)
    return data if isinstance(data, dict) else {}


def start_polish(tab: Tab, pool) -> None:
    if not brain.available():
        status(tab, "Polishing needs Claude Code - connect it in Settings.")
        return
    drafts = [f for f in _collect(tab) if f["kind"] in ("textarea", "text") and len((f.get("value") or "").strip()) >= 25
              and not answers.SENSITIVE.search(f.get("label") or "")
              and (f.get("source") in ("", "none", None) or (f.get("value") or "") != (f.get("filled") or ""))]
    if not drafts:
        status(tab, "Type your own answer in a text box first (a sentence or two is enough), then press Polish.")
        return
    tab.polish_backup = {d["fid"]: d["value"] for d in drafts}
    status(tab, f"…Claude is polishing {len(drafts)} of your answers…")
    tab.polish_future = pool.submit(ask_polish, tab, drafts)


def finish_polish(tab: Tab, data: dict) -> None:
    n = 0
    for fid, text in data.items():
        if fid in tab.polish_backup and text:
            fno, idx = fid.split(":", 1)
            fr = tab.frames.get(fno)
            if fr and fr.evaluate("([i,v,s,n]) => window.__careeros.setValue(i,v,s,n)", [idx, text, "ai", "Polished from your draft — Undo in the panel"]):
                n += 1
    tab.info["canUndo"] = bool(n)
    info(tab)
    status(tab, f"Polished {n} answer(s). Read them — 'Undo polish' brings back your originals.")


def undo_polish(tab: Tab) -> None:
    for fid, text in tab.polish_backup.items():
        fno, idx = fid.split(":", 1)
        fr = tab.frames.get(fno)
        if fr:
            fr.evaluate("([i,v,s,n]) => window.__careeros.setValue(i,v,s,n)", [idx, text, "none", ""])
    tab.polish_backup = {}
    tab.info["canUndo"] = False
    info(tab)
    status(tab, "Your original answers are back.")


def info(tab: Tab) -> None:
    try:
        tab.page.evaluate("d => window.__careeros && window.__careeros.info(d)", tab.info)
    except Exception:  # noqa: BLE001
        pass


def page_url(pg) -> str:
    try:
        return pg.url
    except Exception:  # noqa: BLE001
        return ""


THANKS = re.compile(r"thank(s| you)[^.]{0,60}(appl|submi|interest)|application (has been |was )?(received|submitted|complete)|"
                    r"we(.ve| have) received your|successfully (submitted|applied)|you(.ve| have) (successfully )?applied", re.I)


def check_submit(tab: Tab) -> None:
    at, url0, fields = tab.pending_submit
    tab.pending_submit = None
    pg = tab.page
    try:
        text = pg.evaluate("() => document.body ? document.body.innerText.slice(0, 20000) : ''")
        errors = 0
        for fr in pg.frames:
            try:
                errors += fr.evaluate("() => window.__careeros ? window.__careeros.errorsShown() : 0") or 0
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        text, errors = "", 0
    accepted = bool(THANKS.search(text or "")) or (page_url(pg).split("#")[0] != url0.split("#")[0] and not errors)
    if not accepted:
        status(tab, ("The site is showing errors, so it wasn't submitted yet - fix the fields it marks and submit again."
                     if errors else "Not marked as submitted yet - I couldn't see a confirmation.\nIf it went through, press 'I submitted it'."))
        return
    r = do_learn(tab, snapshot(tab) or fields, final=True)
    if tab.oid and not tab.submitted:
        tab.submitted = True
        db.set_status(tab.oid, "submitted", "confirmed by the site")
        log(f"  #{tab.oid} submitted by you (site confirmed). Learned {r['saved']}.")
    status(tab, "Submitted - the site confirmed it. Marked in Track.\nYou can close this tab.")


def _focus(tab: Tab, fields: dict) -> str:
    best = None
    for fno, fr in tab.frames.items():
        try:
            lf = fr.evaluate("() => window.__careeros ? window.__careeros.lastFocus() : null")
        except Exception:  # noqa: BLE001
            lf = None
        if lf and (not best or lf["at"] > best[1]["at"]):
            best = (fno, lf)
    if not best:
        return "(none - they haven't clicked into a question)"
    f = fields.get(f"{best[0]}:{best[1]['idx']}")
    if not f:
        return "(unknown)"
    return json.dumps({"id": f["fid"], "label": f.get("label", "")[:300], "help": f.get("help", "")[:300],
                       "options": (f.get("options") or [])[:30], "their text so far": (f.get("value") or "")[:1500]}, ensure_ascii=False)


def ask_chat(tab: Tab, text: str, fields: list[dict], focus: str, info: dict) -> dict:
    from . import aboutme
    brain.set_purpose("Browser chat", (tab.job or {}).get("org", "") or info.get("title", ""))
    rows = [json.dumps({"id": f["fid"], "type": f["kind"], "label": f.get("label", "")[:200], "help": f.get("help", "")[:160],
                        "value": (f.get("value") or "")[:200]}, ensure_ascii=False)
            for f in fields if f["kind"] not in ("password",) and not answers.SENSITIVE.search(f.get("label") or "")]
    same_page = tab.chat_session and tab.chat_url == info.get("url")
    turn = CHAT_TURN.format(url=info.get("url", ""), page="(same page as before)" if same_page else info.get("text", "")[:12000],
                            fields="\n".join(rows[:80]) or "(no form fields)", focus=focus, text=text)
    tools = ["WebSearch", "WebFetch"]
    if tab.chat_session:
        try:
            data, res = brain.ask_json(turn, resume=tab.chat_session, tools=tools, max_turns=8, timeout=400, fast=True)
        except brain.AuthError:
            raise
        except brain.BrainError:
            tab.chat_session = ""   # old conversation gone - start a fresh one below
            return ask_chat(tab, text, fields, focus, info)
    else:
        first = CHAT_FIRST.format(name=(profile().get("preferred_name") or profile().get("first_name") or "the candidate"),
                                  about=brain.me_context()[:22000], history=aboutme.history(4000) or "(none yet)",
                                  job=_job_text(tab, info))
        data, res = brain.ask_json(first + "\n" + turn, tools=tools, max_turns=8, timeout=400, fast=True)
    tab.chat_session, tab.chat_url = res.get("session_id") or tab.chat_session, info.get("url", "")
    return data if isinstance(data, dict) else {"reply": str(data)}


def start_chat(tab: Tab, text: str, pool) -> None:
    if not brain.available():
        tab.page.evaluate("t => window.__careeros.chat(t, [])", "Claude Code isn't installed yet - connect it in Career OS → Settings.")
        return
    fields = _collect(tab)
    byid = {f["fid"]: f for f in fields}
    tab.chat_future = pool.submit(ask_chat, tab, text, fields, _focus(tab, byid), _page_info(tab))


def finish_chat(tab: Tab, data: dict) -> None:
    fields = {f["fid"]: f for f in _collect(tab)}
    fills = [{"id": f["id"], "value": f.get("value", ""), "label": fields[f["id"]].get("label", "")}
             for f in (data.get("fill") or []) if isinstance(f, dict) and f.get("id") in fields and f.get("value")
             and fields[f["id"]]["kind"] in ("text", "textarea", "combobox")]
    tab.page.evaluate("([t, f]) => window.__careeros.chat(t, f)", [data.get("reply") or "(no reply)", fills])  # the reply is the AI's own words


def chat_insert(tab: Tab, fid: str, value: str) -> None:
    if ":" not in fid:
        return
    _collect(tab)   # refresh frame map
    fno, idx = fid.split(":", 1)
    fr = tab.frames.get(fno)
    if fr:
        fr.evaluate("([i,v,s,n]) => window.__careeros.setValue(i,v,s,n)", [idx, value, "ai", "From your chat with Claude — read it before submitting"])


def status(tab: Tab, text: str) -> None:
    text = brain.tr(text)
    try:
        tab.page.evaluate("t => window.__careeros && window.__careeros.status(t)", text)
    except Exception:  # noqa: BLE001
        pass


def snapshot(tab: Tab) -> list[dict]:
    out = []
    for fr in tab.page.frames:
        try:
            out += fr.evaluate("() => window.__careeros ? window.__careeros.snapshot() : []")
        except Exception:  # noqa: BLE001
            pass
    return out


def do_learn(tab: Tab, fields: list[dict], final: bool = False) -> dict:
    res = answers.learn(fields, tab.oid)
    if final:
        try:
            from . import aboutme
            j = tab.job or {}
            aboutme.record_answers(fields, j.get("org", "") or tab.page.url, j.get("title", "") or tab.page.title())
        except Exception:  # noqa: BLE001
            pass
    if res["saved"] or res["corrected"]:
        log(f"  learned {res['saved']} answers, {res['corrected']} corrections (opp {tab.oid})")
        if tab.oid:
            db.event(tab.oid, "learned", f"{res['saved']} answers saved, {res['corrected']} corrections")
    return res


def launch(pw):
    s = settings()
    chan = s.get("browser_channel") or None
    BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
    kw = dict(user_data_dir=str(BROWSER_PROFILE), headless=os.environ.get("CAREEROS_HEADLESS") == "1", no_viewport=True,
              chromium_sandbox=sys.platform == "win32",  # no "--no-sandbox" warning bar on Windows
              ignore_default_args=["--enable-automation"],
              args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    try:
        return pw.chromium.launch_persistent_context(channel=chan, **kw) if chan else pw.chromium.launch_persistent_context(**kw)
    except Exception as e:  # noqa: BLE001
        log(f"Could not start {chan}: {str(e)[:120]} - falling back to bundled Chromium")
        return pw.chromium.launch_persistent_context(**kw)


def main() -> int:
    from playwright.sync_api import Error as PWError, sync_playwright
    inbox: "queue.Queue[tuple]" = queue.Queue()
    tabs = TABS
    pool = ThreadPoolExecutor(max_workers=2)
    db.kv_set("filler_heartbeat", time.time())
    with sync_playwright() as pw:
        ctx = launch(pw)
        ctx.add_init_script(script=INJECT)
        ctx.expose_binding("__careeros_send", lambda source, payload: inbox.put((source.get("page"), payload)))

        def on_page(pg):
            pg.on("load", lambda _p=pg: _mark_refill(_p))
            # a tab opened from an application (e.g. "apply on our partner's form") belongs to the same application
            try:
                op = pg.opener()
            except Exception:  # noqa: BLE001
                op = None
            if pg not in tabs and op is not None and op in tabs:
                tabs[pg] = Tab(pg, tabs[op].oid, pg.url)
        def _mark_refill(pg):
            t = tabs.get(pg)
            if t:
                t.needs_fill = True
        ctx.on("page", on_page)
        for pg in ctx.pages:
            on_page(pg)
        blank = ctx.pages[0] if ctx.pages else None
        log("Autofill browser ready.")
        last_snap = 0.0
        while True:
            db.kv_set("filler_heartbeat", time.time())
            # 1) open newly requested applications
            for req in db.q("SELECT * FROM fill_requests WHERE status='pending' ORDER BY id"):
                db.x("UPDATE fill_requests SET status='opened' WHERE id=?", (req["id"],))
                url = req["url"]
                try:
                    pg = blank if (blank and not blank.is_closed() and blank.url in ("about:blank", "")) else ctx.new_page()
                    blank = None
                    tabs[pg] = Tab(pg, req["opp_id"], url)
                    log(f"Opening #{req['opp_id']}: {url}")
                    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                    tabs[pg].needs_fill = True
                except Exception as e:  # noqa: BLE001
                    log(f"  could not open {url}: {str(e)[:150]}")
            # 2) fill pages that (re)loaded
            for pg, tab in list(tabs.items()):
                if pg.is_closed():
                    if tab.last_snapshot and not tab.submitted:
                        do_learn(tab, tab.last_snapshot)
                    tabs.pop(pg, None)
                    continue
                if tab.needs_fill and time.time() - tab.last_fill > 2:
                    tab.needs_fill = False
                    try:
                        pg.wait_for_timeout(1800)  # let the SPA render
                        fill_tab(tab, pool)
                    except PWError as e:
                        log(f"  fill error: {str(e)[:150]}")
                if tab.ai_future and tab.ai_future.done():
                    fut, tab.ai_future = tab.ai_future, None
                    try:
                        data = fut.result()
                        log(f"  Claude read the page and planned {len(data.get('fields') or [])} fields (#{tab.oid})")
                        apply_agent(tab, data, ctx, pool)
                    except Exception as e:  # noqa: BLE001
                        log(f"  form agent failed: {str(e)[:200]}")
                        if isinstance(e, brain.AuthError):
                            status(tab, "Claude Code isn't signed in (its sign-in expired), so it couldn't read this page.\n"
                                        "In Career OS press 'Sign in' on the red bar, sign in with your subscription, "
                                        "then press 'Read & fill this page' here again.")
                        else:
                            status(tab, f"Claude couldn't finish this page ({str(e)[:90]}).\nFill the rest yourself, or press 'Read & fill this page' to retry.")
                if tab.chat_future and tab.chat_future.done():
                    fut, tab.chat_future = tab.chat_future, None
                    try:
                        finish_chat(tab, fut.result())
                    except brain.AuthError:
                        pg.evaluate("t => window.__careeros.chat(t, [])", brain.tr("I can't answer - Claude Code's sign-in has expired. In Career OS press 'Sign in' on the red bar, sign in, then ask me again."))
                    except Exception as e:  # noqa: BLE001
                        pg.evaluate("t => window.__careeros.chat(t, [])", f"Sorry - that didn't work ({str(e)[:160]}). Try again.")
                if tab.pending_submit and time.time() - tab.pending_submit[0] > 4:
                    check_submit(tab)
                if tab.polish_future and tab.polish_future.done():
                    fut, tab.polish_future = tab.polish_future, None
                    try:
                        finish_polish(tab, fut.result())
                    except Exception as e:  # noqa: BLE001
                        status(tab, f"Couldn't polish ({str(e)[:90]}).")
            # 3) messages from the page panel
            try:
                while True:
                    pg, raw = inbox.get_nowait()
                    tab = tabs.get(pg)
                    if tab is None:
                        tab = tabs[pg] = Tab(pg, None, pg.url)
                    msg = json.loads(raw)
                    t = msg.get("type")
                    if t == "fill":
                        fill_tab(tab, pool, manual=True)
                    elif t == "chat":
                        start_chat(tab, str(msg.get("text") or "")[:4000], pool)
                    elif t == "chat_insert":
                        chat_insert(tab, str(msg.get("id") or ""), str(msg.get("value") or ""))
                    elif t == "polish":
                        start_polish(tab, pool)
                    elif t == "undo_polish":
                        undo_polish(tab)
                    elif t == "consents":
                        do_consents(tab)
                    elif t == "learn":
                        r = do_learn(tab, snapshot(tab))
                        status(tab, f"Saved: {r['saved']} answers learned, {r['corrected']} corrections noted.")
                    elif t == "submit_click":
                        # you clicked the site's submit button - only count it once the site has accepted it
                        tab.pending_submit = (time.time(), page_url(pg), msg.get("fields") or [])
                        status(tab, "…Checking the site accepted your application…")
                    elif t == "submitted":
                        r = do_learn(tab, snapshot(tab) or msg.get("fields") or [], final=True)
                        if tab.oid and not tab.submitted:
                            tab.submitted = True
                            db.set_status(tab.oid, "submitted", "you clicked submit" if t == "submit_click" else "marked in browser")
                            log(f"  #{tab.oid} submitted by you. Learned {r['saved']}.")
                        status(tab, "Marked as submitted in Track. Nice one.\nYou can close this tab.")
            except queue.Empty:
                pass
            # 4) periodic silent snapshot so closing a tab still teaches us
            if time.time() - last_snap > 8:
                last_snap = time.time()
                for pg, tab in list(tabs.items()):
                    if not pg.is_closed():
                        snap = snapshot(tab)
                        if snap:
                            tab.last_snapshot = snap
            # 5) exit when the window is closed
            try:
                live = [p for p in ctx.pages if not p.is_closed()]
            except Exception:  # noqa: BLE001
                live = []
            if not live:
                break
            try:
                live[0].wait_for_timeout(400)
            except PWError:
                break
        for tab in tabs.values():
            if tab.last_snapshot and not tab.submitted:
                do_learn(tab, tab.last_snapshot)
        try:
            ctx.close()
        except Exception:  # noqa: BLE001
            pass
    db.kv_set("filler_heartbeat", 0)
    log("Autofill browser closed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        db.kv_set("filler_heartbeat", 0)
        sys.exit(1)
