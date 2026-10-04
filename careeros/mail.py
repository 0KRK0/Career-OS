"""Gmail tracking over IMAP (free; uses a Google 'app password', read-only except for
saving follow-up DRAFTS - it never sends anything).

- Matches recruiter/ATS emails to your applications and moves them along Track:
  received -> submitted, assessment, interviewing, offer, rejected.
- Applications you made elsewhere (LinkedIn Easy Apply, etc.) are added to Track
  automatically from their 'thanks for applying' emails.
- If you've heard nothing after N days, drafts a polite follow-up in your Gmail Drafts."""
from __future__ import annotations

import email
import imaplib
import re
import time
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime

from . import db, opps
from .notify import notify
from .config import profile, settings
from .sources import strip_html

CATS = [
    ("offer", re.compile(r"offer (letter|of employment)|pleased to (extend|offer)|(like|happy|delighted) to offer you|congratulations[^.]{0,80}offer", re.I)),
    ("rejected", re.compile(r"unfortunately|not (be )?(moving|progressing|proceeding) (forward|further)|decided to (move|proceed|go) (forward )?with other|not been successful|won.?t be (moving|progressing)|regret to inform|position has been filled|not (been )?selected|other candidates whose|will not be taking your application", re.I)),
    ("assessment", re.compile(r"assessment|coding (test|challenge|exercise)|hackerrank|codility|codesignal|hirevue|online test|take[- ]home|numerical reasoning|pymetrics|game-based", re.I)),
    ("interviewing", re.compile(r"\binterview|schedule (a |some )?(call|chat|time)|your availability|speak with you|next (step|stage|round)s?\b|phone screen|invite you to|book a (slot|time)|calendly", re.I)),
    ("received", re.compile(r"(thank you|thanks) for (your )?(applying|application|interest)|application (has been )?(received|submitted|confirmation)|we.?ve received your application|we have received your application|successfully (applied|submitted)", re.I)),
]
ATS_SENDERS = re.compile(r"greenhouse|lever\.co|myworkday|workday|ashbyhq|smartrecruiters|workable|icims|successfactors|taleo|jobvite|teamtailor|recruitee|bamboohr|personio|oraclecloud|avature|eightfold|linkedin|indeed|hackerrank|codility|hirevue", re.I)
NOREPLY = re.compile(r"no-?reply|donotreply|do-not-reply|notifications?@|mailer|jobs-noreply|talent@|careers@|recruiting@", re.I)
STAGE = {"submitted": 1, "responded": 2, "assessment": 3, "interviewing": 4, "offer": 5, "rejected": 6}


def _dec(s) -> str:
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:  # noqa: BLE001
        return s or ""


def _body(msg) -> str:
    text = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not text:
                try:
                    text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:  # noqa: BLE001
                    pass
        if not text:
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        text = strip_html(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace"))
                        break
                    except Exception:  # noqa: BLE001
                        pass
    else:
        try:
            raw = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
            text = strip_html(raw) if msg.get_content_type() == "text/html" else raw
        except Exception:  # noqa: BLE001
            text = ""
    return re.sub(r"\s+", " ", text)[:4000]


def _org_key(org: str) -> str:
    o = re.sub(r"\b(inc|ltd|llc|plc|limited|group|holdings|technologies|technology|capital|corp|corporation|co|gmbh|ag|the)\b\.?", " ", (org or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", o).strip()


def classify(subject: str, body: str) -> str:
    text = f"{subject}\n{body[:2500]}"
    for cat, rx in CATS:
        if rx.search(text):
            return cat
    return ""


def match_opp(sender_name: str, sender_addr: str, subject: str, body: str) -> dict | None:
    cands = db.q("SELECT id, org, title, status FROM opportunities WHERE status IN "
                 "('ready','filling','submitted','responded','assessment','interviewing','offer') ORDER BY updated_at DESC")
    dom = sender_addr.split("@")[-1].lower() if "@" in sender_addr else ""
    hay = f"{sender_name} {dom} {subject} {body[:1500]}".lower()
    best, best_len = None, 0
    for c in cands:
        k = _org_key(c["org"])
        if len(k) < 3:
            continue
        compact = k.replace(" ", "")
        if k in hay or (len(compact) >= 4 and compact in dom.replace("-", "")):
            if len(k) > best_len:
                best, best_len = c, len(k)
    return best


def _connect():
    e = settings()["email"]
    M = imaplib.IMAP4_SSL(e["imap_host"])
    M.login(e["address"], e["app_password"].replace(" ", ""))
    return M


def check(log=print) -> dict:
    e = settings()["email"]
    if not (e.get("enabled") and e.get("address") and e.get("app_password")):
        return {"skipped": "email not configured"}
    M = _connect()
    gmail = "gmail" in e["imap_host"]
    M.select('"[Gmail]/All Mail"' if gmail else "INBOX", readonly=True)
    days = int(e.get("lookback_days") or 45)
    if gmail:
        raw = (f'newer_than:{days}d (application OR applying OR interview OR candidate OR assessment OR offer '
               'OR unfortunately OR recruiting OR recruiter OR "next steps" OR hackerrank OR codility) -category:promotions')
        typ, data = M.search(None, "X-GM-RAW", f'"{raw}"')
    else:
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, "SINCE", since)
    ids = (data[0] or b"").split()[-600:]
    stats = {"scanned": 0, "matched": 0, "updated": 0, "new_tracked": 0}
    for i in range(0, len(ids), 50):
        batch = b",".join(ids[i:i + 50])
        typ, hdrs = M.fetch(batch, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
        for part in hdrs:
            if not isinstance(part, tuple):
                continue
            num = part[0].split()[0]
            h = email.message_from_bytes(part[1])
            mid = (h.get("Message-ID") or f"{num.decode()}-{h.get('Date')}").strip()
            if db.q1("SELECT 1 FROM emails WHERE msg_id=?", (mid,)):
                continue
            stats["scanned"] += 1
            name, addr = parseaddr(_dec(h.get("From")))
            subject = _dec(h.get("Subject"))
            try:
                when = parsedate_to_datetime(h.get("Date")).astimezone(timezone.utc).replace(microsecond=0).isoformat()
            except Exception:  # noqa: BLE001
                when = db.now()
            opp = match_opp(name, addr, subject, "")
            relevant = opp or ATS_SENDERS.search(addr) or CATS[-1][1].search(subject) or re.search(r"application|interview|candidate", subject, re.I)
            body = ""
            if relevant:
                typ, full = M.fetch(num, "(BODY.PEEK[])")
                msg = email.message_from_bytes(full[0][1]) if full and isinstance(full[0], tuple) else None
                body = _body(msg) if msg else ""
                opp = opp or match_opp(name, addr, subject, body)
            cat = classify(subject, body) if relevant else ""
            db.x("INSERT OR IGNORE INTO emails(msg_id,opp_id,sender,subject,received_at,category,snippet,created_at) VALUES(?,?,?,?,?,?,?,?)",
                 (mid, opp["id"] if opp else None, f"{name} <{addr}>", subject[:300], when, cat, body[:400], db.now()))
            if not relevant:
                continue
            if opp:
                stats["matched"] += 1
                _apply(opp, cat, name, addr, subject, when, log)
                stats["updated"] += 1 if cat else 0
            elif cat == "received":
                # applied somewhere else (LinkedIn etc.) -> track it automatically
                org = name.split(" via ")[0].replace("Careers", "").replace("Recruiting", "").replace("Talent", "").strip() or addr.split("@")[-1]
                title = re.sub(r"(?i)thank(s| you) for (your )?(applying|application|interest)( to| in| for)?", "", subject).strip(" :-|") or "Application"
                oid, new = opps.upsert({"source": "email", "ext_id": f"mail:{mid}", "org": org[:80], "title": title[:200],
                                        "location": "", "url": "", "kind": "job"})
                if new:
                    db.x("UPDATE opportunities SET status='submitted', submitted_at=?, last_contact_at=? WHERE id=?", (when, when, oid))
                    db.event(oid, "email", f"auto-tracked from email: {subject[:200]}")
                    stats["new_tracked"] += 1
    M.logout()
    fu = followups(log)
    stats["followups"] = fu
    db.kv_set("email_last_check", db.now())
    log(f"  email: {stats}")
    return stats


def _apply(opp: dict, cat: str, name: str, addr: str, subject: str, when: str, log) -> None:
    oid = opp["id"]
    db.x("UPDATE opportunities SET last_contact_at=? WHERE id=?", (when, oid))
    if addr and not NOREPLY.search(addr) and not ATS_SENDERS.search(addr):
        db.x("UPDATE opportunities SET contact=? WHERE id=? AND (contact IS NULL OR contact='')", (f"{name} <{addr}>", oid))
    db.event(oid, "email", f"[{cat or 'email'}] {subject[:200]}")
    cur = opp["status"]
    target = {"received": "submitted", "assessment": "assessment", "interviewing": "interviewing",
              "offer": "offer", "rejected": "rejected"}.get(cat)
    if not target:
        if cur == "submitted":
            db.set_status(oid, "responded", subject[:120])
        return
    if target == "submitted" and cur in ("ready", "filling"):
        db.set_status(oid, "submitted", "confirmation email")
    elif target != "submitted" and STAGE.get(target, 0) >= STAGE.get(cur, 0):
        db.set_status(oid, target, subject[:120])
        if target in ("interviewing", "assessment", "offer"):
            notify(f"mail:{oid}:{target}", f"{opp['org']}: {target}!", subject[:180], "#track")


FOLLOWUP = """Subject: Following up on my application - {title}

Dear {greet},

I applied for the {title} role at {org} on {applied} and wanted to follow up briefly. I remain very interested in the role and believe my experience is closely relevant to it.

I would be grateful for any update on the timeline, and I'm happy to share anything else that would help.

{sign}
{name}
{contact}"""


def followups(log=print) -> int:
    e = settings()["email"]
    days = int(e.get("followup_after_days") or 14)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.q("SELECT * FROM opportunities WHERE status='submitted' AND submitted_at IS NOT NULL AND submitted_at < ? "
                "AND (followup_at IS NULL OR followup_at='') AND (last_contact_at IS NULL OR last_contact_at < ?)",
                (cutoff, cutoff))
    p = profile()
    n = 0
    for o in rows:
        greet = "Hiring Team"
        to = ""
        if o.get("contact"):
            nm, to = parseaddr(o["contact"])
            greet = nm.split()[0] if nm else greet
        text = FOLLOWUP.format(title=o["title"], org=o["org"], applied=(o["submitted_at"] or "")[:10], greet=greet,
                               sign="Sincerely," if o.get("country") == "US" else "Kind regards,",
                               contact=f"{p.get('phone', '')} · {p.get('linkedin', '')}", name=p.get('full_name', ''))
        d = opps.app_dir(o["id"])
        (d / "followup.txt").write_text(text, encoding="utf-8")
        if e.get("create_drafts"):
            try:
                _save_draft(to, text)
            except Exception as ex:  # noqa: BLE001
                log(f"  draft save failed: {ex}")
        db.x("UPDATE opportunities SET followup_at=? WHERE id=?", (db.now(), o["id"]))
        db.event(o["id"], "followup", "follow-up drafted" + (f" to {to}" if to else " (no recruiter address yet)"))
        n += 1
    if n:
        notify(f"followups:{db.now()[:10]}", f"{n} follow-up email(s) drafted",
               "No reply after " + str(days) + " days. Check Gmail Drafts / Track, edit and send.", "#track")
    return n


def _save_draft(to: str, text: str) -> None:
    e = settings()["email"]
    subj, _, body = text.partition("\n\n")
    msg = EmailMessage()
    msg["From"] = e["address"]
    if to:
        msg["To"] = to
    msg["Subject"] = subj.replace("Subject:", "").strip()
    msg.set_content(body)
    M = _connect()
    box = '"[Gmail]/Drafts"' if "gmail" in e["imap_host"] else "Drafts"
    M.append(box, "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    M.logout()


def test_login() -> str:
    M = _connect()
    M.logout()
    return "ok"
