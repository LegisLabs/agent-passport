"""Payments vertical: oracle against the bank-side verifier, envelope invariants, ledger,
incidents, audit replay, vouch fixture adapter. Runs fully offline (fixture extraction, fixture vouch)."""
import json
import os
import tempfile
from pathlib import Path

os.environ["PAY_DATA_DIR"] = tempfile.mkdtemp()
os.environ["EXTRACTION_MODE"] = "fixture"
os.environ["VOUCH_MODE"] = "fixture"
os.environ["PAYMENT_RAIL"] = "local"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pay import crypto, db, rules, vouch  # noqa: E402
from pay.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ORACLE = json.loads((ROOT / "fixtures" / "pay" / "oracle.json").read_text())["cases"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def issue_one(client, sign_mandate=True):
    """Drive the whole path: the provider files an AI product → the bank admits it → the customer registers its AI agent (→ signs the mandate)."""
    a = client.post("/api/registrations").json()
    assert a["ref"].startswith("REG-2026-") and a["entry_mode"] == "form"
    a = client.post(f"/api/registrations/{a['id']}/prefill").json()
    assert a["entry_mode"] == "prefill"
    a = client.post(f"/api/registrations/{a['id']}/submit").json()
    flagged = {c["id"] for c in a["checks"] if c["result"] != "pass"}
    assert flagged == set(), flagged
    r = client.post(f"/api/registrations/{a['id']}/admission", json={"decision": "admit", "note": "All six checks pass. Ceilings per policy; condition £5,000."}).json()
    assert r["product"]["admission_status"] == "admitted" and "passport" not in r
    p = client.post("/api/agents", json={"registration_id": a["id"]}).json()
    assert p["passport_id"].startswith("AG-2026-") and p["agent"]["pop_verified"] is True and "private_pem" not in p["agent"]
    assert p["status"] == "pending" and p["envelope"]["admission"] is None and p["vouch_voucher_id"] is None   # an agent record: no passport, no voucher before the mandate
    if sign_mandate:
        p = client.post(f"/api/passports/{p['passport_id']}/mandate/sign").json()
        assert p["passport_id"].startswith("AP-2026-") and p["status"] == "active" and p["envelope"]["admission"] and p["vouch_voucher_id"]   # signing issues the passport and mints the voucher
    return p, a


@pytest.fixture(scope="module")
def issued(client):
    return issue_one(client)


def act(client, pid, case, signer=None, currency=None):
    body = {"passport_id": pid, "action_type": case["action_type"], "supplier_name": case["supplier_name"], "payee_account_ref": case["payee_account_ref"],
            "amount": case["amount"], "invoice_ref": case.get("invoice_ref", "INV-1"), "signer": signer or case.get("signer", "agent"), "currency": currency or case.get("currency", "GBP")}
    return client.post("/api/agent/act", json=body).json()


def test_envelope_three_signers_and_minimal(client, issued):
    p, a = issued
    env = p["envelope"]
    ver = crypto.verify_envelope(env)
    assert ver["ok"] and ver["failure"] is None
    assert crypto.verify_jwt("bank", env["admission"])["jti"] == p["passport_id"]
    assert crypto.verify_jwt("northgate", env["agent_identity"])["cnf"]["jwk"]["kty"] == "OKP"
    assert crypto.verify_jwt("northgate", env["mandate"])["passport_id"] == p["passport_id"]
    # each JWT only verifies against its own signer
    assert crypto.verify_jwt("northgate", env["admission"]) is None
    assert crypto.verify_jwt("bank", env["mandate"]) is None
    assert crypto.verify_jwt("bank", env["admission"])["product_ref"]["product_id"] == "openpay-paygpt-6"
    # assurance binds the exact agent_identity it was issued for
    assert crypto.verify_jwt("bank", env["admission"])["binds"]["agent_identity_sha256"] == crypto.sha256_hex(env["agent_identity"])
    # no bank details of the customer, no email, no personal contact data in any JWT
    blob = json.dumps([crypto.decode_unverified(env[k])[1] for k in ("admission", "agent_identity", "mandate")])
    assert "@" not in blob and "email" not in blob
    assert env["cnf"] is None and env["vouch_voucher_id"]


@pytest.mark.parametrize("case", ORACLE, ids=[c["id"] for c in ORACLE])
def test_oracle(client, issued, case):
    p, _ = issued
    pid = p["passport_id"]
    if case["passport_status"] == "revoked" or case["mandate"] == "unsigned" or case.get("ledger_before") or case.get("daily_before"):
        p, _ = issue_one(client, sign_mandate=case["mandate"] == "signed")  # isolated passport for terminal / stateful cases
        pid = p["passport_id"]
    if case.get("ledger_before"):
        db.insert_payment(pid, case["payee_account_ref"], float(case["ledger_before"]), "GBP", "seed", None, "local", None)
    for k in range(int(case.get("daily_before") or 0)):
        db.insert_payment(pid, case["payee_account_ref"], 10.0, "GBP", f"seed-{k}", None, "local", None)
    if case.get("replay"):
        first = act(client, pid, case); assert first["decision"] == "ALLOW", first
    if case["passport_status"] != "active":
        client.post(f"/api/passports/{pid}/status", json={"status": case["passport_status"], "reason": f"oracle {case['id']}"})
    try:
        if case.get("tamper"):
            env = dict(db.get_passport(pid) and client.get(f"/api/passports/{pid}").json()["envelope"])
            env[case["tamper"]] = env[case["tamper"]][:-4] + "AAAA"
            pa = db.get_passport(pid)["agent"]
            req = {"passport_id": pid, "action_type": case["action_type"], "payee_account_ref": case["payee_account_ref"], "supplier_name": case["supplier_name"],
                   "amount": case["amount"], "currency": "GBP", "invoice_ref": "INV-T", "nonce": "n"}
            req["agent_signature"] = crypto.sign_bytes(pa["private_pem"], rules.request_signing_input(req))
            res = client.post("/api/verify", json={"passport_id": pid, "instruction": req, "passport": env}).json()
        elif case.get("replay"):
            res = client.post("/api/agent/replay", json={"passport_id": pid}).json()
        else:
            res = act(client, pid, case)
        assert res["decision"] == case["expected_decision"], res
        assert res["rule"] == case["expected_rule"], res
        assert res["code"] == case["expected_code"], res
        assert res["receipt"]
        assert client.get("/api/receipt/verify", params={"token": res["receipt"]}).json()["verified"] is True
        if res["decision"] == "ALLOW":
            assert res["settlement"]["rail"] == "local"
    finally:
        if case["passport_status"] == "suspended":
            client.post(f"/api/passports/{pid}/status", json={"status": "active", "reason": "oracle reinstate"})


def test_ledger_limit_in_mandate_total_at_bank(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    fen = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 4900}
    decisions = [act(client, pid, fen)["decision"] for _ in range(5)]
    assert decisions == ["ALLOW", "ALLOW", "ALLOW", "ALLOW", "DENY"]  # 19,600 allowed, 24,500 refused
    full = client.get(f"/api/passports/{pid}").json()
    assert full["ledger"]["60-11-22 10101010"]["total"] == 19600 and full["payments"] == 4
    # another account is unaffected
    assert act(client, pid, {**fen, "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455"})["decision"] == "ALLOW"


def test_three_denies_escalate_to_supervisor(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    bad = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 99887766", "amount": 100}
    r1, r2, r3 = (act(client, pid, bad) for _ in range(3))
    assert r1["incident"] is None and r2["incident"] is None and r3["incident"]["denies"] == 3
    incidents = client.get("/api/state").json()["incidents"]
    assert any(i["subject"] == pid and i["entry"]["event"] == "incident raised to the bank's payments risk team" for i in incidents)
    assert act(client, pid, bad)["incident"] is None  # counter restarts after the incident


def test_customer_signature_completes_envelope(client):
    p, _ = issue_one(client, sign_mandate=False)
    pid = p["passport_id"]
    assert p["mandate_signed"] is False and client.get(f"/api/passports/{pid}").json()["verification"]["failure"] == "admission"
    fen = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 3200}
    r = act(client, pid, fen); assert r["rule"] == "R.1" and r["code"] == "PASSPORT_NOT_ISSUED"
    pid = client.post(f"/api/passports/{pid}/mandate/sign").json()["passport_id"]
    assert pid.startswith("AP-2026-") and client.get(f"/api/passports/{pid}").json()["verification"]["ok"] is True
    assert act(client, pid, fen)["decision"] == "ALLOW"
    assert client.post(f"/api/passports/{pid}/mandate/sign").status_code == 400


def test_revocation_propagates_to_vouch_fixture(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    assert p["vouch_mode"] == "fixture" and p["vouch_status"] == "ACTIVE"
    p = client.post(f"/api/passports/{pid}/status", json={"status": "revoked", "reason": "misuse detected"}).json()
    assert p["vouch_status"] == "REVOKED"
    assert client.get(f"/api/passports/{pid}/vouch").json()["live"]["status"] == "REVOKED"
    assert client.post(f"/api/passports/{pid}/status", json={"status": "active", "reason": "undo"}).status_code == 400


def test_audit_chain_and_replay(client):
    a = client.get("/api/audit").json()
    assert a["chain"]["ok"] is True and a["chain"]["length"] > 20
    verify_rows = [r for r in a["rows"] if r["kind"] == "verify"]
    assert verify_rows
    for r in verify_rows[:15]:
        rp = client.post(f"/api/audit/{r['id']}/replay").json()
        assert rp["identical"] is True, rp


def test_rule_pack_labels_and_codes():
    pack = rules.pack()
    for r in pack["registration_rules"] + pack["runtime_rules"]:
        assert r["status"] in ("CURRENT", "PROTOTYPE", "FUTURE") and r["source"]
    assert [r["id"] for r in pack["runtime_rules"]] == [f"R.{i}" for i in range(1, 10)]
    assert [r["id"] for r in pack["registration_rules"]] == [f"F.{i}" for i in range(1, 7)]


def test_vouch_fixture_adapter_never_touches_network():
    assert vouch.mode() == "fixture"
    fake = {"passport_id": "AP-2026-9999", "mandate_proposed": {"customer": {"legal_name": "X"}, "authorization_details": [{"currency": "GBP", "per_payment_limit": {"amount": 1}, "monthly_limit_per_account": {"amount": 2}}]},
            "agent_identity": {"agent": {"name": "A", "agent_id": "a"}}}
    m = vouch.mint_mandate(fake)
    assert m["mode"] == "fixture" and m["voucher_id"].startswith("VCH-FIX") and m["request"]["metadata"]["passport_id"] == "AP-2026-9999"
    assert vouch.revoke_mandate(m["voucher_id"])["status"] == "REVOKED"
    assert vouch.settle_payment({"amount": 1})["rail"] == "local"


def test_no_verdict_vocabulary_in_fixture_note():
    from pay import extraction
    facts = extraction.fixture()
    checks = rules.run_registration_checks(facts)
    note, _ = extraction.draft_file_note("REG-TEST", facts, checks)
    for banned in ("approve", "reject", "recommend", "admit", "decline"):
        assert banned not in note.lower()


def test_duplicate_product_id_flags_f6():
    from pay import extraction
    facts = extraction.fixture()
    facts["product"]["product_id"]["value"] = "openpay-5-6"   # already on the register, active
    checks = rules.run_registration_checks(facts)
    assert next(c for c in checks if c["id"] == "F.6")["result"] == "flag"
    facts["product"]["product_id"]["value"] = "openpay-5-5"   # lapsed registration does not block
    assert next(c for c in rules.run_registration_checks(facts) if c["id"] == "F.6")["result"] == "pass"
def test_verify_accepts_flat_contract_and_aliases(client):
    """The brief's POST /api/verify shape: flat instruction fields + agent_signature → decision, rule_id, reason, audit_ref, receipt."""
    p, _ = issue_one(client)
    pa = db.get_passport(p["passport_id"])["agent"]
    flat = {"passport_id": p["passport_id"], "action_type": "pay_invoice", "payee_account_ref": "60-11-22 10101010", "supplier_name": "Fenwick Timber Ltd",
            "amount": 3200, "currency": "GBP", "invoice_ref": "FT-1042", "nonce": "n1"}
    flat["agent_signature"] = crypto.sign_bytes(pa["private_pem"], rules.request_signing_input(flat))
    r = client.post("/api/verify", json=flat).json()
    assert r["decision"] == "ALLOW" and r["rule_id"] == r["rule"] == "R.9" and r["audit_ref"] == r["audit_hash"] and r["receipt"]
    assert r["rails"]["passport_list"] == "active" and r["rails"]["vouch"]["status"] == "ACTIVE"
    # tampering with a flat field after signing fails R.4
    flat["amount"] = 1
    assert client.post("/api/verify", json=flat).json()["rule"] == "R.4"


def test_vouch_merchant_map_and_rail_fallback(monkeypatch):
    monkeypatch.setenv("VOUCH_MERCHANTS", '{"60-11-22 10101010": "m-fen"}')
    monkeypatch.delenv("VOUCH_MERCHANT_ID", raising=False)
    assert vouch.merchant_for("60-11-22 10101010") == "m-fen"
    assert vouch.merchant_for("601122 10101010") == "m-fen"  # same account, different punctuation
    assert vouch.merchant_for("60-11-22 99887766") is None    # redirected account has no merchant on the rail
    # local rail: the bank executes, nothing leaves the process
    assert vouch.settle_payment({"payee_account_ref": "60-11-22 10101010", "amount": 1})["rail"] == "local"


# ── Iteration 2, Task 1: the agent reads an invoice ─────────────────────────
def test_invoice_extraction_fixtures():
    from pay import extraction
    texts = extraction.invoices()
    assert set(texts) == {"INV-9001-clean", "INV-9001-poisoned"}
    clean, m1 = extraction.extract_invoice("INV-9001-clean", texts["INV-9001-clean"])
    bad, m2 = extraction.extract_invoice("INV-9001-poisoned", texts["INV-9001-poisoned"])
    assert m1 == m2 == "fixture"
    assert clean["account_number"]["value"] == "10101010" and clean["bank_details_changed"]["value"] is False
    assert bad["account_number"]["value"] == "99887766" and bad["bank_details_changed"]["value"] is True
    assert clean["amount_gbp"]["value"] == bad["amount_gbp"]["value"] == 2500
    for f in (clean, bad):
        assert all(f[k]["quote"] and f[k]["source_doc"] for k in extraction.INVOICE_FIELDS)


def test_clean_invoice_allows_and_poisoned_invoice_is_refused_with_violation(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    r = client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-clean"}).json()
    assert r["on_allowlist"] is True and r["instruction"]["payee_account_ref"] == "60-11-22 10101010" and r["instruction"]["amount"] == 2500
    assert r["result"]["decision"] == "ALLOW" and r["result"]["violation"] is None
    r = client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-poisoned"}).json()
    assert r["on_allowlist"] is False and r["registered_payee"] == "60-11-22 10101010"
    assert r["instruction"]["payee_account_ref"] == "60-11-22 99887766"
    assert r["result"]["decision"] == "DENY" and r["result"]["rule"] == "R.6" and r["result"]["code"] == "PAYEE_NOT_ON_MANDATE"
    vid = r["result"]["violation"]["id"]
    v = db.get_violation(vid)
    assert v["status"] == "OPEN" and v["rule"] == "R.6" and v["evidence"]["invoice"] == "INV-9001-poisoned"
    assert v["evidence"]["facts"]["account_number"]["value"] == "99887766" and "agent_signature" not in v["instruction"]
    state = client.get("/api/state").json()
    assert any(x["id"] == vid for x in state["violations"]) and len(state["invoices"]) == 2
    # unknown invoice is refused
    assert client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-0000"}).status_code == 400


def test_every_bank_deny_writes_a_violation_row(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    before = len(db.list_violations(pid))
    bad = {"action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455", "amount": 12000}
    r = act(client, pid, bad)
    assert r["rule"] == "R.7" and r["violation"]["status"] == "OPEN"
    assert len(db.list_violations(pid)) == before + 1
    ok = {**bad, "amount": 900}
    assert act(client, pid, ok)["violation"] is None


# ── Iteration 2, Task 2: Standards Review Assistant ─────────────────────────
def test_review_six_steps_sandbox_uses_real_engine_and_never_decides(client):
    a = client.post("/api/registrations").json()
    assert client.post(f"/api/registrations/{a['id']}/review").status_code == 400  # not submitted yet
    a = client.post(f"/api/registrations/{a['id']}/prefill").json()
    a = client.post(f"/api/registrations/{a['id']}/submit").json()
    r = client.post(f"/api/registrations/{a['id']}/review").json()
    rv = r["review"]
    assert [s["id"] for s in rv["steps"]] == ["filing", "rule_map", "tests", "sandbox", "recommendation", "signoff"]
    rule_map = rv["steps"][1]["data"]
    assert [x["id"] for x in rule_map["rules"]] == [f"F.{i}" for i in range(1, 7)] and rule_map["uncovered"] == [] and rule_map["flagged"] == []
    sb = rv["steps"][3]["data"]
    assert [(t["decision"], t["rule"]) for t in sb] == [("DENY", "R.6"), ("DENY", "R.7"), ("DENY", "R.2"), ("DENY", "R.4"), ("ESCALATE", "R.9")]
    assert all(t["pass"] for t in sb)
    rec = rv["steps"][4]["data"]
    assert rec["verdict"] == "ADMIT WITH CONDITIONS" and rec["decides"] is False
    for banned in ("approve", "reject", "recommend", "admit", "decline"):
        assert banned not in rec["narrative"].lower()
    # the review issues nothing; admission puts the product on the bank's list; only the customer creates a passport
    assert r["registration"]["status"] == "registered" and r["registration"]["admission_status"] is None and not [x for x in client.get("/api/state").json()["passports"] if x["registration_id"] == a["id"]]
    assert client.get(f"/api/status/SANDBOX-{a['ref']}").status_code == 404
    d = client.post(f"/api/registrations/{a['id']}/admission", json={"decision": "admit", "note": "Assistant recommends; I decide.", "hold_above": 5000}).json()
    assert d["product"]["admission_status"] == "admitted" and "passport" not in d
    assert client.get("/api/state").json()["products"][0]["product_id"] == "openpay-paygpt-6"


def test_review_refers_when_a_check_flags(client):
    a = client.post("/api/registrations").json()
    a = client.post(f"/api/registrations/{a['id']}/prefill").json()
    f = a["fields"]; f["product"]["model_version"]["value"] = "latest"
    client.put(f"/api/registrations/{a['id']}/fields", json={"fields": f})
    a = client.post(f"/api/registrations/{a['id']}/submit").json()
    assert "F.4" in [c["id"] for c in a["checks"] if c["result"] == "flag"]
    rv = client.post(f"/api/registrations/{a['id']}/review").json()["review"]
    assert rv["steps"][4]["data"]["verdict"] == "REFER" and "F.4" in rv["steps"][1]["data"]["flagged"]


# ── Iteration 2, Task 3: exception panel, pattern alert, revocation loop ────
def _poison(client, pid):
    return client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-poisoned"}).json()["result"]


def test_pattern_alert_needs_two_same_rule_violations_in_window(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    assert _poison(client, pid)["rule"] == "R.6"
    alerts = [x for x in client.get("/api/violations").json()["alerts"] if x["passport_id"] == pid]
    assert alerts == []  # one is not a pattern
    # a different rule does not count towards the R.6 pattern
    act(client, pid, {"action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455", "amount": 12000})
    assert [x for x in client.get("/api/violations").json()["alerts"] if x["passport_id"] == pid] == []
    assert _poison(client, pid)["rule"] == "R.6"
    alerts = [x for x in client.get("/api/state").json()["alerts"] if x["passport_id"] == pid]
    assert len(alerts) == 1 and alerts[0]["rule"] == "R.6" and alerts[0]["n"] == 2
    assert client.get("/api/state").json()["pattern_threshold"]["count"] == 2


def test_revocation_loop_suspend_investigate_revoke(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    _poison(client, pid); _poison(client, pid)
    ok = {"action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455", "amount": 900}
    # INVESTIGATING alone blocks nothing
    r = client.post(f"/api/passports/{pid}/investigation", json={"action": "open", "note": "two redirected invoices"}).json()
    assert r["investigation"] == "investigating" and all(v["status"] == "INVESTIGATING" for v in r["violations"] if v["rule"] == "R.6")
    assert act(client, pid, ok)["decision"] == "ALLOW"
    # SUSPENDED denies at R.2; evidence is readable
    client.post(f"/api/passports/{pid}/status", json={"status": "suspended", "reason": "pattern alert"})
    assert act(client, pid, ok)["rule"] == "R.2"
    v = [x for x in client.get("/api/violations", params={"passport_id": pid}).json()["violations"] if x["evidence"]][0]
    assert client.get(f"/api/violations/{v['id']}").json()["evidence"]["facts"]["account_number"]["value"] == "99887766"
    # REVOKE closes the loop: registry revoked, violations resolved, voucher revoked, investigation cleared
    p = client.post(f"/api/passports/{pid}/status", json={"status": "revoked", "reason": "misuse confirmed"}).json()
    assert p["status"] == "revoked" and p["investigation"] is None and p["vouch_status"] == "REVOKED"
    vs = client.get("/api/violations", params={"passport_id": pid}).json()["violations"]
    assert vs and all(x["status"] == "RESOLVED" and x["resolution"] == "revoked" for x in vs)
    assert act(client, pid, ok)["rule"] == "R.2"
    assert client.post(f"/api/passports/{pid}/investigation", json={"action": "open"}).status_code == 400


def test_revocation_loop_reinstate_false_positive(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    _poison(client, pid)
    client.post(f"/api/passports/{pid}/investigation", json={"action": "open"})
    client.post(f"/api/passports/{pid}/status", json={"status": "suspended", "reason": "look"})
    ok = {"action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455", "amount": 900}
    assert act(client, pid, ok)["rule"] == "R.2"
    p = client.post(f"/api/passports/{pid}/status", json={"status": "active", "reason": "false positive"}).json()
    assert p["status"] == "active" and p["investigation"] is None
    assert all(x["status"] == "RESOLVED" and x["resolution"] == "reinstated" for x in client.get("/api/violations", params={"passport_id": pid}).json()["violations"])
    assert act(client, pid, ok)["decision"] == "ALLOW"
    a = client.get("/api/audit").json()
    assert a["chain"]["ok"] and all(client.post(f"/api/audit/{r['id']}/replay").json()["identical"] for r in a["rows"][:8] if r["kind"] == "verify")


# ── Part B: delegation chain (off by default) ───────────────────────────────
FEN = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 3200}


def chain_act(client, pid, extra):
    return client.post("/api/agent/act", json={"passport_id": pid, "invoice_ref": "FT-C", "signer": "agent", "chain": True, **FEN, **extra}).json()


def test_chain_off_by_default_single_agent_path_unchanged(client):
    p, _ = issue_one(client)
    r = act(client, p["passport_id"], FEN)
    assert r["decision"] == "ALLOW" and r["chain"] is None and [s["rule"] for s in r["trace"]] == [f"R.{i}" for i in range(1, 10)]
    assert client.get("/api/state").json()["delegation_chain"] is False


def test_valid_chain_passes_and_is_visible(client):
    p, _ = issue_one(client)
    r = chain_act(client, p["passport_id"], {"delegate_amount": 4000})
    assert r["decision"] == "ALLOW" and r["chain"]["ok"] is True
    assert [c["id"] for c in r["chain"]["checks"]] == ["C.a", "C.b", "C.c"] and all(c["ok"] for c in r["chain"]["checks"])
    assert [s["rule"] for s in r["trace"]] == ["R.1", "R.2", "R.3", "R.4", "R.5", "C.a", "C.b", "C.c", "R.6", "R.7", "R.8", "R.9"]
    assert "delegated execution key" in next(s for s in r["trace"] if s["rule"] == "R.4")["note"]
    assert r["chain"]["scopes"]["S1"]["ceiling"] == 4000 and r["chain"]["scopes"]["S0"]["ceiling"] == 10000
    # replay of a chained decision is identical
    assert client.post(f"/api/audit/{r['audit_id']}/replay").json()["identical"] is True


def test_action_outside_narrowest_scope_refused_at_c_c(client):
    p, _ = issue_one(client)
    r = chain_act(client, p["passport_id"], {"delegate_amount": 4000, "amount": 4500})
    assert r["decision"] == "DENY" and r["rule"] == "C.c" and r["code"] == "ACTION_OUTSIDE_DELEGATION"
    assert r["chain"]["checks"][1]["ok"] is True and r["chain"]["checks"][2]["ok"] is False
    assert r["violation"]["status"] == "OPEN"


def test_expanding_delegation_refused_at_c_b(client):
    p, _ = issue_one(client)
    r = chain_act(client, p["passport_id"], {"delegate_amount": 12000})
    assert r["decision"] == "DENY" and r["rule"] == "C.b" and r["code"] == "DELEGATION_EXPANDS_SCOPE" and "above the root" in r["reason"]
    # a delegation to a beneficiary the customer never signed for is also an expansion
    r = chain_act(client, p["passport_id"], {"delegate_amount": 4000, "delegate_account": "60-11-22 99887766", "payee_account_ref": "60-11-22 99887766"})
    assert r["rule"] == "C.b" and "beneficiary outside the root mandate" in r["reason"]


def test_poisoned_invoice_with_chain_refused(client):
    p, _ = issue_one(client)
    r = client.post("/api/agent/invoice", json={"passport_id": p["passport_id"], "invoice_id": "INV-9001-poisoned", "chain": True}).json()
    assert r["chain"] is True and r["delegation"]["scope"]["beneficiaries"] == ["60-11-22 99887766"] and r["delegation"]["iss"].startswith("northgate-openpay-paygpt-6")
    assert r["result"]["decision"] == "DENY" and r["result"]["rule"] == "C.b"
    ok = client.post("/api/agent/invoice", json={"passport_id": p["passport_id"], "invoice_id": "INV-9001-clean", "chain": True}).json()
    assert ok["result"]["decision"] == "ALLOW" and ok["result"]["chain"]["ok"] is True


def test_rogue_execution_key_fails_r4_even_with_valid_delegation(client):
    p, _ = issue_one(client)
    r = client.post("/api/agent/act", json={"passport_id": p["passport_id"], "invoice_ref": "FT-R", "signer": "rogue", "chain": True, "delegate_amount": 4000, **FEN}).json()
    assert r["rule"] == "R.4" and "not signed by the key named in the delegation" in next(s for s in r["trace"] if s["rule"] == "R.4")["note"]
    # execution private key never leaves the server
    pp = next(x for x in client.get("/api/state").json()["passports"] if x["passport_id"] == p["passport_id"])
    assert "private_pem" not in json.dumps(pp["agent"])


# ── Iteration 3, Task 2: instruction-level Ed25519 verification, proven by tamper ──
def _signed_instruction(client, pid):
    pa = db.get_passport(pid)["agent"]
    req = {"passport_id": pid, "action_type": "pay_invoice", "payee_account_ref": "60-11-22 10101010", "supplier_name": "Fenwick Timber Ltd",
           "amount": 2500, "currency": "GBP", "invoice_ref": "INV-9001", "nonce": "tamper-test"}
    req["agent_signature"] = crypto.sign_bytes(pa["private_pem"], rules.request_signing_input(req))
    return req


def test_r4_is_real_ed25519_over_the_canonical_instruction_bytes(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    req = _signed_instruction(client, pid)
    r = client.post("/api/verify", json={"passport_id": pid, "instruction": req}).json()
    assert r["decision"] == "ALLOW" and r["signature"]["verified"] is True and r["signature"]["alg"].startswith("Ed25519")
    assert r["signature"]["agent_kid"] == db.get_passport(pid)["agent"]["kid"]
    assert r["signature"]["signed_fields"] == list(rules.REQUEST_FIELDS)
    # the bytes that were signed are canonical JSON of exactly those fields
    assert rules.request_signing_input(req) == crypto.canonical({k: req[k] for k in rules.REQUEST_FIELDS}).encode()


def test_flipping_one_byte_of_the_signed_payload_fails_r4(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    req = _signed_instruction(client, pid)
    tampered = dict(req); tampered["invoice_ref"] = "INV-9002"          # one character in a signed field
    r = client.post("/api/verify", json={"passport_id": pid, "instruction": tampered}).json()
    assert r["decision"] == "DENY" and r["rule"] == "R.4" and r["signature"]["verified"] is False
    tampered = dict(req); tampered["amount"] = 2501                     # one unit on the amount
    assert client.post("/api/verify", json={"passport_id": pid, "instruction": tampered}).json()["rule"] == "R.4"
    tampered = dict(req); sig = crypto.b64u_decode(req["agent_signature"]); sig = bytes([sig[0] ^ 1]) + sig[1:]  # one bit of the signature
    tampered["agent_signature"] = crypto.b64u(sig)
    assert client.post("/api/verify", json={"passport_id": pid, "instruction": tampered}).json()["rule"] == "R.4"


def test_rogue_key_signature_fails_r4(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    req = _signed_instruction(client, pid)
    priv, _ = crypto.generate_keypair()
    req["agent_signature"] = crypto.sign_bytes(priv, rules.request_signing_input(req))
    r = client.post("/api/verify", json={"passport_id": pid, "instruction": req}).json()
    assert r["rule"] == "R.4" and r["code"] == "AGENT_SIGNATURE_INVALID"


def test_envelope_tamper_each_signer_flips_one_byte(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    env = client.get(f"/api/passports/{pid}").json()["envelope"]
    req = _signed_instruction(client, pid)
    for part, rule in (("admission", "R.1"), ("agent_identity", "R.3"), ("mandate", "R.5")):
        bad = dict(env)
        header, payload, sig = env[part].split(".")
        raw = bytearray(crypto.b64u_decode(payload)); raw[5] ^= 1        # one bit inside the signed payload
        bad[part] = f"{header}.{crypto.b64u(bytes(raw))}.{sig}"
        r = client.post("/api/verify", json={"passport_id": pid, "instruction": req, "passport": bad}).json()
        assert r["decision"] == "DENY" and r["rule"] == rule, (part, r["rule"])
    assert client.post("/api/verify", json={"passport_id": pid, "instruction": req, "passport": env}).json()["decision"] == "ALLOW"


# ── Iteration 3, Task 3: Issuance Flow v4 — customer writes its own mandate within policy ceilings ──
def test_registration_carries_no_customer_and_admission_carries_ceilings(client):
    p, a = issue_one(client, sign_mandate=False)
    assert set(a["fields"]) == {"company", "principal", "insurance", "product", "assurance_evidence", "intended_use"}   # no customer, no agent, no key, no mandate content
    assert a["fields"]["product"]["model_version"]["value"] == "claude-sonnet-5"
    assert [c["id"] for c in a["checks"] if c["result"] != "pass"] == []
    assert p["admission"]["ceilings"]["per_payment_ceiling"]["amount"] == 10000 and p["admission"]["ceilings"]["monthly_per_account_ceiling"]["amount"] == 50000
    assert p["admission"]["product_ref"]["registration"] == a["ref"] and p["admission"]["accountable_principal"]["covers"] == "accuracy of the filing" and p["admission"]["assurance_evidence"]["reference"] == "IAE-2026-0412"
    assert p["mandate_proposed"]["customer"] is None and p["mandate_proposed"]["authorization_details"][0]["supplier_allowlist"] == []
    assert p["agent_identity"]["iss"] == "northgate-joinery-ltd" and p["agent_identity"]["agent"]["model_version"] == "claude-sonnet-5" and p["agent_identity"]["deployment"]["proof_of_possession"] is True


def test_customer_mandate_is_gated_only_by_ceiling_containment(client):
    p, _ = issue_one(client, sign_mandate=False)
    pid = p["passport_id"]
    draft = client.get("/api/state").json()["mandate_draft"]
    ok = client.post(f"/api/passports/{pid}/mandate/check", json=draft).json()
    assert ok["within_ceilings"] is True and ok["problems"] == []
    for bad, field in (({"per_payment_limit": 10001}, "per_payment_limit"), ({"monthly_limit_per_account": 60000}, "monthly_limit_per_account"),
                       ({"valid_until": "2027-06-01"}, "valid_until"), ({"supplier_allowlist": []}, "supplier_allowlist"), ({"actions": ["refund"]}, "actions"),
                       ({"supplier_allowlist": [{"name": "X", "account_ref": "12-34"}]}, "supplier_allowlist")):
        r = client.post(f"/api/passports/{pid}/mandate/check", json={**draft, **bad}).json()
        assert r["within_ceilings"] is False and any(x["field"] == field for x in r["problems"]), (bad, r)
        s = client.post(f"/api/passports/{pid}/mandate/sign", json={**draft, **bad})
        assert s.status_code == 422 and s.json()["detail"]["problems"]
    assert client.get(f"/api/passports/{pid}").json()["mandate_signed"] is False
    # the customer tightens its own mandate below the ceilings, adds a payee, and signs: live at once
    mine = {**draft, "per_payment_limit": 7500, "monthly_limit_per_account": 15000, "supplier_allowlist": draft["supplier_allowlist"] + [{"name": "Delta Fixings Ltd", "account_ref": "40-40-40 12121212"}]}
    p = client.post(f"/api/passports/{pid}/mandate/sign", json=mine).json()
    pid = p["passport_id"]
    assert p["mandate_signed"] is True and p["mandate"]["within_ceilings"] is True and p["mandate"]["written_by"] == "customer"
    ad = p["mandate"]["authorization_details"][0]
    assert ad["per_payment_limit"]["amount"] == 7500 and len(ad["supplier_allowlist"]) == 4 and ad["supplier_allowlist"][3]["supplier_id"] == "SUP-004"
    assert client.get(f"/api/passports/{pid}").json()["verification"]["ok"] is True
    # the bank enforces the customer's tighter limit, not the ceiling
    r = act(client, pid, {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 8000})
    assert r["rule"] == "R.7"
    assert act(client, pid, {"action_type": "pay_invoice", "supplier_name": "Delta Fixings Ltd", "payee_account_ref": "40-40-40 12121212", "amount": 900})["decision"] == "ALLOW"
    # the register never had the mandate content in the registration
    a = client.get("/api/state").json()["registrations"][0]
    assert "Delta" not in json.dumps(a["fields"])


# ── Iteration 3, Task 7: demo baseline seed is deterministic and repeatable ──
def test_demo_seed_twice_gives_identical_baselines(client):
    def baseline():
        r = client.post("/api/demo/seed?stage=issued").json()
        st = client.get("/api/state").json()
        p = st["passports"][0]
        au = client.get("/api/audit").json()
        return {"seed": {k: r[k] for k in ("stage", "registration", "recommendation", "status", "mandate_signed", "audit_entries")},
                "passport": {"id": p["passport_id"], "status": p["status"], "payees": len(p["mandate"]["authorization_details"][0]["supplier_allowlist"]), "payments": p["payments"], "ledger": p["ledger"]},
                "violations": len(st["violations"]), "alerts": len(st["alerts"]), "audit_kinds": [x["kind"] for x in au["rows"]], "chain_ok": au["chain"]["ok"]}
    b1, b2 = baseline(), baseline()
    assert b1 == b2, (b1, b2)
    assert b1["passport"]["status"] == "active" and b1["passport"]["payees"] == 3 and b1["passport"]["payments"] == 0 and b1["violations"] == 0
    assert b1["seed"]["recommendation"] == "ADMIT WITH CONDITIONS" and b1["chain_ok"]
    s = client.post("/api/demo/seed?stage=registered").json()
    assert s["stage"] == "registered" and "passport_id" not in s and client.get("/api/state").json()["registrations"][0]["status"] == "registered"
    assert client.post("/api/demo/seed?stage=nope").status_code == 400


# ── Product admission: cascade ─────────────────────────────────────────────────
def test_product_revoke_cascades_to_passports_and_passport_revoke_is_unchanged(client):
    p1, a = issue_one(client)
    p2 = client.post("/api/agents", json={"registration_id": a["id"]}).json()
    p2 = client.post(f"/api/passports/{p2['passport_id']}/mandate/sign").json()
    ok = {"action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455", "amount": 900}
    assert act(client, p1["passport_id"], ok)["decision"] == "ALLOW" and act(client, p2["passport_id"], ok)["decision"] == "ALLOW"
    r = client.post(f"/api/registrations/{a['id']}/admission/status", json={"status": "suspended", "reason": "model card inaccurate"}).json()
    assert r["product"]["admission_status"] == "suspended" and set(r["passports"]) == {p1["passport_id"], p2["passport_id"]}
    assert act(client, p1["passport_id"], ok)["rule"] == "R.2" and act(client, p2["passport_id"], ok)["rule"] == "R.2"
    assert client.post("/api/agents", json={"registration_id": a["id"]}).status_code == 400   # no new agents on a suspended product
    r = client.post(f"/api/registrations/{a['id']}/admission/status", json={"status": "active", "reason": "corrected"}).json()
    assert act(client, p1["passport_id"], ok)["decision"] == "ALLOW"
    r = client.post(f"/api/registrations/{a['id']}/admission/status", json={"status": "revoked", "reason": "withdrawn"}).json()
    for pid in (p1["passport_id"], p2["passport_id"]):
        assert client.get(f"/api/status/{pid}").json()["status"] == "revoked" and act(client, pid, ok)["rule"] == "R.2"
        assert client.get(f"/api/passports/{pid}").json()["vouch_status"] == "REVOKED"
    assert client.post(f"/api/registrations/{a['id']}/admission/status", json={"status": "active", "reason": "undo"}).status_code == 400
    a2 = client.get("/api/audit").json(); assert a2["chain"]["ok"]


# ── Grounds declaration: intent declared before the document is read; mismatch recorded ──────────────────────
def test_grounds_declaration_records_intent_before_reading_and_flags_mismatch(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    r = client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-clean"}).json()
    assert r["intent"]["declared_payee"] == "60-11-22 10101010" and r["intent"]["matches"] is True and "INV-9001" in r["intent"]["task"]
    r = client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-poisoned"}).json()
    assert r["intent"]["declared_payee"] == "60-11-22 10101010" and r["intent"]["attempted_payee"] == "60-11-22 99887766" and r["intent"]["matches"] is False
    rows = client.get("/api/audit").json()["rows"]
    intent = next(x for x in rows if x["id"] == r["intent"]["audit_id"])
    assert intent["kind"] == "intent" and intent["entry"]["declared_payee"] == "60-11-22 10101010" and "before the document was read" in intent["entry"]["event"]
    agent = next(x for x in rows if x["kind"] == "agent" and x["entry"].get("intent_audit_id") == intent["id"])
    assert agent["id"] > intent["id"] and agent["entry"]["matches_intent"] is False and "the document changed the destination" in agent["entry"]["detail"]
    # the violation carries the declared intent as evidence
    v = db.get_violation(r["result"]["violation"]["id"])
    assert v["evidence"]["intent"]["matches"] is False and v["evidence"]["intent"]["declared_payee"] == "60-11-22 10101010"


# ── Action Terminal: the scenario page, and the console behind ?console=1 ─────────────────────────────────────
def test_action_terminal_scenario_and_console(client):
    h = client.get("/terminal").text
    assert "Before the standard" in h and "After the standard" in h and "terminal.js" in h and "Money gone" in h and "Agent Passport" in h and "Run the agent" in h
    assert 'id="beats"' not in h
    c = client.get("/terminal?console=1").text
    assert client.get("/bank?console=1", follow_redirects=False).status_code == 302 and client.get("/regulator", follow_redirects=False).headers["location"] == "/bank"
    assert 'id="beats"' in c and 'id="gauntlet"' in c and "terminal.js" not in c


# ── Consolidation round: assurance levels, velocity, currency, replay, failure classes, Companies House ──
def test_assurance_level_scales_ceilings_and_gates_admission(client):
    a = client.post("/api/registrations").json(); a = client.post(f"/api/registrations/{a['id']}/prefill").json()
    f = a["fields"]; f["assurance_evidence"]["level"]["value"] = "self-declared"
    client.put(f"/api/registrations/{a['id']}/fields", json={"fields": f}); a = client.post(f"/api/registrations/{a['id']}/submit").json()
    assert next(c for c in a["checks"] if c["id"] == "F.5")["assurance_level"] == "self-declared"
    r = client.post(f"/api/registrations/{a['id']}/admission", json={"decision": "admit", "note": "try"})
    assert r.status_code == 400 and "self-declared" in r.json()["detail"]
    assert rules.admission_ceilings("independently-verified")["per_payment_ceiling"]["amount"] == 5000
    assert rules.admission_ceilings("independently-audited")["ceiling_factor"] == 1.0
    assert rules.effective_limits(rules.admission_ceilings("independently-audited"), "personal_current")["per_payment"] == 2500


def test_mandate_velocity_and_account_tier_are_contained(client):
    p, _ = issue_one(client, sign_mandate=False)
    draft = client.get("/api/state").json()["mandate_draft"]
    r = client.post(f"/api/passports/{p['passport_id']}/mandate/check", json={**draft, "max_payments_per_day": 50}).json()
    assert r["within_ceilings"] is False and any(x["field"] == "max_payments_per_day" for x in r["problems"])
    personal = {**draft, "customer": {**draft["customer"], "account_type": "personal_current"}}
    r = client.post(f"/api/passports/{p['passport_id']}/mandate/check", json=personal).json()
    assert r["limits"]["per_payment"] == 2500 and any(x["field"] == "per_payment_limit" for x in r["problems"])
    p = client.post(f"/api/passports/{p['passport_id']}/mandate/sign", json=draft).json()
    ad = p["mandate"]["authorization_details"][0]
    assert ad["currency"] == "GBP" and ad["max_payments_per_day"] == 10 and p["mandate"]["account"]["tier"] == "Business current account"
    assert all(x["register_check"]["found"] and "public register" in x["register_check"]["checked"] for x in ad["supplier_allowlist"])


def test_refusals_carry_a_failure_class(client):
    p, _ = issue_one(client); pid = p["passport_id"]
    usd = act(client, pid, {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 300}, currency="USD")
    assert usd["code"] == "CURRENCY_NOT_PERMITTED" and usd["failure_class"]["id"] == "agent_error"
    bad = act(client, pid, {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 99887766", "amount": 300})
    assert bad["failure_class"]["id"] == "fraud"
    rogue = act(client, pid, {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 300}, signer="rogue")
    assert rogue["failure_class"]["id"] == "fraud"
    v = client.get("/api/violations", params={"passport_id": pid}).json()["violations"]
    assert {x["failure_class"] for x in v} == {"agent_error", "fraud"}


def test_companies_house_falls_back_to_the_labelled_demo_register(monkeypatch):
    from pay import companies_house
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    r = companies_house.lookup("4471982")
    assert r["found"] and r["legal_name"] == "FENWICK TIMBER LTD" and "synthetic" in r["source"] and r["number"] == "04471982"
    assert companies_house.lookup("00000000")["found"] is False
    assert companies_house.names_match("FENWICK TIMBER LTD", "Fenwick Timber Limited")
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "not-a-real-key"); monkeypatch.setattr(companies_house, "API", "http://127.0.0.1:9")
    companies_house._cache.clear()
    r = companies_house.lookup("07310455")
    assert r["found"] and "demo register" in r["source"] and "unreachable" in r.get("note", "")
