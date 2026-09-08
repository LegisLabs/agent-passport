"""The deterministic middle. No model is involved anywhere in this module; every function is
pure over its inputs so a decision can be replayed later.

Filing checks (F.*) run on the register when a provider files an AI product: completeness and
accountability, never a quality judgement. Runtime verification (R.*) runs at the bank over a
presented envelope (three JWTs), a signed payment instruction, the bank's own passport list and
the bank's own ledger total, in a fixed order, deny by default.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from . import companies_house, config, crypto

_PACK: dict | None = None


def pack() -> dict:
    global _PACK
    if _PACK is None:
        _PACK = json.loads(config.RULEPACK_PATH.read_text())
    return _PACK


def public_records() -> dict:
    return json.loads((config.FIXTURES_DIR / "registry.json").read_text())


def agent_config_hash() -> str:
    return hashlib.sha256((config.FIXTURES_DIR / "agent_config.json").read_bytes()).hexdigest()


def _v(fields: dict, *path, default=None):
    cur = fields
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    if isinstance(cur, dict) and "value" in cur:
        return cur["value"]
    return cur


def norm_account(ref: str | None) -> str:
    """'60-11-22 10101010' -> '6011221010101 0' style: keep digits only."""
    return re.sub(r"\D", "", str(ref or ""))


# ── Filing checks on the register ──────────────────────────────────────────
def _check(rule: dict, ok: bool, evidence: str, detail: str = "") -> dict:
    return {
        "id": rule["id"], "title": rule["title"], "status": rule["status"], "source": rule["source"],
        "result": "pass" if ok else "flag", "evidence": evidence, "detail": detail,
    }


def register_entries() -> list[dict]:
    return json.loads((config.FIXTURES_DIR / "register.json").read_text())["products"]


def run_registration_checks(fields: dict, reg: dict | None = None, today: date | None = None) -> list[dict]:
    """F.1 to F.6 over the fields the provider filed plus public records. Completeness and accountability only.
    A flag does not stop the filing; it is visible to every bank that reads the register."""
    reg = reg or public_records()
    today = today or date.today()
    pol = pack()["policy"]
    out = []
    for rule in pack()["registration_rules"]:
        c = rule["check"]
        if c == "companies_house_match":
            num = _v(fields, "company", "companies_house_number") or ""
            rec = companies_house.lookup(num)
            ok = bool(rec.get("found") and rec.get("active") and companies_house.names_match(rec.get("legal_name"), _v(fields, "company", "legal_name")))
            out.append({**_check(rule, ok, f"Companies House {num} · {rec.get('source', '')}", f"{rec.get('legal_name')}, {rec.get('status')}, {rec.get('address')}: filed name matches" if ok else (f"register shows {rec.get('legal_name')} ({rec.get('status')}); name or status does not match" if rec.get("found") else "no company with this number on the register")), "verification": rec})
        elif c == "accountable_principal":
            at = fields.get("principal", {})
            ok = all(_v(at, k) for k in ("name", "role", "declaration_ref"))
            out.append(_check(rule, ok, "filing: accountable principal", f"{_v(at, 'name')}, {_v(at, 'role')}, declaration {_v(at, 'declaration_ref')}: accountable for the accuracy of this filing" if ok else "accountable principal incomplete"))
        elif c == "insurance":
            ins = fields.get("insurance", {})
            cover = float(_v(ins, "cover_gbp") or 0)
            exp = str(_v(ins, "expires") or "")
            ok = bool(_v(ins, "insurer") and _v(ins, "policy_ref")) and cover >= pol["min_insurance_cover_gbp"] and exp >= today.isoformat()
            out.append(_check(rule, ok, f"policy {_v(ins, 'policy_ref') or '—'}", f"{_v(ins, 'insurer')}: cover £{cover:,.0f}, in force to {exp}" if ok else ("cover below the £{:,.0f} minimum".format(pol["min_insurance_cover_gbp"]) if cover < pol["min_insurance_cover_gbp"] else "policy missing or expired")))
        elif c == "product_documented":
            m = fields.get("product", {})
            missing = [k for k in ("product_name", "product_id", "release", "model_provider", "model_version", "documentation_url") if not _v(m, k)]
            ver = str(_v(m, "model_version") or "")
            pinned = bool(ver) and not re.search(r"latest|\*|current", ver, re.I) and bool(re.search(r"[\d]", ver))
            url_ok = bool(re.match(r"^https://\S+$", str(_v(m, "documentation_url") or "")))
            ok = not missing and pinned and url_ok
            out.append(_check(rule, ok, "filing: product", f"{_v(m, 'product_name')} release {_v(m, 'release')} on {_v(m, 'model_provider')} {ver}; documentation published" if ok else ("missing: " + ", ".join(missing) if missing else ("model version is not pinned" if not pinned else "documentation is not an https URL"))))
        elif c == "assurance_evidence":
            ae = fields.get("assurance_evidence", {})
            level = assurance_level(_v(ae, "level"))
            missing = [k for k in ("issuer", "reference", "date", "use_case", "report_url") if not _v(ae, k)] if level["id"] != "self-declared" else [k for k in ("use_case",) if not _v(ae, k)]
            covers = (_v(ae, "use_case") or "") == (_v(fields, "intended_use", "action_type") or "")
            url_ok = level["id"] == "self-declared" or bool(re.match(r"^https://\S+$", str(_v(ae, "report_url") or "")))
            level_ok = _v(ae, "level") in {x["id"] for x in pol["assurance_levels"]}
            ok = not missing and covers and url_ok and level_ok
            out.append({**_check(rule, ok, f"{level['label']} · {_v(ae, 'issuer') or 'no independent party'} {_v(ae, 'reference') or ''}".strip(), f"assurance level {level['label'].lower()}; evidence dated {_v(ae, 'date')} for use case {_v(ae, 'use_case')}; attached, not assessed by the register" if ok else ("assurance level not declared" if not level_ok else ("missing: " + ", ".join(missing) if missing else ("evidence does not cover the registered use case" if not covers else "report is not an https URL")))), "assurance_level": level["id"]})
        elif c == "not_already_registered":
            pid = _v(fields, "product", "product_id")
            clash = next((m for m in register_entries() if m.get("product_id") == pid and m.get("status") == "active"), None)
            ok = bool(pid) and clash is None
            out.append(_check(rule, ok, "Agent Passport Register", f"{pid} is new to the register" if ok else (f"{pid} is already on the register as {clash['registration']}" if clash else "no product id")))
    return out


# ── Assurance levels, account tiers and the ceilings they produce ─────────
def assurance_level(level_id: str | None) -> dict:
    levels = pack()["policy"]["assurance_levels"]
    return next((x for x in levels if x["id"] == level_id), levels[0])


def level_meets(level_id: str | None, minimum_id: str | None) -> bool:
    return assurance_level(level_id)["rank"] >= assurance_level(minimum_id)["rank"]


def admission_ceilings(level_id: str | None = None) -> dict:
    """The bank's admission ceilings for a product: the policy ceilings scaled by the provider's assurance level."""
    pol = pack()["policy"]
    f = assurance_level(level_id)["ceiling_factor"] if level_id else 1.0
    return {"per_payment_ceiling": {"amount": float(pol["per_payment_ceiling_gbp"]) * f, "currency": pol["currency"]},
            "monthly_per_account_ceiling": {"amount": float(pol["monthly_per_account_ceiling_gbp"]) * f, "currency": pol["currency"], "window": pol["monthly_window"]},
            "velocity_ceiling_per_day": int(pol["velocity_ceiling_per_day"]), "max_validity": pol["max_validity"], "action_types": list(pol["action_types"]), "currency": pol["currency"],
            "assurance_level": assurance_level(level_id)["id"] if level_id else None, "ceiling_factor": f}


def account_tier(account_type: str | None) -> dict:
    tiers = pack()["policy"]["account_tiers"]
    t = tiers.get(account_type or "") or tiers["business_current"]
    return {"id": account_type if account_type in tiers else "business_current", **t}


def effective_limits(ceilings: dict, account_type: str | None) -> dict:
    """What a customer may grant an AI agent on this account: the lower of the admission ceilings and the account tier."""
    tier = account_tier(account_type)
    return {"per_payment": min(float(ceilings["per_payment_ceiling"]["amount"]), float(tier["per_payment_gbp"])),
            "monthly_per_account": min(float(ceilings["monthly_per_account_ceiling"]["amount"]), float(tier["monthly_per_account_gbp"])),
            "max_payments_per_day": min(int(ceilings.get("velocity_ceiling_per_day", 20)), int(tier["velocity_per_day"])),
            "max_validity": ceilings["max_validity"], "currency": ceilings.get("currency", "GBP"), "account_tier": tier, "assurance_level": ceilings.get("assurance_level")}


def classify_refusal(code: str | None) -> dict:
    """fraud | agent_error: the class a refusal belongs to, from the reason code alone. Encoded once, in the rule pack,
    next to the rules, so console labels and the About page definitions cannot drift apart."""
    for cid, c in pack()["failure_classes"].items():
        if code in c["codes"]:
            return {"id": cid, "label": c["label"], "note": c["note"]}
    c = pack()["failure_classes"]["agent_error"]   # an unmapped code is a malformed instruction: the agent's own error
    return {"id": "agent_error", "label": c["label"], "note": c["note"]}


# ── Runtime verification at the bank ───────────────────────────────────────
def _rule(rid: str) -> dict:
    return next(r for r in pack()["runtime_rules"] if r["id"] == rid)


def _result(rid: str, decision: str, code: str, reason: str, trace: list[dict]) -> dict:
    return {"decision": decision, "rule": rid, "code": code, "reason": reason, "trace": trace, "rule_pack": pack()["id"]}


REQUEST_FIELDS = ("passport_id", "action_type", "payee_account_ref", "supplier_name", "amount", "currency", "invoice_ref", "nonce")


def request_signing_input(req: dict) -> bytes:
    """Canonical bytes the AI agent signs: the instruction without the signature.
    Integral floats are written as integers so 3200 and 3200.0 sign identically whichever side parsed them."""
    body = {}
    for k in REQUEST_FIELDS:
        if k in req:
            v = req[k]
            body[k] = int(v) if isinstance(v, float) and v.is_integer() else v
    return crypto.canonical(body).encode()


def verify_action(envelope: dict, passport_status: str, req: dict, ledger_total: float = 0.0, today: date | None = None, nonce_seen: bool = False, daily_count: int = 0) -> dict:
    """Ordered checks at the bank, deny by default.

    envelope         {admission, agent_identity, mandate} compact JWTs (mandate may be null)
    passport_status  the bank's current status for the passport id on its own list
    req              {passport_id, action_type, payee_account_ref, supplier_name, amount, currency, invoice_ref, nonce, agent_signature}
    ledger_total     the bank's executed total for this payee account in the trailing 30 days
    nonce_seen       whether the bank has already accepted an instruction with this nonce on this passport
    daily_count      the bank's count of executed payments on this passport in the trailing 24 hours
    """
    today = today or date.today()
    trace: list[dict] = []

    def step(rid, ok, note):
        trace.append({"rule": rid, "title": _rule(rid)["title"], "ok": ok, "note": note})
        return ok

    # R.1 admission signature (bank key); no admission at all means the passport was never issued
    if not envelope.get("admission"):
        step("R.1", False, "no admission: the passport has not been issued (the customer has not signed its mandate)")
        return _result("R.1", "DENY", "PASSPORT_NOT_ISSUED", "passport not issued: the customer has not yet signed the mandate that gives the AI agent authority", trace)
    admission = crypto.verify_jwt("bank", envelope.get("admission"))
    if not step("R.1", admission is not None, "bank admission signature verifies" if admission else "admission does not verify against the bank key"):
        return _result("R.1", "DENY", _rule("R.1")["code"], "admission signature invalid", trace)

    # R.2 status + expiry (the bank's list is authoritative; token validity is the second guard)
    expired = today.isoformat() > admission.get("valid_until", "9999-12-31")
    active = passport_status == "active" and not expired
    if not step("R.2", active, f"passport list status {passport_status}" + (", expired" if expired else "")):
        return _result("R.2", "DENY", _rule("R.2")["code"], f"passport not active: status is {passport_status.upper()}" + (" and validity has ended" if expired else ""), trace)

    # R.3 agent identity signature (customer) and binding to this admission
    ident = crypto.verify_jwt("northgate", envelope.get("agent_identity"))
    bound = bool(ident) and crypto.sha256_hex(envelope.get("agent_identity") or "") == (admission.get("binds") or {}).get("agent_identity_sha256")
    if not step("R.3", bool(ident) and bound, "customer signature verifies; agent identity bound to this admission" if ident and bound else ("agent identity does not verify against the customer key" if not ident else "agent identity is not the one this admission was issued for")):
        return _result("R.3", "DENY", _rule("R.3")["code"], "agent identity signature invalid or not bound to this admission", trace)

    # R.4 instruction signed by the AI agent key in agent_identity.cnf. With a delegation chain, the
    # orchestrator's key signs the delegation and the delegated execution key signs the instruction.
    jwk = (ident.get("cnf") or {}).get("jwk")
    delegation = None
    if req.get("delegation"):
        delegation = crypto.verify_jwt_jwk(jwk, req["delegation"])
        exec_jwk = ((delegation or {}).get("cnf") or {}).get("jwk")
        sig_ok = bool(delegation and exec_jwk and req.get("agent_signature") and crypto.verify_with_jwk(exec_jwk, request_signing_input(req), req["agent_signature"]))
        note_ok = "delegation signed by the orchestrator key bound in agent_identity; instruction signed by the delegated execution key"
        note_bad = "delegation not signed by the bound orchestrator key" if not delegation else "instruction not signed by the key named in the delegation"
    else:
        sig_ok = bool(jwk and req.get("agent_signature") and crypto.verify_with_jwk(jwk, request_signing_input(req), req["agent_signature"]))
        note_ok, note_bad = "instruction signature matches the AI agent key", "instruction not signed by the bound AI agent key: possible copied passport"
    if not step("R.4", sig_ok, note_ok if sig_ok else note_bad):
        return _result("R.4", "DENY", "AGENT_SIGNATURE_INVALID", "instruction not signed by the passport's AI agent key (possession not proven)", trace)
    if not req.get("nonce") or nonce_seen:
        step("R.4", False, "nonce already accepted on this passport: a replayed instruction" if req.get("nonce") else "instruction carries no nonce")
        return _result("R.4", "DENY", "REPLAY_DETECTED", "instruction replayed: its nonce was already accepted, so the same signed instruction cannot be executed twice", trace)

    # R.5 mandate present, signed by the customer, unexpired, not revoked
    if envelope.get("mandate_revoked"):
        step("R.5", False, "mandate revoked by the customer")
        return _result("R.5", "DENY", "MANDATE_REVOKED", "mandate revoked: the customer ended this AI agent's authority", trace)
    if not envelope.get("mandate"):
        step("R.5", False, "mandate not signed by the customer")
        return _result("R.5", "DENY", "MANDATE_NOT_SIGNED", "mandate not signed: the customer has not yet authorised this AI agent", trace)
    mandate = crypto.verify_jwt("northgate", envelope.get("mandate"))
    if not step("R.5", mandate is not None and mandate.get("passport_id") == admission.get("jti"), "customer signature verifies" if mandate else "mandate does not verify against the customer key"):
        return _result("R.5", "DENY", "MANDATE_SIGNATURE_INVALID", "mandate signature invalid or for a different passport", trace)
    if today.isoformat() > mandate.get("valid_until", "9999-12-31"):
        step("R.5", False, f"mandate expired {mandate.get('valid_until')}")
        return _result("R.5", "DENY", "MANDATE_EXPIRED", f"mandate expired on {mandate.get('valid_until')}", trace)

    ad = (mandate.get("authorization_details") or [{}])[0]

    # C.a to C.c delegation chain: only when a delegation is presented. S_action ⊆ S_1 (delegation) ⊆ S_0 (mandate).
    chain = None
    if delegation is not None:
        chain = verify_chain(ad, delegation, req, today)
        for c in chain["checks"]:
            trace.append({"rule": c["id"], "title": c["title"], "ok": c["ok"], "note": c["note"]})
        if not chain["ok"]:
            failed = next(c for c in chain["checks"] if not c["ok"])
            out = _result(failed["id"], "DENY", failed["code"], failed["note"], trace)
            out["chain"] = chain
            return out

    # R.6 action permitted and payee account on the allowlist
    if req.get("action_type") not in set(ad.get("actions", [])):
        step("R.6", False, f'action "{req.get("action_type")}" not granted (granted: {", ".join(ad.get("actions", []))})')
        return _result("R.6", "DENY", "OUT_OF_SCOPE", f'action "{req.get("action_type")}" is not within the mandate (granted: {", ".join(ad.get("actions", []))})', trace)
    if req.get("currency") != ad.get("currency"):
        step("R.6", False, f'currency {req.get("currency")} not permitted (mandate is in {ad.get("currency")})')
        return _result("R.6", "DENY", "CURRENCY_NOT_PERMITTED", f'instruction in {req.get("currency")}; the mandate operates in {ad.get("currency")} only', trace)
    want = norm_account(req.get("payee_account_ref"))
    match = next((s for s in ad.get("supplier_allowlist", []) if norm_account(s.get("account_ref")) == want and want), None)
    if not step("R.6", match is not None, f"payee account matches {match['supplier_id']} {match['name']}" if match else f"payee account {req.get('payee_account_ref')} is not on the customer-signed allowlist"):
        return _result("R.6", "DENY", "PAYEE_NOT_ON_MANDATE", f"payee account {req.get('payee_account_ref')} ({req.get('supplier_name')}) is not on the customer-signed mandate", trace)

    # R.7 per-payment limit
    amount = float(req.get("amount") or 0)
    cap = float((ad.get("per_payment_limit") or {}).get("amount") or 0)
    if not step("R.7", amount <= cap, f"£{amount:,.0f} within per-payment limit £{cap:,.0f}" if amount <= cap else f"£{amount:,.0f} exceeds per-payment limit £{cap:,.0f}"):
        return _result("R.7", "DENY", _rule("R.7")["code"], f"£{amount:,.0f} exceeds the per-payment limit of £{cap:,.0f}", trace)

    # R.8 monthly per-account limit (limit in the mandate, running total at the bank)
    monthly = float((ad.get("monthly_limit_per_account") or {}).get("amount") or 0)
    projected = float(ledger_total) + amount
    if projected > monthly:
        step("R.8", False, f"£{ledger_total:,.0f} already paid to this account in 30 days + £{amount:,.0f} = £{projected:,.0f} exceeds £{monthly:,.0f}")
        return _result("R.8", "DENY", "MONTHLY_LIMIT_EXCEEDED", f"30-day total for this account would reach £{projected:,.0f}, above the £{monthly:,.0f} limit; cumulative pattern refused", trace)
    per_day = int(ad.get("max_payments_per_day") or 0)
    if per_day and daily_count + 1 > per_day:
        step("R.8", False, f"{daily_count} payments already executed in 24 hours; the mandate allows {per_day} a day")
        return _result("R.8", "DENY", "DAILY_COUNT_EXCEEDED", f"payment {daily_count + 1} in 24 hours; the mandate allows {per_day} a day; velocity pattern refused", trace)
    step("R.8", True, f"£{ledger_total:,.0f} + £{amount:,.0f} = £{projected:,.0f} within £{monthly:,.0f}" + (f" · payment {daily_count + 1} of {per_day} a day" if per_day else ""))

    # R.9 the bank's hold condition
    thr = ((admission.get("condition") or {}).get("hold_above") or {}).get("amount")
    if thr is not None and amount > float(thr):
        step("R.9", False, f"£{amount:,.0f} above the £{float(thr):,.0f} hold condition")
        return _result("R.9", "ESCALATE", _rule("R.9")["code"], f"£{amount:,.0f} exceeds the bank's £{float(thr):,.0f} hold condition; held for the customer's named approver", trace)
    step("R.9", True, f"£{amount:,.0f} within the hold condition")
    out = _result("R.9", "ALLOW", "WITHIN_MANDATE", "within the customer-signed mandate and the bank's admission conditions", trace)
    out["chain"] = chain
    return out


# ── Delegation chain ────────────────────────────────────────────────────────
CHAIN_RULES = [
    {"id": "C.a", "title": "Root mandate scope is well formed", "code": "ROOT_SCOPE_INVALID"},
    {"id": "C.b", "title": "Delegation is a subset of the root mandate (beneficiaries, ceiling, actions, validity)", "code": "DELEGATION_EXPANDS_SCOPE"},
    {"id": "C.c", "title": "Action lies inside the narrowest scope", "code": "ACTION_OUTSIDE_DELEGATION"},
]


def verify_chain(root_ad: dict, delegation: dict, req: dict, today: date | None = None) -> dict:
    """S_n ⊆ … ⊆ S_1 ⊆ S_0. Delegation can only narrow authority, never expand it.
    (a) the root scope is valid; (b) the delegation is a subset of its parent; (c) the action is inside the narrowest scope."""
    today = today or date.today()
    checks = []
    root_accts = {norm_account(x.get("account_ref")) for x in root_ad.get("supplier_allowlist", [])}
    root_cap = float((root_ad.get("per_payment_limit") or {}).get("amount") or 0)
    root_actions = set(root_ad.get("actions", []))
    a_ok = bool(root_accts) and root_cap > 0 and bool(root_actions)
    checks.append({**CHAIN_RULES[0], "ok": a_ok, "note": f"S0: {len(root_accts)} beneficiaries, ceiling £{root_cap:,.0f}, actions {', '.join(sorted(root_actions))}" if a_ok else "root mandate has no beneficiaries, ceiling or actions"})
    scope = delegation.get("scope") or {}
    d_accts = {norm_account(x) for x in scope.get("beneficiaries", [])}
    d_cap = float(scope.get("max_amount") or 0)
    d_actions = set(scope.get("actions", []))
    problems = []
    if not d_accts or not d_accts <= root_accts:
        problems.append("beneficiary outside the root mandate")
    if d_cap <= 0 or d_cap > root_cap:
        problems.append(f"ceiling £{d_cap:,.0f} above the root £{root_cap:,.0f}")
    if not d_actions or not d_actions <= root_actions:
        problems.append("action not granted by the root")
    if today.isoformat() > str(scope.get("valid_until") or "9999-12-31"):
        problems.append("delegation expired")
    b_ok = a_ok and not problems
    checks.append({**CHAIN_RULES[1], "ok": b_ok, "note": f"S1 ⊆ S0: {len(d_accts)} beneficiar{'y' if len(d_accts) == 1 else 'ies'}, ceiling £{d_cap:,.0f}, actions {', '.join(sorted(d_actions))}" if b_ok else "delegation expands scope: " + "; ".join(problems)})
    amount = float(req.get("amount") or 0)
    c_problems = []
    if req.get("action_type") not in d_actions:
        c_problems.append(f'action "{req.get("action_type")}" not in the delegation')
    if norm_account(req.get("payee_account_ref")) not in d_accts:
        c_problems.append(f"payee {req.get('payee_account_ref')} not in the delegation")
    if amount > d_cap:
        c_problems.append(f"£{amount:,.0f} above the delegated ceiling £{d_cap:,.0f}")
    c_ok = b_ok and not c_problems
    checks.append({**CHAIN_RULES[2], "ok": c_ok, "note": f"action ⊆ S1: {req.get('action_type')} · {req.get('payee_account_ref')} · £{amount:,.0f}" if c_ok else "; ".join(c_problems) if c_problems else "not evaluated: the delegation itself is invalid"})
    return {"ok": a_ok and b_ok and c_ok, "checks": checks, "invariant": "S_action ⊆ S_1 ⊆ S_0",
            "scopes": {"S0": {"beneficiaries": len(root_accts), "ceiling": root_cap, "actions": sorted(root_actions)},
                       "S1": {"beneficiaries": sorted(x for x in scope.get("beneficiaries", [])), "ceiling": d_cap, "actions": sorted(d_actions), "delegate": delegation.get("sub"), "issuer": delegation.get("iss")},
                       "action": {"payee": req.get("payee_account_ref"), "amount": amount, "action": req.get("action_type")}}}


# ── The customer's own mandate must sit within the bank's admission ceilings ──
def check_mandate_containment(mandate: dict, admission_valid_until: str | None = None, ceilings: dict | None = None) -> list[dict]:
    """Ceiling containment at signing: the lower of the bank's admission ceilings (scaled by the provider's assurance level)
    and the account-type tier. Returns the failed checks (empty = within ceilings)."""
    pol = pack()["policy"]
    ad = mandate
    lim = effective_limits(ceilings or admission_ceilings(), (ad.get("customer") or {}).get("account_type"))
    problems = []
    if not ad.get("supplier_allowlist"):
        problems.append({"field": "supplier_allowlist", "problem": "at least one payee account is required"})
    for s in ad.get("supplier_allowlist", []):
        if len(norm_account(s.get("account_ref"))) != 14 or not s.get("name"):
            problems.append({"field": "supplier_allowlist", "problem": f"payee '{s.get('name') or '?'}' needs a name and a sort code plus 8-digit account"})
    per = float(ad.get("per_payment_limit") or 0)
    if per <= 0 or per > lim["per_payment"]:
        problems.append({"field": "per_payment_limit", "problem": f"per-payment limit £{per:,.0f} must be between £1 and the agent-channel limit £{lim['per_payment']:,.0f} for this account"})
    monthly = float(ad.get("monthly_limit_per_account") or 0)
    if monthly <= 0 or monthly > lim["monthly_per_account"]:
        problems.append({"field": "monthly_limit_per_account", "problem": f"30-day limit £{monthly:,.0f} must be between £1 and the agent-channel limit £{lim['monthly_per_account']:,.0f} for this account"})
    per_day = int(ad.get("max_payments_per_day") or 0)
    if per_day <= 0 or per_day > lim["max_payments_per_day"]:
        problems.append({"field": "max_payments_per_day", "problem": f"payments per day must be between 1 and {lim['max_payments_per_day']} for this account"})
    if (ad.get("currency") or pol["currency"]) != lim["currency"]:
        problems.append({"field": "currency", "problem": f"the mandate must be in {lim['currency']}"})
    if per > 0 and monthly > 0 and monthly < per:
        problems.append({"field": "monthly_limit_per_account", "problem": "30-day limit cannot be below the per-payment limit"})
    vu = str(ad.get("valid_until") or "")
    cap = min(pol["max_validity"], admission_valid_until or pol["max_validity"])
    if not vu or vu > cap:
        problems.append({"field": "valid_until", "problem": f"expiry must be on or before {cap}"})
    if not set(ad.get("actions") or []) <= set(pol["action_types"]) or not ad.get("actions"):
        problems.append({"field": "actions", "problem": f"actions must be within {', '.join(pol['action_types'])}"})
    return problems
