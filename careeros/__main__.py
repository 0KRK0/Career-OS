"""Career OS command line.

  python -m careeros                 start the app (http://127.0.0.1:8765) + scheduler
  python -m careeros status          counts, next runs, Claude/Gmail status
  python -m careeros scout           run every enabled scout now (waits)
  python -m careeros agents          list agents
  python -m careeros run <agent-id>  run one agent now (waits)
  python -m careeros add-agent "<field>" "<country>" [kinds]   new research agent
  python -m careeros list [status] [limit]                     e.g. list ready 20
  python -m careeros prepare <id>|top <N>                      draft cover letters
  python -m careeros fill <id> [<id> ...]                      open + autofill in the browser
  python -m careeros email           check Gmail now
  python -m careeros learned         what the autofill has learned from you
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import webbrowser

from . import agents, db, opps
from .config import LOG_DIR, ROOT, settings


def _print_rows(rows, cols):
    for r in rows:
        print("  " + " | ".join(str(r.get(c, ""))[:60] for c in cols))


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv and not argv[0].startswith("--") else "serve"
    db.conn()
    agents.ensure_defaults()
    if cmd == "serve":
        import uvicorn
        from .server import app
        port = int(settings().get("port", 8765))
        url = f"http://127.0.0.1:{port}/"
        if "--no-browser" not in argv:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        print(f"Career OS running at {url}  (Ctrl+C to stop)")
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return 0
    if cmd == "status":
        print(json.dumps(opps.stats(), indent=2))
        from . import brain
        print("claude:", brain.status())
        return 0
    if cmd == "scout":
        started = agents.run_all_scouts(slot_index=None, wait=True)
        opps.rescore_all()
        for a in agents.all_agents():
            if a["id"] in started:
                print(f"  {a['name']}: {a['last_status']} ({a['last_found']} new)")
        return 0
    if cmd == "agents":
        _print_rows(agents.all_agents(), ["id", "name", "kind", "enabled", "last_run", "last_status", "last_found"])
        return 0
    if cmd == "run":
        agents.run_agent(int(argv[1]), wait=True)
        r = db.q1("SELECT log FROM runs WHERE agent_id=? ORDER BY id DESC LIMIT 1", (int(argv[1]),))
        print(r["log"] if r else "")
        return 0
    if cmd == "add-agent":
        cfg = {"field": argv[1], "country": argv[2], "kinds": argv[3] if len(argv) > 3 else "jobs, internships, graduate roles", "slots": 1}
        aid = db.x("INSERT INTO agents(name,kind,config,enabled,on_schedule,created_at) VALUES(?,?,?,?,?,?)",
                   (f"Research · {argv[1]} ({argv[2]})", "research", json.dumps(cfg), 1, 1, db.now()))
        print(f"agent {aid} created")
        return 0
    if cmd == "list":
        st = argv[1] if len(argv) > 1 else "new,shortlisted,ready"
        lim = int(argv[2]) if len(argv) > 2 else 30
        _print_rows(opps.listing(status=st, limit=lim), ["id", "score", "kind", "title", "org", "country", "deadline", "status"])
        return 0
    if cmd == "prepare":
        from . import prepare
        if argv[1] == "top":
            a = agents.agent_by_kind("prepare")
            a["config"]["top"] = int(argv[2])
            db.x("UPDATE agents SET config=? WHERE id=?", (json.dumps(a["config"]), a["id"]))
            agents.run_agent(a["id"], wait=True)
        else:
            d = prepare.prepare(int(argv[1]))
            print(d.get("cover_letter", ""))
        return 0
    if cmd == "fill":
        for i in argv[1:]:
            o = opps.get(int(i))
            if o:
                db.x("INSERT INTO fill_requests(opp_id,url,status,created_at) VALUES(?,?,?,?)",
                     (o["id"], o["apply_url"] or o["url"], "pending", db.now()))
        hb = db.kv_get("filler_heartbeat", 0) or 0
        if not hb or time.time() - float(hb) > 15:
            log = open(LOG_DIR / "filler.out.log", "a", encoding="utf-8")
            subprocess.Popen([sys.executable, "-m", "careeros.filler"], cwd=str(ROOT), stdout=log, stderr=log)
        print("queued - the browser window will open")
        return 0
    if cmd == "email":
        from . import mail
        print(mail.check())
        return 0
    if cmd == "learned":
        _print_rows(db.q("SELECT label,value,source,uses FROM answers ORDER BY updated_at DESC"), ["label", "value", "source", "uses"])
        return 0
    print(__doc__)
    return 0 if cmd in ("help", "-h") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
