"""Agent Passport, bank-first. FastAPI routes: server-rendered views + JSON API.

Layers: the provider files an AI product on the register (/provider) → the bank admits it to its list (/bank)
        → the customer signs a mandate inside its bank's app (/customer) → the bank checks every payment (/terminal, /api/verify)
        → the evidence trail (/audit) that a supervisor can request through normal supervisory processes (/api/evidence).
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

from . import audit, companies_house, config, crypto, db, extraction, fixtures, review, rules, vouch

HERE = Path(__file__).parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    crypto.all_signers()
    yield


app = FastAPI(title="Agent Passport", version=config.APP_VERSION, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def ctx(request: Request, **kw) -> dict:
    s = crypto.all_signers()
    return {"request": request, "rule_pack": rules.pack()["id"], "register_name": config.REGISTER_NAME, "register_operator": config.REGISTER_OPERATOR,
            "officer": config.BANK_OFFICER, "bank_team": config.BANK_TEAM, "provider": config.PROVIDER, "customer": config.CUSTOMER, "bank": config.BANK,
            "product_name": config.PRODUCT_NAME, "supervisor": config.SUPERVISOR,
            "kids": {n: v["kid"] for n, v in s.items()}, "version": config.APP_VERSION, "extraction_mode": config.EXTRACTION_MODE,
            "vouch_mode": vouch.mode(), "payment_rail": vouch.rail(), **kw}


# ── Views ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", ctx(request, view="home", pack=rules.pack(), logo_rows=LOGO_ROWS))


LOGO_ROWS = [{"label": "Organisers and regulators", "speed": 55, "logos": [{"img": "/static/logos/badge-cdir.png", "alt": "C:\\>DIR Cambridge Digital Innovation & Regulation Initiative", "h": 60}, {"img": "/static/logos/fii.png", "alt": "Financial Innovation for Impact", "h": 48}, {"img": "/static/logos/nayaone.svg", "alt": "NayaOne", "h": 36}, {"brand": "vouch"}, {"img": "/static/logos/parts/regulatory-00.png", "alt": "BIS Innovation Hub"}, {"img": "/static/logos/parts/regulatory-01.png", "alt": "Global Financial Innovation Network"}, {"img": "/static/logos/parts/regulatory-02.png", "alt": "Digital Regulation Cooperation Forum and Regulator Knowledge Exchange"}, {"img": "/static/logos/parts/regulatory-03.png", "alt": "Women Regulators Network"}, {"img": "/static/logos/parts/supporters-00.png", "alt": "Networks for Humanity"}, {"img": "/static/logos/parts/supporters-01.png", "alt": "Ethereum Foundation"}, {"img": "/static/logos/parts/supporters-02.png", "alt": "Swift"}, {"img": "/static/logos/parts/supporters-03.png", "alt": "Google"}, {"img": "/static/logos/parts/supporters-04.png", "alt": "Moneybox"}, {"img": "/static/logos/parts/supporters-05.png", "alt": "Ant International"}, {"img": "/static/logos/parts/supporters-06.png", "alt": "Euroclear"}]}, {"label": "Ecosystem and academia", "speed": 150, "logos": [{"img": "/static/logos/parts/ecosystem1-00.png", "alt": "GFTN"}, {"img": "/static/logos/parts/ecosystem1-01.png", "alt": "Innovate Finance"}, {"img": "/static/logos/parts/ecosystem1-03.png", "alt": "MENA Fintech Association"}, {"img": "/static/logos/parts/ecosystem1-04.png", "alt": "IDB"}, {"img": "/static/logos/parts/ecosystem1-05.png", "alt": "Africa Fintech Network"}, {"img": "/static/logos/parts/ecosystem1-06.png", "alt": "ABFintechs"}, {"img": "/static/logos/parts/ecosystem1-07.png", "alt": "American Fintech Council"}, {"img": "/static/logos/parts/ecosystem1-08.png", "alt": "TRM"}, {"img": "/static/logos/parts/ecosystem1-10.png", "alt": "Alliance for Innovative Regulation"}, {"img": "/static/logos/parts/ecosystem1-12.png", "alt": "Fintech Alliance PH"}, {"img": "/static/logos/parts/ecosystem1-13.png", "alt": "airdropd"}, {"img": "/static/logos/parts/ecosystem1-14.png", "alt": "DFSAK"}, {"img": "/static/logos/parts/ecosystem2-00.png", "alt": "World Alliance of International Financial Centers"}, {"img": "/static/logos/parts/ecosystem2-01.png", "alt": "AFSI"}, {"img": "/static/logos/parts/ecosystem2-02.png", "alt": "Anacofi"}, {"img": "/static/logos/parts/ecosystem2-03.png", "alt": "CFTE"}, {"img": "/static/logos/parts/ecosystem2-04.png", "alt": "Fintech Association of Hong Kong"}, {"img": "/static/logos/parts/ecosystem2-05.png", "alt": "Fintech Association of Japan"}, {"img": "/static/logos/parts/ecosystem2-06.png", "alt": "FACE"}, {"img": "/static/logos/parts/ecosystem2-07.png", "alt": "Alliance of Digital Finance and Fintech Associations"}, {"img": "/static/logos/parts/ecosystem2-08.png", "alt": "GBBC"}, {"img": "/static/logos/parts/ecosystem2-09.png", "alt": "Insurtech Australia"}, {"img": "/static/logos/parts/ecosystem2-10.png", "alt": "FinTech Wales"}, {"img": "/static/logos/parts/ecosystem2-11.png", "alt": "NCFA"}, {"img": "/static/logos/parts/ecosystem2-12.png", "alt": "partner"}, {"img": "/static/logos/parts/academic1-00.png", "alt": "Cambridge Centre for Alternative Finance"}, {"img": "/static/logos/parts/academic1-01.png", "alt": "E-Lab, King's College Cambridge"}, {"img": "/static/logos/parts/academic1-02.png", "alt": "Entrepreneurship Centre, Cambridge Judge Business School"}, {"img": "/static/logos/parts/academic1-03.png", "alt": "Oxford AI Governance Initiative and Oxford Martin School"}, {"img": "/static/logos/parts/academic1-04.png", "alt": "University of Manchester"}, {"img": "/static/logos/parts/academic2-00.png", "alt": "UNRaf"}, {"img": "/static/logos/parts/academic2-01.png", "alt": "Singapore Management University"}, {"img": "/static/logos/parts/academic2-02.png", "alt": "LITE Lab, University of Hong Kong"}, {"img": "/static/logos/parts/academic2-03.png", "alt": "CSO"}, {"img": "/static/logos/parts/academic2-04.png", "alt": "Technical University of Munich"}, {"img": "/static/logos/parts/technology-00.png", "alt": "NayaOne"}, {"img": "/static/logos/parts/technology-02.png", "alt": "Productopedia"}, {"img": "/static/logos/parts/technology-04.png", "alt": "Autracon"}]}]


for _name in ("provider", "customer", "audit"):
    def _make(name):
        def view(request: Request):
            return templates.TemplateResponse(request, f"{name}.html", ctx(request, view=name))
        view.__name__ = f"view_{name}"
        return view
    app.get(f"/{_name}", response_class=HTMLResponse, include_in_schema=False)(_make(_name))


@app.get("/bank", response_class=HTMLResponse, include_in_schema=False)
def view_bank(request: Request):
    if request.query_params.get("console"):
        return RedirectResponse("/terminal?console=1", status_code=302)
    return templates.TemplateResponse(request, "bank.html", ctx(request, view="bank", pack=rules.pack()))


@app.get("/terminal", response_class=HTMLResponse, include_in_schema=False)
def view_terminal(request: Request):
    view = "console" if request.query_params.get("console") else "terminal"
    return templates.TemplateResponse(request, "terminal.html", ctx(request, view=view))


@app.get("/regulator", include_in_schema=False)
def view_regulator_redirect(request: Request):
    return RedirectResponse("/bank" + ("?" + str(request.query_params) if request.query_params else ""), status_code=302)


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
    what = {"register": "registration receipt (the AI product is on the register; someone is accountable)",
            "bank": "admission (the product is on this bank's list, with ceilings and a hold condition) and every verification receipt",
            "northgate": "agent_identity and mandate (the customer's deployment and the authority it granted)"}
    return {n: {"kid": s["kid"], "jwk": s["jwk"], "alg": "EdDSA", "signs": what[n]} for n, s in crypto.all_signers().items()}


@app.get("/api/vouch")
def vouch_info():
    return {"mode": vouch.mode(), "payment_rail": vouch.rail(), "base_url": config.VOUCH_BASE_URL if vouch.mode() == "live" else None, **vouch.org_self()}


@app.get("/api/state")
def state():
    """Everything the views need in one call."""
    regs = db.list_registrations()
    pps = db.list_passports()
    pol = rules.pack()["policy"]
    pat = pol.get("pattern_threshold", {"count": 2, "window_hours": 24})
    return {"registrations": [public_reg(a) for a in regs], "passports": [public_passport(p) for p in pps], "beats": fixtures.BEATS,
            "invoices": [{"id": k, "label": "Genuine invoice" if k.endswith("clean") else "Altered invoice · payment destination changed", "text": t} for k, t in extraction.invoices().items()],
            "register": fixtures.register_entries(),
            "products": [product_summary(a) for a in regs if a.get("admission_status") in ("admitted", "suspended", "revoked")],
            "incidents": db.list_audit(50, kind="incident"), "violations": db.list_violations(), "alerts": db.pattern_alerts(pat["count"], pat["window_hours"]), "pattern_threshold": pat,
            "payments": db.list_payments(limit=100),
            "vouch_mode": vouch.mode(), "payment_rail": vouch.rail(),
            "mandate_draft": mandate_draft(), "agent_draft": agent_draft(), "policy": {k: pol[k] for k in ("per_payment_ceiling_gbp", "monthly_per_account_ceiling_gbp", "max_validity", "action_types", "currency", "hold_above_gbp", "min_insurance_cover_gbp", "velocity_ceiling_per_day", "assurance_levels", "min_assurance_level_for_admission", "account_tiers", "customer_classes")},
            "failure_classes": rules.pack().get("failure_classes", {}), "planned_fields": rules.pack().get("planned_fields", []), "companies_house_mode": companies_house.mode(),
            "cast": {"bank": config.BANK, "officer": config.BANK_OFFICER, "team": config.BANK_TEAM, "customer": config.CUSTOMER, "provider": config.PROVIDER, "register": config.REGISTER_NAME, "supervisor": config.SUPERVISOR},
            "delegation_chain": config.DELEGATION_CHAIN == "on", "delegation_max_gbp": config.DELEGATION_MAX_GBP, "chain_beats": fixtures.CHAIN_BEATS, "chain_rules": rules.pack().get("chain_rules", [])}


def product_summary(a: dict) -> dict:
    f = a.get("fields") or {}
    return {"registration_id": a["id"], "ref": a["ref"], "product_name": rules._v(f, "product", "product_name"), "product_id": rules._v(f, "product", "product_id"),
            "provider": rules._v(f, "company", "legal_name"), "model_version": rules._v(f, "product", "model_version"), "admission_status": a.get("admission_status"),
            "assurance_level": rules._v(f, "assurance_evidence", "level"), "ceilings": rules.admission_ceilings(rules._v(f, "assurance_evidence", "level")),
            "admitted_at": a.get("admitted_at"), "condition": a.get("condition"), "passports": [p["passport_id"] for p in db.passports_for_registration(a["id"])]}


def agent_draft() -> dict:
    import json as _json
    d = _json.loads((config.FIXTURES_DIR / "customer" / "agent_draft.json").read_text())
    d.pop("_comment", None)
    return d


def mandate_draft() -> dict:
    """The customer's own draft mandate (prefill). Never part of the provider's registration."""
    import json as _json
    d = _json.loads((config.FIXTURES_DIR / "customer" / "mandate_draft.json").read_text())
    d.pop("_comment", None)
    return d


def public_reg(a: dict) -> dict:
    return dict(a)


def public_passport(p: dict) -> dict:
    p = dict(p)
    if p.get("agent"):
        ag = {k: v for k, v in p["agent"].items() if k != "private_pem"}
        if ag.get("execution"):
            ag["execution"] = {k: v for k, v in ag["execution"].items() if k != "private_pem"}
        p["agent"] = ag
    p["envelope"] = envelope_of(p)
    p["mandate_signed"] = bool(p.get("mandate_jwt"))
    p["payments"] = db.count_payments(p["passport_id"])
    p["ledger"] = db.ledger_totals(p["passport_id"])
    return p


def envelope_of(p: dict) -> dict:
    """The composite passport as presented to a relying party."""
    return {
        "passport_id": p["passport_id"],
        "admission": p["admission_jwt"] or None,
        "agent_identity": p["agent_identity_jwt"],
        "mandate": p.get("mandate_jwt"),
        "status_url": f"/api/status/{p['passport_id']}",
        "vouch_voucher_id": p.get("vouch_voucher_id"),
        "cnf": None,  # key binding lives inside agent_identity.cnf, signed by the customer
    }


# ── API: the public register of companies (Companies House, or the labelled demo register) ──
@app.get("/api/companies/search")
def companies_search(q: str):
    return {"mode": companies_house.mode(), "items": companies_house.search(q)}


@app.get("/api/companies/{number}")
def companies_lookup(number: str):
    return {"mode": companies_house.mode(), **companies_house.lookup(number)}


# ── API: the register (Layer 1, the provider files an AI product) ──────────
@app.post("/api/registrations")
def create_registration():
    """An empty registration form. The provider fills it in; nothing is reviewed."""
    n = db.count_registrations() + 14
    ref = f"REG-2026-{n:04d}"
    a = db.create_registration(ref)
    a = db.update_registration(a["id"], fields=extraction.blank_fields(), entry_mode="form")
    audit.record("registration", ref, {"event": "AI product registration started on the register", "provider": config.PROVIDER})
    return public_reg(a)


@app.post("/api/registrations/{reg_id}/prefill")
def prefill(reg_id: int):
    """Demo convenience: fill the registration form with the synthetic OpenPay values. A person would type them."""
    a = db.get_registration(reg_id) or _404()
    if a["status"] != "draft":
        raise HTTPException(409, "registration already filed")
    a = db.update_registration(reg_id, fields=extraction.fixture(), entry_mode="prefill")
    audit.record("registration", a["ref"], {"event": "registration form prefilled for the demo", "mode": "prefill"})
    return public_reg(a)


class FieldsIn(BaseModel):
    fields: dict


@app.put("/api/registrations/{reg_id}/fields")
def put_fields(reg_id: int, body: FieldsIn):
    a = db.get_registration(reg_id) or _404()
    if a["status"] != "draft" and a.get("admission_status") != "info_requested":
        raise HTTPException(409, "registration is no longer editable")
    a = db.update_registration(reg_id, fields=body.fields)
    return public_reg(a)


@app.post("/api/registrations/{reg_id}/submit")
def submit(reg_id: int):
    """The provider files its registration. Filing is a declaration by the accountable principal that the filing is
    accurate. The register runs completeness checks F.1 to F.6, records the result and signs a receipt. Nobody reviews it."""
    a = db.get_registration(reg_id) or _404()
    if not a.get("fields"):
        _400("fill in the registration first")
    checks = rules.run_registration_checks(a["fields"])
    f = a["fields"]
    receipt = crypto.sign_jwt("register", {
        "iss": config.REGISTER_ID, "typ": "registration_receipt", "jti": a["ref"], "iat": crypto.now_ts(),
        "provider": {"legal_name": rules._v(f, "company", "legal_name"), "companies_house_number": rules._v(f, "company", "companies_house_number")},
        "accountable_principal": {"name": rules._v(f, "principal", "name"), "role": rules._v(f, "principal", "role"), "declaration_ref": rules._v(f, "principal", "declaration_ref")},
        "product": {"product_name": rules._v(f, "product", "product_name"), "product_id": rules._v(f, "product", "product_id"), "release": rules._v(f, "product", "release"),
                    "model_provider": rules._v(f, "product", "model_provider"), "model_version": rules._v(f, "product", "model_version")},
        "assurance_evidence": {"level": rules._v(f, "assurance_evidence", "level"), "issuer": rules._v(f, "assurance_evidence", "issuer"), "reference": rules._v(f, "assurance_evidence", "reference"), "date": rules._v(f, "assurance_evidence", "date"), "use_case": rules._v(f, "assurance_evidence", "use_case")},
        "filing_sha256": crypto.sha256_hex(crypto.canonical(f)), "checks": {c["id"]: c["result"] for c in checks},
        "meaning": "on the register: identity and accountability recorded; no quality judgement made",
    }, typ="registration-receipt+jwt")
    a = db.update_registration(reg_id, status="registered", submitted_at=db.now_iso(), checks=checks, registration_jwt=receipt)
    audit.record("check", a["ref"], {"event": "AI product filed on the register; accountable principal declared the filing accurate; filing checks F.1 to F.6 run; receipt signed by the register",
                                     "passed": sum(c["result"] == "pass" for c in checks), "flagged": [c["id"] for c in checks if c["result"] != "pass"], "register_kid": crypto.signer("register")["kid"]})
    return public_reg(a)


# ── API: the bank admits a product to its list (Layer 2) ───────────────────
class ReviewIn(BaseModel):
    hold_above: float | None = None


@app.post("/api/registrations/{reg_id}/review")
def run_review(reg_id: int, body: ReviewIn | None = None):
    """The bank's admission review assistant: six steps. Deterministic; the sandbox uses the bank's own engine.
    Stored on the registration. Never changes its status."""
    a = db.get_registration(reg_id) or _404()
    if a["status"] != "registered":
        _400("file the registration first")
    try:
        r = review.run(a, body.hold_above if body else None)
    except ValueError as exc:
        _400(str(exc))
    a = db.update_registration(reg_id, review=r)
    sb = r["steps"][3]["data"]
    audit.record("review", a["ref"], {"event": "admission review assistant run by the bank", "rule_pack": r["rule_pack"], "sandbox_passed": sum(1 for t in sb if t["pass"]), "sandbox_total": len(sb),
                                      "recommendation": r["steps"][4]["data"]["verdict"], "decides": False})
    return {"registration": public_reg(a), "review": r}


class AdmissionIn(BaseModel):
    decision: str  # admit | request_info | decline
    note: str
    hold_above: float | None = None


@app.post("/api/registrations/{reg_id}/admission")
def admission_decision(reg_id: int, body: AdmissionIn):
    """The bank's decision: whether its customers may delegate payments to this registered product. A commercial risk
    decision by a named officer, recorded with a note. Admission sets the ceilings every mandate must sit within and a hold condition."""
    a = db.get_registration(reg_id) or _404()
    if a["status"] != "registered":
        raise HTTPException(409, "the product is not on the register")
    if a.get("admission_status") not in (None, "info_requested", "declined"):
        raise HTTPException(409, f"admission is already {a['admission_status']}")
    if not body.note.strip():
        _400("an officer note is required")
    who = f"{config.BANK_OFFICER}, {config.BANK_TEAM}"
    if body.decision == "admit":
        level = rules._v(a["fields"], "assurance_evidence", "level")
        pol = rules.pack()["policy"]
        if not rules.level_meets(level, pol["min_assurance_level_for_admission"]):
            _400(f"this bank admits products at {rules.assurance_level(pol['min_assurance_level_for_admission'])['label'].lower()} or above; this filing is {rules.assurance_level(level)['label'].lower()}")
        thr = float(body.hold_above if body.hold_above is not None else pol["hold_above_gbp"])
        condition = {"hold_above": {"amount": thr, "currency": "GBP"}}
        ceilings = rules.admission_ceilings(level)
        a = db.update_registration(reg_id, admission_status="admitted", admitted_at=db.now_iso(), officer=who, officer_note=body.note, condition=condition)
        audit.record("admission", a["ref"], {"event": "AI product admitted to the bank's list; ceilings and hold condition set", "officer": who, "note": body.note, "condition": condition,
                                             "product_id": rules._v(a["fields"], "product", "product_id"), "assurance_level": level, "ceilings": {"per_payment": ceilings["per_payment_ceiling"]["amount"], "monthly_per_account": ceilings["monthly_per_account_ceiling"]["amount"], "max_validity": pol["max_validity"], "ceiling_factor": ceilings["ceiling_factor"]}})
        return {"registration": public_reg(a), "product": product_summary(a)}
    if body.decision == "request_info":
        a = db.update_registration(reg_id, admission_status="info_requested", officer=who, officer_note=body.note)
        audit.record("admission", a["ref"], {"event": "bank requested further information from the provider", "officer": who, "note": body.note})
        return {"registration": public_reg(a)}
    if body.decision == "decline":
        a = db.update_registration(reg_id, admission_status="declined", admitted_at=db.now_iso(), officer=who, officer_note=body.note)
        audit.record("admission", a["ref"], {"event": "bank declined to admit the product; it stays on the register", "officer": who, "note": body.note})
        return {"registration": public_reg(a)}
    _400("unknown decision")


class ProductStatusIn(BaseModel):
    status: str   # suspended | active | revoked
    reason: str


@app.post("/api/registrations/{reg_id}/admission/status")
def product_lifecycle(reg_id: int, body: ProductStatusIn):
    """Product-level control at the bank. Cascades to every passport on the product: suspend freezes them, reinstate releases
    the ones the cascade froze, revoke closes them all and revokes their vouch vouchers."""
    a = db.get_registration(reg_id) or _404()
    if a.get("admission_status") not in ("admitted", "suspended", "revoked"):
        _400("product is not admitted")
    if body.status not in ("suspended", "active", "revoked"):
        _400("status must be suspended, active or revoked")
    if not body.reason.strip():
        _400("an officer reason is required")
    if a.get("admission_status") == "revoked":
        _400("a revoked admission cannot change; a fresh admission decision is needed")
    who = f"{config.BANK_OFFICER}, {config.BANK_TEAM}"
    a = db.update_registration(reg_id, admission_status="admitted" if body.status == "active" else body.status)
    touched = []
    for p in db.passports_for_registration(reg_id):
        if p["status"] == "revoked":
            continue
        if body.status == "active" and p["status"] != "suspended":
            continue
        p = db.set_passport_status(p["passport_id"], body.status, who, f"product {body.status}: {body.reason}")
        if body.status in ("revoked", "active"):
            db.set_violation_status(p["passport_id"], "RESOLVED", "revoked" if body.status == "revoked" else "reinstated")
            db.set_investigation(p["passport_id"], None)
        if body.status == "revoked":
            r = vouch.revoke_mandate(p.get("vouch_voucher_id"))
            db.set_vouch(p["passport_id"], p.get("vouch_voucher_id"), r["mode"], r["status"])
        touched.append(p["passport_id"])
    audit.record("lifecycle", a["ref"], {"event": f"product admission {body.status}; cascaded to {len(touched)} passports", "officer": who, "reason": body.reason, "product_id": rules._v(a["fields"], "product", "product_id"), "passports": touched})
    return {"product": product_summary(a), "passports": touched}


def mirror_on_vouch(p: dict) -> dict:
    r = vouch.mint_mandate(p)
    p = db.set_vouch(p["passport_id"], r["voucher_id"], r["mode"], r["status"])
    audit.record("vouch", p["passport_id"], {"event": "mandate mirrored on the vouch rail", "mode": r["mode"], "voucher_id": r["voucher_id"], "detail": r["detail"]})
    return p


@app.post("/api/registrations/{reg_id}/file-note")
def file_note(reg_id: int):
    a = db.get_registration(reg_id) or _404()
    if not a.get("checks"):
        _400("no checks yet")
    note, mode = extraction.draft_file_note(a["ref"], a["fields"], a["checks"])
    a = db.update_registration(reg_id, file_note=note)
    audit.record("draft", a["ref"], {"event": "file note drafted for the bank's officer (edge use of the model; not a decision)", "mode": mode})
    return {"note": note, "mode": mode}


# ── API: the customer (Layer 3) ────────────────────────────────────────────
def create_agent_on_product(a: dict, deployment: dict) -> dict:
    """The customer registers its AI agent on an admitted product, inside its bank's app. Deployment-specific material lives here:
    the agent key pair (demo: kept with the passport), proof of possession by signed challenge, configuration hash, key custody.
    The customer signs agent_identity; the bank's system issues the admission JWT when the mandate is signed."""
    if a.get("admission_status") != "admitted":
        _400("product is not on the bank's list")
    f = a["fields"]
    pol = rules.pack()["policy"]
    level = rules._v(f, "assurance_evidence", "level")
    ceilings = rules.admission_ceilings(level)
    n = db.count_passports() + 107
    pid = f"AG-2026-{n:04d}"   # the agent record; it becomes passport AP-2026-{n} when the customer signs its mandate
    priv, pub = crypto.generate_keypair()
    jwk = crypto.public_jwk(pub)
    agent_id = f"northgate-{rules._v(f, 'product', 'product_id')}-{n - 106:02d}"
    challenge = crypto.new_nonce()
    sig = crypto.sign_bytes(priv, challenge.encode())
    pop = crypto.verify_bytes(pub, challenge.encode(), sig)
    ag = {"agent_id": agent_id, "public_pem": pub, "private_pem": priv, "jwk": jwk, "kid": crypto.jwk_thumbprint(jwk)[:16], "challenge": challenge, "challenge_sig": sig, "pop_verified": pop,
          "config_sha256": rules.agent_config_hash(), "key_storage": deployment.get("key_storage"), "key_rotation": deployment.get("key_rotation")}
    ident_payload = {"iss": config.CUSTOMER_ID, "typ": "agent_identity", "sub": agent_id, "iat": crypto.now_ts(), "agent_record": pid,
                     "agent": {"name": deployment.get("agent_name") or f"{rules._v(f, 'product', 'product_name')} · customer deployment", "agent_id": agent_id,
                               "product_id": rules._v(f, "product", "product_id"), "product_name": rules._v(f, "product", "product_name"), "provider": rules._v(f, "company", "legal_name"),
                               "model_provider": rules._v(f, "product", "model_provider"), "model_version": rules._v(f, "product", "model_version"), "registration": a["ref"], "config_sha256": ag["config_sha256"]},
                     "deployment": {"key_storage": ag["key_storage"], "key_rotation": ag["key_rotation"], "proof_of_possession": pop},
                     "cnf": {"jwk": jwk}}
    ident_jwt = crypto.sign_jwt("northgate", ident_payload, typ="agent-identity+jwt")
    valid_until = pol["max_validity"]
    exp = int(datetime.fromisoformat(valid_until + "T23:59:59+00:00").timestamp())
    checks = a.get("checks") or []
    admission = {
        "iss": config.BANK_ID, "typ": "admission", "jti": pid.replace("AG-", "AP-"), "iat": crypto.now_ts(), "nbf": crypto.now_ts(), "exp": exp, "valid_until": valid_until, "rule_pack_version": rules.pack()["id"],
        "product_ref": {"registration": a["ref"], "product_id": rules._v(f, "product", "product_id"), "product_name": rules._v(f, "product", "product_name"), "model_version": rules._v(f, "product", "model_version"),
                        "provider": rules._v(f, "company", "legal_name"), "admitted_by": a.get("officer") or config.BANK_OFFICER, "admitted_at": a.get("admitted_at"),
                        "registration_receipt_sha256": crypto.sha256_hex(a.get("registration_jwt") or "")},
        "agent_id": agent_id,
        "admission": {"status": "ADMITTED", "filing_checks_passed": sum(c["result"] == "pass" for c in checks), "filing_checks_flagged": [c["id"] for c in checks if c["result"] != "pass"],
                      "issued": "by the bank's system from its admission decision when the customer signed its mandate; no per-customer review"},
        "condition": a.get("condition") or {"hold_above": {"amount": float(pol["hold_above_gbp"]), "currency": "GBP"}},
        "ceilings": ceilings,
        "accountable_principal": {"name": rules._v(f, "principal", "name"), "role": rules._v(f, "principal", "role"), "declaration_ref": rules._v(f, "principal", "declaration_ref"), "covers": "accuracy of the filing"},
        "assurance_evidence": {"level": level, "issuer": rules._v(f, "assurance_evidence", "issuer"), "reference": rules._v(f, "assurance_evidence", "reference"), "date": rules._v(f, "assurance_evidence", "date")},
        "binds": {"agent_identity_sha256": crypto.sha256_hex(ident_jwt), "agent_kid": ag["kid"]},
        "status": {"list": f"/api/status/{pid.replace('AG-', 'AP-')}"}, "issued_by": "the bank's system, from its admission decision",
    }
    mandate_proposed = {
        "typ": "mandate", "passport_id": pid.replace("AG-", "AP-"), "valid_until": valid_until, "exp": exp, "customer": None, "authorising_officer": None,
        "provider": rules._v(f, "company", "legal_name"), "agent_id": agent_id, "agent_kid": ag["kid"], "written_by": "customer",
        "authorization_details": [{"type": "payment_initiation", "actions": list(pol["action_types"]), "currency": pol["currency"], "supplier_allowlist": [],
                                   "per_payment_limit": {"amount": ceilings["per_payment_ceiling"]["amount"], "currency": pol["currency"]},
                                   "monthly_limit_per_account": {"amount": ceilings["monthly_per_account_ceiling"]["amount"], "currency": pol["currency"], "window": pol["monthly_window"]},
                                   "max_payments_per_day": ceilings["velocity_ceiling_per_day"]}],
        "ceilings": ceilings,
    }
    p = db.create_passport(pid, a["id"], "", admission, ident_jwt, ident_payload, mandate_proposed, valid_until, config.CUSTOMER, agent=ag, status="pending")
    audit.record("agent", pid, {"event": "customer registered its AI agent on an admitted product: key generated, possession proven, agent_identity signed by the customer; no passport until the customer signs its mandate",
                                "registration": a["ref"], "agent_id": agent_id, "agent_kid": ag["kid"], "pop_verified": pop, "config_sha256": ag["config_sha256"]})
    return p


class AgentIn(BaseModel):
    registration_id: int
    agent_name: str | None = None
    key_storage: str | None = None
    key_rotation: str | None = None


@app.post("/api/agents")
def create_agent(body: AgentIn):
    a = db.get_registration(body.registration_id) or _404()
    d = {**agent_draft(), **{k: v for k, v in body.model_dump().items() if v is not None and k != "registration_id"}}
    p = create_agent_on_product(a, d)
    return public_passport(p)


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
        _400("a revoked passport cannot change status; a fresh mandate is needed")
    who = f"{config.BANK_OFFICER}, {config.BANK_TEAM}"
    p = db.set_passport_status(passport_id, body.status, who, body.reason)
    audit.record("lifecycle", passport_id, {"event": f"status changed to {body.status}", "officer": who, "reason": body.reason})
    if body.status in ("revoked", "active"):
        n = db.set_violation_status(passport_id, "RESOLVED", "revoked" if body.status == "revoked" else "reinstated")
        if p.get("investigation") or n:
            p = db.set_investigation(passport_id, None)
            audit.record("exception", passport_id, {"event": "investigation closed", "outcome": "revoked" if body.status == "revoked" else "reinstated", "violations_resolved": n, "officer": who, "reason": body.reason})
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
    """INVESTIGATING is a state the bank's risk team puts around the lifecycle, not a rule. It blocks nothing by itself:
    the verifier still reads active / suspended / revoked. Opening it marks the passport's OPEN violations INVESTIGATING."""
    p = db.get_passport(passport_id) or _404()
    who = f"{config.BANK_OFFICER}, {config.BANK_TEAM}"
    if body.action == "open":
        if p["status"] == "revoked":
            _400("a revoked passport is closed; nothing to investigate")
        p = db.set_investigation(passport_id, "investigating")
        n = db.set_violation_status(passport_id, "INVESTIGATING", None, only_status=("OPEN",))
        audit.record("exception", passport_id, {"event": "investigation opened", "officer": who, "note": body.note, "violations": n, "passport_status": p["status"]})
    elif body.action == "close":
        p = db.set_investigation(passport_id, None)
        audit.record("exception", passport_id, {"event": "investigation closed without change", "officer": who, "note": body.note})
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


class MandateIn(BaseModel):
    """The customer's own mandate. Omitted fields fall back to the customer's draft."""
    customer: dict | None = None
    authorising_officer: dict | None = None
    supplier_allowlist: list[dict] | None = None
    per_payment_limit: float | None = None
    monthly_limit_per_account: float | None = None
    max_payments_per_day: int | None = None
    currency: str | None = None
    valid_until: str | None = None
    actions: list[str] | None = None


@app.post("/api/passports/{passport_id}/mandate/check")
def check_mandate(passport_id: str, body: MandateIn | None = None):
    """Ceiling containment preview: the same check that runs at signing, without signing."""
    p = db.get_passport(passport_id) or _404()
    m = _merge_mandate(body)
    ceilings = p["admission"].get("ceilings") or rules.admission_ceilings()
    problems = rules.check_mandate_containment(m, p["admission"]["valid_until"], ceilings)
    return {"within_ceilings": not problems, "problems": problems, "ceilings": ceilings, "limits": rules.effective_limits(ceilings, (m.get("customer") or {}).get("account_type")), "mandate": m}


def _merge_mandate(body: MandateIn | None) -> dict:
    d = mandate_draft()
    if body:
        for k in ("customer", "authorising_officer", "supplier_allowlist", "per_payment_limit", "monthly_limit_per_account", "max_payments_per_day", "currency", "valid_until", "actions"):
            v = getattr(body, k)
            if v is not None:
                d[k] = v
    d["supplier_allowlist"] = [{"supplier_id": (x.get("supplier_id") or f"SUP-{i + 1:03d}"), "name": (x.get("name") or "").strip(), "account_ref": (x.get("account_ref") or "").strip(),
                               "companies_house_number": companies_house.normalise_number(x.get("companies_house_number")) or None} for i, x in enumerate(d.get("supplier_allowlist") or [])]
    return d


def verify_payees(suppliers: list[dict]) -> list[dict]:
    """Each payee with a company number is checked against the public register at signing; the result travels in the mandate.
    Companies House reports what companies filed. It holds no bank accounts, so the account still comes from the customer."""
    out = []
    for sp in suppliers:
        sp = dict(sp)
        if sp.get("companies_house_number"):
            rec = companies_house.lookup(sp["companies_house_number"])
            sp["register_check"] = {"checked": "Companies House public register", "source": rec.get("source"), "checked_at": rec.get("checked_at"), "legal_name": rec.get("legal_name"),
                                    "status": rec.get("status"), "registered_office": rec.get("address"), "found": bool(rec.get("found")),
                                    "result": ("active company; filed name matches" if rec.get("active") and companies_house.names_match(rec.get("legal_name"), sp.get("name")) else ("active company; filed name differs from the payee name given" if rec.get("active") else f"company is {rec.get('status')}")) if rec.get("found") else "no company with this number on the register",
                                    "account_check": "Confirmation of Payee (account name to account number) planned, bank-side; the register holds no bank account data"}
        out.append(sp)
    return out


@app.post("/api/passports/{passport_id}/mandate/sign")
def sign_mandate(passport_id: str, body: MandateIn | None = None):
    """The customer writes and signs its own mandate with the customer key, inside its bank's app. Live at once.
    The only gate is ceiling containment against the ceilings the bank set at admission."""
    p = db.get_passport(passport_id) or _404()
    if p.get("mandate_jwt"):
        _400("mandate already signed")
    if p["status"] == "revoked":
        _400("passport revoked; nothing to sign")
    if (db.get_registration(p["registration_id"]) or {}).get("admission_status") != "admitted":
        _400("the product is suspended or no longer on the bank's list; no passport can be issued on it")
    m = _merge_mandate(body)
    ceilings = p["admission"].get("ceilings") or rules.admission_ceilings()
    problems = rules.check_mandate_containment(m, p["admission"]["valid_until"], ceilings)
    if problems:
        raise HTTPException(422, {"message": "mandate outside the agent-channel limits for this account", "problems": problems})
    pol = rules.pack()["policy"]
    mp = p["mandate_proposed"]
    new_id = passport_id.replace("AG-", "AP-")
    suppliers = verify_payees(m["supplier_allowlist"])
    limits = rules.effective_limits(ceilings, (m.get("customer") or {}).get("account_type"))
    payload = {
        "iss": config.CUSTOMER_ID, "typ": "mandate", "passport_id": new_id, "iat": crypto.now_ts(), "valid_until": m["valid_until"],
        "exp": int(datetime.fromisoformat(m["valid_until"] + "T23:59:59+00:00").timestamp()),
        "customer": m["customer"], "authorising_officer": m["authorising_officer"], "signed_by": m["authorising_officer"],
        "account": {"type": (m.get("customer") or {}).get("account_type"), "tier": limits["account_tier"]["label"], "customer_class": (m.get("customer") or {}).get("customer_class"), "agent_channel_limits": {k: limits[k] for k in ("per_payment", "monthly_per_account", "max_payments_per_day")}},
        "provider": mp["provider"], "agent_id": mp["agent_id"], "agent_kid": mp["agent_kid"], "written_by": "customer",
        "authorization_details": [{"type": "payment_initiation", "actions": list(m["actions"]), "currency": m.get("currency") or pol["currency"], "supplier_allowlist": suppliers,
                                   "per_payment_limit": {"amount": float(m["per_payment_limit"]), "currency": pol["currency"]},
                                   "monthly_limit_per_account": {"amount": float(m["monthly_limit_per_account"]), "currency": pol["currency"], "window": pol["monthly_window"]},
                                   "max_payments_per_day": int(m.get("max_payments_per_day") or limits["max_payments_per_day"])}],
        "within_ceilings": True,
    }
    token = crypto.sign_jwt("northgate", payload, typ="mandate+jwt")
    p = db.set_mandate(passport_id, token, payload)
    p = db.set_mandate_proposed(passport_id, {**mp, **{k: payload[k] for k in ("customer", "authorising_officer", "valid_until", "authorization_details")}})
    audit.record("mandate", passport_id, {"event": "customer wrote and signed its mandate inside its bank's app; ceiling containment passed", "signer": payload["signed_by"], "customer_kid": crypto.signer("northgate")["kid"],
                                          "suppliers": len(suppliers), "payees_checked": [{"name": x["name"], "companies_house_number": x.get("companies_house_number"), "result": (x.get("register_check") or {}).get("result"), "source": (x.get("register_check") or {}).get("source")} for x in suppliers],
                                          "per_payment_limit": float(m["per_payment_limit"]), "monthly_limit_per_account": float(m["monthly_limit_per_account"]), "max_payments_per_day": payload["authorization_details"][0]["max_payments_per_day"], "currency": payload["authorization_details"][0]["currency"], "account_type": payload["account"]["type"], "valid_until": m["valid_until"]})
    # the customer's signature gives the AI agent authority: the bank's system now issues the passport from its admission decision
    if not p.get("admission_jwt"):
        admission = {**p["admission"], "jti": new_id, "iat": crypto.now_ts(), "nbf": crypto.now_ts()}
        atoken = crypto.sign_jwt("bank", admission, typ="admission+jwt")
        p = db.set_passport_admission(passport_id, atoken, admission)
        if new_id != passport_id:
            db.rename_passport(passport_id, new_id)
        p = db.set_passport_status(new_id, "active", f"{config.BANK} system", f"Issued as {new_id}: the customer signed the mandate; admission signed from the bank's decision")
        audit.record("issue", new_id, {"event": "passport issued: admission signed by the bank's system from its admission decision; passport list ACTIVE; envelope complete; live at once",
                                       "agent_record": passport_id, "bank_kid": crypto.signer("bank")["kid"], "agent_kid": p["agent"]["kid"], "registration": p["admission"]["product_ref"]["registration"]})
        p = mirror_on_vouch(p)
    return public_passport(p)


# ── API: the bank checks (Layer 4) ─────────────────────────────────────────
@app.get("/api/status/{passport_id}")
def status(passport_id: str):
    p = db.get_passport(passport_id) or _404()
    return {"passport_id": passport_id, "status": p["status"], "mandate_signed": bool(p.get("mandate_jwt")), "expires_at": p["expires_at"], "checked_at": db.now_iso()}


@app.get("/api/passports/{passport_id}")
def get_passport(passport_id: str):
    p = db.get_passport(passport_id) or _404()
    env = envelope_of(p)
    ver = crypto.verify_envelope(env)
    parts = {"admission": (crypto.verify_jwt("bank", env["admission"]) is not None) if env.get("admission") else None,
             "agent_identity": crypto.verify_jwt("northgate", env["agent_identity"]) is not None,
             "mandate": (crypto.verify_jwt("northgate", env["mandate"]) is not None) if env.get("mandate") else None}
    headers = {k: crypto.decode_unverified(env[k])[0] for k in ("admission", "agent_identity", "mandate") if env.get(k)}
    reg = db.get_registration(p["registration_id"]) or {}
    return {**public_passport(p), "verification": {"ok": ver["ok"], "failure": ver["failure"], "parts": parts}, "headers": headers, "minimal": minimal_passport(p),
            "registration_receipt": reg.get("registration_jwt"), "registration_receipt_verified": crypto.verify_jwt("register", reg.get("registration_jwt")) is not None if reg.get("registration_jwt") else None}


def minimal_passport(p: dict) -> dict:
    """What the verifier sees: permission and keys, not personal data."""
    a, i, m = p["admission"], p["agent_identity"], p.get("mandate")
    ad = (m or p["mandate_proposed"])["authorization_details"][0]
    return {
        "passport_id": p["passport_id"], "issuer": a["iss"], "provider": a["product_ref"]["provider"], "product": f"{a['product_ref']['product_name']} · {a['product_ref']['model_version']}", "product_ref": a["product_ref"], "ceilings": a.get("ceilings"),
        "agent": i["agent"]["name"], "agent_id": i["agent"]["agent_id"], "agent_kid": crypto.jwk_thumbprint(i["cnf"]["jwk"])[:16],
        "condition": a["condition"], "valid_until": a["valid_until"], "status": p["status"], "mandate_signed": bool(m),
        "scope": {"actions": ad["actions"], "currency": ad["currency"], "suppliers": len(ad["supplier_allowlist"]), "per_payment_limit": ad["per_payment_limit"], "monthly_limit_per_account": ad["monthly_limit_per_account"], "max_payments_per_day": ad.get("max_payments_per_day")},
        "assurance_level": (a.get("assurance_evidence") or {}).get("level"),
        "signers": {"admission": crypto.signer("bank")["kid"], "agent_identity": crypto.signer("northgate")["kid"], "mandate": crypto.signer("northgate")["kid"]},
    }


# ── Delegation chain: orchestrator → execution agent ───────────────────────
def execution_key(p: dict) -> dict:
    """The execution agent's own key pair, generated once per passport and kept with the agent record (demo)."""
    ag = p["agent"]
    if not ag.get("execution"):
        priv, pub = crypto.generate_keypair()
        jwk = crypto.public_jwk(pub)
        ag["execution"] = {"agent_id": f"{ag['agent_id']}-exec", "private_pem": priv, "public_pem": pub, "jwk": jwk, "kid": crypto.jwk_thumbprint(jwk)[:16]}
        db.set_passport_agent(p["passport_id"], ag)
    return ag["execution"]


def make_delegation(p: dict, passport_id: str, beneficiary: str, max_amount: float, valid_until: str) -> str:
    """The orchestrator (the key bound in agent_identity) delegates a narrowed scope to the execution agent."""
    ex = execution_key(p)
    payload = {"iss": p["agent"]["agent_id"], "typ": "delegation", "sub": ex["agent_id"], "passport_id": passport_id, "iat": crypto.now_ts(), "cnf": {"jwk": ex["jwk"]},
               "scope": {"beneficiaries": [beneficiary], "max_amount": float(max_amount), "currency": "GBP", "actions": ["pay_invoice"], "valid_until": valid_until, "purpose": "pay one supplier invoice"}}
    return crypto.sign_jwt_pem(p["agent"]["private_pem"], payload, typ="delegation+jwt")


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
    """Simulated AI agent: builds a payment instruction, signs it, presents it to the bank."""
    p = db.get_passport(body.passport_id) or _404()
    req = {"passport_id": body.passport_id, "action_type": body.action_type, "payee_account_ref": body.payee_account_ref, "supplier_name": body.supplier_name,
           "amount": body.amount, "currency": body.currency, "invoice_ref": body.invoice_ref, "nonce": crypto.new_nonce()}
    if chain_on(body.chain):
        req["delegation"] = make_delegation(p, body.passport_id, body.delegate_account or body.payee_account_ref, body.delegate_amount or config.DELEGATION_MAX_GBP, p["expires_at"])
        key = execution_key(p)["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    else:
        key = p["agent"]["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
    out = verify(VerifyIn(passport_id=body.passport_id, instruction=req))
    if out["decision"] in ("ALLOW", "ESCALATE"):
        _last_instruction[body.passport_id] = dict(req)   # the last instruction the bank executed or held: the one worth replaying
    return out


_last_instruction: dict[str, dict] = {}


class ReplayIn(BaseModel):
    passport_id: str


@app.post("/api/agent/replay")
def agent_replay(body: ReplayIn):
    """Something re-presents the last executed instruction, byte for byte. The signature is genuine; the nonce is spent."""
    req = _last_instruction.get(body.passport_id)
    if not req:
        _400("no executed instruction to replay yet: pay something first")
    return verify(VerifyIn(passport_id=body.passport_id, instruction=dict(req)))


class InvoiceIn(BaseModel):
    passport_id: str
    invoice_id: str          # INV-9001-clean | INV-9001-poisoned
    signer: str = "agent"
    chain: bool | None = None


@app.post("/api/agent/invoice")
def agent_invoice(body: InvoiceIn):
    """The AI agent reads an invoice with the model (verbatim-quote extraction), turns what it read into a
    signed payment instruction, and presents it to the bank. Returns every step so the UI can show the manipulation
    moment: extracted text → generated instruction → bank decision. The model reads; it never decides."""
    p = db.get_passport(body.passport_id) or _404()
    texts = extraction.invoices()
    if body.invoice_id not in texts:
        _400("unknown invoice")
    mandate = p.get("mandate") or p["mandate_proposed"]
    allow = mandate["authorization_details"][0]["supplier_allowlist"]
    # Grounds declaration: before the document is opened, the AI agent declares what it intends to do from the task queue and
    # the mandate. The declared payee comes from the customer-signed mandate, never from the document.
    task = fixtures.INVOICE_TASKS.get(body.invoice_id, {"invoice_ref": body.invoice_id, "supplier_name": None})
    declared_payee = next((x["account_ref"] for x in allow if (x.get("name") or "").lower() == str(task.get("supplier_name") or "").lower()), None)
    intent_rec = audit.record("intent", body.passport_id, {"event": "grounds declaration: intent declared before the document was read", "invoice": body.invoice_id,
                                                          "task": f"pay invoice {task['invoice_ref']} from {task['supplier_name']}", "supplier_name": task["supplier_name"],
                                                          "invoice_ref": task["invoice_ref"], "declared_payee": declared_payee, "action_type": "pay_invoice",
                                                          "detail": f"declared payee {declared_payee} (the account the customer signed for this supplier)"})
    facts, mode = extraction.extract_invoice(body.invoice_id, texts[body.invoice_id])
    v = lambda k: (facts.get(k) or {}).get("value")  # noqa: E731
    account_ref = f"{v('sort_code')} {v('account_number')}".strip()
    matches = bool(declared_payee) and rules.norm_account(declared_payee) == rules.norm_account(account_ref)
    audit.record("agent", body.passport_id, {"event": "AI agent read an invoice into a payment instruction", "invoice": body.invoice_id, "mode": mode,
                                             "model": config.GEMINI_MODEL if mode == "gemini" else None, "payee_account_ref": account_ref, "amount": v("amount_gbp"),
                                             "bank_details_changed": v("bank_details_changed"), "declared_payee": declared_payee, "attempted_payee": account_ref,
                                             "matches_intent": matches, "intent_audit_id": intent_rec["id"],
                                             "detail": (f"attempted payee {account_ref} matches the declared intent" if matches else
                                                        f"attempted payee {account_ref} differs from the declared {declared_payee}: the document changed the destination, the AI agent did not")})
    req = {"passport_id": body.passport_id, "action_type": "pay_invoice", "payee_account_ref": account_ref, "supplier_name": v("supplier_name"),
           "amount": float(v("amount_gbp") or 0), "currency": "GBP", "invoice_ref": v("invoice_ref"), "nonce": crypto.new_nonce()}
    if chain_on(body.chain):
        req["delegation"] = make_delegation(p, body.passport_id, account_ref, config.DELEGATION_MAX_GBP, p["expires_at"])
        key = execution_key(p)["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    else:
        key = p["agent"]["private_pem"] if body.signer == "agent" else rogue_key()["private_pem"]
    req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
    on_allowlist = any(rules.norm_account(x["account_ref"]) == rules.norm_account(account_ref) for x in allow)
    registered = next((x["account_ref"] for x in allow if (x.get("name") or "").lower() == str(v("supplier_name") or "").lower()), None)
    intent = {"task": f"pay invoice {task['invoice_ref']} from {task['supplier_name']}", "declared_payee": declared_payee, "attempted_payee": account_ref, "matches": matches, "audit_id": intent_rec["id"]}
    evidence = {"invoice": body.invoice_id, "extraction_mode": mode, "facts": facts, "instruction_payee": account_ref, "registered_payee": registered, "intent": intent}
    result = verify(VerifyIn(passport_id=body.passport_id, instruction=req, evidence=evidence))
    return {"invoice": body.invoice_id, "text": texts[body.invoice_id], "extraction": facts, "extraction_mode": mode, "chain": bool(req.get("delegation")),
            "delegation": crypto.decode_unverified(req["delegation"])[1] if req.get("delegation") else None,
            "instruction": {k: v_ for k, v_ in req.items() if k not in ("agent_signature", "delegation")}, "on_allowlist": on_allowlist, "registered_payee": registered, "intent": intent, "result": result}


class VerifyIn(BaseModel):
    """Two accepted shapes. Nested: {passport_id, instruction: {...signed fields..., agent_signature}, passport?}.
    Flat: {passport_id, agent_signature, action_type, payee_account_ref, supplier_name, amount, currency, invoice_ref, nonce}."""
    passport_id: str
    instruction: dict | None = None   # signed payment instruction
    passport: dict | None = None      # optional presented envelope; otherwise fetched from the bank's list by id
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
    """The bank's gateway. Envelope (presented or fetched by id) + signed instruction + passport status +
    the bank's own ledger total → decision + signed receipt. The audit entry stores every input the decision
    depended on so /api/audit/{id}/replay can re-run the pure function later.
    Response carries both names for the rule and the audit anchor: rule / rule_id, audit_hash / audit_ref."""
    p = db.get_passport(body.passport_id)
    env = body.passport or (envelope_of(p) if p else {"passport_id": body.passport_id, "admission": None, "agent_identity": None, "mandate": None})
    pp_status = p["status"] if p else "unknown"
    req = body.instruction_dict()
    ledger_total = db.ledger_total(body.passport_id, str(req.get("payee_account_ref") or ""))
    seen = db.nonce_seen(body.passport_id, req.get("nonce"))
    daily = db.daily_count(body.passport_id)
    res = rules.verify_action(env, pp_status, req, ledger_total, nonce_seen=seen, daily_count=daily)
    fclass = rules.classify_refusal(res["code"]) if res["decision"] == "DENY" else None
    entry = {"event": "verification", "passport_id": body.passport_id, "instruction": req, "passport_status": pp_status, "presented_envelope": env,
             "ledger_total_before": ledger_total, "daily_count_before": daily, "nonce_seen_before": seen, "instruction_hash": crypto.sha256_hex(rules.request_signing_input(req)),
             "decision": res["decision"], "rule": res["rule"], "code": res["code"], "reason": res["reason"], "failure_class": fclass["id"] if fclass else None, "trace": res["trace"], "rule_pack": res["rule_pack"]}
    rec = audit.record("verify", body.passport_id, entry, receipt_for={"passport_id": body.passport_id, "decision": res["decision"], "rule": res["rule"], "code": res["code"], "instruction_hash": entry["instruction_hash"]})
    r4 = next((t for t in res["trace"] if t["rule"] == "R.4"), None)
    agent_kid = None
    try:
        ident_jwk = ((crypto.verify_jwt("northgate", env.get("agent_identity")) or {}).get("cnf") or {}).get("jwk")
        agent_kid = crypto.jwk_thumbprint(ident_jwk)[:16] if ident_jwk else None
    except Exception:  # noqa: BLE001
        agent_kid = None
    signature = {"checked": r4 is not None, "verified": bool(r4 and r4["ok"]), "alg": "Ed25519 (EdDSA, RFC 8037)", "agent_kid": agent_kid,
                 "signed_fields": list(rules.REQUEST_FIELDS), "instruction_hash": crypto.sha256_hex(rules.request_signing_input(req))}
    if res["decision"] in ("ALLOW", "ESCALATE"):
        db.remember_nonce(body.passport_id, req.get("nonce"), rec["id"])   # an executed or held instruction spends its nonce; presenting it again is a replay
    out = {**res, "rule_id": res["rule"], "failure_class": fclass, "signature": signature, "audit_id": rec["id"], "audit_hash": rec["hash"], "audit_ref": rec["hash"], "prev_hash": rec["prev_hash"], "receipt": rec["receipt"],
           "ledger_total_before": ledger_total, "settlement": None, "incident": None, "violation": None,
           "rails": {"passport_list": pp_status, "vouch": {"voucher_id": p.get("vouch_voucher_id") if p else None, "status": p.get("vouch_status") if p else None, "mode": p.get("vouch_mode") if p else None}}}
    if res["decision"] == "ALLOW":
        s = vouch.settle_payment(req)
        pay = db.insert_payment(body.passport_id, str(req.get("payee_account_ref")), float(req.get("amount") or 0), str(req.get("currency") or "GBP"), req.get("invoice_ref"), rec["id"], s["rail"], s.get("ref"))
        out["settlement"] = {**s, "ledger_total_after": ledger_total + float(req.get("amount") or 0), "payment_id": pay["id"]}
    elif res["decision"] == "DENY" and p:
        vio = db.insert_violation(body.passport_id, p["admission"].get("agent_id"), res["rule"], res["code"], req, body.evidence, rec["id"], fclass["id"] if fclass else None)
        out["violation"] = {"id": vio["id"], "status": vio["status"], "failure_class": fclass}
        n = db.denies_since_last_incident(body.passport_id)
        threshold = rules.pack()["policy"]["incident_deny_threshold"]
        out["deny_count"] = n
        if n >= threshold:
            inc = audit.record("incident", body.passport_id, {"event": "incident raised to the bank's payments risk team", "reason": f"{n} refused instructions since the last incident", "denies": n,
                                                              "last_rule": res["rule"], "last_code": res["code"], "product": p["admission"]["product_ref"]["product_name"], "provider": p["admission"]["product_ref"]["provider"], "agent_id": p["admission"]["agent_id"]})
            out["incident"] = {"audit_id": inc["id"], "hash": inc["hash"], "denies": n}
    return out


# ── API: audit and the evidence a supervisor can request ───────────────────
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
    res = rules.verify_action(e["presented_envelope"], e.get("passport_status", e.get("registry_status", "unknown")), e["instruction"], e.get("ledger_total_before", 0.0), today=day,
                              nonce_seen=bool(e.get("nonce_seen_before")), daily_count=int(e.get("daily_count_before") or 0))
    same = res["decision"] == e["decision"] and res["rule"] == e["rule"] and res["code"] == e["code"]
    return {"audit_id": audit_id, "original": {"decision": e["decision"], "rule": e["rule"], "code": e["code"]}, "replay": {"decision": res["decision"], "rule": res["rule"], "code": res["code"]}, "identical": same, "rule_pack": res["rule_pack"]}


@app.get("/api/receipt/verify")
def receipt_verify(token: str):
    payload = crypto.verify_jwt("bank", token)
    return {"verified": payload is not None, "payload": payload}


def evidence_bundle(p: dict, violation_ids: list[int] | None = None) -> dict:
    """Everything a supervisor needs to reconstruct what happened on one passport, in one self-verifying bundle:
    the register filing and its receipt, the bank's admission, the customer's agent identity and mandate, every
    verification with its inputs and receipt, the violations, and the hash chain segment. Read-only; the request itself is logged."""
    reg = db.get_registration(p["registration_id"]) or {}
    subj = [p["passport_id"]]
    if p["passport_id"].startswith("AP-"):
        subj.append(p["passport_id"].replace("AP-", "AG-"))
    rows = [r for s in subj for r in db.list_audit(1000, subject=s)]
    if violation_ids:
        vios = [v for v in db.list_violations(p["passport_id"]) if v["id"] in violation_ids]
    else:
        vios = db.list_violations(p["passport_id"])
    rows.sort(key=lambda r: r["id"])
    chain_all = db.list_audit(100000)
    head = audit.verify_chain(list(reversed(chain_all)))
    env = envelope_of(p)
    return {
        "bundle": "agent-passport-evidence/1", "generated_at": db.now_iso(), "requested_by": config.SUPERVISOR,
        "access_basis": "supervisory or incident process (read-only); this request is itself recorded in the audit chain",
        "passport": {"passport_id": p["passport_id"], "status": p["status"], "issued_at": p["issued_at"], "expires_at": p["expires_at"], "history": p["history"], "investigation": p.get("investigation")},
        "envelope": env, "envelope_verification": crypto.verify_envelope(env),
        "register_entry": {"ref": reg.get("ref"), "filed_at": reg.get("submitted_at"), "fields": reg.get("fields"), "filing_checks": reg.get("checks"), "receipt_jwt": reg.get("registration_jwt"),
                           "receipt_verified": crypto.verify_jwt("register", reg.get("registration_jwt")) is not None if reg.get("registration_jwt") else None},
        "bank_admission": {"status": reg.get("admission_status"), "officer": reg.get("officer"), "note": reg.get("officer_note"), "admitted_at": reg.get("admitted_at"), "condition": reg.get("condition")},
        "agent_identity": p["agent_identity"], "mandate": p.get("mandate"), "payments": db.list_payments(p["passport_id"]),
        "violations": vios, "audit_entries": rows, "chain": {"ok": head["ok"], "head": head.get("head"), "length": head.get("length"), "rule": "hash = sha256(prev_hash + canonical(entry))"},
        "signers": {n: {"kid": s["kid"], "jwk": s["jwk"]} for n, s in crypto.all_signers().items()},
    }


@app.get("/api/evidence/passports/{passport_id}")
def evidence_passport(passport_id: str):
    p = db.get_passport(passport_id) or _404()
    b = evidence_bundle(p)
    audit.record("evidence", passport_id, {"event": "evidence bundle exported for supervisory access", "requested_by": config.SUPERVISOR, "entries": len(b["audit_entries"]), "violations": len(b["violations"])})
    return b


@app.get("/api/evidence/violations/{vid}")
def evidence_violation(vid: int):
    v = db.get_violation(vid) or _404()
    p = db.get_passport(v["passport_id"]) or _404()
    b = evidence_bundle(p, [vid])
    b["focus"] = {"violation_id": vid, "audit_id": v.get("audit_id"), "rule": v["rule"], "code": v["code"]}
    audit.record("evidence", v["passport_id"], {"event": "evidence bundle exported for supervisory access", "requested_by": config.SUPERVISOR, "violation_id": vid, "entries": len(b["audit_entries"])})
    return b


# ── Demo control ───────────────────────────────────────────────────────────
@app.post("/api/reset")
def reset():
    db.reset_all()
    audit.record("system", None, {"event": "demo reset"})
    return {"ok": True}


@app.post("/api/demo/seed")
def demo_seed(stage: str = "issued"):
    """Restore the exact pre-demo baseline between takes. stage=registered: the product is filed on the register and the bank's
    review has run, ready for the officer. stage=issued (default): admitted, customer mandate signed, passport ACTIVE,
    no payments, no violations. Deterministic: fixture values, the customer's draft mandate, the default hold condition."""
    if stage not in ("registered", "issued"):
        _400("stage must be registered or issued")
    db.reset_all()
    audit.record("system", None, {"event": "demo baseline seeded", "stage": stage})
    n = db.count_registrations() + 14
    a = db.create_registration(f"REG-2026-{n:04d}")
    audit.record("registration", a["ref"], {"event": "AI product registration started on the register", "provider": config.PROVIDER})
    a = db.update_registration(a["id"], fields=extraction.fixture(), entry_mode="prefill")
    a = submit(a["id"])
    r = run_review(a["id"], ReviewIn())
    out = {"ok": True, "stage": stage, "registration": r["registration"]["ref"], "recommendation": r["review"]["steps"][4]["data"]["verdict"]}
    if stage == "issued":
        admission_decision(a["id"], AdmissionIn(decision="admit", note="Baseline: six filing checks pass, Independent Assurance Evidence covers the use case, sandbox 5 of 5, hold above £5,000.", hold_above=rules.pack()["policy"]["hold_above_gbp"]))
        p = create_agent(AgentIn(registration_id=a["id"]))
        p = sign_mandate(p["passport_id"], MandateIn())
        pid = p["passport_id"]
        out.update({"passport_id": pid, "status": p["status"], "mandate_signed": p["mandate_signed"], "vouch": {"voucher_id": p.get("vouch_voucher_id"), "mode": p.get("vouch_mode")}})
    out["audit_entries"] = len(db.list_audit())
    return out


def _404():
    raise HTTPException(404, "not found")


def _400(msg: str):
    raise HTTPException(400, msg)
