"""Import a CV: extract its text locally, then (with Claude Code) turn it into your profile and
a fact sheet (config/career-facts.md) that every cover letter and form answer is checked against."""
from __future__ import annotations

import base64
import re
import zipfile
from pathlib import Path

from . import brain
from .config import CONFIG_DIR, DATA_DIR, profile, save_profile, save_settings, settings

UPLOADS = DATA_DIR / "uploads"

CV_PROMPT = """Here is the text of a CV. Extract the facts - copy them faithfully, never invent or embellish.
Return ONLY JSON:
{{"profile": {{"full_name": "", "first_name": "", "last_name": "", "email": "", "phone": "", "location": "city, country",
   "city": "", "country": "", "linkedin": "full URL or ''", "github": "full URL or ''", "website": "",
   "current_company": "", "current_title": "", "years_experience": "number as text"}},
 "education": [{{"level": "e.g. Master's Degree / Bachelor's Degree", "field": "", "school": "", "start": "YYYY or YYYY-MM", "end": "YYYY or YYYY-MM or 'present'", "grade": ""}}],
 "suggested_roles": ["up to 6 role names this CV fits"],
 "summary": "2-3 factual sentences for recruiters (third person, no adjectives that aren't in the CV)",
 "facts_markdown": "A markdown fact sheet with sections: # Career facts, ## Rules (always: 'Never make up metrics, awards, results, technology or dates.'), ## Contact, ## Experience, ## Education, ## Projects, ## Publications, ## Certifications, ## Awards, ## Skills - every bullet taken from the CV, numbers exactly as written."}}
Newest education first.

=== CV TEXT ===
{text}"""


def extract_text(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        from pypdf import PdfReader
        r = PdfReader(str(path))
        return "\n".join((pg.extract_text() or "") for pg in r.pages)
    if suf == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    return path.read_text(encoding="utf-8", errors="replace")


def _basic(text: str) -> dict:
    """No-Claude fallback: just the obvious fields."""
    p: dict = {}
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        p["email"] = m.group(0)
    m = re.search(r"\+?\d[\d \-()]{8,}\d", text)
    if m:
        p["phone"] = m.group(0).strip()
    m = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-%]+", text)
    if m:
        p["linkedin"] = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
    m = re.search(r"(?:https?://)?github\.com/[\w\-]+", text)
    if m:
        p["github"] = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if 2 <= len(first.split()) <= 5 and not re.search(r"\d|@", first):
        p["full_name"] = first.title() if first.isupper() else first
    return p


def import_cv(filename: str | None = None, data_b64: str | None = None, path: str | None = None,
              text: str | None = None, overwrite: bool = True) -> dict:
    brain.set_purpose("CV import", "")
    src: Path | None = None
    if data_b64:
        from .aboutme import folder
        dest = folder() if folder() and folder().exists() else UPLOADS
        dest.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w.\-]+", "_", filename or "cv.pdf")
        src = dest / name
        src.write_bytes(base64.b64decode(data_b64.split(",")[-1]))
    elif path:
        src = Path(path)
        if not src.exists():
            raise ValueError(f"File not found: {path}")
    if src is not None:
        text = extract_text(src)
        if src.suffix.lower() == ".pdf" and (data_b64 or not settings().get("cv_path")):
            save_settings({"cv_path": str(src.resolve())})
    if not (text or "").strip():
        raise ValueError("Couldn't read any text from that CV. Try a PDF/DOCX, or paste the text.")
    (CONFIG_DIR / "cv.md").write_text(text, encoding="utf-8")
    result: dict = {"used_claude": False}
    if brain.available():
        data, _ = brain.ask_json(CV_PROMPT.format(text=text[:30000]), max_turns=3, timeout=900)
        result.update(data if isinstance(data, dict) else {})
        result["used_claude"] = True
    else:
        result["profile"] = _basic(text)
    cur = profile() if (CONFIG_DIR / "profile.yaml").exists() else {}
    newp = dict(cur)
    for k, v in (result.get("profile") or {}).items():
        if v and (overwrite or not cur.get(k)):
            newp[k] = v
    if result.get("education"):
        newp["education"] = result["education"]
        e0 = result["education"][0]
        newp.update({"school": e0.get("school", ""), "discipline": e0.get("field", ""),
                     "degree": e0.get("level", ""), "grad_year": str(e0.get("end", ""))[:4]})
    if result.get("summary"):
        newp["summary"] = result["summary"]
    if newp.get("full_name") and not newp.get("first_name"):
        parts = newp["full_name"].split()
        newp["first_name"], newp["last_name"] = " ".join(parts[:-1]) or parts[0], parts[-1]
    newp.setdefault("preferred_name", (newp.get("first_name") or "").split(" ")[0])
    save_profile(newp)
    facts = result.get("facts_markdown")
    if facts and (overwrite or not (CONFIG_DIR / "career-facts.md").exists()):
        (CONFIG_DIR / "career-facts.md").write_text(facts, encoding="utf-8")
        from .aboutme import work_dir
        if work_dir():  # a copy lives in the career folder too, so you can see/edit what Claude read
            (work_dir() / "facts-from-cv.md").write_text(facts, encoding="utf-8")
    return {"profile": newp, "suggested_roles": result.get("suggested_roles") or [], "used_claude": result["used_claude"],
            "facts_written": bool(facts)}
