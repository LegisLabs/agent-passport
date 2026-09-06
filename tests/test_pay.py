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
    """Drive the whole path: draft → extract → key → challenge → submit → approve (→ customer signs)."""
    a = client.post("/api/applications").json()
    a = client.post(f"/api/applications/{a['id']}/extract").json()
    assert a["extraction_mode"] == "fixture"
    a = client.post(f"/api/applications/{a['id']}/agent-key").json()
    a = client.post(f"/api/applications/{a['id']}/sign-challenge").json()
    assert a["agent"]["pop_verified"] is True
    a = client.post(f"/api/applications/{a['id']}/submit").json()
    assert a["agent_identity_jwt"]
    flagged = {c["id"] for c in a["checks"] if c["result"] != "pass"}
    assert flagged == set(), flagged
    r = client.post(f"/api/applications/{a['id']}/decision", json={"decision": "approve", "note": "All eight checks pass. Condition: hold above £5,000."}).json()
    p = r["passport"]
    if sign_mandate:
        p = client.post(f"/api/passports/{p['passport_id']}/mandate/sign").json()
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
    assert crypto.verify_jwt("authority", env["assurance"])["jti"] == p["passport_id"]
    assert crypto.verify_jwt("payrail", env["agent_identity"])["cnf"]["jwk"]["kty"] == "OKP"
    assert crypto.verify_jwt("northgate", env["mandate"])["passport_id"] == p["passport_id"]
    # each JWT only verifies against its own signer
    assert crypto.verify_jwt("payrail", env["assurance"]) is None
    assert crypto.verify_jwt("authority", env["mandate"]) is None
    # assurance binds the exact agent_identity it was issued for
    assert crypto.verify_jwt("authority", env["assurance"])["binds"]["agent_identity_sha256"] == crypto.sha256_hex(env["agent_identity"])
    # no bank details of the customer, no email, no personal contact data in any JWT
    blob = json.dumps([crypto.decode_unverified(env[k])[1] for k in ("assurance", "agent_identity", "mandate")])
    assert "@" not in blob and "email" not in blob
    assert env["cnf"] is None and env["vouch_voucher_id"]


@pytest.mark.parametrize("case", ORACLE, ids=[c["id"] for c in ORACLE])
def test_oracle(client, issued, case):
    p, _ = issued
    pid = p["passport_id"]
    if case["passport_status"] == "revoked" or case["mandate"] == "unsigned" or case.get("ledger_before"):
        p, _ = issue_one(client, sign_mandate=case["mandate"] == "signed")  # isolated passport for terminal / stateful cases
        pid = p["passport_id"]
    if case.get("ledger_before"):
        db.insert_payment(pid, case["payee_account_ref"], float(case["ledger_before"]), "GBP", "seed", None, "local", None)
    if case["passport_status"] != "active":
        client.post(f"/api/passports/{pid}/status", json={"status": case["passport_status"], "reason": f"oracle {case['id']}"})
    try:
        if case.get("tamper"):
            env = dict(db.get_passport(pid) and client.get(f"/api/passports/{pid}").json()["envelope"])
            env[case["tamper"]] = env[case["tamper"]][:-4] + "AAAA"
            a = db.get_application(db.get_passport(pid)["application_id"])
            req = {"passport_id": pid, "action_type": case["action_type"], "payee_account_ref": case["payee_account_ref"], "supplier_name": case["supplier_name"],
                   "amount": case["amount"], "currency": "GBP", "invoice_ref": "INV-T", "nonce": "n"}
            req["agent_signature"] = crypto.sign_bytes(a["agent"]["private_pem"], rules.request_signing_input(req))
            res = client.post("/api/verify", json={"passport_id": pid, "instruction": req, "passport": env}).json()
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
    fen = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 44556677", "amount": 4900}
    decisions = [act(client, pid, fen)["decision"] for _ in range(5)]
    assert decisions == ["ALLOW", "ALLOW", "ALLOW", "ALLOW", "DENY"]  # 19,600 allowed, 24,500 refused
    full = client.get(f"/api/passports/{pid}").json()
    assert full["ledger"]["60-11-22 44556677"]["total"] == 19600 and full["payments"] == 4
    # another account is unaffected
    assert act(client, pid, {**fen, "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455"})["decision"] == "ALLOW"


def test_three_denies_escalate_to_supervisor(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    bad = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 100}
    r1, r2, r3 = (act(client, pid, bad) for _ in range(3))
    assert r1["incident"] is None and r2["incident"] is None and r3["incident"]["denies"] == 3
    incidents = client.get("/api/state").json()["incidents"]
    assert any(i["subject"] == pid and i["entry"]["event"] == "escalated to supervisor" for i in incidents)
    assert act(client, pid, bad)["incident"] is None  # counter restarts after the incident


def test_customer_signature_completes_envelope(client):
    p, _ = issue_one(client, sign_mandate=False)
    pid = p["passport_id"]
    assert p["mandate_signed"] is False and client.get(f"/api/passports/{pid}").json()["verification"]["failure"] == "mandate_missing"
    fen = {"action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 44556677", "amount": 3200}
    assert act(client, pid, fen)["rule"] == "R.5"
    client.post(f"/api/passports/{pid}/mandate/sign")
    assert client.get(f"/api/passports/{pid}").json()["verification"]["ok"] is True
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
    for r in pack["application_rules"] + pack["runtime_rules"]:
        assert r["status"] in ("CURRENT", "PROTOTYPE", "FUTURE") and r["source"]
    assert [r["id"] for r in pack["runtime_rules"]] == [f"R.{i}" for i in range(1, 10)]


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
    from pay.fixtures import evidence_pack
    facts, _ = extraction.extract(evidence_pack())
    checks = rules.run_application_checks(facts, {"pop_verified": True, "kid": "x"})
    note, _ = extraction.draft_file_note("AP-TEST", facts, checks)
    for banned in ("approve", "reject", "recommend"):
        assert banned not in note.lower()


def test_config_hash_mismatch_flags_a8():
    from pay import extraction
    facts = extraction.fixture()
    facts["agent"]["config_hash"]["value"] = "deadbeef"
    checks = rules.run_application_checks(facts, {"pop_verified": True, "kid": "x"})
    assert next(c for c in checks if c["id"] == "A.8")["result"] == "flag"


def test_verify_accepts_flat_contract_and_aliases(client):
    """The brief's POST /api/verify shape: flat instruction fields + agent_signature → decision, rule_id, reason, audit_ref, receipt."""
    p, _ = issue_one(client)
    a = db.get_application(db.get_passport(p["passport_id"])["application_id"])
    flat = {"passport_id": p["passport_id"], "action_type": "pay_invoice", "payee_account_ref": "60-11-22 44556677", "supplier_name": "Fenwick Timber Ltd",
            "amount": 3200, "currency": "GBP", "invoice_ref": "FT-1042", "nonce": "n1"}
    flat["agent_signature"] = crypto.sign_bytes(a["agent"]["private_pem"], rules.request_signing_input(flat))
    r = client.post("/api/verify", json=flat).json()
    assert r["decision"] == "ALLOW" and r["rule_id"] == r["rule"] == "R.9" and r["audit_ref"] == r["audit_hash"] and r["receipt"]
    assert r["rails"]["authority_registry"] == "active" and r["rails"]["vouch"]["status"] == "ACTIVE"
    # tampering with a flat field after signing fails R.4
    flat["amount"] = 1
    assert client.post("/api/verify", json=flat).json()["rule"] == "R.4"


def test_vouch_merchant_map_and_rail_fallback(monkeypatch):
    monkeypatch.setenv("VOUCH_MERCHANTS", '{"60-11-22 44556677": "m-fen"}')
    monkeypatch.delenv("VOUCH_MERCHANT_ID", raising=False)
    assert vouch.merchant_for("60-11-22 44556677") == "m-fen"
    assert vouch.merchant_for("601122 44556677") == "m-fen"  # same account, different punctuation
    assert vouch.merchant_for("60-11-22 10101010") is None    # redirected account has no merchant on the rail
    # local rail: the bank executes, nothing leaves the process
    assert vouch.settle_payment({"payee_account_ref": "60-11-22 44556677", "amount": 1})["rail"] == "local"


# ── Iteration 2, Task 1: the agent reads an invoice ─────────────────────────
def test_invoice_extraction_fixtures():
    from pay import extraction
    texts = extraction.invoices()
    assert set(texts) == {"INV-9001-clean", "INV-9001-poisoned"}
    clean, m1 = extraction.extract_invoice("INV-9001-clean", texts["INV-9001-clean"])
    bad, m2 = extraction.extract_invoice("INV-9001-poisoned", texts["INV-9001-poisoned"])
    assert m1 == m2 == "fixture"
    assert clean["account_number"]["value"] == "44556677" and clean["bank_details_changed"]["value"] is False
    assert bad["account_number"]["value"] == "10101010" and bad["bank_details_changed"]["value"] is True
    assert clean["amount_gbp"]["value"] == bad["amount_gbp"]["value"] == 2500
    for f in (clean, bad):
        assert all(f[k]["quote"] and f[k]["source_doc"] for k in extraction.INVOICE_FIELDS)


def test_clean_invoice_allows_and_poisoned_invoice_is_refused_with_violation(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    r = client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-clean"}).json()
    assert r["on_allowlist"] is True and r["instruction"]["payee_account_ref"] == "60-11-22 44556677" and r["instruction"]["amount"] == 2500
    assert r["result"]["decision"] == "ALLOW" and r["result"]["violation"] is None
    r = client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-9001-poisoned"}).json()
    assert r["on_allowlist"] is False and r["registered_payee"] == "60-11-22 44556677"
    assert r["instruction"]["payee_account_ref"] == "60-11-22 10101010"
    assert r["result"]["decision"] == "DENY" and r["result"]["rule"] == "R.6" and r["result"]["code"] == "PAYEE_NOT_ON_MANDATE"
    vid = r["result"]["violation"]["id"]
    v = db.get_violation(vid)
    assert v["status"] == "OPEN" and v["rule"] == "R.6" and v["evidence"]["invoice"] == "INV-9001-poisoned"
    assert v["evidence"]["facts"]["account_number"]["value"] == "10101010" and "agent_signature" not in v["instruction"]
    state = client.get("/api/state").json()
    assert any(x["id"] == vid for x in state["violations"]) and len(state["invoices"]) == 2
    # unknown invoice is refused
    assert client.post("/api/agent/invoice", json={"passport_id": pid, "invoice_id": "INV-0000"}).status_code == 400


def test_every_bank_deny_writes_a_violation_row(client):
    p, _ = issue_one(client)
    pid = p["passport_id"]
    before = len(db.list_violations(pid))
    bad = {"action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": "30-98-76 22334455", "amount": 11400}
    r = act(client, pid, bad)
    assert r["rule"] == "R.7" and r["violation"]["status"] == "OPEN"
    assert len(db.list_violations(pid)) == before + 1
    ok = {**bad, "amount": 900}
    assert act(client, pid, ok)["violation"] is None
