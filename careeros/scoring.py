"""Rule-based classification and scoring. Fast, free, explainable.
Claude re-scores the top matches later during 'prepare'."""
from __future__ import annotations

import re
from datetime import date, datetime

from .config import settings

TRACKS = [  # priority order: first match wins as primary track
    ("salesforce", r"salesforce|\bapex\b|\blwc\b|sfdc|agentforce|\bcrm (developer|engineer)|service cloud|sales cloud|marketing cloud|mulesoft|\bveeva\b"),
    ("slack", r"\bslack\b"),
    ("quant", r"\bquant|quantitative|\btrad(er|ing)\b|market[- ]?mak|algorithmic|\balgo (dev|trad)|\bstrats?\b|systematic (trading|equities|strategies)"),
    ("research", r"research (scientist|engineer|fellow|intern|residen)|\bresiden(cy|t)\b|fellowship|\bfellows?\b|research programme|research program"),
    ("ml", r"machine learning|\bml\b|\bai\b|deep learning|\bllms?\b|\bnlp\b|computer vision|applied scientist|\bgenai\b|generative|inference|mlops"),
    ("data", r"data scien|data analy|analytics engineer|data engineer|\bbi developer|business intelligence|statistician"),
    ("systems", r"back[- ]?end|distributed|infrastructure|platform engineer|\bsre\b|site reliability|systems engineer|devops|cloud engineer|low[- ]latency|kernel|database engineer"),
    ("swe", r"software|\bsde\b|\bswe\b|developer|full[- ]?stack|programmer|\bengineer\b|engineering"),
]
TRACK_RE = [(t, re.compile(p, re.I)) for t, p in TRACKS]

LEVEL_GOOD = re.compile(r"\binterns?\b|internship|placement|graduate|new grad|early[- ]career|entry[- ]level|junior|campus|student|\bfellow|\bresiden(cy|t)\b|apprentice|2027|\bassociate\b|\b(i|1)\b\s*$|\bii\b|\b2\b\s*$|university|scholar|bursar", re.I)
LEVEL_BAD = re.compile(r"senior|\bsr\b\.?|\bstaff\b|principal|\blead\b|manager|director|head of|\bvp\b|vice president|distinguished|\biii\b|\biv\b|chief|partner\b|\bexpert\b", re.I)
PHD = re.compile(r"\bph\.?\s?d\b|doctoral|post-?doc", re.I)
NON_TECH = re.compile(r"\bsales\b|account (executive|manager)|recruit|talent acquisition|marketing|\blegal\b|counsel|accountant|payroll|\bnurse\b|clinical|customer success|\bhr\b|office manager|executive assistant|copywriter|paralegal|driver|warehouse|medical|physician|doctor|biolog|chemist|lawyer|finance fellow|nursing|pharma", re.I)
SPONSOR_POS = re.compile(r"visa sponsorship (is )?(available|provided|offered|possible)|(we|will|can) (can |will )?sponsor|sponsorship (is )?available|skilled worker (visa )?sponsor|relocation (and|&) visa", re.I)
SPONSOR_NEG = re.compile(r"(no|not|unable to|cannot|can't|won't|do not|does not) (currently )?(provide |offer |able to )?(offer )?(visa )?sponsor|must (already )?have (the )?(full |existing )?right to work|without (the need for |requiring )?(visa )?sponsorship|not (able|eligible) to sponsor|us citizen(ship)? (is )?required|security clearance", re.I)
SKILLS = re.compile(r"\bpython\b|fastapi|\bllm|agent|salesforce|\bapex\b|distributed|postgres|typescript|react|\bc\+\+|rust|\bjava\b|opengl|gpu|profiling|retrieval|\brag\b|search engine|backend|api", re.I)

COUNTRY_PATTERNS = [
    ("REMOTE", r"\bremote\b|anywhere|worldwide|work from home"),
    ("UK", r"united kingdom|\buk\b|england|scotland|wales|london|edinburgh|glasgow|manchester|cambridge|oxford|bristol|leeds|birmingham|belfast|reading|guildford|\bgb\b|great britain"),
    ("IN", r"india|bengaluru|bangalore|hyderabad|mumbai|pune|gurgaon|gurugram|chennai|noida|delhi|kolkata|ahmedabad"),
    ("IE", r"ireland|dublin|cork"),
    ("US", r"united states|\busa\b|\bu\.s\.|new york|\bnyc\b|san francisco|seattle|chicago|austin|boston|los angeles|mountain view|palo alto|menlo park|sunnyvale|bellevue|denver|miami|washington|atlanta|\b(ca|ny|wa|tx|il|ma|nj|pa)\b"),
    ("DE", r"germany|deutschland|berlin|munich|münchen|frankfurt|hamburg|cologne|köln|stuttgart"),
    ("NL", r"netherlands|amsterdam|rotterdam|eindhoven|utrecht"),
    ("CH", r"switzerland|zurich|zürich|geneva|zug|basel|lausanne"),
    ("FR", r"france|paris|lyon"),
    ("IT", r"italy|italia|milan|milano|rome|roma|turin|torino"),
    ("ES", r"spain|madrid|barcelona"),
    ("SG", r"singapore"),
    ("HK", r"hong kong"),
    ("AE", r"dubai|abu dhabi|united arab emirates|\buae\b"),
    ("AU", r"australia|sydney|melbourne|brisbane|perth"),
    ("CA", r"canada|toronto|vancouver|montreal|ottawa|waterloo|ontario"),
    ("JP", r"japan|tokyo"),
    ("PL", r"poland|warsaw|krakow|kraków|wroclaw"),
    ("SE", r"sweden|stockholm"),
    ("DK", r"denmark|copenhagen"),
    ("PT", r"portugal|lisbon|porto"),
    ("EE", r"estonia|tallinn"),
    ("CN", r"china|shanghai|beijing|shenzhen|hangzhou"),
    ("IL", r"israel|tel aviv"),
    ("KR", r"korea|seoul"),
    ("TW", r"taiwan|taipei"),
    ("AT", r"austria|vienna|wien"),
    ("BE", r"belgium|brussels"),
    ("CZ", r"czech|prague"),
    ("BG", r"bulgaria|sofia"),
    ("RO", r"romania|bucharest"),
    ("NO", r"norway|oslo"),
    ("FI", r"finland|helsinki"),
    ("BR", r"brazil|são paulo|sao paulo"),
]
COUNTRY_RE = [(c, re.compile(p, re.I)) for c, p in COUNTRY_PATTERNS]


def detect_country(location: str) -> str:
    loc = location or ""
    hits = [c for c, r in COUNTRY_RE if r.search(loc)]
    real = [c for c in hits if c != "REMOTE"]
    if real:
        return real[0]
    if hits:
        return "REMOTE"
    return "OTHER"


def detect_track(title: str, desc: str = "") -> str:
    for t, r in TRACK_RE:
        if r.search(title or ""):
            return t
    return ""


def detect_kind(title: str, desc: str = "", default: str = "job") -> str:
    t = (title or "").lower()
    if re.search(r"scholarship|bursar|studentship|grant\b|hardship fund", t):
        return "scholarship"
    if re.search(r"\bfellow|\bresiden(cy|t)\b", t):
        return "fellowship"
    if re.search(r"\binterns?\b|internship|placement|summer (analyst|associate)|\bco-?op\b", t):
        return "internship"
    if re.search(r"apprentice", t):
        return "apprenticeship"
    if re.search(r"graduate|new grad|early career|campus", t):
        return "graduate"
    if re.search(r"part[- ]time|tutor|demonstrator|marker|teaching assistant", t):
        return "parttime"
    if re.search(r"hackathon|competition|challenge|prize", t):
        return "competition"
    return default


_GOAL_CACHE: dict = {"t": 0.0, "rx": []}
GENERIC = {"engineer", "developer", "manager", "analyst", "specialist", "associate", "senior", "junior", "lead", "and", "the", "roles"}


def _goal_patterns() -> list[re.Pattern]:
    """Your own target roles (any field) as title patterns - so a nurse, lawyer or designer gets matched too."""
    import time
    if time.time() - _GOAL_CACHE["t"] < 30:
        return _GOAL_CACHE["rx"]
    from .config import profile
    out = []
    for r in ((profile().get("goals") or {}).get("roles") or []):
        words = [w for w in re.findall(r"[a-z]+", r.lower()) if len(w) > 2 and w not in GENERIC]
        if words:
            out.append(re.compile(r"\b" + r"\b.*\b".join(re.escape(w) for w in words[:2]) + r"", re.I))
    _GOAL_CACHE.update(t=time.time(), rx=out)
    return out


def score(o: dict) -> tuple[int, list[str], str]:
    """Return (score 0-100, reasons, sponsorship yes/no/unknown)."""
    s = settings()
    title = o.get("title") or ""
    desc = (o.get("description") or "")[:20000]
    kind = o.get("kind") or "job"
    reasons: list[str] = []
    pts = 0

    track = o.get("track") or detect_track(title, desc)
    enabled = set(s.get("tracks_enabled") or [])
    goal_hit = any(rx.search(title) for rx in _goal_patterns())
    if goal_hit:
        pts += 35
        reasons.append("your target role")
    elif track and (track in enabled or kind in ("fellowship", "scholarship", "competition", "parttime", "apprenticeship")):
        pts += 32
        reasons.append(f"track:{track}")
    elif kind in ("fellowship", "scholarship", "competition", "parttime", "apprenticeship"):
        pts += 25
    else:
        reasons.append("no target track in title")

    if NON_TECH.search(title) and track not in ("salesforce", "quant") and not goal_hit:
        pts -= 60
        reasons.append("non-technical role")

    if LEVEL_GOOD.search(title):
        pts += 20
        reasons.append("right level")
    if LEVEL_BAD.search(title) and not re.search(r"salesforce", title, re.I):
        pts -= 45
        reasons.append("too senior")
    if PHD.search(title):
        pts -= 25
        reasons.append("PhD required")

    country = o.get("country") or detect_country(o.get("location") or "")
    cw = s.get("country_weights_goal") or s.get("country_weights") or {}
    w = cw.get(country, cw.get("OTHER", 0))
    pts += int(w)
    reasons.append(f"{country}+{w}")

    sponsorship = o.get("sponsorship") or "unknown"
    if SPONSOR_NEG.search(desc):
        sponsorship = "no"
        pts -= 22
        reasons.append("says no sponsorship")
    elif SPONSOR_POS.search(desc):
        sponsorship = "yes"
        pts += 10
        reasons.append("sponsors visas")

    if kind in ("fellowship", "scholarship"):
        pts += 15
    skill_hits = len(set(m.group(0).lower() for m in SKILLS.finditer(desc)))
    if skill_hits:
        pts += min(10, skill_hits * 2)
        reasons.append(f"{skill_hits} skill matches")

    dl = o.get("deadline")
    if dl:
        try:
            d = datetime.fromisoformat(str(dl)[:10]).date()
            days = (d - date.today()).days
            if days < 0:
                pts -= 100
                reasons.append("deadline passed")
            elif days <= 14:
                pts += 6
                reasons.append(f"closes in {days}d")
        except ValueError:
            pass

    return max(0, min(100, pts)), reasons, sponsorship
