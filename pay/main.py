"""Agent Passport — payments vertical. FastAPI routes: server-rendered views + JSON API.

Flow: Apply (/provider) → Review & issue (/regulator) → Customer signs the mandate (/customer)
      → Act & check at the bank (/bank) → Maintain (lifecycle, incidents) → /audit.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import audit, config, crypto, db, extraction, fixtures, review, rules, vouch

HERE = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    crypto.all_signers()
    yield


app = FastAPI(title="Agent Passport · payments", version=config.APP_VERSION, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def ctx(request: Request, **kw) -> dict:
    s = crypto.all_signers()
    return {"request": request, "rule_pack": rules.pack()["id"], "issuer": config.ISSUER_NAME, "officer": config.OFFICER,
            "operator": config.OPERATOR, "customer": config.CUSTOMER, "bank": config.BANK, "agent_name": config.AGENT_NAME,
            "kids": {n: v["kid"] for n, v in s.items()}, "version": config.APP_VERSION, "extraction_mode": config.EXTRACTION_MODE,
            "vouch_mode": vouch.mode(), "payment_rail": vouch.rail(), **kw}


# ── Views ──────────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/provider")


for _name in ("provider", "regulator", "customer", "bank", "audit"):
    def _make(name):
        def view(request: Request):
            return templates.TemplateResponse(request, f"{name}.html", ctx(request, view=name))
        view.__name__ = f"view_{name}"
        return view
    app.get(f"/{_name}", response_class=HTMLResponse, include_in_schema=False)(_make(_name))


@app.get("/about", response_class=HTMLResponse, include_in_schema=False)
def view_about(request: Request):
    return templates.TemplateResponse(request, "about.html", ctx(request, view="about", pack=rules.pack()))


# ── API: meta ──────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True, "version": config.APP_VERSION, "vertical": "payments", "rule_pack": rules.pack()["id"],
            "extraction_mode": config.EXTRACTION_MODE, "vouch_mode": vouch.mode(), "payment_rail": vouch.rail()}


@app.get("/api/rulepack")
def rulepack():
    return rules.pack()


@app.get("/api/signers")
def signers():
    """The three public keys a relying party needs. Nothing private."""
    return {n: {"kid": s["kid"], "jwk": s["jwk"], "alg": "EdDSA", "signs": {"authority": "assurance", "payrail": "agent_identity", "northgate": "mandate"}[n]}
            for n, s in crypto.all_signers().items()}


@app.get("/api/vouch")
def vouch_info():
    return {"mode": vouch.mode(), "payment_rail": vouch.rail(), "base_url": config.VOUCH_BASE_URL if vouch.mode() == "live" else None, **vouch.org_self()}


@app.get("/api/state")
def state():
    """Everything the views need in one call."""
    apps = db.list_applications()
    pps = db.list_passports()
    pol = rules.pack()["policy"]
    pat = pol.get("pattern_threshold", {"count": 2, "window_hours": 24})
    return {"applications": [public_app(a) for a in apps], "passports": [public_passport(p) for p in pps], "beats": fixtures.BEATS,
            "invoices": [{"id": k, "label": "Clean invoice" if k.endswith("clean") else "Poisoned invoice", "text": t} for k, t in extraction.invoices().items()],
            "incidents": db.list_audit(50, kind="incident"), "violations": db.list_violations(), "alerts": db.pattern_alerts(pat["count"], pat["window_hours"]), "pattern_threshold": pat,
            "vouch_mode": vouch.mode(), "payment_rail": vouch.rail(),
            "mandate_draft": mandate_draft(), "policy": {k: pol[k] for k in ("per_payment_ceiling_gbp", "monthly_per_account_ceiling_gbp", "max_validity", "action_types", "currency", "human_confirm_above_gbp")},
            "delegation_chain": config.DELEGATION_CHAIN == "on", "delegation_max_gbp": config.DELEGATION_MAX_GBP, "chain_beats": fixtures.CHAIN_BEATS, "chain_rules": rules.pack().get("chain_rules", [])}


def mandate_draft() -> dict:
    """The customer's own draft mandate (Phase 3 prefill). Never part of the provider's registration."""
    import json as _json
    d = _json.loads((config.FIXTURES_DIR / "customer" / "mandate_draft.json").read_text())
    d.pop("_comment", None)
    return d


def public_app(a: dict) -> dict:
    a = dict(a)
    ag = a.get("agent") or {}
    a["agent"] = {k: v for k, v in ag.items() if k != "private_pem"}
    if a["agent"].get("execution"):
        a["agent"]["execution"] = {k: v for k, v in a["agent"]["execution"].items() if k != "private_pem"}
    return a


def public_passport(p: dict) -> dict:
    p = dict(p)
    p["envelope"] = envelope_of(p)
    p["mandate_signed"] = bool(p.get("mandate_jwt"))
    p["payments"] = db.count_payments(p["passport_id"])
    p["ledger"] = db.ledger_totals(p["passport_id"])
    return p


def envelope_of(p: dict) -> dict:
    """The composite passport as presented to a relying party."""
    return {
        "passport_id": p["passport_id"],
        "assurance": p["assurance_jwt"],
        "agent_identity": p["agent_identity_jwt"],
        "mandate": p.get("mandate_jwt"),
        "status_url": f"/api/status/{p['passport_id']}",
        "vouch_voucher_id": p.get("vouch_voucher_id"),
        "cnf": None,  # key binding lives inside agent_identity.cnf, signed by the provider
    }


# ── API: provider (operator) ───────────────────────────────────────────────
@app.post("/api/applications")
def create_application():
    n = db.count_applications() + 107
    ref = f"AP-2026-{n:04d}"
    a = db.create_application(ref, fixtures.evidence_pack())
    audit.record("application", ref, {"event": "draft created", "provider": config.OPERATOR, "documents": [d["name"] for d in a["documents"]]})
    return public_app(a)


@app.post("/api/applications/{app_id}/extract")
def extract(app_id: int):
    a = db.get_application(app_id) or _404()
    facts, mode = extraction.extract(a["documents"])
    a = db.update_application(app_id, extraction=facts, fields=facts, extraction_mode=mode)
    n_fields = sum(len(v) for k, v in facts.items() if isinstance(v, dict) and not k.startswith("_")) + len(facts.get("suppliers", []))
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
    """PayRail provisions the agent's key pair and the authority issues a challenge."""
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


def agent_identity_payload(a: dict) -> dict:
    f, ag = a["fields"], a["agent"]
    return {
        "iss": "payrail-ltd", "typ": "agent_identity", "sub": ag["agent_id"], "iat": crypto.now_ts(), "application": a["ref"],
        "operator": {"legal_name": rules._v(f, "provider", "legal_name"), "licence_ref": rules._v(f, "provider", "licence_ref")},
        "agent": {"name": rules._v(f, "agent", "agent_name"), "agent_id": ag["agent_id"], "software": rules._v(f, "agent", "software"),
                  "software_version": rules._v(f, "agent", "software_version"), "model_provider": rules._v(f, "agent", "model_provider"),
                  "model_version": rules._v(f, "agent", "model_version"), "training_type": rules._v(f, "agent", "training_type"),
                  "config_sha256": rules._v(f, "agent", "config_hash")},
        "key_management": {"storage": rules._v(f, "agent", "key_storage"), "rotation": rules._v(f, "agent", "key_rotation")},
        "cnf": {"jwk": ag["jwk"]},
    }


@app.post("/api/applications/{app_id}/submit")
def submit(app_id: int):
    a = db.get_application(app_id) or _404()
    if not a.get("fields"):
        _400("read the documents first")
    checks = rules.run_application_checks(a["fields"], a.get("agent"))
    ident_jwt = crypto.sign_jwt("payrail", agent_identity_payload(a), typ="agent-identity+jwt") if a.get("agent") else None
    a = db.update_application(app_id, status="submitted", submitted_at=db.now_iso(), checks=checks, agent_identity_jwt=ident_jwt)
    audit.record("check", a["ref"], {"event": "application submitted; agent_identity signed by the provider; automated checks run",
                                     "passed": sum(c["result"] == "pass" for c in checks), "flagged": [c["id"] for c in checks if c["result"] != "pass"],
                                     "agent_identity_sha256": crypto.sha256_hex(ident_jwt) if ident_jwt else None})
    return public_app(a)


# ── API: regulator ─────────────────────────────────────────────────────────
class ReviewIn(BaseModel):
    human_confirm_above: float | None = None


@app.post("/api/applications/{app_id}/review")
def run_review(app_id: int, body: ReviewIn | None = None):
    """Task 2: the Standards Review Assistant's six steps. Deterministic; the sandbox uses the bank's own engine.
    Stored on the application. Never changes its status."""
    a = db.get_application(app_id) or _404()
    if a["status"] not in ("submitted", "info_requested", "approved", "rejected"):
        _400("submit the application first")
    try:
        r = review.run(a, body.human_confirm_above if body else None)
    except ValueError as exc:
        _400(str(exc))
    a = db.update_application(app_id, review=r)
    sb = r["steps"][3]["data"]
    audit.record("review", a["ref"], {"event": "Standards Review Assistant run", "rule_pack": r["rule_pack"], "sandbox_passed": sum(1 for t in sb if t["pass"]), "sandbox_total": len(sb),
                                      "recommendation": r["steps"][4]["data"]["verdict"], "decides": False})
    return {"application": public_app(a), "review": r}


class DecisionIn(BaseModel):
    decision: str  # approve | request_info | reject
    note: str
    human_confirm_above: float | None = None


@app.post("/api/applications/{app_id}/decision")
def decide(app_id: int, body: DecisionIn):
    a = db.get_application(app_id) or _404()
    if a["status"] not in ("submitted", "info_requested"):
        raise HTTPException(409, f"application is {a['status']}")
    if not body.note.strip():
        _400("an officer note is required")
    if body.decision == "approve":
        thr = float(body.human_confirm_above if body.human_confirm_above is not None else rules.pack()["policy"]["human_confirm_above_gbp"])
        condition = {"human_confirm_above": {"amount": thr, "currency": "GBP"}}
        p = issue_passport(a, body.note, condition)
        a = db.update_application(app_id, status="approved", decided_at=db.now_iso(), officer=config.OFFICER, officer_note=body.note, condition=condition)
        audit.record("decision", a["ref"], {"event": "approved with condition; assurance signed", "officer": config.OFFICER, "note": body.note, "condition": condition, "passport_id": p["passport_id"]})
        p = mirror_on_vouch(p)
        return {"application": public_app(a), "passport": public_passport(p)}
    if body.decision == "request_info":
        a = db.update_application(app_id, status="info_requested", officer=config.OFFICER, officer_note=body.note)
        audit.record("decision", a["ref"], {"event": "further information requested", "officer": config.OFFICER, "note": body.note})
        return {"application": public_app(a)}
    if body.decision == "reject":
        a = db.update_application(app_id, status="rejected", decided_at=db.now_iso(), officer=config.OFFICER, officer_note=body.note)
        audit.record("decision", a["ref"], {"event": "rejected", "officer": config.OFFICER, "note": body.note})
        return {"application": public_app(a)}
    _400("unknown decision")


def issue_passport(a: dict, note: str, condition: dict) -> dict:
    f = a["fields"]
    ag = a["agent"] or _400("agent key not registered")
    if not ag.get("pop_verified"):
        _400("agent has not proven possession of its key")
    ident_jwt = a.get("agent_identity_jwt") or _400("agent identity not signed by the provider")
    ident = crypto.verify_jwt("payrail", ident_jwt) or _400("agent identity signature does not verify")
    pol = rules.pack()["policy"]
    valid_until = pol["max_validity"]
    exp = int(datetime.fromisoformat(valid_until + "T23:59:59+00:00").timestamp())
    checks = a.get("checks") or []
    ceilings = {"per_payment_ceiling": {"amount": float(pol["per_payment_ceiling_gbp"]), "currency": pol["currency"]},
                "monthly_per_account_ceiling": {"amount": float(pol["monthly_per_account_ceiling_gbp"]), "currency": pol["currency"], "window": pol["monthly_window"]},
                "max_validity": pol["max_validity"], "action_types": list(pol["action_types"])}
    assurance = {
        "iss": config.ISSUER, "typ": "assurance", "jti": a["ref"], "iat": crypto.now_ts(), "nbf": crypto.now_ts(), "exp": exp,
        "valid_until": valid_until, "rule_pack_version": rules.pack()["id"],
        "provider": {"legal_name": rules._v(f, "provider", "legal_name"), "licence_ref": rules._v(f, "provider", "licence_ref"), "companies_house_number": rules._v(f, "provider", "companies_house_number")},
        "agent_id": ag["agent_id"],
        "assurance": {"kya_status": "ASSURED", "checks_passed": sum(c["result"] == "pass" for c in checks), "checks_flagged": [c["id"] for c in checks if c["result"] != "pass"]},
        "condition": condition,
        "policy_ceilings": ceilings,
        "accountable_person": {"name": rules._v(f, "accountable_person", "name"), "role": rules._v(f, "accountable_person", "role"), "declaration_ref": rules._v(f, "accountable_person", "declaration_ref")},
        "binds": {"agent_identity_sha256": crypto.sha256_hex(ident_jwt), "agent_kid": ag["kid"]},
        "status": {"registry": f"/api/status/{a['ref']}"},
        "issued_by": config.OFFICER,
    }
    # Phase 3 belongs to the customer: until it signs, the envelope carries only the ceilings the mandate must fit in.
    mandate_proposed = {
        "typ": "mandate", "passport_id": a["ref"], "valid_until": valid_until, "exp": exp, "customer": None, "authorising_officer": None,
        "provider": rules._v(f, "provider", "legal_name"), "agent_id": ag["agent_id"], "agent_kid": ag["kid"], "written_by": "customer",
        "authorization_details": [{
            "type": "payment_initiation", "actions": list(pol["action_types"]), "currency": pol["currency"], "supplier_allowlist": [],
            "per_payment_limit": {"amount": float(pol["per_payment_ceiling_gbp"]), "currency": pol["currency"]},
            "monthly_limit_per_account": {"amount": float(pol["monthly_per_account_ceiling_gbp"]), "currency": pol["currency"], "window": pol["monthly_window"]},
        }],
        "ceilings": ceilings,
    }
    token = crypto.sign_jwt("authority", assurance, typ="assurance+jwt")
    p = db.create_passport(a["ref"], a["id"], token, assurance, ident_jwt, ident, mandate_proposed, valid_until, config.OFFICER)
    audit.record("issue", a["ref"], {"event": "assurance signed and entered in registry as ACTIVE; policy ceilings set; the customer writes its own mandate",
                                     "authority_kid": crypto.signer("authority")["kid"], "agent_kid": ag["kid"], "condition": condition, "policy_ceilings": ceilings})
    return p


def mirror_on_vouch(p: dict) -> dict:
    r = vouch.mint_mandate(p)
    p = db.set_vouch(p["passport_id"], r["voucher_id"], r["mode"], r["status"])
    audit.record("vouch", p["passport_id"], {"event": "mandate mirrored on the vouch rail", "mode": r["mode"], "voucher_id": r["voucher_id"], "detail": r["detail"]})
    return p


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


@app.post("/api/passports/{passport_id}/status")
def lifecycle(passport_id: str, body: LifecycleIn):
    p = db.get_passport(passport_id) or _404()
    if body.status not in ("suspended", "active", "revoked"):
        _400("status must be suspended, active or revoked")
    if not body.reason.strip():
        _400("an officer reason is required")
    if p["status"] == "revoked":
        _400("a revoked passport cannot change status; a fresh application is needed")
    p = db.set_passport_status(passport_id, body.status, config.OFFICER, body.reason)
    audit.record("lifecycle", passport_id, {"event": f"status changed to {body.status}", "officer": config.OFFICER, "reason": body.reason})
    if body.status in ("revoked", "active"):
        # the exception loop closes: REVOKE resolves the open violations as revoked, REINSTATE as false positives
        n = db.set_violation_status(passport_id, "RESOLVED", "revoked" if body.status == "revoked" else "reinstated")
        if p.get("investigation") or n:
            p = db.set_investigation(passport_id, None)
            audit.record("exception", passport_id, {"event": "investigation closed", "outcome": "revoked" if body.status == "revoked" else "reinstated", "violations_resolved": n, "officer": config.OFFICER, "reason": body.reason})
    if body.status == "revoked":
        r = vouch.revoke_mandate(p.get("vouch_voucher_id"))
        p = db.set_vouch(passport_id, p.get("vouch_voucher_id"), r["mode"], r["status"])
        audit.record("vouch", passport_id, {"event": "mandate revoked on the vouch rail", "mode": r["mode"], "voucher_id": p.get("vouch_voucher_id"), "detail": r["detail"]})
    return public_passport(p)


class InvestigationIn(BaseModel):
    action: str   # open | close
    note: str = ""


@app.post("/api/passports/{passport_id}/investigation")
def investigation(passport_id: str, body: InvestigationIn):
    """Task 3: INVESTIGATING is a supervisor state around the lifecycle, not a bank rule. It blocks nothing by itself:
    the bank still reads active / suspended / revoked. Opening it marks the passport's OPEN violations INVESTIGATING."""
    p = db.get_passport(passport_id) or _404()
    if body.action == "open":
        if p["status"] == "revoked":
            _400("a revoked passport is closed; nothing to investigate")
        p = db.set_investigation(passport_id, "investigating")
        n = db.set_violation_status(passport_id, "INVESTIGATING", None, only_status=("OPEN",))
        audit.record("exception", passport_id, {"event": "investigation opened", "officer": config.OFFICER, "note": body.note, "violations": n, "passport_status": p["status"]})
    elif body.action == "close":
        p = db.set_investigation(passport_id, None)
        audit.record("exception", passport_id, {"event": "investigation closed without change", "officer": config.OFFICER, "note": body.note})
    else:
        _400("action must be open or close")
    return {**public_passport(p), "violations": db.list_violations(passport_id)}


@app.get("/api/violations")
def violations(passport_id: str | None = None):
    pat = rules.pack()["policy"].get("pattern_threshold", {"count": 2, "window_hours": 24})
    return {"violations": db.list_violations(passport_id), "alerts": db.pattern_alerts(pat["count"], pat["window_hours"]), "pattern_threshold": pat}


@app.get("/api/violations/{vid}")
def violation(vid: int):
    return db.get_violation(vid) or _404()


@app.get("/api/passports/{passport_id}/vouch")
def passport_vouch(passport_id: str):
    p = db.get_passport(passport_id) or _404()
    return {"voucher_id": p.get("vouch_voucher_id"), "recorded": {"mode": p.get("vouch_mode"), "status": p.get("vouch_status")}, "live": vouch.mandate_status(p.get("vouch_voucher_id"))}


# ── API: customer ──────────────────────────────────────────────────────────
class MandateIn(BaseModel):
    """The customer's own mandate (Phase 3). Omitted fields fall back to the customer's draft."""
    customer: dict | None = None
    authorising_officer: dict | None = None
    supplier_allowlist: list[dict] | None = None
    per_payment_limit: float | None = None
    monthly_limit_per_account: float | None = None
    valid_until: str | None = None
    actions: list[str] | None = None


@app.post("/api/passports/{passport_id}/mandate/check")
def check_mandate(passport_id: str, body: MandateIn | None = None):
    """Ceiling containment preview: the same check that runs at signing, without signing."""
    p = db.get_passport(passport_id) or _404()
    m = _merge_mandate(body)
    problems = rules.check_mandate_containment(m, p["assurance"]["valid_until"])
    return {"within_ceilings": not problems, "problems": problems, "ceilings": p["mandate_proposed"].get("ceilings"), "mandate": m}


def _merge_mandate(body: MandateIn | None) -> dict:
    d = mandate_draft()
    if body:
        for k in ("customer", "authorising_officer", "supplier_allowlist", "per_payment_limit", "monthly_limit_per_account", "valid_until", "actions"):
            v = getattr(body, k)
            if v is not None:
                d[k] = v
    d["supplier_allowlist"] = [{"supplier_id": (x.get("supplier_id") or f"SUP-{i + 1:03d}"), "name": (x.get("name") or "").strip(), "account_ref": (x.get("account_ref") or "").strip()} for i, x in enumerate(d.get("supplier_allowlist") or [])]
    return d


@app.post("/api/passports/{passport_id}/mandate/sign")
def sign_mandate(passport_id: str, body: MandateIn | None = None):
    """Phase 3: the customer writes and signs its own mandate with the customer key. Live at once; no authority review.
    The only gate is ceiling containment against the policy ceilings the authority set at Phase 2."""
    p = db.get_passport(passport_id) or _404()
    if p.get("mandate_jwt"):
        _400("mandate already signed")
    if p["status"] == "revoked":
        _400("passport revoked; nothing to sign")
    m = _merge_mandate(body)
    problems = rules.check_mandate_containment(m, p["assurance"]["valid_until"])
    if problems:
        raise HTTPException(422, {"message": "mandate outside the policy ceilings", "problems": problems})
    pol = rules.pack()["policy"]
    mp = p["mandate_proposed"]
    payload = {
        "iss": "northgate-joinery-ltd", "typ": "mandate", "passport_id": passport_id, "iat": crypto.now_ts(), "valid_until": m["valid_until"],
        "exp": int(datetime.fromisoformat(m["valid_until"] + "T23:59:59+00:00").timestamp()),
        "customer": m["customer"], "authorising_officer": m["authorising_officer"], "signed_by": m["authorising_officer"],
        "provider": mp["provider"], "agent_id": mp["agent_id"], "agent_kid": mp["agent_kid"], "written_by": "customer",
        "authorization_details": [{"type": "payment_initiation", "actions": list(m["actions"]), "currency": pol["currency"], "supplier_allowlist": m["supplier_allowlist"],
                                   "per_payment_limit": {"amount": float(m["per_payment_limit"]), "currency": pol["currency"]},
                                   "monthly_limit_per_account": {"amount": float(m["monthly_limit_per_account"]), "currency": pol["currency"], "window": pol["monthly_window"]}}],
        "within_ceilings": True,
    }
    token = crypto.sign_jwt("northgate", payload, typ="mandate+jwt")
    p = db.set_mandate(passport_id, token, payload)
    with db.tx() as con:
        con.execute("UPDATE passports SET mandate_proposed_json=? WHERE passport_id=?", (__import__("json").dumps({**mp, **{k: payload[k] for k in ("customer", "authorising_officer", "valid_until", "authorization_details")}}), passport_id))
    p = db.get_passport(passport_id)
    audit.record("mandate", passport_id, {"event": "customer wrote and signed its mandate; ceiling containment passed; envelope complete; live at once", "signer": payload["signed_by"], "customer_kid": crypto.signer("northgate")["kid"],
                                          "suppliers": len(m["supplier_allowlist"]), "per_payment_limit": float(m["per_payment_limit"]), "monthly_limit_per_account": float(m["monthly_limit_per_account"]), "valid_until": m["valid_until"]})
    return public_passport(p)


# ── API: relying party (the bank) ──────────────────────────────────────────
@app.get("/api/status/{passport_id}")
def status(passport_id: str):
    p = db.get_passport(passport_id) or _404()
    return {"passport_id": passport_id, "status": p["status"], "mandate_signed": bool(p.get("mandate_jwt")), "expires_at": p["expires_at"], "checked_at": db.now_iso()}


@app.get("/api/passports/{passport_id}")
def get_passport(passport_id: str):
    p = db.get_passport(passport_id) or _404()
    env = envelope_of(p)
    ver = crypto.verify_envelope(env)
    parts = {"assurance": crypto.verify_jwt("authority", env["assurance"]) is not None,
             "agent_identity": crypto.verify_jwt("payrail", env["agent_identity"]) is not None,
             "mandate": (crypto.verify_jwt("northgate", env["mandate"]) is not None) if env.get("mandate") else None}
    headers = {k: crypto.decode_unverified(env[k])[0] for k in ("assurance", "agent_identity", "mandate") if env.get(k)}
    return {**public_passport(p), "verification": {"ok": ver["ok"], "failure": ver["failure"], "parts": parts}, "headers": headers, "minimal": minimal_passport(p)}


def minimal_passport(p: dict) -> dict:
    """What the bank sees: permission and keys, not personal data."""
    a, i, m = p["assurance"], p["agent_identity"], p.get("mandate")
    ad = (m or p["mandate_proposed"])["authorization_details"][0]
    return {
        "passport_id": p["passport_id"], "issuer": a["iss"], "provider": a["provider"]["legal_name"], "licence_ref": a["provider"]["licence_ref"], "policy_ceilings": a.get("policy_ceilings"),
        "agent": i["agent"]["name"], "agent_id": i["agent"]["agent_id"], "agent_kid": crypto.jwk_thumbprint(i["cnf"]["jwk"])[:16],
        "condition": a["condition"], "valid_until": a["valid_until"], "status": p["status"], "mandate_signed": bool(m),
        "scope": {"actions": ad["actions"], "currency": ad["currency"], "suppliers": len(ad["supplier_allowlist"]), "per_payment_limit": ad["per_payment_limit"], "monthly_limit_per_account": ad["monthly_limit_per_account"]},
        "signers": {"assurance": crypto.signer("authority")["kid"], "agent_identity": crypto.signer("payrail")["kid"], "mandate": crypto.signer("northgate")["kid"]},
    }


# ── Part B: AP Orchestrator Agent → Payment Execution Agent ─────────────────
def execution_key(a: dict) -> dict:
    """The Payment Execution Agent's own key pair, generated once per application and kept with the agent record (demo)."""
    ag = a["agent"]
    if not ag.get("execution"):
        priv, pub = crypto.generate_keypair()
        jwk = crypto.public_jwk(pub)
        ag["execution"] = {"agent_id": f"{ag['agent_id']}-exec", "private_pem": priv, "public_pem": pub, "jwk": jwk, "kid": crypto.jwk_thumbprint(jwk)[:16]}
        db.update_application(a["id"], agent=ag)
    return ag["execution"]


def make_delegation(a: dict, passport_id: str, beneficiary: str, max_amount: float, valid_until: str) -> str:
    """The orchestrator (the key bound in agent_identity) delegates a narrowed scope to the execution agent."""
    ex = execution_key(a)
    payload = {"iss": a["agent"]["agent_id"], "typ": "delegation", "sub": ex["agent_id"], "passport_id": passport_id, "iat": crypto.now_ts(), "cnf": {"jwk": ex["jwk"]},
               "scope": {"beneficiaries": [beneficiary], "max_amount": float(max_amount), "currency": "GBP", "actions": ["pay_invoice"], "valid_until": valid_until, "purpose": "pay one supplier invoice"}}
    return crypto.sign_jwt_pem(a["agent"]["private_pem"], payload, typ="delegation+jwt")


def chain_on(flag: bool | None) -> bool:
    return config.DELEGATION_CHAIN == "on" if flag is None else bool(flag)


class ActIn(BaseModel):
    passport_id: str
    action_type: str = "pay_invoice"
    payee_account_ref: str
    supplier_name: str
    amount: float
    currency: str = "GBP"
    invoice_ref: str | None = None
    signer: str = "agent"  # agent | rogue
    chain: bool | None = None            # None = deployment default (DELEGATION_CHAIN)
    delegate_amount: float | None = None # orchestrator's ceiling for this delegation
    delegate_account: str | None = None  # orchestrator's beneficiary (defaults to the instruction's payee)


_rogue: dict | None = None


def rogue_key() -> dict:
    global _rogue
    if _rogue is None:
        priv, pub = crypto.generate_keypair()
        _rogue = {"private_pem": priv, "public_pem": pub}
    return _rogue


@app.post("/api/agent/act")
def agent_act(body: ActIn):
    """Simulated Agent 247: builds a payment instruction, signs it, presents it to the bank."""
    p = db.get_passport(body.passport_id) or _404()
    a = db.get_application(p["application_id"])
    req = {"passport_id": body.passport_id, "action_type": body.action_type, "payee_account_ref": body.payee_account_ref, "supplier_name": body.supplier_name,
           "amount": body.amount, "currency": body.currency, "invoice_ref": body.invoice_ref, "nonce": crypto.new_nonce()}
    if chain_on(body.chain):
        req["delegation"] = make_delegation(a, body.passport_id, body.delegate_account or body.payee_account_ref, body.delegate_amount or config.DELEGATION_MAX_GBP, p["expires_at"])
        key = execution_key(a)["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    else:
        key = a["agent"]["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
    return verify(VerifyIn(passport_id=body.passport_id, instruction=req))


class InvoiceIn(BaseModel):
    passport_id: str
    invoice_id: str          # INV-9001-clean | INV-9001-poisoned
    signer: str = "agent"
    chain: bool | None = None


@app.post("/api/agent/invoice")
def agent_invoice(body: InvoiceIn):
    """Task 1: Agent 247 reads an invoice with the model (verbatim-quote extraction), turns what it read into a
    signed payment instruction, and presents it to the bank. Returns every step so the UI can show the manipulation
    moment: extracted text → generated instruction → bank decision. The model reads; it never decides."""
    p = db.get_passport(body.passport_id) or _404()
    texts = extraction.invoices()
    if body.invoice_id not in texts:
        _400("unknown invoice")
    facts, mode = extraction.extract_invoice(body.invoice_id, texts[body.invoice_id])
    v = lambda k: (facts.get(k) or {}).get("value")  # noqa: E731
    account_ref = f"{v('sort_code')} {v('account_number')}".strip()
    audit.record("agent", body.passport_id, {"event": "agent read an invoice into a payment instruction", "invoice": body.invoice_id, "mode": mode,
                                             "model": config.GEMINI_MODEL if mode == "gemini" else None, "payee_account_ref": account_ref, "amount": v("amount_gbp"),
                                             "bank_details_changed": v("bank_details_changed")})
    a = db.get_application(p["application_id"])
    req = {"passport_id": body.passport_id, "action_type": "pay_invoice", "payee_account_ref": account_ref, "supplier_name": v("supplier_name"),
           "amount": float(v("amount_gbp") or 0), "currency": "GBP", "invoice_ref": v("invoice_ref"), "nonce": crypto.new_nonce()}
    if chain_on(body.chain):
        # the orchestrator read the invoice; it delegates exactly what it read to the execution agent
        req["delegation"] = make_delegation(a, body.passport_id, account_ref, config.DELEGATION_MAX_GBP, p["expires_at"])
        key = execution_key(a)["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    else:
        key = a["agent"]["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
    mandate = p.get("mandate") or p["mandate_proposed"]
    allow = mandate["authorization_details"][0]["supplier_allowlist"]
    on_allowlist = any(rules.norm_account(x["account_ref"]) == rules.norm_account(account_ref) for x in allow)
    registered = next((x["account_ref"] for x in allow if (x.get("name") or "").lower() == str(v("supplier_name") or "").lower()), None)
    evidence = {"invoice": body.invoice_id, "extraction_mode": mode, "facts": facts, "instruction_payee": account_ref, "registered_payee": registered}
    result = verify(VerifyIn(passport_id=body.passport_id, instruction=req, evidence=evidence))
    return {"invoice": body.invoice_id, "text": texts[body.invoice_id], "extraction": facts, "extraction_mode": mode, "chain": bool(req.get("delegation")),
            "delegation": crypto.decode_unverified(req["delegation"])[1] if req.get("delegation") else None,
            "instruction": {k: v_ for k, v_ in req.items() if k not in ("agent_signature", "delegation")}, "on_allowlist": on_allowlist, "registered_payee": registered, "result": result}


class VerifyIn(BaseModel):
    """Two accepted shapes. Nested: {passport_id, instruction: {...signed fields..., agent_signature}, passport?}.
    Flat (the brief's contract): {passport_id, agent_signature, action_type, payee_account_ref, supplier_name, amount, currency, invoice_ref, nonce}."""
    passport_id: str
    instruction: dict | None = None   # signed payment instruction
    passport: dict | None = None      # optional presented envelope; otherwise fetched from the registry by id
    agent_signature: str | None = None
    action_type: str | None = None
    payee_account_ref: str | None = None
    supplier_name: str | None = None
    amount: float | None = None
    currency: str | None = None
    invoice_ref: str | None = None
    nonce: str | None = None
    evidence: dict | None = None      # e.g. the invoice extraction that produced this instruction (recorded on refusal)

    def instruction_dict(self) -> dict:
        if self.instruction:
            return self.instruction
        flat = {"passport_id": self.passport_id, "action_type": self.action_type, "payee_account_ref": self.payee_account_ref, "supplier_name": self.supplier_name,
                "amount": self.amount, "currency": self.currency, "invoice_ref": self.invoice_ref, "nonce": self.nonce, "agent_signature": self.agent_signature}
        return {k: v for k, v in flat.items() if v is not None}


@app.post("/api/verify")
def verify(body: VerifyIn):
    """The bank's gateway. Envelope (presented or fetched by id) + signed instruction + registry status +
    the bank's own ledger total → decision + signed receipt. The audit entry stores every input the decision
    depended on so /api/audit/{id}/replay can re-run the pure function later.
    Response carries both names for the rule and the audit anchor: rule / rule_id, audit_hash / audit_ref."""
    p = db.get_passport(body.passport_id)
    env = body.passport or (envelope_of(p) if p else {"passport_id": body.passport_id, "assurance": None, "agent_identity": None, "mandate": None})
    reg_status = p["status"] if p else "unknown"
    req = body.instruction_dict()
    ledger_total = db.ledger_total(body.passport_id, str(req.get("payee_account_ref") or ""))
    res = rules.verify_action(env, reg_status, req, ledger_total)
    entry = {"event": "verification", "passport_id": body.passport_id, "instruction": req, "registry_status": reg_status, "presented_envelope": env,
             "ledger_total_before": ledger_total, "instruction_hash": crypto.sha256_hex(rules.request_signing_input(req)),
             "decision": res["decision"], "rule": res["rule"], "code": res["code"], "reason": res["reason"], "trace": res["trace"], "rule_pack": res["rule_pack"]}
    rec = audit.record("verify", body.passport_id, entry, receipt_for={"passport_id": body.passport_id, "decision": res["decision"], "rule": res["rule"], "code": res["code"], "instruction_hash": entry["instruction_hash"]})
    r4 = next((t for t in res["trace"] if t["rule"] == "R.4"), None)
    agent_kid = None
    try:
        ident_jwk = ((crypto.verify_jwt("payrail", env.get("agent_identity")) or {}).get("cnf") or {}).get("jwk")
        agent_kid = crypto.jwk_thumbprint(ident_jwk)[:16] if ident_jwk else None
    except Exception:  # noqa: BLE001
        agent_kid = None
    signature = {"checked": r4 is not None, "verified": bool(r4 and r4["ok"]), "alg": "Ed25519 (EdDSA, RFC 8037)", "agent_kid": agent_kid,
                 "signed_fields": list(rules.REQUEST_FIELDS), "instruction_hash": crypto.sha256_hex(rules.request_signing_input(req))}
    out = {**res, "rule_id": res["rule"], "signature": signature, "audit_id": rec["id"], "audit_hash": rec["hash"], "audit_ref": rec["hash"], "prev_hash": rec["prev_hash"], "receipt": rec["receipt"],
           "ledger_total_before": ledger_total, "settlement": None, "incident": None, "violation": None,
           "rails": {"authority_registry": reg_status, "vouch": {"voucher_id": p.get("vouch_voucher_id") if p else None, "status": p.get("vouch_status") if p else None, "mode": p.get("vouch_mode") if p else None}}}
    if res["decision"] == "ALLOW":
        s = vouch.settle_payment(req)
        pay = db.insert_payment(body.passport_id, str(req.get("payee_account_ref")), float(req.get("amount") or 0), str(req.get("currency") or "GBP"), req.get("invoice_ref"), rec["id"], s["rail"], s.get("ref"))
        out["settlement"] = {**s, "ledger_total_after": ledger_total + float(req.get("amount") or 0), "payment_id": pay["id"]}
    elif res["decision"] == "DENY" and p:
        vio = db.insert_violation(body.passport_id, p["assurance"].get("agent_id"), res["rule"], res["code"], req, body.evidence, rec["id"])
        out["violation"] = {"id": vio["id"], "status": vio["status"]}
        n = db.denies_since_last_incident(body.passport_id)
        threshold = rules.pack()["policy"]["incident_deny_threshold"]
        out["deny_count"] = n
        if n >= threshold:
            inc = audit.record("incident", body.passport_id, {"event": "escalated to supervisor", "reason": f"{n} refused instructions since the last incident", "denies": n,
                                                              "last_rule": res["rule"], "last_code": res["code"], "provider": p["assurance"]["provider"]["legal_name"], "agent_id": p["assurance"]["agent_id"]})
            out["incident"] = {"audit_id": inc["id"], "hash": inc["hash"], "denies": n}
    return out


# ── API: audit ─────────────────────────────────────────────────────────────
@app.get("/api/audit")
def audit_list():
    rows = db.list_audit()
    chain = audit.verify_chain(list(reversed(rows)))
    return {"rows": rows, "chain": chain}


@app.post("/api/audit/{audit_id}/replay")
def replay(audit_id: int):
    """Re-run a past verification from its stored inputs. Same inputs, same rule pack, same ledger total, same answer."""
    r = db.get_audit(audit_id) or _404()
    if r["kind"] != "verify":
        _400("only verification entries can be replayed")
    e = r["entry"]
    day = date.fromisoformat(e["ts"][:10])
    res = rules.verify_action(e["presented_envelope"], e["registry_status"], e["instruction"], e.get("ledger_total_before", 0.0), today=day)
    same = res["decision"] == e["decision"] and res["rule"] == e["rule"] and res["code"] == e["code"]
    return {"audit_id": audit_id, "original": {"decision": e["decision"], "rule": e["rule"], "code": e["code"]}, "replay": {"decision": res["decision"], "rule": res["rule"], "code": res["code"]}, "identical": same, "rule_pack": res["rule_pack"]}


@app.get("/api/receipt/verify")
def receipt_verify(token: str):
    payload = crypto.verify_jwt("authority", token)
    return {"verified": payload is not None, "payload": payload}


# ── Demo control ───────────────────────────────────────────────────────────
@app.post("/api/reset")
def reset():
    db.reset_all()
    audit.record("system", None, {"event": "demo reset"})
    return {"ok": True}


@app.post("/api/demo/seed")
def demo_seed(stage: str = "issued"):
    """Restore the exact pre-demo baseline between takes. stage=submitted: registration submitted and reviewed,
    ready for the officer (Stage 1). stage=issued (default): approved, customer mandate signed, passport ACTIVE,
    no payments, no violations. Deterministic: fixture extraction, the customer's draft mandate, the default condition."""
    if stage not in ("submitted", "issued"):
        _400("stage must be submitted or issued")
    db.reset_all()
    audit.record("system", None, {"event": "demo baseline seeded", "stage": stage})
    n = db.count_applications() + 107
    a = db.create_application(f"AP-2026-{n:04d}", fixtures.evidence_pack())
    audit.record("application", a["ref"], {"event": "draft created", "provider": config.OPERATOR, "documents": [d["name"] for d in a["documents"]]})
    facts = extraction.fixture()
    a = db.update_application(a["id"], extraction=facts, fields=facts, extraction_mode="fixture")
    audit.record("extraction", a["ref"], {"event": "documents read into structured facts", "mode": "fixture", "fields": sum(len(v) for k, v in facts.items() if isinstance(v, dict) and not k.startswith("_")), "model": None})
    a = agent_key(a["id"]); a = sign_challenge(a["id"]); a = submit(a["id"])
    r = run_review(a["id"], ReviewIn())
    out = {"ok": True, "stage": stage, "application": r["application"]["ref"], "recommendation": r["review"]["steps"][4]["data"]["verdict"]}
    if stage == "issued":
        d = decide(a["id"], DecisionIn(decision="approve", note="Baseline: eight checks pass, sandbox 5 of 5, condition £5,000.", human_confirm_above=rules.pack()["policy"]["human_confirm_above_gbp"]))
        pid = d["passport"]["passport_id"]
        p = sign_mandate(pid, MandateIn())
        out.update({"passport_id": pid, "status": p["status"], "mandate_signed": p["mandate_signed"], "vouch": {"voucher_id": p.get("vouch_voucher_id"), "mode": p.get("vouch_mode")}})
    out["audit_entries"] = len(db.list_audit())
    return out


def _404():
    raise HTTPException(404, "not found")


def _400(msg: str):
    raise HTTPException(400, msg)
