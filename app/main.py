"""Agent Passport — v1 skeleton. FastAPI routes: server-rendered views + JSON API.

Flow: Apply (/operator) → Review & issue (/regulator) → Act & check (/relying) → Maintain (lifecycle) → /audit.
"""
from __future__ import annotations

import os

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import audit, config, crypto, db, extraction, fixtures, rules

HERE = Path(__file__).parent
app = FastAPI(title="Agent Passport", version=config.APP_VERSION, docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


@app.on_event("startup")
def _startup() -> None:
    db.init()
    crypto.authority_keys()


ROOT_PATH = os.environ.get("ROOT_PATH", "").rstrip("/")   # served under a path prefix (cdir.legislabs.uk/tax)


def ctx(request: Request, **kw) -> dict:
    a = crypto.authority_keys()
    return {"request": request, "rule_pack": rules.pack()["id"], "issuer": config.ISSUER_NAME, "officer": config.OFFICER,
            "kid": a["kid"], "version": config.APP_VERSION, "extraction_mode": config.EXTRACTION_MODE, "root": ROOT_PATH, **kw}


# ── Views ──────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(ROOT_PATH + "/operator")


@app.get("/operator", response_class=HTMLResponse, include_in_schema=False)
def view_operator(request: Request):
    return templates.TemplateResponse(request, "operator.html", ctx(request, view="operator"))


@app.get("/regulator", response_class=HTMLResponse, include_in_schema=False)
def view_regulator(request: Request):
    return templates.TemplateResponse(request, "regulator.html", ctx(request, view="regulator"))


@app.get("/relying", response_class=HTMLResponse, include_in_schema=False)
def view_relying(request: Request):
    return templates.TemplateResponse(request, "relying.html", ctx(request, view="relying"))


@app.get("/audit", response_class=HTMLResponse, include_in_schema=False)
def view_audit(request: Request):
    return templates.TemplateResponse(request, "audit.html", ctx(request, view="audit"))


@app.get("/about", response_class=HTMLResponse, include_in_schema=False)
def view_about(request: Request):
    return templates.TemplateResponse(request, "about.html", ctx(request, view="about", pack=rules.pack()))


# ── API: meta ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True, "version": config.APP_VERSION, "rule_pack": rules.pack()["id"], "extraction_mode": config.EXTRACTION_MODE}


@app.get("/api/rulepack")
def rulepack():
    return rules.pack()


@app.get("/api/authority")
def authority():
    a = crypto.authority_keys()
    return {"issuer": config.ISSUER, "name": config.ISSUER_NAME, "kid": a["kid"], "jwk": a["jwk"], "alg": "EdDSA"}


@app.get("/api/state")
def state():
    """Everything the views need in one call."""
    apps = db.list_applications()
    pps = db.list_passports()
    return {"applications": [public_app(a) for a in apps], "passports": [public_passport(p) for p in pps], "beats": fixtures.BEATS}


def public_app(a: dict) -> dict:
    a = dict(a)
    ag = a.get("agent") or {}
    a["agent"] = {k: v for k, v in ag.items() if k != "private_pem"}
    return a


def public_passport(p: dict) -> dict:
    return p


# ── API: operator ──────────────────────────────────────────────────────────
@app.post("/api/applications")
def create_application():
    n = len(db.list_applications()) + 91
    ref = f"AP-2026-{n:04d}"
    a = db.create_application(ref, fixtures.evidence_pack())
    audit.record("application", ref, {"event": "draft created", "documents": [d["name"] for d in a["documents"]]})
    return public_app(a)


@app.post("/api/applications/{app_id}/extract")
def extract(app_id: int):
    a = db.get_application(app_id) or _404()
    facts, mode = extraction.extract(a["documents"])
    a = db.update_application(app_id, extraction=facts, fields=facts, extraction_mode=mode)
    n_fields = sum(len(v) for k, v in facts.items() if isinstance(v, dict) and not k.startswith("_")) + len(facts.get("clients", []))
    audit.record("extraction", a["ref"], {"event": "documents read into structured facts", "mode": mode, "fields": n_fields, "model": config.GEMINI_MODEL if mode == "gemini" else None})
    return public_app(a)


class FieldsIn(BaseModel):
    fields: dict


@app.put("/api/applications/{app_id}/fields")
def put_fields(app_id: int, body: FieldsIn):
    a = db.get_application(app_id) or _404()
    if a["status"] not in ("draft", "info_requested"):
        raise HTTPException(409, "application is no longer editable")
    a = db.update_application(app_id, fields=body.fields)
    return public_app(a)


@app.post("/api/applications/{app_id}/agent-key")
def agent_key(app_id: int):
    """The firm provisions the agent's key pair and the authority issues a challenge."""
    a = db.get_application(app_id) or _404()
    priv, pub = crypto.generate_keypair()
    jwk = crypto.public_jwk(pub)
    agent_id = rules._v(a.get("fields") or {}, "agent", "agent_id") or "agent"
    ag = {"agent_id": agent_id, "public_pem": pub, "private_pem": priv, "jwk": jwk, "kid": crypto.jwk_thumbprint(jwk)[:16],
          "challenge": crypto.new_nonce(), "challenge_sig": None, "pop_verified": False}
    a = db.update_application(app_id, agent=ag)
    audit.record("application", a["ref"], {"event": "agent key registered, challenge issued", "agent_id": agent_id, "kid": ag["kid"]})
    return public_app(a)


@app.post("/api/applications/{app_id}/sign-challenge")
def sign_challenge(app_id: int):
    """Simulated agent: signs the authority's nonce with its private key; authority verifies."""
    a = db.get_application(app_id) or _404()
    ag = a.get("agent") or _400("no agent key yet")
    sig = crypto.sign_bytes(ag["private_pem"], ag["challenge"].encode())
    ok = crypto.verify_bytes(ag["public_pem"], ag["challenge"].encode(), sig)
    ag.update({"challenge_sig": sig, "pop_verified": ok})
    a = db.update_application(app_id, agent=ag)
    audit.record("application", a["ref"], {"event": "challenge signed by agent", "kid": ag["kid"], "verified": ok})
    return public_app(a)


@app.post("/api/applications/{app_id}/submit")
def submit(app_id: int):
    a = db.get_application(app_id) or _404()
    if not a.get("fields"):
        _400("read the documents first")
    checks = rules.run_application_checks(a["fields"], a.get("agent"))
    a = db.update_application(app_id, status="submitted", submitted_at=db.now_iso(), checks=checks)
    audit.record("check", a["ref"], {"event": "application submitted; automated checks run", "passed": sum(c["result"] == "pass" for c in checks), "flagged": [c["id"] for c in checks if c["result"] != "pass"]})
    return public_app(a)


# ── API: regulator ─────────────────────────────────────────────────────────
class DecisionIn(BaseModel):
    decision: str  # approve | request_info | reject
    note: str


@app.post("/api/applications/{app_id}/decision")
def decide(app_id: int, body: DecisionIn):
    a = db.get_application(app_id) or _404()
    if a["status"] not in ("submitted", "info_requested"):
        raise HTTPException(409, f"application is {a['status']}")
    if not body.note.strip():
        _400("an officer note is required")
    if body.decision == "approve":
        p = issue_passport(a, body.note)
        a = db.update_application(app_id, status="approved", decided_at=db.now_iso(), officer=config.OFFICER, officer_note=body.note)
        audit.record("decision", a["ref"], {"event": "approved and passport issued", "officer": config.OFFICER, "note": body.note, "jti": p["jti"]})
        return {"application": public_app(a), "passport": p}
    if body.decision == "request_info":
        a = db.update_application(app_id, status="info_requested", officer=config.OFFICER, officer_note=body.note)
        audit.record("decision", a["ref"], {"event": "further information requested", "officer": config.OFFICER, "note": body.note})
        return {"application": public_app(a)}
    if body.decision == "reject":
        a = db.update_application(app_id, status="rejected", decided_at=db.now_iso(), officer=config.OFFICER, officer_note=body.note)
        audit.record("decision", a["ref"], {"event": "rejected", "officer": config.OFFICER, "note": body.note})
        return {"application": public_app(a)}
    _400("unknown decision")


def issue_passport(a: dict, note: str) -> dict:
    f = a["fields"]
    ag = a["agent"] or _400("agent key not registered")
    if not ag.get("pop_verified"):
        _400("agent has not proven possession of its key")
    ra = f["requested_authority"]
    pol = rules.pack()["policy"]
    action_type = rules._v(ra, "action_type")
    actions = ["submit_sa100"] + (["amend_sa100"] if action_type == "submit_and_amend" else [])
    valid_until = min(str(rules._v(ra, "valid_until") or "2027-01-31"), "2027-01-31")
    payload = {
        "iss": config.ISSUER, "jti": a["ref"], "iat": crypto.now_ts(),
        "nbf": crypto.now_ts(), "exp": int(__import__("datetime").datetime.fromisoformat(valid_until + "T23:59:59+00:00").timestamp()),
        "valid_until": valid_until,
        "rule_pack_version": rules.pack()["id"],
        "subject": {
            "agent_id": ag["agent_id"],
            "operator": {"firm": rules._v(f, "firm", "name"), "asa_reference": rules._v(f, "firm", "asa_reference"), "companies_house_number": rules._v(f, "firm", "companies_house_number")},
            "software": f"{rules._v(f, 'agent', 'software')} {rules._v(f, 'agent', 'software_version')}",
        },
        "authorization_details": [{
            "type": "uk_self_assessment_filing",
            "task": rules._v(ra, "task"),
            "actions": actions,
            "tax_year": rules._v(ra, "tax_year"),
            "action_type": action_type,
            "client_coverage": "by reference to the authority's authorisation records",
            "escalation_threshold": {"amount": float(rules._v(ra, "escalation_threshold_gbp") or pol["escalation_threshold_gbp"]), "currency": "GBP", "basis": pol["escalation_basis"]},
        }],
        "cnf": {"jwk": ag["jwk"]},
        "status": {"registry": f"/api/status/{a['ref']}"},
        "issued_by": config.OFFICER,
    }
    token = crypto.sign_jwt(payload)
    p = db.create_passport(a["ref"], a["id"], token, payload, valid_until, config.OFFICER)
    audit.record("issue", a["ref"], {"event": "passport signed and entered in registry as ACTIVE", "kid": crypto.authority_keys()["kid"], "agent_kid": ag["kid"], "scope": payload["authorization_details"][0]})
    return p


class NoteIn(BaseModel):
    pass


@app.post("/api/applications/{app_id}/file-note")
def file_note(app_id: int):
    a = db.get_application(app_id) or _404()
    if not a.get("checks"):
        _400("no checks yet")
    note, mode = extraction.draft_file_note(a["ref"], a["fields"], a["checks"])
    a = db.update_application(app_id, file_note=note)
    audit.record("draft", a["ref"], {"event": "file note drafted (edge use of the model; not a decision)", "mode": mode})
    return {"note": note, "mode": mode}


class LifecycleIn(BaseModel):
    status: str  # suspended | active | revoked
    reason: str


@app.post("/api/passports/{jti}/status")
def lifecycle(jti: str, body: LifecycleIn):
    p = db.get_passport(jti) or _404()
    if body.status not in ("suspended", "active", "revoked"):
        _400("status must be suspended, active or revoked")
    if not body.reason.strip():
        _400("an officer reason is required")
    if p["status"] == "revoked":
        _400("a revoked passport cannot change status; renew instead")
    p = db.set_passport_status(jti, body.status, config.OFFICER, body.reason)
    audit.record("lifecycle", jti, {"event": f"status changed to {body.status}", "officer": config.OFFICER, "reason": body.reason})
    return p


@app.post("/api/passports/{jti}/renew")
def renew(jti: str):
    p = db.get_passport(jti) or _404()
    audit.record("lifecycle", jti, {"event": "renewal requested (recorded only in v1; a new passport for the next tax year would be issued through a fresh review)", "officer": config.OFFICER})
    return {"ok": True, "note": "Renewal recorded. v1 does not mint a second passport."}


# ── API: relying party ─────────────────────────────────────────────────────
@app.get("/api/status/{jti}")
def status(jti: str):
    p = db.get_passport(jti) or _404()
    return {"jti": jti, "status": p["status"], "expires_at": p["expires_at"], "checked_at": db.now_iso()}


@app.get("/api/passports/{jti}")
def get_passport(jti: str):
    p = db.get_passport(jti) or _404()
    header, _ = crypto.decode_unverified(p["jwt"])
    return {**p, "header": header, "minimal": minimal_passport(p)}


def minimal_passport(p: dict) -> dict:
    """What the relying party sees: permission, not personal data."""
    pl = p["payload"]
    return {
        "passport_id": pl["jti"], "issuer": pl["iss"], "agent_id": pl["subject"]["agent_id"],
        "scope": pl["authorization_details"][0], "issued_at": p["issued_at"], "valid_until": pl["valid_until"],
        "status": p["status"], "agent_key_kid": crypto.jwk_thumbprint(pl["cnf"]["jwk"])[:16], "signature_kid": crypto.authority_keys()["kid"],
    }


class ActIn(BaseModel):
    jti: str
    action: str
    utr: str
    tax_year: str
    tax_due: float = 0
    signer: str = "agent"  # agent | rogue


_rogue: dict | None = None


def rogue_key() -> dict:
    global _rogue
    if _rogue is None:
        priv, pub = crypto.generate_keypair()
        _rogue = {"private_pem": priv, "public_pem": pub}
    return _rogue


@app.post("/api/agent/act")
def agent_act(body: ActIn):
    """Simulated agent: builds a request, signs it, presents it to the gateway."""
    p = db.get_passport(body.jti) or _404()
    a = db.get_application(p["application_id"])
    req = {"passport_jti": body.jti, "action": body.action, "utr": body.utr, "tax_year": body.tax_year, "tax_due": body.tax_due, "nonce": crypto.new_nonce()}
    key = a["agent"]["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    req["agent_sig"] = crypto.sign_bytes(key, rules.request_signing_input(req))
    return verify(VerifyIn(passport=p["jwt"], request=req))


class VerifyIn(BaseModel):
    passport: str
    request: dict


@app.post("/api/verify")
def verify(body: VerifyIn):
    """The authority gateway. Presented passport + signed request → decision + signed receipt.
    The audit entry stores every input the decision depended on (token, registry status at the
    time, the signed request) so /api/audit/{id}/replay can re-run the pure function later."""
    _, unverified = crypto.decode_unverified(body.passport)
    jti = unverified.get("jti")
    p = db.get_passport(jti) if jti else None
    reg_status = p["status"] if p else "unknown"
    res = rules.verify_action(body.passport, reg_status, body.request)
    entry = {"event": "verification", "jti": jti, "request": body.request, "registry_status": reg_status, "presented_token": body.passport,
             "request_hash": crypto.sha256_hex(rules.request_signing_input(body.request)), "decision": res["decision"], "rule": res["rule"], "code": res["code"], "reason": res["reason"], "trace": res["trace"], "rule_pack": res["rule_pack"]}
    rec = audit.record("verify", jti, entry, receipt_for={"jti": jti, "decision": res["decision"], "rule": res["rule"], "code": res["code"], "request_hash": entry["request_hash"]})
    return {**res, "audit_id": rec["id"], "audit_hash": rec["hash"], "prev_hash": rec["prev_hash"], "receipt": rec["receipt"]}


# ── API: audit ─────────────────────────────────────────────────────────────
@app.get("/api/audit")
def audit_list():
    rows = db.list_audit()
    chain = audit.verify_chain(list(reversed(rows)))
    return {"rows": rows, "chain": chain}


@app.post("/api/audit/{audit_id}/replay")
def replay(audit_id: int):
    """Re-run a past verification from its stored inputs. Same inputs, same rule pack, same answer."""
    r = db.get_audit(audit_id) or _404()
    if r["kind"] != "verify":
        _400("only verification entries can be replayed")
    e = r["entry"]
    res = rules.verify_action(e["presented_token"], e["registry_status"], e["request"])
    same = res["decision"] == e["decision"] and res["rule"] == e["rule"] and res["code"] == e["code"]
    return {"audit_id": audit_id, "original": {"decision": e["decision"], "rule": e["rule"], "code": e["code"]}, "replay": {"decision": res["decision"], "rule": res["rule"], "code": res["code"]}, "identical": same, "rule_pack": res["rule_pack"]}


@app.get("/api/receipt/verify")
def receipt_verify(token: str):
    payload = crypto.verify_jwt(token)
    return {"verified": payload is not None, "payload": payload}


# ── Demo control ───────────────────────────────────────────────────────────
@app.post("/api/reset")
def reset():
    db.reset_all()
    audit.record("system", None, {"event": "demo reset"})
    return {"ok": True}


def _404():
    raise HTTPException(404, "not found")


def _400(msg: str):
    raise HTTPException(400, msg)
