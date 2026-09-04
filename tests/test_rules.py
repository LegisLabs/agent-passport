"""Jean's oracle against the runtime verifier, plus crypto and audit invariants.
Runs fully offline (fixture extraction, no Gemini)."""
import json
import os
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["EXTRACTION_MODE"] = "fixture"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, crypto, rules  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ORACLE = json.loads((ROOT / "fixtures" / "oracle.json").read_text())["cases"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def issue_one(client):
    """Drive the whole application path: draft → extract → key → challenge → submit → approve."""
    a = client.post("/api/applications").json()
    a = client.post(f"/api/applications/{a['id']}/extract").json()
    assert a["extraction_mode"] == "fixture"
    a = client.post(f"/api/applications/{a['id']}/agent-key").json()
    a = client.post(f"/api/applications/{a['id']}/sign-challenge").json()
    assert a["agent"]["pop_verified"] is True
    a = client.post(f"/api/applications/{a['id']}/submit").json()
    flagged = {c["id"] for c in a["checks"] if c["result"] != "pass"}
    assert flagged == {"A.6", "A.7"}, flagged  # Priya pending, Oliver no consent
    r = client.post(f"/api/applications/{a['id']}/decision", json={"decision": "approve", "note": "Flags noted; both clients excluded at action time by R.5 / consent condition."}).json()
    return r["passport"], a


@pytest.fixture(scope="module")
def issued(client):
    return issue_one(client)


def test_passport_is_signed_and_minimal(client, issued):
    p, _ = issued
    payload = crypto.verify_jwt(p["jwt"])
    assert payload and payload["jti"] == p["jti"]
    assert "clients" not in json.dumps(payload)  # no personal data in the token
    assert payload["cnf"]["jwk"]["kty"] == "OKP"
    tampered = p["jwt"][:-4] + "AAAA"
    assert crypto.verify_jwt(tampered) is None


@pytest.mark.parametrize("case", ORACLE, ids=[c["id"] for c in ORACLE])
def test_oracle(client, issued, case):
    p, _ = issued
    if case["passport_status"] == "revoked":
        p, _ = issue_one(client)  # revocation is terminal: use a fresh passport
    # put the registry into the case's state without touching other tests' expectations
    if case["passport_status"] != "active":
        client.post(f"/api/passports/{p['jti']}/status", json={"status": case["passport_status"], "reason": f"oracle {case['id']}"})
    try:
        if case.get("tamper_passport"):
            from app import db
            row = db.get_passport(p["jti"])
            req = {"passport_jti": p["jti"], "action": case["action"], "utr": case["utr"], "tax_year": case["tax_year"], "tax_due": case["tax_due"], "nonce": "n"}
            res = client.post("/api/verify", json={"passport": row["jwt"][:-4] + "AAAA", "request": req}).json()
        else:
            res = client.post("/api/agent/act", json={"jti": p["jti"], "action": case["action"], "utr": case["utr"], "tax_year": case["tax_year"], "tax_due": case["tax_due"], "signer": case["signer"]}).json()
        assert res["decision"] == case["expected_decision"], res
        assert res["rule"] == case["expected_rule"], res
        assert res["code"] == case["expected_code"], res
        assert res["receipt"]
        assert client.get("/api/receipt/verify", params={"token": res["receipt"]}).json()["verified"] is True
    finally:
        if case["passport_status"] == "suspended":
            client.post(f"/api/passports/{p['jti']}/status", json={"status": "active", "reason": "oracle reinstate"})


def test_revoked_is_terminal(client):
    p, _ = issue_one(client)
    client.post(f"/api/passports/{p['jti']}/status", json={"status": "revoked", "reason": "misuse detected"})
    r = client.post(f"/api/passports/{p['jti']}/status", json={"status": "active", "reason": "try to undo"})
    assert r.status_code == 400


def test_audit_chain_and_replay(client):
    a = client.get("/api/audit").json()
    assert a["chain"]["ok"] is True and a["chain"]["length"] > 10
    verify_rows = [r for r in a["rows"] if r["kind"] == "verify"]
    assert verify_rows
    for r in verify_rows[:5]:
        rp = client.post(f"/api/audit/{r['id']}/replay").json()
        assert rp["identical"] is True, rp


def test_rule_pack_labels():
    pack = rules.pack()
    for r in pack["application_rules"] + pack["runtime_rules"]:
        assert r["status"] in ("CURRENT", "PROTOTYPE", "FUTURE")
        assert r["source"]


def test_no_verdict_vocabulary_in_fixture_note():
    from app import extraction
    from app.fixtures import evidence_pack
    facts, mode = extraction.extract(evidence_pack())
    checks = rules.run_application_checks(facts, {"pop_verified": True, "kid": "x"})
    note, _ = extraction.draft_file_note("AP-TEST", facts, checks)
    for banned in ("approve", "reject", "recommend"):
        assert banned not in note.lower()
