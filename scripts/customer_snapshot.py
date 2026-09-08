"""Freeze the customer dashboard's data. Seeds the demo history on a running fixture-mode server, reads back the state and
the audit rows, and writes fixtures/pay/customer_snapshot.json. The customer dashboard renders from that file, so nothing
that happens on the bank dashboard, the terminal or a reseed moves it. Run: BASE=http://127.0.0.1:8017 python3 scripts/customer_snapshot.py"""
import json, os, sys, urllib.request
BASE = os.environ.get("BASE", "http://127.0.0.1:8014")
def call(method, path):
    req = urllib.request.Request(BASE + path, method=method, headers={"Content-Type": "application/json"}, data=b"{}" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)
seed = call("POST", "/api/demo/seed?stage=history")
state = call("GET", "/api/state"); audit = call("GET", "/api/audit")
keep = {k: state[k] for k in ("passports", "products", "violations", "payments", "decisions", "incidents", "alerts", "mandate_draft", "agent_draft", "policy", "failure_classes", "cast", "companies_house_mode")}
keep["registrations"] = [{k: v for k, v in a.items() if k != "review"} for a in state["registrations"]]
out = {"_comment": "Static data for the customer dashboard, frozen from the demo history seed. Timestamps are rebased to today when served (GET /api/customer/snapshot).", "seeded": seed["history"], "state": keep, "audit": audit}
p = os.path.join(os.path.dirname(__file__), "..", "fixtures", "pay", "customer_snapshot.json")
json.dump(out, open(p, "w"), indent=1); print("wrote", os.path.abspath(p), len(audit["rows"]), "rows")
