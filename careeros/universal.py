"""Everything that turns a person's goals into a working setup: which agents run,
how matches are scored, and which Learn tracks they start with. Nothing here is
specific to one user - it all derives from profile.yaml (written by the setup wizard)."""
from __future__ import annotations

import re

from .config import profile, save_settings, settings

COUNTRIES = {
    "United Kingdom": "UK", "India": "IN", "United States": "US", "Ireland": "IE", "Germany": "DE",
    "Netherlands": "NL", "Switzerland": "CH", "France": "FR", "Italy": "IT", "Spain": "ES", "Poland": "PL",
    "Sweden": "SE", "Denmark": "DK", "Portugal": "PT", "Austria": "AT", "Belgium": "BE", "Singapore": "SG",
    "Hong Kong": "HK", "UAE": "AE", "Australia": "AU", "Canada": "CA", "Japan": "JP", "China": "CN",
    "Israel": "IL", "Remote": "REMOTE",
}
REGIONS = {"Europe": ["IE", "DE", "NL", "CH", "FR", "IT", "ES", "PL", "SE", "DK", "PT", "AT", "BE"],
           "Anywhere": list(COUNTRIES.values())}
ADZUNA = {"UK": "gb", "IN": "in", "US": "us", "DE": "de", "IT": "it", "NL": "nl", "AU": "au", "SG": "sg",
          "CA": "ca", "FR": "fr", "AT": "at", "CH": "ch", "ES": "es", "PL": "pl", "BE": "be"}

# role -> learn tracks, scout groups, scoring tracks, research wording
ROLES: dict[str, dict] = {
    "Software Engineer": {"tracks": ["swe"], "groups": ["bigtech_ai", "uk_eu", "india"], "score": ["swe", "systems"],
                          "field": "graduate and early-career software engineer roles",
                          "extra": "Prioritise employers whose career sites the scouts can't read: Google, Microsoft, Amazon, Meta, Apple, Bloomberg, Revolut, Arm, Goldman Sachs, J.P. Morgan, Morgan Stanley and large local employers."},
    "Backend / Platform Engineer": {"tracks": ["swe"], "groups": ["bigtech_ai", "uk_eu"], "score": ["swe", "systems"],
                                    "field": "backend, platform, infrastructure and site-reliability engineer roles"},
    "ML / AI Engineer": {"tracks": ["ml_engineer"], "groups": ["bigtech_ai"], "score": ["ml"],
                         "field": "machine learning / AI / LLM engineer roles"},
    "Research Scientist": {"tracks": ["research"], "groups": ["bigtech_ai"], "score": ["research", "ml"],
                           "field": "AI/ML research scientist and research engineer roles, research internships and AI residencies"},
    "Quant Developer": {"tracks": ["quant_dev"], "groups": ["quant"], "score": ["quant", "systems"],
                        "field": "quant developer and low-latency developer roles at trading firms",
                        "extra": "Focus on firms WITHOUT public job-board APIs (the scouts already read Jane Street, HRT, Jump, IMC, Optiver, DRW, Tower, Squarepoint, XTX, Qube, Man Group): Citadel, Citadel Securities, SIG, Two Sigma, D. E. Shaw, G-Research, Millennium, Marshall Wace, Da Vinci, Balyasny, bank strats programmes."},
    "Quant Researcher": {"tracks": ["quant_researcher"], "groups": ["quant"], "score": ["quant", "research"],
                         "field": "quantitative researcher roles and internships at trading firms and hedge funds",
                         "extra": "Include firms without public job boards: Citadel, SIG, Two Sigma, D. E. Shaw, G-Research, Millennium, WorldQuant, Graviton, Quadeye, NK Securities."},
    "Quant Trader": {"tracks": ["quant_trader", "trading"], "groups": ["quant"], "score": ["quant"],
                     "field": "quantitative trader roles, trading internships and graduate trading programmes"},
    "Data Scientist": {"tracks": ["data_scientist"], "groups": ["bigtech_ai", "uk_eu"], "score": ["data", "ml"],
                       "field": "data scientist roles"},
    "Data Analyst": {"tracks": ["data_scientist"], "groups": ["uk_eu"], "score": ["data"],
                     "field": "data analyst and analytics roles"},
    "Data Engineer": {"tracks": ["data_scientist", "swe"], "groups": ["bigtech_ai", "uk_eu"], "score": ["data", "systems"],
                      "field": "data engineer roles"},
    "Salesforce Developer": {"tracks": ["salesforce"], "groups": ["salesforce"], "score": ["salesforce"],
                             "field": "Salesforce developer, Salesforce engineer and Agentforce roles"},
    "Slack Developer": {"tracks": ["slack"], "groups": ["salesforce"], "score": ["slack"],
                        "field": "Slack platform developer and Slack app developer roles"},
    "Trading / Markets": {"tracks": ["trading"], "groups": ["quant"], "score": ["quant"],
                          "field": "trading, markets and investment analyst roles"},
    "Product Manager": {"tracks": [], "groups": ["bigtech_ai", "uk_eu"], "score": ["swe"],
                        "field": "associate product manager and product manager roles", "custom_track": "Product Management"},
    "DevOps / SRE": {"tracks": ["swe"], "groups": ["bigtech_ai"], "score": ["systems"],
                     "field": "DevOps, cloud and site-reliability engineering roles"},
    "Cybersecurity": {"tracks": [], "groups": ["bigtech_ai"], "score": ["systems"],
                      "field": "security engineer and cybersecurity analyst roles", "custom_track": "Cybersecurity"},
}

# role -> sectors whose top employers we look up (Company finder)
SECTORS = ["Big Tech", "AI labs & AI startups", "Quant trading & market makers", "Hedge funds & asset managers",
           "Investment banks & financial services", "Fintech", "SaaS & developer tools", "E-commerce & consumer internet",
           "Consulting & IT services", "Salesforce partners & ISVs", "Gaming & media", "Semiconductors & hardware",
           "Healthcare & biotech", "Public sector & research institutes"]
ROLE_SECTORS = {
    "Software Engineer": ["Big Tech", "AI labs & AI startups", "Fintech", "SaaS & developer tools", "E-commerce & consumer internet"],
    "Backend / Platform Engineer": ["Big Tech", "SaaS & developer tools", "Fintech"],
    "ML / AI Engineer": ["Big Tech", "AI labs & AI startups"],
    "Research Scientist": ["AI labs & AI startups", "Public sector & research institutes"],
    "Quant Developer": ["Quant trading & market makers", "Hedge funds & asset managers"],
    "Quant Researcher": ["Quant trading & market makers", "Hedge funds & asset managers"],
    "Quant Trader": ["Quant trading & market makers", "Investment banks & financial services"],
    "Data Scientist": ["Big Tech", "Fintech", "E-commerce & consumer internet"],
    "Data Analyst": ["Consulting & IT services", "Fintech", "E-commerce & consumer internet"],
    "Data Engineer": ["Big Tech", "SaaS & developer tools", "Fintech"],
    "Salesforce Developer": ["Salesforce partners & ISVs", "Consulting & IT services"],
    "Slack Developer": ["Salesforce partners & ISVs", "SaaS & developer tools"],
    "Trading / Markets": ["Investment banks & financial services", "Hedge funds & asset managers"],
    "Product Manager": ["Big Tech", "SaaS & developer tools", "Fintech"],
    "DevOps / SRE": ["Big Tech", "SaaS & developer tools"],
    "Cybersecurity": ["Big Tech", "Investment banks & financial services", "Consulting & IT services"],
}


def sectors_for(p: dict | None = None) -> list[str]:
    """Sectors you chose, else the ones your roles imply (roles we don't know become their own sector)."""
    p = p or profile()
    g = p.get("goals") or {}
    if g.get("sectors"):
        return list(g["sectors"])
    out: list[str] = []
    for r in g.get("roles") or []:
        for sct in ROLE_SECTORS.get(r) or [f"Top employers of {r}"]:
            if sct not in out:
                out.append(sct)
    return out[:8]


DEGREES = [  # regex on the degree field -> mandatory Learn tracks
    (r"computer|comput|software|informatic|\bit\b|information tech|artificial|\bai\b|data sci|cyber", ["maths", "probability", "cs", "dsa", "software", "interview"]),
    (r"math|statistic|physics|actuar", ["maths", "probability", "dsa", "interview"]),
    (r"electr|electronic|mechanic|civil|engineer", ["maths", "cs", "dsa", "software", "interview"]),
    (r"financ|econom|account|business|commerce|management|mba", ["probability", "maths", "interview"]),
]


def role_info(name: str) -> dict:
    if name in ROLES:
        return ROLES[name]
    low = name.lower()
    for k, v in ROLES.items():
        if k.lower().split(" ")[0] in low:
            return v
    return {"tracks": [], "groups": ["bigtech_ai"], "score": ["swe"], "field": f"{name} roles", "custom_track": name}


def country_codes(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names or []:
        if n in REGIONS:
            out += REGIONS[n]
        elif n in COUNTRIES:
            out.append(COUNTRIES[n])
        elif n.upper() in COUNTRIES.values():
            out.append(n.upper())
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def degree_tracks(p: dict | None = None) -> list[str]:
    p = p or profile()
    fields = " ".join(str(e.get("field", "")) + " " + str(e.get("level", "")) for e in (p.get("education") or []))
    fields += " " + str(p.get("discipline", ""))
    for rx, tracks in DEGREES:
        if re.search(rx, fields, re.I):
            return tracks
    return ["maths", "interview"]


def default_learn_tracks(p: dict | None = None) -> list[str]:
    p = p or profile()
    out = list(degree_tracks(p))
    for r in (p.get("goals") or {}).get("roles") or []:
        for t in role_info(r).get("tracks", []):
            if t not in out:
                out.append(t)
    return out


def custom_tracks_needed(p: dict | None = None) -> list[str]:
    p = p or profile()
    return [role_info(r)["custom_track"] for r in (p.get("goals") or {}).get("roles") or [] if role_info(r).get("custom_track")]


def generate_agents(p: dict | None = None) -> list[dict]:
    """The agent line-up for this person."""
    p = p or profile()
    g = p.get("goals") or {}
    roles = g.get("roles") or ["Software Engineer"]
    kinds = g.get("kinds") or ["job", "internship", "graduate", "fellowship", "scholarship"]
    codes = country_codes(g.get("countries") or ["Remote"])
    names = [k for k, v in COUNTRIES.items() if v in codes]
    where = ", ".join(n for n in (g.get("countries") or names)) or "worldwide"
    groups: list[str] = ["bigtech_ai"]
    for r in roles:
        for grp in role_info(r)["groups"]:
            if grp == "india" and "IN" not in codes:
                continue
            if grp == "uk_eu" and not (set(codes) & set(["UK", "REMOTE"] + REGIONS["Europe"])):
                continue
            if grp not in groups:
                groups.append(grp)
    if "IN" in codes and "india" not in groups:
        groups.append("india")
    label = {"bigtech_ai": "Big tech & AI labs", "quant": "Quant & trading firms", "uk_eu": "UK/EU fintech & startups",
             "salesforce": "Salesforce ecosystem", "india": "India high-pay tech"}
    agents: list[dict] = [{"name": f"Scout · {label[gr]}", "kind": "ats", "config": {"groups": [gr]}} for gr in groups]
    kw = [re.sub(r"[/()]", " ", r).split()[0].lower() for r in roles]
    agents.append({"name": "Scout · Open job feeds (EU + remote)", "kind": "feeds",
                   "config": {"arbeitnow": bool(set(codes) & set(REGIONS["Europe"] + ["REMOTE"])), "himalayas": True,
                              "remotive": list(dict.fromkeys([role_info(r)["field"].split(" roles")[0].split(",")[0][:40] for r in roles]))[:6],
                              "jobicy": list(dict.fromkeys(kw))[:4]}})
    queries = [re.sub(r"\s*/.*", "", r).lower() for r in roles][:7]
    az = [ADZUNA[c] for c in codes if c in ADZUNA][:10]
    if az:
        agents.append({"name": "Scout · Adzuna (" + ", ".join(a.upper() for a in az) + ")", "kind": "adzuna", "enabled": 0,
                       "config": {"countries": az, "queries": queries}})
    if "UK" in codes:
        agents.append({"name": "Scout · Reed (UK)", "kind": "reed", "enabled": 0, "config": {"queries": queries}})
    for r in roles[:8]:
        info = role_info(r)
        agents.append({"name": f"Research · {r} ({where})", "kind": "research",
                       "config": {"field": info["field"], "country": where,
                                  "kinds": "jobs, internships, graduate roles", "extra": info.get("extra", ""), "slots": 1}})
    edu = (p.get("education") or [{}])[0] if p.get("education") else {}
    if "fellowship" in kinds:
        agents.append({"name": "Research · Paid fellowships & programmes (worldwide)", "kind": "research",
                       "config": {"field": f"paid fellowships, residencies and stipended programmes relevant to {', '.join(roles[:4])}",
                                  "country": f"worldwide ({where} first)", "kinds": "fellowships, residencies, stipends", "slots": 1}})
    if "scholarship" in kinds:
        who = " ".join(x for x in [edu.get("level", ""), edu.get("field", ""), "student"] if x)
        at = f" at {edu['school']}" if edu.get("school") else ""
        agents.append({"name": "Research · Scholarships, bursaries & hardship funds", "kind": "research",
                       "config": {"field": f"scholarships, bursaries, prizes and hardship funds for a {who}{at}",
                                  "country": p.get("country") or where, "kinds": "scholarships, bursaries, grants, prizes", "slots": 1}})
    if "parttime" in kinds:
        notes = (p.get("work_rights") or {}).get("notes", "")
        agents.append({"name": f"Research · Part-time work ({p.get('city') or where})", "kind": "research",
                       "config": {"field": "part-time paid work: university tutoring, demonstrating, marking, research assistant and part-time tech roles"
                                           + (f" ({notes})" if notes else ""),
                                  "country": p.get("location") or where, "kinds": "part-time jobs", "slots": 1}})
    if "competition" in kinds:
        agents.append({"name": "Research · Hackathons & competitions with cash prizes", "kind": "research",
                       "config": {"field": "hackathons, coding/ML competitions and bug bounties with cash prizes",
                                  "country": f"online / {p.get('country') or where}", "kinds": "competitions, hackathons, prizes", "slots": 1}})
    for sct in sectors_for(p):
        agents.append({"name": f"Company finder · {sct}", "kind": "discover",
                       "config": {"sector": sct, "n": 100}})
    from .discover import KIND_LABELS
    for k in kinds:
        if k in KIND_LABELS:
            agents.append({"name": f"Programme finder · {KIND_LABELS[k][0].upper() + KIND_LABELS[k][1:]}", "kind": "programs",
                           "config": {"kind": k, "n": 100}})
    agents += [
        {"name": "Fixer · Repair broken company job boards", "kind": "sources_fix", "on_schedule": 0, "config": {}},
        {"name": "Writer · Draft cover letters for top new matches", "kind": "prepare", "on_schedule": 0, "config": {}},
        {"name": "Tracker · Gmail (statuses + follow-ups)", "kind": "email", "on_schedule": 1, "config": {}},
        {"name": "Watcher · Deadlines & daily digest", "kind": "deadlines", "on_schedule": 1, "config": {}},
    ]
    return agents


def goal_weights(p: dict | None = None) -> dict:
    """Only the scoring parts (country weights + scored tracks) - used to upgrade older installs."""
    p = p or profile()
    g = p.get("goals") or {}
    codes = country_codes(g.get("countries") or [])
    weights = {"OTHER": 1}
    for i, c in enumerate(codes):
        weights[c] = max(10, 20 - 2 * i)
    tracks: list[str] = []
    for r in g.get("roles") or []:
        for t in role_info(r)["score"]:
            if t not in tracks:
                tracks.append(t)
    out = {}
    if codes:
        out["country_weights_goal"] = weights
    if tracks:
        out["tracks_enabled"] = tracks
    return out


def apply_goals_to_settings(p: dict | None = None) -> dict:
    """Scoring weights, scored tracks and the default filter view from the goals."""
    p = p or profile()
    g = p.get("goals") or {}
    codes = country_codes(g.get("countries") or [])
    weights = {"OTHER": 1}
    for i, c in enumerate(codes):
        weights[c] = max(10, 20 - 2 * i)
    score_tracks: list[str] = []
    for r in g.get("roles") or []:
        for t in role_info(r)["score"]:
            if t not in score_tracks:
                score_tracks.append(t)
    s = settings()
    new = {"country_weights_goal": weights if codes else None,
           "tracks_enabled": score_tracks or s.get("tracks_enabled"),
           "filters": {**(s.get("filters") or {}), "countries": codes, "kinds": g.get("kinds") or []},
           "learn": {**(s.get("learn") or {}), "selected": default_learn_tracks(p)}}
    return save_settings(new)
