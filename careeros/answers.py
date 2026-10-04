"""The answer bank: how a form field gets its value, and how it learns from you.

Priority: 1) answers you gave/corrected before (learned)  2) your profile rules
3) Claude-drafted (yellow, needs your eye)  4) blank (red, you fill it - then it's learned)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from . import db
from .config import profile

DECLINE = re.compile(r"decline|prefer not|don.?t wish|do not wish|not to (say|answer|disclose|self)|rather not|choose not|not specified|i don.?t want", re.I)
JOB_SPECIFIC = re.compile(r"how did you (hear|find|learn)|where did you (hear|see|find)|referral|cover letter|why (do|would|are|did|us|this|our|the)|motivat|interest(s|ed) you|excite|attract|tell us about|about yourself|introduce yourself|describe|additional information|anything else|what makes you|why should|good fit|message to|summary", re.I)
SENSITIVE = re.compile(r"password|passcode|\bssn\b|social security|national insurance|\bnin?o?\b number|passport (number|no)|card number|\bcvv\b|bank account|sort code|iban|date of birth|\bdob\b", re.I)
# labels asking about SOMEONE ELSE (referee's email, manager's name...) - never answered with your details
NOT_SELF = re.compile(r"refere|reference|referr|recruiter|hiring manager|manager|supervisor|emergency|next of kin|parent|guardian|"
                      r"contact person|friend|colleague|advis|mentor|professor|tutor|who (told|referred|recommended)|employee", re.I)
CONSENT = re.compile(r"\bagree\b|consent|acknowledg|privacy|terms|certify|confirm that|i understand|accurate and complete|declar", re.I)

RULES: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), k) for p, k in [
    (r"preferred (first )?name|nickname|name you go by", "preferred_name"),
    (r"(legal )?first name|given name|forename", "first_name"),
    (r"middle name", "middle_name"),
    (r"last name|surname|family name", "last_name"),
    (r"^(your )?(full |legal )?name$|full name|legal name|^name \(as", "full_name"),
    (r"e-?mail", "email"),
    (r"country code|phone country|dialling code|dial code", "phone_country"),
    (r"phone|mobile|telephone|contact number", "phone"),
    (r"linkedin", "linkedin"),
    (r"github", "github"),
    (r"portfolio|personal (web)?site|^website|website url|blog|other (url|link|website)|personal url", "website"),
    (r"(current|most recent|previous|last|latest) (company|employer)|^company( name)?$|^employer$", "current_company"),
    (r"(current|most recent|latest) (job )?(title|role|position)|^job title$|^title$", "current_title"),
    (r"years of (professional |relevant |industry |work )?experience|how many years", "years_experience"),
    (r"post ?code|zip", "postcode"),
    (r"street|address line|^address$|home address", "address"),
    (r"^location$|current location|where are you (currently )?(based|located)|location \(city\)|^city,? (state|country)|city and country", "location"),
    (r"^city$|city of residence|^town|current city", "city"),
    (r"^country$|country of residence|current country|country (you|where you) (live|reside)|country/region", "country"),
    (r"school|university|college|institution|alma mater", "school"),
    (r"^degree|degree (type|level)|highest (level of )?(education|degree|qualification)|education level|^qualification", "degree"),
    (r"discipline|field of study|major|course of study|area of study", "discipline"),
    (r"graduat\w* (date|year|month)|expected graduation|year of graduation|completion (date|year)|when (do|will) you graduate", "grad_year"),
    (r"(require|need)\w*.{0,60}sponsor|sponsorship|work visa|visa support|visa to work", "requires_sponsorship"),
    (r"how did you (hear|find|learn)|where did you (hear|see|find)|referral source|source of (application|referral)|how you heard", "how_heard"),
    (r"gender|\bsex\b|pronoun", "EEO"),
    (r"\brace\b|ethnic", "EEO"),
    (r"veteran|military|armed forces", "EEO"),
    (r"disabilit", "EEO"),
    (r"sexual orientation|lgbt|transgender|trans\b", "EEO"),
    (r"salary|compensation|pay expectation|expected (base|pay)|desired pay", "salary_expectation"),
    (r"notice period", "notice_period"),
    (r"(earliest|availab).{0,30}start|start date|when can you (start|join)|date available", "earliest_start"),
    (r"cover letter", "COVER"),
    (r"why .{0,40}(us|company|join|interested|apply|role|position|team|firm|here)|motivat|what (excites|interests|attracts) you|why do you want", "WHY"),
    (r"tell us about yourself|introduce yourself|about you\b|good fit|why should we|what makes you", "PITCH"),
]]


def norm_label(label: str) -> str:
    s = (label or "").lower()
    s = re.sub(r"\(required\)|\brequired\b|\(optional\)|\boptional\b|\*", " ", s)
    s = re.sub(r"[^a-z0-9?/ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ?")
    return s[:200]


def _learned() -> list[dict]:
    return db.q("SELECT key,label,value,source FROM answers")


TICK_VALUES = {"checked", "unchecked", "true", "false", "on", "off", "yes", "no"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def plausible(label: str, kind: str, value: str) -> bool:
    """Reject answers that can't be right for this box (e.g. 'checked' in an Email field)."""
    v = (value or "").strip()
    if not v:
        return False
    if kind != "checkbox" and v.lower() in ("checked", "unchecked", "true", "false", "on", "off"):
        return False
    l = (label or "").lower()
    if re.search(r"e-?mail", l) and kind in ("text", "") and not re.search(r"refere|reference|manager", l):
        return bool(EMAIL.match(v))
    if re.search(r"phone|mobile|telephone", l) and kind in ("text", ""):
        return len(re.sub(r"\D", "", v)) >= 6
    if re.search(r"linkedin|github|website|portfolio|url", l) and kind in ("text", ""):
        return "." in v and " " not in v
    return True


def learned_lookup(label: str, kind: str = "") -> dict | None:
    key = norm_label(label)
    if kind == "checkbox":
        key = "[tick] " + key
    if not key:
        return None
    r = db.q1("SELECT * FROM answers WHERE key=?", (key,))
    if r:
        return r
    best, best_s = None, 0.0
    for a in _learned():
        if a["key"].startswith("[tick] ") != key.startswith("[tick] "):
            continue
        if abs(len(a["key"]) - len(key)) > max(12, len(key) * 0.3):
            continue
        s = SequenceMatcher(None, a["key"], key).ratio()
        if s > best_s:
            best, best_s = a, s
    return best if best_s >= 0.88 else None


def profile_value(k: str, job: dict | None, prepared: dict | None) -> str:
    p = profile()
    ans = p.get("answers") or {}
    kind = (job or {}).get("kind", "job")
    if k == "earliest_start":
        return ans.get("earliest_start_internship" if kind == "internship" else "earliest_start_fulltime", "")
    if k in ("salary_expectation", "notice_period", "how_heard"):
        return ans.get(k, "")
    if k == "COVER":
        return (prepared or {}).get("cover_letter", "")
    if k == "WHY":
        return (prepared or {}).get("why_company", "")
    if k == "PITCH":
        return (prepared or {}).get("pitch", "")
    v = p.get(k, "")
    return "" if v is None else str(v)


def match(field: dict, job: dict | None = None, prepared: dict | None = None) -> tuple[str, str]:
    """Return (value, source) for a collected field. source: learned|profile|decline|ai|none."""
    label = field.get("label") or ""
    kind = field.get("kind")
    if SENSITIVE.search(label) or kind in ("password",):
        return "", "none"
    if NOT_SELF.search(label) and not re.search(r"how did you|where did you|referral source", label, re.I):
        la = learned_lookup(label, kind)   # only an answer you typed for this exact question
        return (la["value"], "learned") if la and la["key"] == norm_label(label) else ("", "none")
    if kind == "checkbox":
        la = learned_lookup(label, "checkbox")
        if la and not CONSENT.search(label):
            return la["value"], "learned"
        return "", "none"  # consent boxes are yours to tick
    if not JOB_SPECIFIC.search(label):
        la = learned_lookup(label, kind)
        if la and plausible(label, kind, la["value"]):
            return la["value"], "learned"
    for rx, key in RULES:
        if rx.search(label):
            if key == "EEO":
                return "__DECLINE__", "decline"
            v = profile_value(key, job, prepared)
            if v and plausible(label, kind, v):
                return v, ("ai" if key in ("COVER", "WHY", "PITCH") else "profile")
            return "", "none"
    if JOB_SPECIFIC.search(label):
        la = None
    return "", "none"


def choose_option(options: list[str], value: str) -> int:
    """Pick the best option index for a value; -1 if nothing fits."""
    if not options:
        return -1
    opts = [(i, (o or "").strip()) for i, o in enumerate(options)]
    real = [(i, o) for i, o in opts if o and not re.match(r"^(select|choose|please select|--|—|-)\b", o, re.I)]
    if value == "__DECLINE__":
        for i, o in real:
            if DECLINE.search(o):
                return i
        return -1
    v = (value or "").strip().lower()
    if not v:
        return -1
    for i, o in real:
        if o.lower() == v:
            return i
    yn = {"yes": r"^(yes|y)\b", "no": r"^(no|n)\b"}
    if v in yn:
        for i, o in real:
            if re.match(yn[v], o, re.I):
                return i
    for i, o in real:
        if o.lower().startswith(v) or v.startswith(o.lower()):
            return i
    for i, o in real:
        if v in o.lower() or (len(o) > 3 and o.lower() in v):
            return i
    best, best_s = -1, 0.0
    for i, o in real:
        s = SequenceMatcher(None, o.lower(), v).ratio()
        if s > best_s:
            best, best_s = i, s
    return best if best_s >= 0.6 else -1


def learn(fields: list[dict], opp_id: int | None) -> dict:
    """Learn from a snapshot of the form as you left it. Returns counts."""
    saved = corrected = 0
    for f in fields:
        label = (f.get("label") or "").strip()
        kind = f.get("kind")
        final = (f.get("value") or "").strip()
        filled = (f.get("filled") or "").strip()
        src = f.get("source") or "none"
        if not label or kind in ("file", "password") or SENSITIVE.search(label):
            continue
        if not final or final.lower() in ("select...", "select", "choose", "please select"):
            continue
        if kind == "checkbox" and CONSENT.search(label):
            continue
        changed = final != filled
        if changed and filled:
            db.x("INSERT INTO corrections(opp_id,label,filled,final,fill_source,created_at) VALUES(?,?,?,?,?,?)",
                 (opp_id, label[:300], filled[:2000], final[:2000], src, db.now()))
            corrected += 1
        if JOB_SPECIFIC.search(label) or len(final) > 1500:
            continue
        if changed or src in ("ai", "none"):
            key = norm_label(label)
            if not key or not plausible(label, kind, final):
                continue
            if kind == "checkbox":
                key = "[tick] " + key
            source = "you" if changed or src == "none" else "ai-accepted"
            db.x("INSERT INTO answers(key,label,value,source,uses,updated_at) VALUES(?,?,?,?,1,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value, label=excluded.label, "
                 "source=excluded.source, uses=answers.uses+1, updated_at=excluded.updated_at",
                 (key, label[:300], final, source, db.now()))
            saved += 1
    return {"saved": saved, "corrected": corrected}
