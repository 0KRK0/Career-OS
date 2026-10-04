"""Opportunity store: insert/merge found items, re-score, list."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from . import db, scoring
from .config import settings

STATUSES = ["new", "shortlisted", "preparing", "ready", "filling", "submitted",
            "responded", "assessment", "interviewing", "offer", "rejected", "withdrawn", "skipped", "expired"]
ACTIVE_PIPELINE = ["submitted", "responded", "assessment", "interviewing", "offer"]


def uid_for(o: dict) -> str:
    base = o.get("ext_id") or (o.get("url") or o.get("apply_url") or "") or f"{o.get('org')}|{o.get('title')}"
    return hashlib.sha1(base.strip().lower().encode()).hexdigest()[:20]


def upsert(o: dict) -> tuple[int, bool]:
    """Insert or refresh. Returns (id, is_new). Never overwrites user status/notes."""
    o = dict(o)
    o.setdefault("kind", scoring.detect_kind(o.get("title", ""), o.get("description", "")))
    if o.get("kind") in (None, "", "job"):
        o["kind"] = scoring.detect_kind(o.get("title", ""), o.get("description", ""), default=o.get("kind") or "job")
    o.setdefault("country", scoring.detect_country(o.get("location", "")))
    if not o.get("country"):
        o["country"] = scoring.detect_country(o.get("location", ""))
    o["track"] = o.get("track") or scoring.detect_track(o.get("title", ""), o.get("description", ""))
    sc, reasons, sponsorship = scoring.score(o)
    uid = uid_for(o)
    existing = db.q1("SELECT id, status FROM opportunities WHERE uid=?", (uid,))
    fields = {
        "source": o.get("source", ""), "kind": o["kind"], "title": o.get("title", "")[:300],
        "org": o.get("org", "")[:200], "location": o.get("location", "")[:300], "country": o["country"],
        "url": o.get("url", ""), "apply_url": o.get("apply_url") or o.get("url", ""),
        "posted": o.get("posted", ""), "deadline": o.get("deadline") or "", "salary": o.get("salary") or "",
        # keep full text only for plausible matches (keeps the database small)
        "description": (o.get("description") or "")[:(12000 if sc >= 25 else 400)], "track": o["track"], "score": sc,
        "reasons": ", ".join(reasons), "sponsorship": sponsorship, "eligibility": o.get("eligibility", ""),
    }
    if existing:
        sets = ",".join(f"{k}=?" for k in fields) + ",updated_at=?"
        db.x(f"UPDATE opportunities SET {sets} WHERE id=?", (*fields.values(), db.now(), existing["id"]))
        return existing["id"], False
    cols = ",".join(fields) + ",uid,status,created_at,updated_at"
    qs = ",".join("?" * (len(fields) + 4))
    oid = db.x(f"INSERT INTO opportunities({cols}) VALUES({qs})",
               (*fields.values(), uid, "new", db.now(), db.now()))
    return oid, True


def rescore_all() -> int:
    rows = db.q("SELECT * FROM opportunities")
    for r in rows:
        sc, reasons, sp = scoring.score(r)
        db.x("UPDATE opportunities SET score=?, reasons=?, sponsorship=? WHERE id=?", (sc, ", ".join(reasons), sp, r["id"]))
    return len(rows)


def expire_old() -> int:
    """Past deadlines, and board jobs that vanished from their board (not seen by a scout for 4 days)."""
    from datetime import timedelta
    today = date.today().isoformat()
    n = db.x("UPDATE opportunities SET status='expired' WHERE deadline!='' AND deadline < ? "
             "AND status IN ('new','shortlisted','preparing','ready')", (today,))
    cutoff = (datetime.utcnow() - timedelta(days=4)).isoformat()
    n += db.x("UPDATE opportunities SET status='expired' WHERE status='new' AND updated_at < ? AND source IN "
              "('greenhouse','lever','ashby','smartrecruiters','workable','workday','arbeitnow','remotive','himalayas','jobicy','reed') "
              "OR (status='new' AND updated_at < ? AND source LIKE 'adzuna%')", (cutoff, cutoff))
    return n


def get(oid: int) -> dict | None:
    return db.q1("SELECT * FROM opportunities WHERE id=?", (oid,))


def listing(status: str | None = None, kind: str | None = None, country: str | None = None,
            track: str | None = None, qtext: str | None = None, min_score: int = 0,
            limit: int = 300, order: str = "score", posted_days: int = 0, sponsor_only: bool = False,
            offset: int = 0, count: bool = False):
    """kind / country / track accept comma-separated lists. count=True returns just the number."""
    where, params = ["1=1"], []

    def multi(col: str, val: str | None):
        vals = [v for v in (val or "").split(",") if v]
        if vals:
            where.append(f"{col} IN ({','.join('?' * len(vals))})")
            params.extend(vals)
    multi("status", status)
    multi("kind", kind)
    multi("country", country)
    multi("track", track)
    if qtext:
        where.append("(title LIKE ? OR org LIKE ? OR location LIKE ?)")
        params += [f"%{qtext}%"] * 3
    if min_score:
        where.append("score>=?"); params.append(min_score)
    if posted_days:
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=int(posted_days))).isoformat()
        where.append("COALESCE(NULLIF(posted,''), substr(created_at,1,10)) >= ?"); params.append(cutoff)
    if sponsor_only:
        where.append("sponsorship!='no'")  # hide roles that say they won't sponsor
    if count:
        return db.q1(f"SELECT COUNT(*) n FROM opportunities WHERE {' AND '.join(where)}", params)["n"]
    ob = {"score": "score DESC, created_at DESC", "new": "created_at DESC",
          "deadline": "CASE WHEN deadline='' THEN 1 ELSE 0 END, deadline ASC, score DESC",
          "updated": "updated_at DESC"}.get(order, "score DESC")
    rows = db.q(f"SELECT id,uid,source,kind,title,org,location,country,url,apply_url,posted,deadline,salary,"
                f"track,score,reasons,sponsorship,eligibility,status,notes,contact,submitted_at,last_contact_at,"
                f"followup_at,created_at,updated_at FROM opportunities WHERE {' AND '.join(where)} "
                f"ORDER BY {ob} LIMIT ? OFFSET ?", (*params, limit, offset))
    return rows


def facets(min_score: int = 0) -> dict:
    """Counts for the filter panel."""
    base = "FROM opportunities WHERE status IN ('new','shortlisted') AND score>=?"
    return {
        "country": {r["k"]: r["n"] for r in db.q(f"SELECT country k, COUNT(*) n {base} GROUP BY country", (min_score,))},
        "kind": {r["k"]: r["n"] for r in db.q(f"SELECT kind k, COUNT(*) n {base} GROUP BY kind", (min_score,))},
        "track": {r["k"]: r["n"] for r in db.q(f"SELECT track k, COUNT(*) n {base} GROUP BY track", (min_score,))},
    }


def app_dir(oid: int):
    from .config import APPS_DIR
    d = APPS_DIR / str(oid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def prepared(oid: int) -> dict:
    p = app_dir(oid) / "prepared.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def stats() -> dict:
    by_status = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM opportunities GROUP BY status")}
    today = date.today().isoformat()
    return {
        "by_status": by_status,
        "total": sum(by_status.values()),
        "new_today": db.q1("SELECT COUNT(*) n FROM opportunities WHERE substr(created_at,1,10)=? AND score>=?",
                           (today, int(settings().get("min_score") or 55)))["n"],
        "submitted_total": sum(by_status.get(s, 0) for s in ACTIVE_PIPELINE + ["rejected"]),
        "ready": by_status.get("ready", 0),
        "matches": db.q1("SELECT COUNT(*) n FROM opportunities WHERE status IN ('new','shortlisted') AND score>=?",
                         (int(settings().get("min_score") or 40),))["n"],
    }


def days_between(a: str, b: str | None = None) -> int:
    try:
        d1 = datetime.fromisoformat(a[:19].replace("Z", ""))
        d2 = datetime.fromisoformat(b[:19]) if b else datetime.utcnow()
        return (d2 - d1).days
    except (ValueError, TypeError):
        return 0
