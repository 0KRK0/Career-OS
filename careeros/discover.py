"""Company finder.

1. Claude (web search) lists the top N employers in a sector that hire your roles in your countries,
   with each one's official careers page.
2. For every careers page, Python works out which job system it runs on (Greenhouse, Lever, Ashby,
   Workday, SmartRecruiters, Workable) by reading the page and its links - those have public job
   feeds we can read directly, fast and free.
3. Companies with their own custom careers site are crawled with a headless browser: we open the
   page, read every job link, and keep the ones that match your target roles.
Everything lands in config/companies.yaml under the sector, and a scout per sector reads them
twice a day."""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import httpx

from . import brain, db, sources
from .config import candidate_summary, companies, goals, save_companies, settings

_lock = threading.Lock()

PATTERNS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
]
WORKDAY = re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)", re.I)
BAD_SLUGS = {"embed", "v1", "jobs", "job", "api", "js", "static", "assets", "apply", "search", "en", "en-us", "careers"}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:48] or "sector"


def detect_ats(url: str, html: str = "") -> dict | None:
    """Find a public job feed behind a careers page (URL and page source)."""
    hay = f"{url}\n{html}"
    m = WORKDAY.search(hay)
    if m:
        tenant, wd, site = m.group(1), m.group(2), m.group(3)
        if site.lower() not in ("wday", "en-us"):
            return {"ats": "workday", "host": f"{tenant}.{wd}.myworkdayjobs.com", "tenant": tenant, "site": site}
    for ats, rx in PATTERNS:
        for m in rx.finditer(hay):
            slug = m.group(1).strip(".").split("?")[0]
            if slug.lower() not in BAD_SLUGS and len(slug) > 1:
                return {"ats": ats, "slugs": [slug]}
    return None


def _try_guess(name: str, c: httpx.Client) -> dict | None:
    """Try the obvious slugs on the public job APIs (cheap JSON calls)."""
    base = re.sub(r"\b(inc|ltd|llc|plc|limited|group|holdings|technologies|corp|corporation|the)\b\.?", "", name.lower())
    cands = list(dict.fromkeys([re.sub(r"[^a-z0-9]", "", base), re.sub(r"[^a-z0-9]+", "-", base).strip("-")]))
    for slug in [s for s in cands if s]:
        for ats, url in (("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
                         ("lever", f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1"),
                         ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}")):
            try:
                r = c.get(url, timeout=10)
                if r.status_code == 200:
                    j = r.json()
                    n = len(j.get("jobs", [])) if isinstance(j, dict) else len(j) if isinstance(j, list) else 0
                    if n:
                        return {"ats": ats, "slugs": [slug]}
            except (httpx.HTTPError, ValueError):
                continue
    return None


def resolve(name: str, careers_url: str, c: httpx.Client) -> dict:
    """Return a companies.yaml entry for this company."""
    entry = {"name": name}
    url = (careers_url or "").strip()
    if url and not url.startswith("http"):
        url = "https://" + url
    if url:
        found = detect_ats(url)
        if not found:
            try:
                r = c.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) career-os"})
                found = detect_ats(str(r.url), r.text[:600000])
                url = str(r.url)
            except httpx.HTTPError:
                found = None
        if found:
            return {**entry, **found, "url": url}
    guess = _try_guess(name, c)
    if guess:
        return {**entry, **guess, "url": url}
    if url:
        return {**entry, "ats": "page", "url": url}
    return {**entry, "ats": "unknown", "url": ""}


# ---------------- sectors in companies.yaml ----------------

def sector_title(key: str) -> str:
    meta = (companies().get("_meta") or {}).get("titles") or {}
    fixed = {"quant": "Quant & trading firms", "bigtech_ai": "Big tech & AI labs", "uk_eu": "UK/EU fintech & startups",
             "salesforce": "Salesforce ecosystem", "india": "India high-pay tech", "custom": "Added by you"}
    return meta.get(key) or fixed.get(key) or key.replace("sector-", "").replace("-", " ").title()


def add_to_group(key: str, title: str, entries: list[dict]) -> dict:
    with _lock:
        comp = companies()
        meta = comp.setdefault("_meta", {}).setdefault("titles", {})
        meta[key] = title
        existing = {c["name"].lower(): c for lst in comp.values() if isinstance(lst, list) for c in lst}
        feeds = {(c.get("ats"), tuple(c.get("slugs") or [c.get("host", "")])) for lst in comp.values() if isinstance(lst, list) for c in lst
                 if c.get("ats") not in ("page", "unknown")}
        group = comp.setdefault(key, [])
        added = updated = 0
        for e in entries:
            cur = existing.get(e["name"].lower())
            if cur:
                if cur.get("ats") in ("page", "unknown") and e.get("ats") not in ("page", "unknown"):
                    cur.clear(); cur.update(e); updated += 1
                continue
            sig = (e.get("ats"), tuple(e.get("slugs") or [e.get("host", "")]))
            if e.get("ats") not in ("page", "unknown") and sig in feeds:
                continue  # same job feed as a company we already read
            feeds.add(sig)
            group.append(e); existing[e["name"].lower()] = e; added += 1
        save_companies(comp)
    ensure_scouts(key, title)
    return {"added": added, "updated": updated}


def ensure_scouts(key: str, title: str) -> None:
    import json
    comp = companies()
    lst = comp.get(key) or []
    want = []
    if any(c.get("ats") not in ("page", "unknown") for c in lst):
        want.append((f"Scout · {title}", "ats", {"groups": [key], "auto": True}))
    if any(c.get("ats") == "page" for c in lst):
        want.append((f"Scout · Career pages · {title}", "pages", {"groups": [key], "auto": True, "slots": 1}))
    for name, kind, cfg in want:
        if not db.q1("SELECT id FROM agents WHERE name=?", (name,)):
            db.x("INSERT INTO agents(name,kind,config,enabled,on_schedule,created_at) VALUES(?,?,?,?,?,?)",
                 (name, kind, json.dumps(cfg), 1, 1, db.now()))


FIND_PROMPT = """List the top {n} employers in this sector: "{sector}".
They should hire people for these roles: {roles}, in or near: {countries}
(global leaders with offices there count). Candidate, for context: {candidate}

For each company give the URL of its official careers / job-search page (ideally the page that
lists open jobs) and, if it has one, its students / early-careers page (graduate programmes,
internships, apprenticeships). Use WebSearch to check URLs you are not sure of. Do not invent companies.
Return ONLY a JSON array: [{{"name": "...", "careers_url": "https://...", "early_careers_url": "https://... or ''",
  "hq_country": "...", "why": "one short line"}}]"""


def find_companies(sector: str, n: int = 100, log=print) -> dict:
    g = goals()
    data, _ = brain.ask_json(FIND_PROMPT.format(n=n, sector=sector, roles=", ".join(g["roles"]) or "any",
                                                countries=", ".join(g["countries"]) or "worldwide",
                                                candidate=candidate_summary()),
                             tools=["WebSearch", "WebFetch"], max_turns=50, timeout=1800, log=log)
    items = [d for d in (data if isinstance(data, list) else []) if isinstance(d, dict) and d.get("name")]
    log(f"  Claude listed {len(items)} companies - checking each careers page…")
    return resolve_many(slugify("sector-" + sector), sector, items, log)


def resolve_many(key: str, title: str, items: list[dict], log=print) -> dict:
    # students / early-careers pages are checked too (grad schemes, internships, apprenticeships)
    extra = [{"name": f"{d['name']} — early careers", "careers_url": d["early_careers_url"]} for d in items
             if d.get("early_careers_url") and d.get("early_careers_url") != d.get("careers_url")]
    items = items + extra
    out: list[dict] = []
    with sources._client() as c, ThreadPoolExecutor(max_workers=8) as ex:
        for e in ex.map(lambda d: resolve(d["name"], d.get("careers_url", ""), c), items):
            out.append(e)
    kinds: dict[str, int] = {}
    for e in out:
        kinds[e["ats"]] = kinds.get(e["ats"], 0) + 1
    log(f"  job systems found: {kinds}")
    res = add_to_group(key, title, [e for e in out if e["ats"] != "unknown"])
    log(f"  {res['added']} companies added to '{title}', {res['updated']} upgraded")
    return {**res, "systems": kinds}


# ---------------- crawling custom career pages ----------------

GENERIC_ROLE = r"engineer|developer|scientist|analyst|intern|graduate|researcher|trader|quant|associate|architect|consultant|specialist|designer|manager|programmer|apprentice|fellow|lead|officer|technician|nurse|teacher|lecturer|assistant"
NAV = re.compile(r"^(careers?|jobs?|search( jobs)?|view (all )?(jobs|openings|roles|positions)|see (all )?(jobs|openings)|open (roles|positions)|life at\b.*|benefits|students|graduates|early careers|join us|apply now|learn more|read more|our (culture|teams?)|teams?|locations?|sign in|log ?in|privacy|cookies?|how we hire.*|meet the team.*|our (people|values|story).*)$", re.I)
HOP = re.compile(r"(search|view|see|browse|explore|find)\b.{0,20}\b(jobs|roles|openings|positions|opportunities|vacancies)|open (roles|positions)|all (jobs|openings|roles|vacancies)|job search|current (openings|vacancies)|job openings|vacancies|opportunities", re.I)
JOBLINK = re.compile(r"job|career|position|opening|vacanc|requisition|/role|apply|opportunit|posting|jid=|gh_jid", re.I)

ANCHORS_JS = """() => Array.from(document.querySelectorAll('a[href]')).map(a => {
  const row = a.closest('li, tr, article, [class*="job" i], [class*="position" i], [class*="result" i], [class*="card" i]') || a.parentElement;
  return { text: (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim(), href: a.href,
           ctx: ((row && row.innerText) || '').replace(/\\s+/g, ' ').trim().slice(0, 300) };
})"""


def role_regex() -> re.Pattern:
    words = set()
    for r in goals()["roles"]:
        for w in re.findall(r"[a-z]+", r.lower()):
            if len(w) > 3 and w not in ("engineer", "developer", "roles", "senior", "junior"):
                words.add(re.escape(w))
    return re.compile(r"\b(" + "|".join(sorted(words) + [GENERIC_ROLE]) + r")", re.I)


def crawl_pages(entries: list[dict], log=print) -> list[dict]:
    from playwright.sync_api import sync_playwright
    rx = role_regex()
    jobs: list[dict] = []
    chan = settings().get("browser_channel") or None
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(channel=chan, headless=True) if chan else pw.chromium.launch(headless=True)
        except Exception:  # noqa: BLE001
            b = pw.chromium.launch(headless=True)
        ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 career-os")
        for co in entries:
            url = co.get("url")
            if not url:
                continue
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=35000)
                pg.wait_for_timeout(3000)
                for _ in range(3):  # load lazy lists
                    pg.mouse.wheel(0, 4000)
                    pg.wait_for_timeout(700)
                found = detect_ats(pg.url, pg.content()[:800000])
                if found:  # the page loads a real job system after all - switch the company over
                    co.update(found)
                    log(f"  {co['name']}: uses {found['ats']} - switched to its job feed")
                    continue
                links = pg.evaluate(ANCHORS_JS)
                matches = [a for a in links if JOBLINK.search(a.get("href", "")) and rx.search(a.get("text", "")) and not NAV.match(a.get("text", ""))]
                if len(matches) < 3:  # probably a landing page: follow its "search jobs" link once
                    hop = next((a["href"] for a in links if HOP.search(a.get("text", "")) and a.get("href", "").startswith("http")), None)
                    if hop:
                        pg.goto(hop, wait_until="domcontentloaded", timeout=35000)
                        pg.wait_for_timeout(3500)
                        for _ in range(3):
                            pg.mouse.wheel(0, 4000)
                            pg.wait_for_timeout(700)
                        found = detect_ats(pg.url, pg.content()[:800000])
                        if found:
                            co.update(found)
                            log(f"  {co['name']}: uses {found['ats']} - switched to its job feed")
                            continue
                        links = pg.evaluate(ANCHORS_JS)
                        url = pg.url
            except Exception as e:  # noqa: BLE001
                log(f"  x {co['name']}: {str(e)[:100]}")
                db.x("INSERT OR REPLACE INTO source_health(key,ok,working_slug,detail,checked_at) VALUES(?,?,?,?,?)",
                     (f"page:{co['name']}", 0, "", str(e)[:200], db.now()))
                continue
            finally:
                pg.close()
            host = urlparse(url).hostname or ""
            seen, n = set(), 0
            for a in links:
                t, h = a.get("text", ""), a.get("href", "")
                if not (6 <= len(t) <= 140) or not h.startswith("http") or h in seen or NAV.match(t):
                    continue
                if not (JOBLINK.search(h) and rx.search(t)):
                    continue
                if (urlparse(h).hostname or "") not in (host, "") and not JOBLINK.search(urlparse(h).hostname or ""):
                    continue
                seen.add(h)
                ctxt = a.get("ctx", "")
                jobs.append({"source": "careers-page", "ext_id": f"cp:{h}", "org": co["name"], "title": t,
                             "location": ctxt.replace(t, "").strip(" ·|-")[:120], "url": h, "apply_url": h,
                             "description": ctxt[:600]})
                n += 1
                if n >= 150:
                    break
            db.x("INSERT OR REPLACE INTO source_health(key,ok,working_slug,detail,checked_at) VALUES(?,?,?,?,?)",
                 (f"page:{co['name']}", 1, "", f"{n} matching links", db.now()))
            if n:
                log(f"  {co['name']}: {n} matching roles on its careers page")
        b.close()
    return jobs


def add_company(name: str = "", url: str = "") -> dict:
    """Add one company (by careers link and/or name) to 'Added by you'."""
    brain.set_purpose("Company finder", "")
    if not name and url:
        name = re.sub(r"^(www|careers|jobs)\.", "", urlparse(url if url.startswith("http") else "https://" + url).hostname or url).split(".")[0].title()
        try:  # a nicer name from the page title, e.g. "G-Research | Join us" -> "G-Research"
            r = httpx.get(url if url.startswith("http") else "https://" + url, timeout=12, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 career-os"})
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
            if m:
                parts = [p.strip() for p in re.split(r"\s[|\-–—:·]\s", re.sub(r"\s+", " ", m.group(1))) if p.strip()]
                parts = [p for p in parts if not re.search(r"career|jobs?\b|join|vacanc|opportunit|work (at|with)|home", p, re.I) and len(p) <= 40]
                if parts:
                    name = min(parts, key=len)
        except httpx.HTTPError:
            pass
    with sources._client() as c:
        e = resolve(name, url, c)
        if e["ats"] == "unknown" and brain.available():
            data, _ = brain.ask_json(f'What is the official careers/jobs page URL of the company "{name}"? Check with WebSearch. '
                                     'Return ONLY JSON: {"careers_url": "https://..."}', tools=["WebSearch", "WebFetch"],
                                     max_turns=8, timeout=300)
            if isinstance(data, dict) and data.get("careers_url"):
                e = resolve(name, data["careers_url"], c)
    if e["ats"] == "unknown":
        return {"ok": False, "error": f"Couldn't find a careers page for {name}. Paste its careers link instead."}
    res = add_to_group("custom", "Added by you", [e])
    return {"ok": True, "company": e, "already": not (res["added"] or res["updated"])}


PROGRAM_PROMPT = """List up to {n} of the best {kind_label} that are currently open or open within the next 6 months,
for this candidate: {candidate}
Relevant to these roles / fields: {roles}. Places: {countries} (plus worldwide / remote programmes).
Think broadly: company programmes, government and university schemes, foundations, non-profits, research
institutes, competitions and well-known named programmes. Use WebSearch/WebFetch to confirm each one on its
official page; skip anything closed for this cycle unless it reopens soon (then give the expected month).
Return ONLY a JSON array:
[{{"title": "...", "org": "...", "kind": "{kind}", "location": "city, country or Remote", "country_code": "UK|IN|US|...|REMOTE",
  "url": "official page", "deadline": "YYYY-MM-DD or null", "opens": "e.g. 'open now' or 'Oct 2026'",
  "pay": "salary/stipend if stated", "sponsorship": "yes|no|unknown", "eligibility": "one line"}}]"""

KIND_LABELS = {"graduate": "graduate programmes and graduate schemes", "internship": "internships and placements (incl. summer internships)",
               "fellowship": "paid fellowships, residencies and research programmes", "apprenticeship": "apprenticeships and degree apprenticeships",
               "scholarship": "scholarships, bursaries, grants and prizes", "competition": "competitions, hackathons and challenges with cash prizes",
               "parttime": "part-time and student jobs"}


def find_programs(kind: str, n: int = 100, log=print) -> list[dict]:
    g = goals()
    data, _ = brain.ask_json(PROGRAM_PROMPT.format(n=n, kind=kind, kind_label=KIND_LABELS.get(kind, kind),
                                                   candidate=candidate_summary(), roles=", ".join(g["roles"]) or "any",
                                                   countries=", ".join(g["countries"]) or "worldwide"),
                             tools=["WebSearch", "WebFetch"], max_turns=60, timeout=2400, log=log)
    from datetime import date
    today = date.today().isoformat()
    out = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict) or not d.get("url") or not d.get("title"):
            continue
        dl = str(d.get("deadline") or "")[:10]
        if dl and len(dl) == 10 and dl < today:
            continue
        out.append({"source": "programme-finder", "ext_id": d["url"].strip(), "title": d["title"], "org": d.get("org", ""),
                    "kind": d.get("kind") or kind, "location": d.get("location", ""),
                    "country": (d.get("country_code") or "").upper().replace("GB", "UK") or None,
                    "url": d["url"], "apply_url": d["url"], "deadline": dl, "salary": d.get("pay", ""),
                    "sponsorship": d.get("sponsorship") if d.get("sponsorship") in ("yes", "no") else None,
                    "eligibility": " · ".join(x for x in [d.get("eligibility", ""), ("opens " + d["opens"]) if d.get("opens") and d["opens"] != "open now" else ""] if x),
                    "description": f"{d.get('eligibility', '')}\nOpens: {d.get('opens', '')}"})
    log(f"  {len(out)} {KIND_LABELS.get(kind, kind)} found")
    return out
