"""The deterministic middle.

Application checks (A.*) run over the reviewed structured fields plus the
authority's own records. Runtime verification (R.*) runs over a presented
passport, a signed request and the registry, in a fixed order, deny by
default. No model is involved anywhere in this module; every function is
pure over its inputs so a decision can be replayed later.
"""
from __future__ import annotations

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


def _v(fields: dict, *path, default=None):
    cur = fields
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    if isinstance(cur, dict) and "value" in cur:
        return cur["value"]
    return cur


# ── Application checks ─────────────────────────────────────────────────────
def _check(rule: dict, ok: bool, evidence: str, detail: str = "") -> dict:
    return {
        "id": rule["id"], "title": rule["title"], "status": rule["status"], "source": rule["source"],
        "result": "pass" if ok else "flag", "evidence": evidence, "detail": detail,
    }


def run_application_checks(fields: dict, agent: dict | None, reg: dict | None = None) -> list[dict]:
    reg = reg or registry()
    pol = pack()["policy"]
    out = []
    for rule in pack()["application_rules"]:
        c = rule["check"]
        if c == "asa_active":
            arn = _v(fields, "firm", "asa_reference")
            rec = reg["asa"].get(arn or "")
            ok = bool(rec and rec["status"] == "active" and rec["firm"].lower() == (_v(fields, "firm", "name") or "").lower())
            out.append(_check(rule, ok, f"ASA record {arn}", "active, name matches" if ok else "no active ASA record for this firm"))
        elif c == "gateway_id_present":
            gid = _v(fields, "firm", "gateway_id") or ""
            ok = bool(re.fullmatch(r"[\d ]{12,16}", gid))
            out.append(_check(rule, ok, "application field", "present" if ok else "missing or malformed"))
        elif c == "companies_house_match":
            num = _v(fields, "firm", "companies_house_number") or ""
            rec = reg["companies_house"].get(num)
            ok = bool(rec and rec["status"] == "active" and rec["name"].lower() == (_v(fields, "firm", "name") or "").lower())
            out.append(_check(rule, ok, f"Companies House {num}", "active company, name matches" if ok else "no matching active company"))
        elif c == "accountable_person":
            ap = fields.get("accountable_person", {})
            ok = all(_v(ap, k) for k in ("name", "role", "email")) and _v(ap, "declaration_accepted") is True and (_v(ap, "professional_body") in pol["professional_bodies"])
            out.append(_check(rule, ok, "declaration document", f"{_v(ap, 'name')}, {_v(ap, 'role')}, {_v(ap, 'professional_body')}" if ok else "incomplete accountability details"))
        elif c == "aml_supervised":
            ref = _v(fields, "compliance", "aml_reference") or ""
            rec = reg["aml_supervision"].get(ref)
            ok = bool(rec and rec["status"] == "active" and rec["supervisor"] == _v(fields, "compliance", "aml_supervisor") and rec["firm"].lower() == (_v(fields, "firm", "name") or "").lower())
            out.append(_check(rule, ok, f"AML register {ref}", f"supervised by {rec['supervisor']} until {rec['valid_until']}" if ok else "no active supervision record"))
        elif c == "clients_authorised":
            arn = _v(fields, "firm", "asa_reference")
            bad = []
            for cl in fields.get("clients", []):
                rec = reg["client_authorisations"].get(cl.get("utr", ""))
                if not (rec and rec["firm_arn"] == arn and rec["status"] == "confirmed"):
                    bad.append(f"{cl.get('name')} ({cl.get('utr')})")
            out.append(_check(rule, not bad, "client authorisation records", "all clients confirmed" if not bad else "not confirmed: " + ", ".join(bad)))
        elif c == "clients_consented":
            bad = [f"{cl.get('name')}" for cl in fields.get("clients", []) if cl.get("consent_automated_processing") is not True]
            out.append(_check(rule, not bad, "client register extract", "all clients consented" if not bad else "no consent recorded: " + ", ".join(bad)))
        elif c == "scope_within_policy":
            ra = fields.get("requested_authority", {})
            problems = []
            if _v(ra, "task") != pol["task"]:
                problems.append("task")
            if _v(ra, "tax_year") not in pol["tax_years_open"]:
                problems.append("tax year")
            if _v(ra, "action_type") not in pol["action_types"]:
                problems.append("action type")
            thr = _v(ra, "escalation_threshold_gbp")
            if thr is None or float(thr) > pol["escalation_threshold_gbp"]:
                problems.append("escalation threshold above policy ceiling")
            out.append(_check(rule, not problems, "policy table", "within ceilings" if not problems else "outside policy: " + ", ".join(problems)))
        elif c == "proof_of_possession":
            ok = bool(agent and agent.get("pop_verified"))
            out.append(_check(rule, ok, "signed challenge", f"challenge signed by kid {agent.get('kid')}" if ok else "challenge not signed"))
        elif c == "software_recognised":
            sw = _v(fields, "agent", "software")
            ok = sw in pol["recognised_software"]
            out.append(_check(rule, ok, "recognised-software list", f"{sw} listed" if ok else f"{sw} not on list"))
    return out


# ── Runtime verification ───────────────────────────────────────────────────
def _rule(rid: str) -> dict:
    return next(r for r in pack()["runtime_rules"] if r["id"] == rid)


def _result(rid: str, decision: str, code: str, reason: str, trace: list[dict]) -> dict:
    return {"decision": decision, "rule": rid, "code": code, "reason": reason, "trace": trace, "rule_pack": pack()["id"]}


def request_signing_input(req: dict) -> bytes:
    """Canonical bytes the agent signs: the request without the signature."""
    body = {k: req[k] for k in ("passport_jti", "action", "utr", "tax_year", "tax_due", "nonce") if k in req}
    return crypto.canonical(body).encode()


def verify_action(token: str, passport_status: str, req: dict, reg: dict | None = None, today: date | None = None) -> dict:
    """Ordered checks, deny by default.

    token            the presented passport JWT
    passport_status  the registry's current status for its jti
    req              {passport_jti, action, utr, tax_year, tax_due, nonce, agent_sig}
    """
    reg = reg or registry()
    today = today or date.today()
    trace: list[dict] = []

    def step(rid, ok, note):
        trace.append({"rule": rid, "title": _rule(rid)["title"], "ok": ok, "note": note})
        return ok

    # R.1 signature
    payload = crypto.verify_jwt(token)
    if not step("R.1", payload is not None, "authority signature verifies" if payload else "signature does not verify against the authority key"):
        return _result("R.1", "DENY", _rule("R.1")["code"], "passport signature invalid", trace)

    # R.2 status + expiry (registry is authoritative; token exp is a second guard)
    expired = today.isoformat() > payload.get("valid_until", "9999-12-31")
    active = passport_status == "active" and not expired
    if not step("R.2", active, f"registry status {passport_status}" + (", expired" if expired else "")):
        return _result("R.2", "DENY", _rule("R.2")["code"], f"passport not active: status is {passport_status.upper()}" + (" and validity has ended" if expired else ""), trace)

    # R.3 request signed by the agent key bound in the passport (cnf)
    cnf = (payload.get("cnf") or {}).get("jwk")
    sig_ok = False
    if cnf and req.get("agent_sig"):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        try:
            pub = Ed25519PublicKey.from_public_bytes(crypto.b64u_decode(cnf["x"]))
            pub.verify(crypto.b64u_decode(req["agent_sig"]), request_signing_input(req))
            sig_ok = True
        except Exception:  # noqa: BLE001
            sig_ok = False
    if not step("R.3", sig_ok, "request signature matches the passport's agent key" if sig_ok else "request not signed by the bound agent key: possible copied passport"):
        return _result("R.3", "DENY", _rule("R.3")["code"], "request not signed by the passport's agent key (possession not proven)", trace)

    # R.4 scope
    ad = (payload.get("authorization_details") or [{}])[0]
    allowed_actions = set(ad.get("actions", []))
    in_scope = req.get("action") in allowed_actions and req.get("tax_year") == ad.get("tax_year")
    why = []
    if req.get("action") not in allowed_actions:
        why.append(f'action "{req.get("action")}" not granted (granted: {", ".join(sorted(allowed_actions)) or "none"})')
    if req.get("tax_year") != ad.get("tax_year"):
        why.append(f"tax year {req.get('tax_year')} outside scope ({ad.get('tax_year')})")
    if not step("R.4", in_scope, "within granted scope" if in_scope else "; ".join(why)):
        return _result("R.4", "DENY", _rule("R.4")["code"], "; ".join(why), trace)

    # R.5 client authorised for THIS firm (registry, by reference; no client data in the token)
    rec = reg["client_authorisations"].get(str(req.get("utr", "")))
    firm_arn = (payload.get("subject") or {}).get("operator", {}).get("asa_reference")
    authorised = bool(rec and rec["firm_arn"] == firm_arn and rec["status"] == "confirmed")
    if not step("R.5", authorised, "client authorisation confirmed for this firm" if authorised else "no confirmed authorisation for this UTR with this firm"):
        return _result("R.5", "DENY", _rule("R.5")["code"], f"client {req.get('utr')} is not authorised for this firm", trace)

    # R.6 escalation threshold
    thr = (ad.get("escalation_threshold") or {}).get("amount")
    tax_due = float(req.get("tax_due") or 0)
    if thr is not None and tax_due > float(thr):
        step("R.6", False, f"tax due £{tax_due:,.0f} above threshold £{float(thr):,.0f}")
        return _result("R.6", "ESCALATE", _rule("R.6")["code"], f"tax due £{tax_due:,.0f} exceeds the £{float(thr):,.0f} human-review threshold; held for a named reviewer", trace)
    step("R.6", True, f"tax due £{tax_due:,.0f} within threshold")
    return _result("R.6", "ALLOW", "WITHIN_SCOPE", "within granted scope and conditions", trace)
