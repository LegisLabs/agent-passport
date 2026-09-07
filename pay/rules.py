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
    """'60-11-22 10101010' -> '601122 10101010' style: keep digits only, split sort code / account."""
    digits = re.sub(r"\D", "", str(ref or ""))
    return digits


# ── Application checks ─────────────────────────────────────────────────────
def _check(rule: dict, ok: bool, evidence: str, detail: str = "") -> dict:
    return {
        "id": rule["id"], "title": rule["title"], "status": rule["status"], "source": rule["source"],
        "result": "pass" if ok else "flag", "evidence": evidence, "detail": detail,
    }


def registered_models() -> list[dict]:
    return json.loads((config.FIXTURES_DIR / "registered_models.json").read_text())["models"]


def run_application_checks(fields: dict, agent: dict | None = None, reg: dict | None = None, today: date | None = None) -> list[dict]:
    """Model registration checks M.1–M.6 over the fields the model company entered plus the authority's records."""
    reg = reg or registry()
    pol = pack()["policy"]
    out = []
    for rule in pack()["application_rules"]:
        c = rule["check"]
        if c == "companies_house_match":
            num = _v(fields, "company", "companies_house_number") or ""
            rec = reg["companies_house"].get(num)
            ok = bool(rec and rec["status"] == "active" and rec["name"].lower() == (_v(fields, "company", "legal_name") or "").lower())
            out.append(_check(rule, ok, f"Companies House {num}", "active company, name matches" if ok else "no matching active company"))
        elif c == "attestation":
            at = fields.get("attestation", {})
            ok = all(_v(at, k) for k in ("name", "role", "declaration_ref"))
            out.append(_check(rule, ok, "registration: attestation", f"{_v(at, 'name')}, {_v(at, 'role')}, declaration {_v(at, 'declaration_ref')}: documentation accuracy attested on submission" if ok else "attestation incomplete"))
        elif c == "model_documented":
            m = fields.get("model", {})
            missing = [k for k in ("model_name", "model_id", "model_provider", "model_version", "benchmarks_url", "training_details_url", "documentation_url") if not _v(m, k)]
            bad_urls = [k for k in ("benchmarks_url", "training_details_url", "documentation_url") if _v(m, k) and not re.match(r"^https://\S+$", str(_v(m, k)))]
            ok = not missing and not bad_urls
            out.append(_check(rule, ok, "registration: model documentation", f"{_v(m, 'model_name')} on {_v(m, 'model_provider')} {_v(m, 'model_version')}; benchmark data, training details and model card published" if ok else ("missing: " + ", ".join(missing) if missing else "not https URLs: " + ", ".join(bad_urls))))
        elif c == "version_pinned":
            ver = str(_v(fields, "model", "model_version") or "")
            ok = bool(ver) and not re.search(r"latest|\*|current", ver, re.I) and bool(re.search(r"[\d]", ver))
            out.append(_check(rule, ok, f"model_version {ver or '—'}", "fixed version; a change means re-registration" if ok else "not a pinned version"))
        elif c == "intended_use_within_policy":
            at = _v(fields, "intended_use", "action_type")
            ok = at in pol["action_types"]
            out.append(_check(rule, ok, "policy table", f"{at} is a permitted action type" if ok else f"{at or 'no action type'} is outside {', '.join(pol['action_types'])}"))
        elif c == "not_already_registered":
            mid = _v(fields, "model", "model_id")
            clash = next((m for m in registered_models() if m.get("model_id") == mid and m.get("status") in ("active", "suspended")), None)
            ok = bool(mid) and clash is None
            out.append(_check(rule, ok, "approved-models registry", f"{mid} is new to the register" if ok else (f"{mid} is already registered as {clash['registration']}" if clash else "no model id")))
    return out


# ── Runtime verification ───────────────────────────────────────────────────
def _rule(rid: str) -> dict:
    return next(r for r in pack()["runtime_rules"] if r["id"] == rid)


def _result(rid: str, decision: str, code: str, reason: str, trace: list[dict]) -> dict:
    return {"decision": decision, "rule": rid, "code": code, "reason": reason, "trace": trace, "rule_pack": pack()["id"]}


REQUEST_FIELDS = ("passport_id", "action_type", "payee_account_ref", "supplier_name", "amount", "currency", "invoice_ref", "nonce")


def request_signing_input(req: dict) -> bytes:
    """Canonical bytes the agent signs: the instruction without the signature.
    Integral floats are written as integers so 3200 and 3200.0 sign identically whichever side parsed them."""
    body = {}
    for k in REQUEST_FIELDS:
        if k in req:
            v = req[k]
            body[k] = int(v) if isinstance(v, float) and v.is_integer() else v
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

    # R.1 assurance signature (authority); no assurance at all means the passport was never issued
    if not envelope.get("assurance"):
        step("R.1", False, "no assurance: the passport has not been issued (the customer has not signed its mandate)")
        return _result("R.1", "DENY", "PASSPORT_NOT_ISSUED", "passport not issued: the customer has not yet signed the mandate that gives the agent life", trace)
    assurance = crypto.verify_jwt("authority", envelope.get("assurance"))
    if not step("R.1", assurance is not None, "authority signature verifies" if assurance else "assurance does not verify against the authority key"):
        return _result("R.1", "DENY", _rule("R.1")["code"], "assurance signature invalid", trace)

    # R.2 status + expiry (registry is authoritative; token validity is the second guard)
    expired = today.isoformat() > assurance.get("valid_until", "9999-12-31")
    active = registry_status == "active" and not expired
    if not step("R.2", active, f"registry status {registry_status}" + (", expired" if expired else "")):
        return _result("R.2", "DENY", _rule("R.2")["code"], f"assurance not active: status is {registry_status.upper()}" + (" and validity has ended" if expired else ""), trace)

    # R.3 agent identity signature (provider) and binding to this assurance
    ident = crypto.verify_jwt("northgate", envelope.get("agent_identity"))
    bound = bool(ident) and crypto.sha256_hex(envelope.get("agent_identity") or "") == (assurance.get("binds") or {}).get("agent_identity_sha256")
    if not step("R.3", bool(ident) and bound, "customer signature verifies; agent identity bound to this assurance" if ident and bound else ("agent identity does not verify against the customer key" if not ident else "agent identity is not the one this assurance was issued for")):
        return _result("R.3", "DENY", _rule("R.3")["code"], "agent identity signature invalid or not bound to this assurance", trace)

    # R.4 instruction signed by the agent key in agent_identity.cnf. With a delegation chain (Part B), the
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
        note_ok, note_bad = "instruction signature matches the agent key", "instruction not signed by the bound agent key: possible copied passport"
    if not step("R.4", sig_ok, note_ok if sig_ok else note_bad):
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

    ad = (mandate.get("authorization_details") or [{}])[0]

    # C.a–C.c delegation chain (Part B): only when a delegation is presented. S_action ⊆ S_1 (delegation) ⊆ S_0 (mandate).
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
    out = _result("R.9", "ALLOW", "WITHIN_MANDATE", "within the customer-signed mandate and the supervisor's conditions", trace)
    out["chain"] = chain
    return out


# ── Part B: delegation chain ────────────────────────────────────────────────
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


# ── Phase 3: the customer's own mandate must sit within the authority's policy ceilings ──
def check_mandate_containment(mandate: dict, assurance_valid_until: str | None = None) -> list[dict]:
    """Ceiling containment at signing. Returns the failed checks (empty = within ceilings)."""
    pol = pack()["policy"]
    ad = mandate
    problems = []
    if not ad.get("supplier_allowlist"):
        problems.append({"field": "supplier_allowlist", "problem": "at least one payee account is required"})
    for s in ad.get("supplier_allowlist", []):
        if len(norm_account(s.get("account_ref"))) != 14 or not s.get("name"):
            problems.append({"field": "supplier_allowlist", "problem": f"payee '{s.get('name') or '?'}' needs a name and a sort code plus 8-digit account"})
    per = float(ad.get("per_payment_limit") or 0)
    if per <= 0 or per > pol["per_payment_ceiling_gbp"]:
        problems.append({"field": "per_payment_limit", "problem": f"per-payment limit £{per:,.0f} must be between £1 and the policy ceiling £{pol['per_payment_ceiling_gbp']:,.0f}"})
    monthly = float(ad.get("monthly_limit_per_account") or 0)
    if monthly <= 0 or monthly > pol["monthly_per_account_ceiling_gbp"]:
        problems.append({"field": "monthly_limit_per_account", "problem": f"30-day limit £{monthly:,.0f} must be between £1 and the policy ceiling £{pol['monthly_per_account_ceiling_gbp']:,.0f}"})
    if per > 0 and monthly > 0 and monthly < per:
        problems.append({"field": "monthly_limit_per_account", "problem": "30-day limit cannot be below the per-payment limit"})
    vu = str(ad.get("valid_until") or "")
    cap = min(pol["max_validity"], assurance_valid_until or pol["max_validity"])
    if not vu or vu > cap:
        problems.append({"field": "valid_until", "problem": f"expiry must be on or before {cap}"})
    if not set(ad.get("actions") or []) <= set(pol["action_types"]) or not ad.get("actions"):
        problems.append({"field": "actions", "problem": f"actions must be within {', '.join(pol['action_types'])}"})
    return problems
