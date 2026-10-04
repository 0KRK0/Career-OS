"""Job sources. All of these are public, documented (or public-JSON) job feeds that
allow automated reading. No LinkedIn/Indeed scraping - those ban accounts."""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from typing import Callable, Iterable

import httpx

from . import db

UA = {"User-Agent": "career-os/0.1 (personal job search tool; local)", "Accept": "application/json"}
TIMEOUT = httpx.Timeout(25.0, connect=10.0)


def _client() -> httpx.Client:
    return httpx.Client(headers=UA, timeout=TIMEOUT, follow_redirects=True)


def strip_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def _iso(v) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)):
        ts = v / 1000 if v > 10_000_000_000 else v
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    return str(v)[:10]


# ---------- ATS boards (per company) ----------

def greenhouse(slug: str, org: str, c: httpx.Client) -> list[dict]:
    r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "source": "greenhouse", "ext_id": f"gh:{slug}:{j['id']}", "org": org,
            "title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url") or f"https://job-boards.greenhouse.io/{slug}/jobs/{j['id']}",
            "apply_url": f"https://job-boards.greenhouse.io/{slug}/jobs/{j['id']}",
            "posted": _iso(j.get("first_published") or j.get("updated_at")),
            "description": strip_html(j.get("content", ""))[:15000],
        })
    return out


def lever(slug: str, org: str, c: httpx.Client) -> list[dict]:
    data = None
    for host in ("api.lever.co", "api.eu.lever.co"):
        r = c.get(f"https://{host}/v0/postings/{slug}", params={"mode": "json"})
        if r.status_code == 200 and isinstance(r.json(), list) and r.json():
            data = r.json()
            break
        if r.status_code == 200 and isinstance(r.json(), list):
            data = data or []
    if data is None:
        raise httpx.HTTPStatusError("lever board not found", request=r.request, response=r)
    out = []
    for j in data:
        cat = j.get("categories") or {}
        loc = cat.get("location") or ", ".join(cat.get("allLocations") or [])
        out.append({
            "source": "lever", "ext_id": f"lv:{slug}:{j['id']}", "org": org,
            "title": j.get("text", ""), "location": loc or "",
            "url": j.get("hostedUrl", ""), "apply_url": j.get("applyUrl") or (j.get("hostedUrl", "") + "/apply"),
            "posted": _iso(j.get("createdAt")),
            "description": (j.get("descriptionPlain") or strip_html(j.get("description", ""))
                            + "\n" + "\n".join(strip_html(x.get("content", "")) for x in j.get("lists", [])))[:15000],
        })
    return out


def ashby(slug: str, org: str, c: httpx.Client) -> list[dict]:
    r = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        locs = [j.get("location") or ""] + [x.get("location", "") for x in (j.get("secondaryLocations") or [])]
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append({
            "source": "ashby", "ext_id": f"ab:{slug}:{j.get('id')}", "org": org,
            "title": j.get("title", ""), "location": ", ".join([l for l in locs if l]) + (" (Remote)" if j.get("isRemote") else ""),
            "url": j.get("jobUrl", ""), "apply_url": j.get("applyUrl") or (j.get("jobUrl", "") + "/application"),
            "posted": _iso(j.get("publishedAt")), "salary": comp,
            "description": (j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", "")))[:15000],
        })
    return out


def smartrecruiters(slug: str, org: str, c: httpx.Client) -> list[dict]:
    out, offset = [], 0
    while offset < 500:
        r = c.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100, "offset": offset})
        r.raise_for_status()
        d = r.json()
        for j in d.get("content", []):
            loc = j.get("location") or {}
            out.append({
                "source": "smartrecruiters", "ext_id": f"sr:{slug}:{j['id']}", "org": org,
                "title": j.get("name", ""),
                "location": ", ".join(x for x in [loc.get("city"), loc.get("country")] if x) + (" (Remote)" if loc.get("remote") else ""),
                "url": f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                "apply_url": f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                "posted": _iso(j.get("releasedDate")), "description": "",
            })
        offset += 100
        if offset >= d.get("totalFound", 0):
            break
    return out


def workable(slug: str, org: str, c: httpx.Client) -> list[dict]:
    r = c.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append({
            "source": "workable", "ext_id": f"wk:{slug}:{j.get('shortcode')}", "org": org,
            "title": j.get("title", ""),
            "location": ", ".join(x for x in [j.get("city"), j.get("country")] if x) + (" (Remote)" if j.get("telecommuting") else ""),
            "url": j.get("url") or j.get("shortlink", ""), "apply_url": j.get("application_url") or j.get("url", ""),
            "posted": _iso(j.get("published_on")), "description": strip_html(j.get("description", ""))[:15000],
        })
    return out


def workday(cfg: dict, org: str, c: httpx.Client) -> list[dict]:
    host, tenant, site = cfg["host"], cfg["tenant"], cfg["site"]
    queries = cfg.get("queries") or ["graduate", "intern", "software engineer", "machine learning", "salesforce"]
    out, seen = [], set()
    for qtext in queries:
        for offset in (0, 20, 40):
            r = c.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                       json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": qtext},
                       headers={**UA, "Content-Type": "application/json"})
            r.raise_for_status()
            posts = r.json().get("jobPostings", [])
            for j in posts:
                path = j.get("externalPath", "")
                if not path or path in seen:
                    continue
                seen.add(path)
                out.append({
                    "source": "workday", "ext_id": f"wd:{tenant}:{path}", "org": org,
                    "title": j.get("title", ""), "location": j.get("locationsText", ""),
                    "url": f"https://{host}/en-US/{site}{path}", "apply_url": f"https://{host}/en-US/{site}{path}/apply",
                    "posted": "", "description": "",
                })
            if len(posts) < 20:
                break
            time.sleep(0.3)
    return out


ATS: dict[str, Callable] = {
    "greenhouse": greenhouse, "lever": lever, "ashby": ashby,
    "smartrecruiters": smartrecruiters, "workable": workable,
}


def fetch_company(comp: dict, c: httpx.Client, log: Callable[[str], None]) -> list[dict]:
    """Try each candidate slug until one works; remember the working one."""
    name, ats = comp["name"], comp["ats"]
    key = f"{ats}:{name}"
    if ats == "workday":
        try:
            jobs = workday(comp, name, c)
            db.x("INSERT OR REPLACE INTO source_health(key,ok,working_slug,detail,checked_at) VALUES(?,?,?,?,?)",
                 (key, 1, comp.get("tenant"), f"{len(jobs)} jobs", db.now()))
            return jobs
        except Exception as e:  # noqa: BLE001
            db.x("INSERT OR REPLACE INTO source_health(key,ok,working_slug,detail,checked_at) VALUES(?,?,?,?,?)",
                 (key, 0, "", str(e)[:200], db.now()))
            log(f"  x {name} (workday): {str(e)[:120]}")
            return []
    slugs = comp.get("slugs") or [comp.get("slug")]
    health = db.q1("SELECT working_slug FROM source_health WHERE key=? AND ok=1", (key,))
    if health and health["working_slug"] in slugs:
        slugs = [health["working_slug"]] + [s for s in slugs if s != health["working_slug"]]
    last_err = ""
    for slug in slugs:
        if not slug:
            continue
        try:
            jobs = ATS[ats](slug, name, c)
            db.x("INSERT OR REPLACE INTO source_health(key,ok,working_slug,detail,checked_at) VALUES(?,?,?,?,?)",
                 (key, 1, slug, f"{len(jobs)} jobs", db.now()))
            return jobs
        except Exception as e:  # noqa: BLE001
            last_err = f"{slug}: {str(e)[:120]}"
    db.x("INSERT OR REPLACE INTO source_health(key,ok,working_slug,detail,checked_at) VALUES(?,?,?,?,?)",
         (key, 0, "", last_err, db.now()))
    log(f"  x {name} ({ats}) not found - {last_err}")
    return []


# ---------- open aggregate feeds ----------

def arbeitnow(c: httpx.Client, pages: int = 5) -> list[dict]:
    out = []
    for p in range(1, pages + 1):
        r = c.get("https://www.arbeitnow.com/api/job-board-api", params={"page": p})
        r.raise_for_status()
        for j in r.json().get("data", []):
            out.append({
                "source": "arbeitnow", "ext_id": f"an:{j.get('slug')}", "org": j.get("company_name", ""),
                "title": j.get("title", ""), "location": (j.get("location") or "") + (" (Remote)" if j.get("remote") else ""),
                "url": j.get("url", ""), "apply_url": j.get("url", ""), "posted": _iso(j.get("created_at")),
                "description": strip_html(j.get("description", ""))[:15000],
            })
        time.sleep(0.5)
    return out


def remotive(c: httpx.Client, searches: Iterable[str]) -> list[dict]:
    out = []
    for s in searches:
        r = c.get("https://remotive.com/api/remote-jobs", params={"search": s, "limit": 100})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            out.append({
                "source": "remotive", "ext_id": f"rm:{j.get('id')}", "org": j.get("company_name", ""),
                "title": j.get("title", ""), "location": f"Remote ({j.get('candidate_required_location', '')})",
                "url": j.get("url", ""), "apply_url": j.get("url", ""), "posted": _iso(j.get("publication_date")),
                "salary": j.get("salary", ""), "description": strip_html(j.get("description", ""))[:15000],
            })
        time.sleep(1)
    return out


def himalayas(c: httpx.Client, pages: int = 5) -> list[dict]:
    out = []
    for p in range(pages):
        r = c.get("https://himalayas.app/jobs/api", params={"limit": 20, "offset": p * 20})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            locs = j.get("locationRestrictions") or []
            out.append({
                "source": "himalayas", "ext_id": f"hm:{j.get('guid') or j.get('applicationLink')}",
                "org": j.get("companyName", ""), "title": j.get("title", ""),
                "location": "Remote (" + ", ".join(locs if isinstance(locs, list) else [str(locs)]) + ")",
                "url": j.get("applicationLink", ""), "apply_url": j.get("applicationLink", ""),
                "posted": _iso(j.get("pubDate")), "description": strip_html(j.get("description", ""))[:15000],
            })
        time.sleep(0.5)
    return out


def jobicy(c: httpx.Client, tags: Iterable[str]) -> list[dict]:
    out = []
    for t in tags:
        r = c.get("https://jobicy.com/api/v2/remote-jobs", params={"count": 50, "tag": t})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            out.append({
                "source": "jobicy", "ext_id": f"jc:{j.get('id')}", "org": j.get("companyName", ""),
                "title": j.get("jobTitle", ""), "location": f"Remote ({j.get('jobGeo', '')})",
                "url": j.get("url", ""), "apply_url": j.get("url", ""), "posted": _iso(j.get("pubDate")),
                "description": strip_html(j.get("jobDescription", ""))[:15000],
            })
        time.sleep(1)
    return out


def adzuna(c: httpx.Client, app_id: str, app_key: str, countries: Iterable[str], queries: Iterable[str]) -> list[dict]:
    out = []
    for cc in countries:
        for qtext in queries:
            r = c.get(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
                      params={"app_id": app_id, "app_key": app_key, "results_per_page": 50, "what": qtext,
                              "max_days_old": 21, "content-type": "application/json"})
            r.raise_for_status()
            for j in r.json().get("results", []):
                sal = ""
                if j.get("salary_min"):
                    sal = f"{int(j['salary_min'])}-{int(j.get('salary_max') or j['salary_min'])}"
                out.append({
                    "source": f"adzuna-{cc}", "ext_id": f"az:{j.get('id')}",
                    "org": (j.get("company") or {}).get("display_name", ""), "title": j.get("title", ""),
                    "location": (j.get("location") or {}).get("display_name", "") + f", {cc.upper()}",
                    "url": j.get("redirect_url", ""), "apply_url": j.get("redirect_url", ""),
                    "posted": _iso(j.get("created")), "salary": sal,
                    "description": strip_html(j.get("description", ""))[:15000],
                })
            time.sleep(0.7)
    return out


def reed(c: httpx.Client, api_key: str, queries: Iterable[str]) -> list[dict]:
    out = []
    for qtext in queries:
        r = c.get("https://www.reed.co.uk/api/1.0/search", params={"keywords": qtext, "resultsToTake": 100},
                  auth=(api_key, ""))
        r.raise_for_status()
        for j in r.json().get("results", []):
            sal = ""
            if j.get("minimumSalary"):
                sal = f"£{int(j['minimumSalary'])}-{int(j.get('maximumSalary') or j['minimumSalary'])}"
            dl = j.get("expirationDate") or ""
            if dl and "/" in dl:  # dd/mm/yyyy
                d, m, y = dl.split("/")
                dl = f"{y}-{m}-{d}"
            out.append({
                "source": "reed", "ext_id": f"rd:{j.get('jobId')}", "org": j.get("employerName", ""),
                "title": j.get("jobTitle", ""), "location": (j.get("locationName") or "") + ", UK",
                "url": j.get("jobUrl", ""), "apply_url": j.get("jobUrl", ""), "posted": "",
                "deadline": dl, "salary": sal, "description": strip_html(j.get("jobDescription", ""))[:15000],
            })
        time.sleep(0.5)
    return out
