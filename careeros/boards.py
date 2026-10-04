"""Job boards - LinkedIn, Indeed, TargetJobs, Prospects, jobs.ac.uk, or any site you name. Read, never apply.

1. You name a site (e.g. "linkedin.com"). Your AI checks it's a real job platform and how its search works.
2. You sign in once, yourself, in Career OS's own board browser (a separate window; your password never
   touches Career OS). The sign-in is remembered in data/boards-profile.
3. The Extra agent searches your roles x places on each board in that browser, scrolls the results like a
   person would and keeps each job as a *lead* (role, company, place). It never applies, messages or clicks
   "Easy Apply".
4. Each lead is then looked for on the company's OWN careers page / job system. Found -> it goes into Matches
   with the employer's link, and the company joins your sources so the scouts keep reading it.

Extra is separate from the scouts and finders: its own agent, own schedule, own list of platforms that YOU add.
It never edits their company lists; the only thing it hands over is the jobs it finds (Matches, source "extra").

Heads-up: sites like LinkedIn don't allow automated reading, even of your own signed-in view, so there is some
risk of an account restriction. Defaults are deliberately slow and small (few searches, human pace, twice a day).
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
from difflib import SequenceMatcher
from urllib.parse import quote_plus, urlparse

from . import brain, db, opps, scoring, sources
from .config import DATA_DIR, ROOT, goals, settings

PROFILE = DATA_DIR / "boards-profile"

SCHEMA = """
CREATE TABLE IF NOT EXISTS boards (
  id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT UNIQUE, url TEXT, name TEXT, what TEXT, template TEXT,
  fixed_url TEXT, needs_login INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, warning TEXT, enabled INTEGER DEFAULT 1,
  created_at TEXT, last_run TEXT, last_status TEXT, found INTEGER DEFAULT 0, cursor INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT, search_id INTEGER, site TEXT, title TEXT, org TEXT, location TEXT,
  url TEXT, key TEXT UNIQUE, first_seen TEXT, status TEXT DEFAULT 'new', tries INTEGER DEFAULT 0,
  opp_id INTEGER, detail TEXT, updated_at TEXT
);
"""

# Boards we already know how to search (anything else: your AI works it out). {q} = role, {loc} = place, {slug} = role-as-slug. Boards without a template open their search page.
CATALOGUE = [
    {"id": "linkedin", "name": "LinkedIn Jobs", "where": "Worldwide", "for": "all",
     "url": "https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}&f_TPR=r604800",
     "note": "Reads the public results (signed out). Never uses your account."},
    {"id": "indeed", "name": "Indeed", "where": "Worldwide", "for": "all", "url": "https://{indeed}/jobs?q={q}&l={loc}",
     "note": "Often blocks automated reading - if a search keeps finding 0, that's why."},
    {"id": "glassdoor", "name": "Glassdoor", "where": "Worldwide", "for": "all", "url": "https://www.glassdoor.com/Job/index.htm",
     "note": "Often blocks automated reading."},
    {"id": "targetjobs", "name": "TargetJobs", "where": "United Kingdom", "for": "graduate internship", "url": "https://targetjobs.co.uk/",
     "note": "Graduate schemes and internships."},
    {"id": "prospects", "name": "Prospects", "where": "United Kingdom", "for": "graduate internship", "url": "https://www.prospects.ac.uk/graduate-jobs"},
    {"id": "brightnetwork", "name": "Bright Network", "where": "United Kingdom", "for": "graduate internship", "url": "https://www.brightnetwork.co.uk/graduate-jobs/"},
    {"id": "gradcracker", "name": "Gradcracker", "where": "United Kingdom", "for": "graduate internship apprenticeship", "url": "https://www.gradcracker.com/"},
    {"id": "ratemyapprenticeship", "name": "RateMyApprenticeship", "where": "United Kingdom", "for": "apprenticeship", "url": "https://www.ratemyapprenticeship.co.uk/"},
    {"id": "findapprenticeship", "name": "Find an apprenticeship (GOV.UK)", "where": "United Kingdom", "for": "apprenticeship",
     "url": "https://www.findapprenticeship.service.gov.uk/apprenticeships"},
    {"id": "govuk", "name": "GOV.UK Find a job", "where": "United Kingdom", "for": "all", "url": "https://findajob.dwp.gov.uk/search?q={q}&w={loc}"},
    {"id": "nhs", "name": "NHS Jobs", "where": "United Kingdom", "for": "all", "url": "https://www.jobs.nhs.uk/candidate/search/results?keyword={q}"},
    {"id": "civilservice", "name": "Civil Service Jobs", "where": "United Kingdom", "for": "all", "url": "https://www.civilservicejobs.service.gov.uk/csr/index.cgi"},
    {"id": "jobsacuk", "name": "jobs.ac.uk", "where": "United Kingdom", "for": "fellowship scholarship job", "url": "https://www.jobs.ac.uk/",
     "note": "Research posts, PhD studentships and fellowships."},
    {"id": "findaphd", "name": "FindAPhD", "where": "Worldwide", "for": "scholarship", "url": "https://www.findaphd.com/"},
    {"id": "euraxess", "name": "EURAXESS", "where": "Europe", "for": "fellowship scholarship job", "url": "https://euraxess.ec.europa.eu/jobs/search",
     "note": "Research jobs and fellowships across Europe."},
    {"id": "eures", "name": "EURES", "where": "Europe", "for": "all", "url": "https://eures.europa.eu/jobs_en"},
    {"id": "stepstone", "name": "StepStone", "where": "Germany", "for": "all", "url": "https://www.stepstone.de/"},
    {"id": "wttj", "name": "Welcome to the Jungle", "where": "Europe", "for": "job internship", "url": "https://www.welcometothejungle.com/en/jobs"},
    {"id": "wellfound", "name": "Wellfound", "where": "Worldwide", "for": "job internship", "url": "https://wellfound.com/jobs", "note": "Startups."},
    {"id": "80000hours", "name": "80,000 Hours job board", "where": "Worldwide", "for": "fellowship job internship",
     "url": "https://jobs.80000hours.org/", "note": "High-impact roles and fellowships (AI safety, policy, global health)."},
    {"id": "profellow", "name": "ProFellow", "where": "Worldwide", "for": "fellowship scholarship", "url": "https://www.profellow.com/fellowships/"},
    {"id": "scholarshipportal", "name": "ScholarshipPortal", "where": "Worldwide", "for": "scholarship", "url": "https://www.scholarshipportal.com/"},
    {"id": "naukri", "name": "Naukri", "where": "India", "for": "all", "url": "https://www.naukri.com/{slug}-jobs"},
    {"id": "internshala", "name": "Internshala", "where": "India", "for": "internship", "url": "https://internshala.com/internships/"},
    {"id": "instahyre", "name": "Instahyre", "where": "India", "for": "job", "url": "https://www.instahyre.com/"},
    {"id": "usajobs", "name": "USAJOBS", "where": "United States", "for": "all", "url": "https://www.usajobs.gov/Search/Results?k={q}"},
    {"id": "handshake", "name": "Handshake", "where": "United States", "for": "graduate internship", "url": "https://joinhandshake.com/"},
    {"id": "seek", "name": "SEEK", "where": "Australia", "for": "all", "url": "https://www.seek.com.au/"},
    {"id": "jobbank", "name": "Job Bank", "where": "Canada", "for": "all", "url": "https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring={q}"},
    {"id": "mycareersfuture", "name": "MyCareersFuture", "where": "Singapore", "for": "all", "url": "https://www.mycareersfuture.gov.sg/"},
]
INDEED = {"United Kingdom": "uk.indeed.com", "India": "in.indeed.com", "Germany": "de.indeed.com", "Netherlands": "nl.indeed.com",
          "Ireland": "ie.indeed.com", "Singapore": "sg.indeed.com", "Canada": "ca.indeed.com", "Australia": "au.indeed.com",
          "France": "fr.indeed.com", "Italy": "it.indeed.com", "Spain": "es.indeed.com", "Switzerland": "ch.indeed.com"}
AGGREGATORS = re.compile(r"linkedin\.|indeed\.|glassdoor\.|naukri\.|targetjobs\.|prospects\.ac|brightnetwork\.|gradcracker\.|"
                         r"ziprecruiter\.|monster\.|totaljobs\.|reed\.co|cv-library\.|adzuna\.|jooble\.|simplyhired\.|wellfound\.|"
                         r"welcometothejungle\.|internshala\.|instahyre\.|handshake|seek\.com|stepstone\.|google\.com", re.I)


def init() -> None:
    with db._lock:
        db.conn().executescript(SCHEMA)
        db.conn().commit()


def _host(url: str) -> str:
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def known(host: str) -> dict | None:
    for b in CATALOGUE:
        bh = _host(b["url"].replace("{indeed}", "indeed.com"))
        if bh and (host == bh or host.endswith("." + bh) or (b["id"] == "indeed" and "indeed." in host)):
            return b
    return None


def catalogue() -> dict:
    from .universal import COUNTRIES
    init()
    g = goals()
    mine = [c for c in (g.get("countries") or []) if c in COUNTRIES or c in ("Europe", "Remote")]
    kinds = set(g.get("kinds") or [])
    added = {r["host"] for r in db.q("SELECT host FROM boards")}
    out = []
    for b in CATALOGUE:
        rel = b["where"] == "Worldwide" or b["where"] in mine or (b["where"] == "Europe" and bool(set(mine) & {
            "Europe", "Ireland", "Germany", "Netherlands", "Switzerland", "France", "Italy", "Spain", "Poland", "Sweden",
            "Denmark", "Portugal", "Austria", "Belgium"}))
        fits = b["for"] == "all" or bool(kinds & set(b["for"].split()))
        out.append({**b, "recommended": bool(rel and fits), "added": _host(b["url"].replace("{indeed}", "indeed.com")) in added})
    out.sort(key=lambda b: (not b["recommended"], b["where"] != "Worldwide", b["name"]))
    return {"boards": out, "roles": g.get("roles") or [], "places": mine}


def boards() -> list[dict]:
    init()
    rows = db.q("SELECT * FROM boards ORDER BY id")
    for r in rows:
        c = db.q1("SELECT COUNT(*) n, SUM(status='traced') t, SUM(status='new') w, SUM(status='board_only') b FROM leads WHERE search_id=?", (r["id"],))
        r.update(leads=c["n"] or 0, traced=c["t"] or 0, waiting=c["w"] or 0, board_only=c["b"] or 0)
    return rows


VERIFY_PROMPT = """Someone wants Career OS to search this website for jobs: {url}
Use WebFetch / WebSearch to check it. Is it a legitimate job-search platform (a job board, graduate / internship /
apprenticeship / fellowship / scholarship listing site, recruiter board, or government job site)? Watch for scams,
fake job sites and sites that charge candidates.

If it is, work out how its job search URL looks so a search can be opened directly, with {{q}} for the role/keywords
and {{loc}} for the place (leave "" if the site has no URL-based search). Say whether results need signing in.

Return ONLY JSON: {{"legit": true|false, "name": "Site name", "what": "one line: what it lists and where",
"search_template": "https://...{{q}}...{{loc}}..." or "", "needs_login": true|false, "warning": "" or why not to use it}}"""


def add_board(text: str) -> dict:
    """You name a site (or paste a results link). Check it's a real job platform, then remember it."""
    init()
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Type a site, e.g. linkedin.com or targetjobs.co.uk")
    if " " in raw and "." not in raw:  # a name like "target jobs": let the AI find the site
        raw = raw.replace(" ", "") + ".com" if not brain.available() else raw
    url = raw if re.match(r"https?://", raw) else "https://" + raw
    host = _host(url)
    fixed = url if urlparse(url).query and not known(host) else ""   # a results link you pasted: re-read exactly that
    b = known(host)
    info = {"legit": True, "name": b["name"] if b else host, "what": (b or {}).get("note", ""),
            "search_template": (b or {}).get("url", "") if "{q}" in (b or {}).get("url", "") else "", "needs_login": b and b["id"] == "linkedin",
            "warning": ""}
    verified = 1 if b else 0
    if not b and brain.available():
        brain.set_purpose("Extra · job boards", host)
        try:
            data, _ = brain.ask_json(VERIFY_PROMPT.format(url=url), tools=["WebSearch", "WebFetch"], max_turns=10, timeout=400)
            if isinstance(data, dict):
                info.update({k: v for k, v in data.items() if v is not None})
                verified = 1
        except brain.BrainError as e:
            info["warning"] = f"Couldn't check it with {brain.name()} ({str(e)[:80]}) - added unchecked."
    if verified and not info.get("legit", True):
        return {"ok": False, "error": info.get("warning") or "That doesn't look like a real job platform, so it wasn't added."}
    tpl = info.get("search_template") or ""
    if tpl and not tpl.startswith("http"):
        tpl = ""
    db.x("INSERT OR IGNORE INTO boards(host,url,name,what,template,fixed_url,needs_login,verified,warning,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
         (host, url.split("?")[0] if not fixed else url, info.get("name") or host, info.get("what", ""), tpl, fixed,
          1 if info.get("needs_login") else 0, verified, info.get("warning", ""), db.now()))
    ensure_agent()
    return {"ok": True, "board": db.q1("SELECT * FROM boards WHERE host=?", (host,))}


def update_board(bid: int, fields: dict) -> None:
    init()
    for k in ("enabled", "template", "fixed_url"):
        if k in fields:
            db.x(f"UPDATE boards SET {k}=? WHERE id=?", (fields[k], bid))


def delete_board(bid: int) -> None:
    init()
    db.x("DELETE FROM boards WHERE id=?", (bid,))
    db.x("DELETE FROM leads WHERE search_id=? AND status IN ('new','not_found')", (bid,))


def leads(limit: int = 200) -> list[dict]:
    init()
    return db.q("SELECT * FROM leads ORDER BY CASE status WHEN 'traced' THEN 0 WHEN 'new' THEN 1 ELSE 2 END, id DESC LIMIT ?", (limit,))


def ensure_agent() -> None:
    if not db.q1("SELECT id FROM agents WHERE kind='boards'"):
        db.x("INSERT INTO agents(name,kind,config,enabled,on_schedule,created_at) VALUES(?,?,?,?,?,?)",
             ("Extra · Your job platforms → company career pages", "boards", json.dumps({"extra": True}), 1, 1, db.now()))


def times() -> list[str]:
    """Extra keeps its own schedule (twice a day by default), separate from the scouts."""
    return sorted((settings().get("extra") or {}).get("times") or ["08:40", "18:40"])


# ---------------- the board browser (your own sign-ins, separate from everything else) ----------------

def _login_lock():
    return DATA_DIR / "boards-login.lock"


def login_open() -> bool:
    lk = _login_lock()
    if not lk.exists():
        return False
    try:
        return time.time() - float(lk.read_text() or 0) < 1800
    except (OSError, ValueError):
        return False


def open_login(bid: int) -> dict:
    """Open the board browser so you can sign in yourself. Career OS never sees your password."""
    init()
    b = db.q1("SELECT * FROM boards WHERE id=?", (bid,))
    if not b:
        raise ValueError("Unknown board")
    url = b["url"] if b["url"].startswith("http") else "https://" + b["host"]
    flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    subprocess.Popen([sys.executable, "-m", "careeros.boards", "login", url], cwd=str(ROOT), **flags)
    return {"ok": True}


def _launch(pw, headless: bool):
    PROFILE.mkdir(parents=True, exist_ok=True)
    chan = settings().get("browser_channel") or None
    kw = dict(user_data_dir=str(PROFILE), headless=headless, no_viewport=not headless,
              viewport={"width": 1366, "height": 900} if headless else None, locale="en-GB",
              chromium_sandbox=sys.platform == "win32", ignore_default_args=["--enable-automation"],
              args=["--disable-blink-features=AutomationControlled"] + ([] if headless else ["--start-maximized"]))
    if kw["viewport"] is None:
        kw.pop("viewport")
    try:
        return pw.chromium.launch_persistent_context(channel=chan, **kw) if chan else pw.chromium.launch_persistent_context(**kw)
    except Exception:  # noqa: BLE001
        return pw.chromium.launch_persistent_context(**kw)


def login_main(url: str) -> None:
    from playwright.sync_api import sync_playwright
    _login_lock().write_text(str(time.time()))
    try:
        with sync_playwright() as pw:
            ctx = _launch(pw, headless=False)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            pg.evaluate("""() => { const d = document.createElement('div'); d.textContent = 'Career OS board browser — sign in here yourself, then just close this window. Career OS only reads job results with this sign-in; it never applies or messages anyone.';
              d.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:2147483647;background:#0f1720;color:#fff;font:600 13px system-ui;padding:10px 16px;text-align:center';
              document.documentElement.appendChild(d); setTimeout(() => d.remove(), 15000); }""")
            while any(not p.is_closed() for p in ctx.pages):
                try:
                    ctx.pages[0].wait_for_timeout(1000)
                except Exception:  # noqa: BLE001
                    break
                _login_lock().write_text(str(time.time()))
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass
    finally:
        try:
            _login_lock().unlink()
        except OSError:
            pass


# ---------------- searching a board like a person ----------------

CARDS_JS = r"""() => {
  const T = el => (el && (el.innerText || el.textContent) || '').replace(/\s+/g, ' ').trim();
  const out = [];
  // LinkedIn (signed-out results)
  document.querySelectorAll('.base-card, .job-search-card').forEach(c => {
    const a = c.querySelector('a.base-card__full-link, a[href*="/jobs/view/"]');
    out.push({ title: T(c.querySelector('.base-search-card__title, h3')), org: T(c.querySelector('.base-search-card__subtitle, h4')),
               location: T(c.querySelector('.job-search-card__location')), url: a ? a.href.split('?')[0] : '' });
  });
  // LinkedIn (signed in)
  document.querySelectorAll('.job-card-container, [data-job-id]').forEach(c => {
    const a = c.querySelector('a.job-card-container__link, a.job-card-list__title, a[href*="/jobs/view/"]');
    const title = T(c.querySelector('.job-card-list__title, .job-card-container__link strong, .artdeco-entity-lockup__title')) || T(a);
    if (!title || !a) return;
    out.push({ title: title.split(' with verification')[0], org: T(c.querySelector('.artdeco-entity-lockup__subtitle, .job-card-container__primary-description, .job-card-container__company-name')),
               location: T(c.querySelector('.artdeco-entity-lockup__caption, .job-card-container__metadata-item')), url: a.href.split('?')[0] });
  });
  if (out.length) return { site: 'linkedin', cards: out.filter((c, i, arr) => arr.findIndex(x => x.url === c.url) === i) };
  // anything else: job-looking links with the text of the card around them
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const text = T(a), href = a.href;
    if (!/^https?:/.test(href) || seen.has(href) || text.length < 4 || text.length > 140) continue;
    if (!/job|vacanc|position|opening|career|graduate|intern|fellow|scholar|programme|program|apprentic|studentship|role|opportunit/i.test(href + ' ' + text)) continue;
    const card = a.closest('li, article, tr, [class*="job" i], [class*="result" i], [class*="card" i], [class*="listing" i]');
    const ctx = T(card || a.parentElement).slice(0, 400);
    if (ctx.length < text.length + 3 && !card) continue;
    seen.add(href); out.push({ title: text, url: href, ctx });
    if (out.length >= 150) break;
  }
  return { site: 'generic', cards: out };
}"""

PARSE_PROMPT = """These are cards from a job-board results page ({site}). Pull out the real job/programme listings.
Ignore navigation, filters, ads, "sign in" and category links. Keep the role title, the EMPLOYER
(not the board), and the place exactly as shown.

{cards}

Return ONLY JSON: [{{"i": <card number>, "title": "...", "org": "...", "location": "..."}}]"""


def _heuristic(c: dict) -> dict | None:
    ctx = c.get("ctx", "")
    rest = ctx.replace(c["title"], " | ")
    parts = [p.strip(" |·-–•") for p in re.split(r"\s{2,}| \| | · | • | - (?=[A-Z])", rest) if p.strip(" |·-–•")]
    org = next((p for p in parts if 2 <= len(p) <= 60 and not re.search(r"\d+ (days?|hours?|weeks?)|ago|apply|save|new\b|£|\$|€|salary|per (year|annum|hour)", p, re.I)), "")
    loc = next((p for p in parts if scoring.detect_country(p) and p != org and len(p) <= 80), "")
    return {"title": c["title"], "org": org, "location": loc, "url": c["url"]} if org else None


SCROLL_JS = """(step) => {  // scroll the page and any scrolling results list inside it (LinkedIn keeps results in a side panel)
  window.scrollBy(0, step);
  for (const el of document.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (/(auto|scroll)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 200 && el.clientHeight > 250 && el.querySelectorAll('a[href]').length > 8) el.scrollBy(0, step);
  }
}"""

WALL = re.compile(r"sign in to (see|view)|join now to see|log ?in to (continue|see)|authwall|/login|/signin|checkpoint|captcha|verify you are human|unusual activity", re.I)


def _searches(b: dict) -> list[tuple[str, str]]:
    """The (role, place) searches for this board, rotating through all combos across runs."""
    g = goals()
    roles = [re.sub(r"\s*/.*", "", r).strip() for r in (g.get("roles") or [])][:6] or ["graduate"]
    places = [p for p in (g.get("countries") or []) if p not in ("Anywhere",)][:6] or [""]
    combos = [(r, p) for r in roles for p in places]
    n = int((settings().get("extra") or {}).get("searches_per_board", 4))
    start = int(b.get("cursor") or 0) % max(1, len(combos))
    pick = (combos[start:] + combos[:start])[:n]
    db.x("UPDATE boards SET cursor=? WHERE id=?", ((start + n) % max(1, len(combos)), b["id"]))
    return pick


def _fill_template(tpl: str, role: str, place: str) -> str:
    loc = "Remote" if place == "Remote" else ("European Union" if place == "Europe" else place)
    return (tpl.replace("{indeed}", INDEED.get(place, "www.indeed.com")).replace("{q}", quote_plus(role))
               .replace("{loc}", quote_plus(loc)).replace("{slug}", re.sub(r"[^a-z0-9]+", "-", role.lower()).strip("-")))


def _search_by_typing(pg, role: str, place: str) -> bool:
    """No URL recipe: use the site's own search boxes like a person."""
    what = pg.locator("input[type=search], input[placeholder*=job i], input[placeholder*=keyword i], input[placeholder*=title i], "
                      "input[placeholder*=what i], input[aria-label*=keyword i], input[aria-label*=search i], input[name*=keyword i], input[name=q]").first
    try:
        what.click(timeout=4000)
        what.fill("")
        what.type(role, delay=60)
    except Exception:  # noqa: BLE001
        return False
    if place:
        where = pg.locator("input[placeholder*=location i], input[placeholder*=where i], input[placeholder*=city i], "
                           "input[aria-label*=location i], input[name*=location i], input[name=l], input[name=w]").first
        try:
            where.click(timeout=2500)
            where.fill("")
            where.type(place, delay=60)
            pg.wait_for_timeout(700)
        except Exception:  # noqa: BLE001
            pass
    pg.keyboard.press("Enter")
    return True


def read_board(b: dict, ctx, log=print) -> list[dict]:
    """Run this board's searches in one tab of the board browser; return leads."""
    found: list[dict] = []
    pg = ctx.new_page()
    try:
        for role, place in _searches(b):
            if b.get("fixed_url"):
                url = b["fixed_url"]
            elif b.get("template"):
                url = _fill_template(b["template"], role, place)
            else:
                url = b["url"] if b["url"].startswith("http") else "https://" + b["host"]
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(random.randint(2500, 4500))
            if not b.get("template") and not b.get("fixed_url"):
                if not _search_by_typing(pg, role, place):
                    log(f"  {b['name']}: couldn't find its search box - paste a results link for this board instead")
                    break
                pg.wait_for_timeout(random.randint(3000, 5000))
            if WALL.search(pg.url) or (pg.locator("input[type=password]").count() and not pg.locator("a[href*=job]").count()):
                db.x("UPDATE boards SET needs_login=1 WHERE id=?", (b["id"],))
                raise RuntimeError("needs you to sign in (press Sign in on this board)")
            for _ in range(random.randint(5, 8)):  # scroll like a person reading
                pg.evaluate(SCROLL_JS, random.randint(600, 1100))
                pg.wait_for_timeout(random.randint(900, 1800))
            res = pg.evaluate(CARDS_JS)
            cards = res.get("cards") or []
            if res.get("site") == "linkedin":
                got = [c for c in cards if c.get("title") and c.get("org")]
            else:
                got = _parse_generic(b, cards, log)
            log(f"  {b['name']} · {role}{' · ' + place if place else ''}: {len(got)} jobs")
            found += got
            if b.get("fixed_url"):
                break
            pg.wait_for_timeout(random.randint(8000, 20000))  # a pause between searches, like a person
    finally:
        try:
            pg.close()
        except Exception:  # noqa: BLE001
            pass
    return found


def _parse_generic(b: dict, cards: list[dict], log) -> list[dict]:
    if not cards:
        return []
    if brain.available():
        brain.set_purpose("Extra · job boards", b["name"])
        try:
            listing = "\n".join(f"{i}. {c['title']} || {c.get('ctx', '')[:260]}" for i, c in enumerate(cards[:120]))
            data, _ = brain.ask_json(PARSE_PROMPT.format(site=b["name"], cards=listing), max_turns=2, timeout=400)
            out = []
            for d in data if isinstance(data, list) else []:
                i = d.get("i")
                if isinstance(i, int) and 0 <= i < len(cards) and d.get("title") and d.get("org"):
                    out.append({"title": d["title"], "org": d["org"], "location": d.get("location", ""), "url": cards[i]["url"]})
            return out
        except brain.BrainError as e:
            log(f"  {brain.name()} couldn't read the cards ({str(e)[:100]}) - using the simple reader")
    return [x for x in (_heuristic(c) for c in cards) if x]


def store_leads(board: dict, found: list[dict]) -> int:
    from .discover import role_regex
    rx = role_regex()
    extra = re.compile(r"fellow|scholar|programme|program|intern|graduate|placement|apprentic|studentship|residency|trainee", re.I)
    new = 0
    for f in found:
        if not (rx.search(f.get("title", "")) or extra.search(f.get("title", ""))):
            continue  # not a job title (menus, blog links...)
        key = re.sub(r"\W+", " ", f"{f['org']}|{f['title']}|{f.get('location', '')}".lower()).strip()
        if not f.get("org") or db.q1("SELECT id FROM leads WHERE key=?", (key,)):
            continue
        db.x("INSERT INTO leads(search_id,site,title,org,location,url,key,first_seen,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
             (board["id"], board["name"], f["title"][:300], f["org"][:200], (f.get("location") or "")[:200], f.get("url", ""), key, db.now(), db.now()))
        new += 1
    return new


# ---------------- tracing a lead to the employer's own site ----------------

def _norm(t: str) -> str:
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", (t or "").lower())
    t = re.sub(r"\b(sr|snr)\b", "senior", t)
    return " ".join(re.findall(r"[a-z0-9+#]+", t))


def same_job(a: str, b: str) -> float:
    x, y = _norm(a), _norm(b)
    if not x or not y:
        return 0.0
    tx, ty = set(x.split()), set(y.split())
    overlap = len(tx & ty) / max(1, min(len(tx), len(ty)))
    return max(SequenceMatcher(None, x, y).ratio(), overlap if len(tx & ty) >= 2 else 0)


def _company(name: str) -> dict | None:
    from .config import companies
    n = name.lower().strip()
    for lst in companies().values():
        if isinstance(lst, list):
            for c in lst:
                if c.get("name", "").lower().strip() == n:
                    return c
    return None


def _match_in(jobs: list[dict], lead: dict) -> dict | None:
    best, score = None, 0.0
    for j in jobs:
        s = same_job(lead["title"], j.get("title", ""))
        if lead.get("location") and j.get("location"):
            ca, cb = scoring.detect_country(lead["location"]), scoring.detect_country(j["location"])
            if ca and cb and ca != cb:
                s -= 0.25
        if s > score:
            best, score = j, s
    return best if score >= 0.72 else None


def _done(lead: dict, status: str, detail: str, opp_id: int | None = None) -> None:
    db.x("UPDATE leads SET status=?, detail=?, opp_id=?, tries=tries+1, updated_at=? WHERE id=?",
         (status, detail[:300], opp_id, db.now(), lead["id"]))


def trace_free(lead: dict, c, log=print) -> bool:
    """No AI needed: guess the company's job system from its name (Greenhouse, Lever, Ashby...) and look there.
    Extra keeps to itself - it reads the company's own site for this one job and doesn't touch your scouts' lists."""
    from .discover import resolve
    comp = _company(lead["org"]) or {}
    if comp.get("ats") in (None, "page", "unknown"):
        comp = resolve(lead["org"], "", c)
    if comp.get("ats") in ("page", "unknown"):
        return False
    jobs = sources.fetch_company(comp, c, log)
    hit = _match_in(jobs, lead)
    if not hit:
        _done(lead, "not_found", f"{comp['name']}'s own job system has {len(jobs)} jobs, but not this one (yet)")
        return True
    _add_match(hit, lead, f"{comp['name']}'s own job system ({comp['ats']})")
    log(f"  ✓ {lead['title']} @ {lead['org']} → {comp['ats']}")
    return True


def _add_match(job: dict, lead: dict, where: str) -> int:
    job = dict(job, source=f"extra · {job.get('source') or 'company site'}")
    oid, _ = opps.upsert(job)
    db.event(oid, "found", f"Extra agent: spotted on {lead['site']}, found on {where}")
    _done(lead, "traced", f"On {where}", oid)
    return oid


TRACE_PROMPT = """For each job below (seen on a job board), find it on the EMPLOYER'S OWN website or job system
(e.g. careers.company.com, Greenhouse, Lever, Ashby, Workday, SmartRecruiters) - never LinkedIn, Indeed,
Glassdoor or another board. Use WebSearch. If you can't find the exact posting, give the company's careers page.

{items}

Return ONLY JSON: [{{"i": <number>, "careers_url": "https://... or empty", "job_url": "https://... or empty"}}]"""


def trace_ai(batch: list[dict], c, log=print) -> int:
    from .discover import resolve
    brain.set_purpose("Extra · job boards", "tracing")
    items = "\n".join(f"{i}. {l['title']} — {l['org']} — {l.get('location') or '?'}" for i, l in enumerate(batch))
    data, _ = brain.ask_json(TRACE_PROMPT.format(items=items), tools=["WebSearch", "WebFetch"], max_turns=25, timeout=1200)
    n = 0
    for d in data if isinstance(data, list) else []:
        i = d.get("i")
        if not isinstance(i, int) or not 0 <= i < len(batch):
            continue
        lead = batch[i]
        cu, ju = (d.get("careers_url") or "").strip(), (d.get("job_url") or "").strip()
        cu = "" if AGGREGATORS.search(cu) else cu
        ju = "" if AGGREGATORS.search(ju) else ju
        if not cu and not ju:
            continue
        e = resolve(lead["org"], cu or ju, c)
        hit = _match_in(sources.fetch_company(e, c, log), lead) if e.get("ats") not in ("page", "unknown") else None
        if not hit and ju:
            hit = {"title": lead["title"], "org": lead["org"], "location": lead.get("location", ""), "url": ju, "apply_url": ju,
                   "source": "company site", "ext_id": ju, "description": f"Seen on {lead['site']}; this is the posting on the employer's own site."}
        if hit:
            _add_match(hit, lead, urlparse(hit.get("url") or ju).hostname or "the employer's site")
            n += 1
        elif cu:
            _done(lead, "not_found", f"Careers page: {cu} - this posting isn't listed there")
    return n


def board_only(lead: dict) -> None:
    """Couldn't find it on the employer's site: still show it, with the board link, clearly marked."""
    if not (settings().get("extra") or {}).get("add_untraced", True):
        _done(lead, "not_found", "Not found on the employer's own site")
        return
    oid, _ = opps.upsert({"title": lead["title"], "org": lead["org"], "location": lead.get("location", ""), "url": lead["url"],
                          "apply_url": lead["url"], "source": f"extra · {lead['site']} only", "ext_id": lead["url"] or lead["key"],
                          "description": f"Only found on {lead['site']} so far - apply there yourself (Career OS never automates job boards)."})
    _done(lead, "board_only", f"Only on {lead['site']} - apply there yourself", oid)


def run(agent: dict, run_log) -> int:
    """The Extra agent: search every board in the board browser, then trace new leads to employers' own sites."""
    from playwright.sync_api import sync_playwright
    init()
    log = run_log.log if hasattr(run_log, "log") else print
    cfg = agent.get("config") or {}
    cfg = json.loads(cfg) if isinstance(cfg, str) else cfg
    todo_boards = db.q("SELECT * FROM boards WHERE enabled=1 ORDER BY id")
    total_new = 0
    if todo_boards and login_open():
        log("  The board sign-in window is open - reading boards next time.")
    elif todo_boards:
        show = bool((settings().get("extra") or {}).get("show_window", False))
        with sync_playwright() as pw:
            ctx = _launch(pw, headless=not show)
            try:
                for b in todo_boards:
                    try:
                        found = read_board(b, ctx, log)
                        new = store_leads(b, found)
                        total_new += new
                        db.x("UPDATE boards SET last_run=?, last_status=?, found=found+?, needs_login=0 WHERE id=?",
                             (db.now(), f"{len(found)} jobs seen, {new} new", len(found), b["id"]))
                    except Exception as e:  # noqa: BLE001
                        db.x("UPDATE boards SET last_run=?, last_status=? WHERE id=?", (db.now(), str(e)[:160], b["id"]))
                        log(f"  x {b['name']}: {str(e)[:150]}")
            finally:
                ctx.close()
    todo = db.q("SELECT * FROM leads WHERE status='new' ORDER BY id LIMIT ?", (int(cfg.get("free_per_run", 60)),))
    traced = 0
    with sources._client() as c:
        rest = []
        for lead in todo:
            try:
                if trace_free(lead, c, log):
                    traced += 1 if db.q1("SELECT status FROM leads WHERE id=?", (lead["id"],))["status"] == "traced" else 0
                    continue
            except Exception as e:  # noqa: BLE001
                log(f"  x {lead['org']}: {str(e)[:120]}")
            rest.append(lead)
        if rest and brain.available():
            per = int(cfg.get("ai_per_run", 16))
            for i in range(0, min(len(rest), per), 8):
                try:
                    traced += trace_ai(rest[i:i + 8], c, log)
                except brain.LimitError:
                    raise
                except brain.BrainError as e:
                    log(f"  AI tracing paused: {str(e)[:150]}")
                    break
        for lead in rest:
            cur = db.q1("SELECT status, tries FROM leads WHERE id=?", (lead["id"],))
            if cur and cur["status"] == "new":
                if brain.available() and cur["tries"] < 1:
                    db.x("UPDATE leads SET tries=tries+1, updated_at=? WHERE id=?", (db.now(), lead["id"]))  # AI gets it next run
                else:
                    board_only(lead)
    log(f"Extra: {total_new} new leads, {traced} traced to employers' own sites")
    return traced


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "login":
        login_main(sys.argv[2])
