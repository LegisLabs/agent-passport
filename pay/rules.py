"""The deterministic middle, payments vertical.

Application checks (A.*) run over the reviewed structured fields plus the
authority's own records. Runtime verification (R.*) runs at the bank over a
presented envelope (three JWTs), a signed payment instruction, the authority's
registry status and the bank's own ledger total, in a fixed order, deny by
default. No model is involved anywhere in this module; every function is pure
over its inputs so a decision can be replayed later.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from . import config, crypto

_PACK: dict | None = None


def pack() -> dict:
    global _PACK
    if _PACK is None:
        _PACK = json.loads(config.RULEPACK_PATH.read_text())
    return _PACK


def registry() -> dict:
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
    """'60-11-22 44556677' -> '601122 44556677' style: keep digits only, split sort code / account."""
    digits = re.sub(r"\D", "", str(ref or ""))
    return digits


# ── Application checks ─────────────────────────────────────────────────────
def _check(rule: dict, ok: bool, evidence: str, detail: str = "") -> dict:
    return {
        "id": rule["id"], "title": rule["title"], "status": rule["status"], "source": rule["source"],
        "result": "pass" if ok else "flag", "evidence": evidence, "detail": detail,
    }


def run_application_checks(fields: dict, agent: dict | None, reg: dict | None = None, today: date | None = None) -> list[dict]:
    reg = reg or registry()
    today = today or date.today()
    pol = pack()["policy"]
    out = []
    firm = (_v(fields, "provider", "legal_name") or "").lower()
    for rule in pack()["application_rules"]:
        c = rule["check"]
        if c == "licence_active":
            ref = _v(fields, "provider", "licence_ref") or ""
            rec = reg["psp_licences"].get(ref)
            ok = bool(rec and rec["status"] == "active" and rec["firm"].lower() == firm and "payment_initiation" in rec["permissions"])
            out.append(_check(rule, ok, f"register entry {ref}", f"{rec['type']}, active, payment initiation permitted" if ok else "no active licence with payment-initiation permission for this firm"))
        elif c == "companies_house_match":
            num = _v(fields, "provider", "companies_house_number") or ""
            rec = reg["companies_house"].get(num)
            ok = bool(rec and rec["status"] == "active" and rec["name"].lower() == firm)
            out.append(_check(rule, ok, f"Companies House {num}", "active company, name matches" if ok else "no matching active company"))
        elif c == "accountable_person":
            ap = fields.get("accountable_person", {})
            ok = all(_v(ap, k) for k in ("name", "role", "email", "declaration_ref")) and _v(ap, "declaration_accepted") is True
            out.append(_check(rule, ok, "appointment letter", f"{_v(ap, 'name')}, {_v(ap, 'role')}, declaration {_v(ap, 'declaration_ref')}" if ok else "incomplete accountability details or no signed declaration"))
        elif c == "insurance_evidenced":
            ins = fields.get("insurance", {})
            cover = float(_v(ins, "cover_gbp") or 0)
            until = str(_v(ins, "valid_until") or "")
            ok = bool(_v(ins, "policy_ref")) and cover >= pol["min_insurance_cover_gbp"] and until >= today.isoformat()
            out.append(_check(rule, ok, f"policy {_v(ins, 'policy_ref')}", f"£{cover:,.0f} cover until {until}" if ok else f"missing, below £{pol['min_insurance_cover_gbp']:,.0f} or lapsed"))
        elif c == "proof_of_possession":
            ok = bool(agent and agent.get("pop_verified"))
            out.append(_check(rule, ok, "signed challenge", f"challenge signed by kid {agent.get('kid')}" if ok else "challenge not signed"))
        elif c == "customer_agreement":
            cu = fields.get("customer", {})
            num = _v(cu, "companies_house_number") or ""
            rec = reg["companies_house"].get(num)
            ch_ok = bool(rec and rec["status"] == "active" and rec["name"].lower() == (_v(cu, "legal_name") or "").lower())
            sup = fields.get("suppliers") or []
            sup_ok = bool(sup) and all(s.get("account_ref") and s.get("name") for s in sup)
            ok = ch_ok and bool(_v(cu, "authorising_officer")) and bool(_v(cu, "officer_role")) and sup_ok
            problems = [p for p, bad in (("customer company", not ch_ok), ("authorising officer", not _v(cu, "authorising_officer")), ("supplier allowlist", not sup_ok)) if bad]
            out.append(_check(rule, ok, f"service agreement; Companies House {num}", f"{_v(cu, 'legal_name')}, officer {_v(cu, 'authorising_officer')}, {len(sup)} suppliers" if ok else "missing: " + ", ".join(problems)))
        elif c == "limits_within_policy":
            m = fields.get("mandate", {})
            problems = []
            if _v(m, "action_type") not in pol["action_types"]:
                problems.append("action type")
            if float(_v(m, "per_payment_limit_gbp") or 0) > pol["per_payment_ceiling_gbp"] or not _v(m, "per_payment_limit_gbp"):
                problems.append("per-payment limit")
            if float(_v(m, "monthly_limit_per_account_gbp") or 0) > pol["monthly_per_account_ceiling_gbp"] or not _v(m, "monthly_limit_per_account_gbp"):
                problems.append("monthly limit")
            vu = str(_v(m, "valid_until") or "")
            if not vu or vu > pol["max_validity"]:
                problems.append("validity")
            out.append(_check(rule, not problems, "policy table", "within ceilings" if not problems else "outside policy: " + ", ".join(problems)))
        elif c == "software_declared":
            sw = _v(fields, "agent", "software")
            ver = _v(fields, "agent", "software_version")
            declared = str(_v(fields, "agent", "config_hash") or "").lower()
            actual = agent_config_hash()
            ok = sw in pol["recognised_software"] and bool(ver) and declared == actual
            why = "hash matches deployed configuration" if declared == actual else "declared hash does not match the deployed configuration file"
            out.append(_check(rule, ok, f"{sw} {ver}; sha256 {actual[:12]}…", f"{sw} listed; {why}" if ok else f"{sw or 'software'} {'listed' if sw in pol['recognised_software'] else 'not on list'}; {why}"))
    return out


# ── Runtime verification ───────────────────────────────────────────────────
def _rule(rid: str) -> dict:
    return next(r for r in pack()["runtime_rules"] if r["id"] == rid)


def _result(rid: str, decision: str, code: str, reason: str, trace: list[dict]) -> dict:
    return {"decision": decision, "rule": rid, "code": code, "reason": reason, "trace": trace, "rule_pack": pack()["id"]}


REQUEST_FIELDS = ("passport_id", "action_type", "payee_account_ref", "supplier_name", "amount", "currency", "invoice_ref", "nonce")


def request_signing_input(req: dict) -> bytes:
    """Canonical bytes the agent signs: the instruction without the signature."""
    body = {k: req[k] for k in REQUEST_FIELDS if k in req}
    return crypto.canonical(body).encode()


def verify_action(envelope: dict, registry_status: str, req: dict, ledger_total: float = 0.0, today: date | None = None) -> dict:
    """Ordered checks at the bank, deny by default.

    envelope         {assurance, agent_identity, mandate} compact JWTs (mandate may be null)
    registry_status  the authority registry's current status for the passport id
    req              {passport_id, action_type, payee_account_ref, supplier_name, amount, currency, invoice_ref, nonce, agent_signature}
    ledger_total     the bank's executed total for this payee account in the trailing 30 days
    """
    today = today or date.today()
    trace: list[dict] = []

    def step(rid, ok, note):
        trace.append({"rule": rid, "title": _rule(rid)["title"], "ok": ok, "note": note})
        return ok

    # R.1 assurance signature (authority)
    assurance = crypto.verify_jwt("authority", envelope.get("assurance"))
    if not step("R.1", assurance is not None, "authority signature verifies" if assurance else "assurance does not verify against the authority key"):
        return _result("R.1", "DENY", _rule("R.1")["code"], "assurance signature invalid", trace)

    # R.2 status + expiry (registry is authoritative; token validity is the second guard)
    expired = today.isoformat() > assurance.get("valid_until", "9999-12-31")
    active = registry_status == "active" and not expired
    if not step("R.2", active, f"registry status {registry_status}" + (", expired" if expired else "")):
        return _result("R.2", "DENY", _rule("R.2")["code"], f"assurance not active: status is {registry_status.upper()}" + (" and validity has ended" if expired else ""), trace)

    # R.3 agent identity signature (provider) and binding to this assurance
    ident = crypto.verify_jwt("payrail", envelope.get("agent_identity"))
    bound = bool(ident) and crypto.sha256_hex(envelope.get("agent_identity") or "") == (assurance.get("binds") or {}).get("agent_identity_sha256")
    if not step("R.3", bool(ident) and bound, "provider signature verifies; identity bound to this assurance" if ident and bound else ("agent identity does not verify against the provider key" if not ident else "agent identity is not the one this assurance was issued for")):
        return _result("R.3", "DENY", _rule("R.3")["code"], "agent identity signature invalid or not bound to this assurance", trace)

    # R.4 instruction signed by the agent key in agent_identity.cnf
    jwk = (ident.get("cnf") or {}).get("jwk")
    sig_ok = bool(jwk and req.get("agent_signature") and crypto.verify_with_jwk(jwk, request_signing_input(req), req["agent_signature"]))
    if not step("R.4", sig_ok, "instruction signature matches the agent key" if sig_ok else "instruction not signed by the bound agent key: possible copied passport"):
        return _result("R.4", "DENY", _rule("R.4")["code"], "instruction not signed by the passport's agent key (possession not proven)", trace)

    # R.5 mandate present, signed by the customer, unexpired
    if not envelope.get("mandate"):
        step("R.5", False, "mandate not signed by the customer")
        return _result("R.5", "DENY", "MANDATE_NOT_SIGNED", "mandate not signed: the customer has not yet authorised this agent", trace)
    mandate = crypto.verify_jwt("northgate", envelope.get("mandate"))
    if not step("R.5", mandate is not None and mandate.get("passport_id") == assurance.get("jti"), "customer signature verifies" if mandate else "mandate does not verify against the customer key"):
        return _result("R.5", "DENY", "MANDATE_SIGNATURE_INVALID", "mandate signature invalid or for a different passport", trace)
    if today.isoformat() > mandate.get("valid_until", "9999-12-31"):
        step("R.5", False, f"mandate expired {mandate.get('valid_until')}")
        return _result("R.5", "DENY", "MANDATE_EXPIRED", f"mandate expired on {mandate.get('valid_until')}", trace)

    # R.6 action permitted and payee account on the allowlist
    ad = (mandate.get("authorization_details") or [{}])[0]
    if req.get("action_type") not in set(ad.get("actions", [])) or req.get("currency") != ad.get("currency"):
        step("R.6", False, f'action "{req.get("action_type")}" {req.get("currency")} not granted (granted: {", ".join(ad.get("actions", []))} {ad.get("currency")})')
        return _result("R.6", "DENY", "OUT_OF_SCOPE", f'action "{req.get("action_type")}" is not within the mandate (granted: {", ".join(ad.get("actions", []))} in {ad.get("currency")})', trace)
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
    if not step("R.8", projected <= monthly, f"£{ledger_total:,.0f} already paid to this account in 30 days + £{amount:,.0f} = £{projected:,.0f} " + ("within" if projected <= monthly else "exceeds") + f" £{monthly:,.0f}"):
        return _result("R.8", "DENY", _rule("R.8")["code"], f"30-day total for this account would reach £{projected:,.0f}, above the £{monthly:,.0f} limit; cumulative pattern refused", trace)

    # R.9 supervisor condition
    thr = ((assurance.get("condition") or {}).get("human_confirm_above") or {}).get("amount")
    if thr is not None and amount > float(thr):
        step("R.9", False, f"£{amount:,.0f} above the £{float(thr):,.0f} human-confirmation condition")
        return _result("R.9", "ESCALATE", _rule("R.9")["code"], f"£{amount:,.0f} exceeds the £{float(thr):,.0f} supervisor condition; held for the customer's authorising officer", trace)
    step("R.9", True, f"£{amount:,.0f} within the human-confirmation condition")
    return _result("R.9", "ALLOW", "WITHIN_MANDATE", "within the customer-signed mandate and the supervisor's conditions", trace)
