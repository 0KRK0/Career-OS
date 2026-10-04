"""Prepare an application: fit check + tailored cover letter (+ PDF) + short pitch.
Uses Claude Code (your Pro plan). Falls back to a plain template without it."""
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from . import brain, db, opps
from .config import cover_letter_name, profile, settings

PREPARE_PROMPT = """You are preparing a job/fellowship application for the candidate below.
Follow any RULES in the candidate's fact sheet exactly. Always: never invent metrics, awards,
results, dates or technology; plain first person in the candidate's own voice; British English
for UK/EU/India roles, American English for US roles.

=== CANDIDATE FACTS (the only source of truth) ===
{facts}

=== OPPORTUNITY ===
Title: {title}
Organisation: {org}
Location: {location} (country code {country})
Kind: {kind}
URL: {url}
Description:
{description}

=== TASK ===
Today is {today}. Return ONLY a JSON object with these keys:
{{
 "fit_score": 0-100 integer (honest: how competitive is he for THIS role),
 "fit_reasons": [up to 4 short strings],
 "gaps": [up to 4 short strings - what he lacks, be frank],
 "eligibility_flags": [strings: e.g. "no visa sponsorship", "requires PhD", "requires US citizenship", "must be available full-time during term", "deadline passed"; empty if none],
 "cover_letter": "220-320 words, no placeholders, no address block, starts 'Dear Hiring Team,' (or the named programme team), ends 'Yours sincerely,\\n{name}' (UK) or 'Sincerely,\\n{name}' (US). Pick the 2-3 most relevant proofs for this role.",
 "pitch": "2-3 sentence answer to 'Why are you a good fit?' in his voice",
 "why_company": "2-3 sentences for 'Why do you want to work here?' - only use facts stated in the description; no flattery",
 "keywords": [8-12 keywords from the description he genuinely matches]
}}"""


def _letter_html(text: str, p: dict) -> str:
    paras = "".join(f"<p>{html.escape(x).replace(chr(10), '<br>')}</p>" for x in text.split("\n\n"))
    contact = " · ".join(x for x in [p.get("location"), p.get("phone"), p.get("email"), p.get("linkedin")] if x)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 22mm 22mm 20mm 22mm; }}
body {{ font-family: 'Calibri','Segoe UI',Arial,sans-serif; font-size: 11pt; line-height: 1.45; color: #111; }}
h1 {{ font-size: 16pt; letter-spacing: .08em; margin: 0 0 2mm 0; }}
.c {{ font-size: 9.5pt; color: #444; margin-bottom: 9mm; border-bottom: 1px solid #bbb; padding-bottom: 3mm; }}
.d {{ margin-bottom: 6mm; color: #333; }} p {{ margin: 0 0 3.2mm 0; }}
</style></head><body><h1>{html.escape(p.get('full_name', '').upper())}</h1>
<div class="c">{html.escape(contact)}</div><div class="d">{date.today().strftime('%d %B %Y')}</div>{paras}</body></html>"""


def render_pdf(html_str: str, out: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    chan = settings().get("browser_channel") or None
    try:
        with sync_playwright() as pw:
            try:
                b = pw.chromium.launch(channel=chan, headless=True) if chan else pw.chromium.launch(headless=True)
            except Exception:  # noqa: BLE001
                b = pw.chromium.launch(headless=True)
            pg = b.new_page()
            pg.set_content(html_str, wait_until="load")
            pg.pdf(path=str(out), format="A4", print_background=True)
            b.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _template(o: dict, p: dict) -> dict:
    us = o.get("country") == "US"
    close = "Sincerely," if us else "Yours sincerely,"
    edu = (p.get("education") or [{}])[0] if p.get("education") else {}
    lines = [f"Dear Hiring Team,\n\nI am applying for the {o['title']} role at {o['org']}."]
    if p.get("current_title") and p.get("current_company"):
        lines.append(f"I have {p.get('years_experience', 'several')} years' experience, most recently as "
                     f"{p['current_title']} at {p['current_company']}.")
    deg = edu.get("field") or p.get("discipline")
    school = edu.get("school") or p.get("school")
    if deg and school:
        lines.append(f"I am studying/have studied {deg} at {school}.")
    letter = " ".join(lines) + (f"\n\nI would welcome the chance to discuss how I could contribute to {o['org']}."
                                f"\n\n{close}\n{p.get('full_name', '')}")
    return {"fit_score": None, "fit_reasons": [], "gaps": [], "eligibility_flags": [],
            "cover_letter": letter, "pitch": "", "why_company": "", "keywords": [], "template": True}


def prepare(oid: int, log=print) -> dict:
    brain.set_purpose("Cover letters", "")
    o = opps.get(oid)
    if not o:
        raise ValueError("no such opportunity")
    p = profile()
    db.set_status(oid, "preparing")
    try:
        if brain.available():
            prompt = PREPARE_PROMPT.format(
                name=p.get("full_name", "the candidate"), facts=brain.me_context(), title=o["title"], org=o["org"], location=o["location"],
                country=o["country"], kind=o["kind"], url=o["url"],
                description=(o.get("description") or "(no description available - infer only from title)")[:9000],
                today=date.today().isoformat())
            data, _ = brain.ask_json(prompt, max_turns=3, timeout=600, log=log)
        else:
            log("  Claude Code not found - using the plain template letter")
            data = _template(o, p)
    except Exception as e:  # noqa: BLE001
        log(f"  prepare failed: {e}")
        db.set_status(oid, "shortlisted", f"prepare failed: {str(e)[:200]}")
        raise
    d = opps.app_dir(oid)
    (d / "prepared.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    letter = data.get("cover_letter") or ""
    (d / "cover_letter.txt").write_text(letter, encoding="utf-8")
    pdf_ok = render_pdf(_letter_html(letter, p), d / cover_letter_name())
    flags = data.get("eligibility_flags") or []
    fit = data.get("fit_score")
    if isinstance(fit, (int, float)):
        # blend Claude's honest fit with the rule score
        new = int(round(0.6 * fit + 0.4 * (o.get("score") or 0)))
        db.x("UPDATE opportunities SET score=?, eligibility=? WHERE id=?", (new, "; ".join(flags), oid))
    else:
        db.x("UPDATE opportunities SET eligibility=? WHERE id=?", ("; ".join(flags), oid))
    db.set_status(oid, "ready", "cover letter drafted" + ("" if pdf_ok else " (PDF render failed)"))
    return data
