"""Standards Review Assistant (the brief's KYA standards evaluation tool).

Six visible steps the regulator's copilot runs when an officer opens a submitted application. Every step is
deterministic over structured facts; the sandbox run uses the same rules.verify_action the bank uses. The
model may phrase a summary (through extraction.draft_file_note, verdict vocabulary rejected); it never scores,
decides or signs. Only the officer's own POST /decision applies the authority signature.

  1 EVIDENCE READ           what the provider claims, what the customer authorised, what the authority is asked to certify
  2 STANDARDS RULE MAP      each rule in the versioned pack mapped to the evidence that satisfies it; uncovered items flagged
  3 ADVERSARIAL TESTS       five test instructions specific to this passport
  4 SANDBOX RUN             each test through the real R.1–R.9 engine against a provisional, sandbox-signed envelope
  5 RECOMMENDATION          APPROVE WITH CONDITIONS / REFER, reasoning drawn from 2–4, labelled "AI recommendation — human decision required"
  6 HUMAN SIGN-OFF          the existing officer decision; nothing here approves anything
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config, crypto, extraction, rules

RULE_EVIDENCE = {
    "A.1": ("provider", "licence_ref"), "A.2": ("provider", "companies_house_number"), "A.3": ("accountable_person", "declaration_ref"),
    "A.4": ("insurance", "policy_ref"), "A.5": None, "A.6": ("customer", "legal_name"), "A.7": ("mandate", "per_payment_limit_gbp"), "A.8": ("agent", "config_hash"),
}


def _v(fields, *path):
    return rules._v(fields, *path)


def step_evidence(a: dict) -> dict:
    f = a["fields"]
    sup = f.get("suppliers") or []
    return {
        "provider_claims": {"legal_name": _v(f, "provider", "legal_name"), "licence_ref": _v(f, "provider", "licence_ref"), "agent": f"{_v(f, 'agent', 'agent_name')} ({_v(f, 'agent', 'agent_id')})",
                            "software": f"{_v(f, 'agent', 'software')} {_v(f, 'agent', 'software_version')}", "accountable_person": f"{_v(f, 'accountable_person', 'name')}, {_v(f, 'accountable_person', 'role')}",
                            "insurance": f"£{float(_v(f, 'insurance', 'cover_gbp') or 0):,.0f} until {_v(f, 'insurance', 'valid_until')}"},
        "customer_authorises": {"customer": _v(f, "customer", "legal_name"), "officer": f"{_v(f, 'customer', 'authorising_officer')}, {_v(f, 'customer', 'officer_role')}",
                                "payees": [f"{x.get('supplier_id')} {x.get('name')} {x.get('account_ref')}" for x in sup],
                                "per_payment_limit": float(_v(f, "mandate", "per_payment_limit_gbp") or 0), "monthly_limit_per_account": float(_v(f, "mandate", "monthly_limit_per_account_gbp") or 0), "valid_until": _v(f, "mandate", "valid_until")},
        "authority_asked_to_certify": {"kya_assurance": "provider identity, licence, accountability, insurance, software and key binding verified against records",
                                       "condition_proposed": float(_v(f, "mandate", "human_confirm_above_gbp") or 0), "action": _v(f, "mandate", "action_type")},
        "documents": [d["name"] for d in a.get("documents") or []], "extraction_mode": a.get("extraction_mode"),
    }


def step_rule_map(a: dict) -> dict:
    checks = {c["id"]: c for c in a.get("checks") or []}
    f = a["fields"]
    rows = []
    for r in rules.pack()["application_rules"]:
        c = checks.get(r["id"])
        path = RULE_EVIDENCE.get(r["id"])
        fact = f.get(path[0], {}).get(path[1]) if path else None
        ev = {"value": fact.get("value"), "source_doc": fact.get("source_doc"), "quote": fact.get("quote")} if isinstance(fact, dict) else ({"value": "signed challenge", "source_doc": "agent key registration", "quote": None} if r["id"] == "A.5" else None)
        rows.append({"id": r["id"], "title": r["title"], "status": r["status"], "source": r["source"], "result": c["result"] if c else "not run", "detail": c["detail"] if c else "", "evidence": ev,
                     "covered": bool(ev and ev.get("value") not in (None, "")) and bool(c)})
    return {"rule_pack": rules.pack()["id"], "rules": rows, "uncovered": [r["id"] for r in rows if not r["covered"]], "flagged": [r["id"] for r in rows if r["result"] == "flag"]}


def step_tests(a: dict) -> list[dict]:
    f = a["fields"]
    sup = f.get("suppliers") or []
    first = sup[0] if sup else {"name": "Supplier", "account_ref": "00-00-00 00000000"}
    cap = float(_v(f, "mandate", "per_payment_limit_gbp") or 0)
    thr = float(_v(f, "mandate", "human_confirm_above_gbp") or rules.pack()["policy"]["human_confirm_above_gbp"])
    return [
        {"id": "T1", "title": "Payment to a non-mandated supplier", "expect": "DENY", "expect_rule": "R.6", "instruction": {"supplier_name": first["name"], "payee_account_ref": "60-11-22 99887766", "amount": min(cap, 2500.0)}, "variant": "normal"},
        {"id": "T2", "title": f"Amount £1 above the per-payment limit (£{cap:,.0f})", "expect": "DENY", "expect_rule": "R.7", "instruction": {"supplier_name": first["name"], "payee_account_ref": first["account_ref"], "amount": cap + 1}, "variant": "normal"},
        {"id": "T3", "title": "Expired passport presented", "expect": "DENY", "expect_rule": "R.2", "instruction": {"supplier_name": first["name"], "payee_account_ref": first["account_ref"], "amount": 100.0}, "variant": "expired"},
        {"id": "T4", "title": "Instruction signed with a rogue key", "expect": "DENY", "expect_rule": "R.4", "instruction": {"supplier_name": first["name"], "payee_account_ref": first["account_ref"], "amount": 100.0}, "variant": "rogue"},
        {"id": "T5", "title": f"Amount above the supervisor condition (£{thr:,.0f}) but within the limit", "expect": "ESCALATE", "expect_rule": "R.9", "instruction": {"supplier_name": first["name"], "payee_account_ref": first["account_ref"], "amount": min(cap, thr + 100)}, "variant": "normal"},
    ]


def _sandbox_envelope(a: dict, condition: float, expired: bool) -> dict:
    """A provisional envelope signed by the real keys but for a SANDBOX id that is never entered in the registry."""
    f, ag = a["fields"], a["agent"]
    pol = rules.pack()["policy"]
    pid = f"SANDBOX-{a['ref']}"
    ident = a.get("agent_identity_jwt")
    valid_until = (date.today() - timedelta(days=1)).isoformat() if expired else min(str(_v(f, "mandate", "valid_until") or pol["max_validity"]), pol["max_validity"])
    assurance = crypto.sign_jwt("authority", {"iss": config.ISSUER, "typ": "assurance", "sandbox": True, "jti": pid, "iat": crypto.now_ts(), "valid_until": valid_until,
                                              "provider": {"legal_name": _v(f, "provider", "legal_name"), "licence_ref": _v(f, "provider", "licence_ref")}, "agent_id": ag["agent_id"],
                                              "condition": {"human_confirm_above": {"amount": condition, "currency": "GBP"}}, "binds": {"agent_identity_sha256": crypto.sha256_hex(ident)}}, typ="assurance+jwt")
    mandate = crypto.sign_jwt("northgate", {"iss": "northgate-joinery-ltd", "typ": "mandate", "sandbox": True, "passport_id": pid, "valid_until": valid_until, "iat": crypto.now_ts(),
                                            "authorization_details": [{"type": "payment_initiation", "actions": [_v(f, "mandate", "action_type") or "pay_invoice"], "currency": pol["currency"],
                                                                       "supplier_allowlist": [{"supplier_id": s.get("supplier_id"), "name": s.get("name"), "account_ref": s.get("account_ref")} for s in f.get("suppliers", [])],
                                                                       "per_payment_limit": {"amount": float(_v(f, "mandate", "per_payment_limit_gbp") or 0), "currency": pol["currency"]},
                                                                       "monthly_limit_per_account": {"amount": float(_v(f, "mandate", "monthly_limit_per_account_gbp") or 0), "currency": pol["currency"], "window": pol["monthly_window"]}}]}, typ="mandate+jwt")
    return {"passport_id": pid, "assurance": assurance, "agent_identity": ident, "mandate": mandate}


def step_sandbox(a: dict, tests: list[dict], condition: float) -> list[dict]:
    """Same code path as the bank: rules.verify_action over a sandbox envelope. PASS = the engine refused or escalated as expected."""
    ag = a["agent"]
    rogue_priv, _ = crypto.generate_keypair()
    out = []
    for t in tests:
        env = _sandbox_envelope(a, condition, expired=t["variant"] == "expired")
        req = {"passport_id": env["passport_id"], "action_type": "pay_invoice", "currency": "GBP", "invoice_ref": f"SANDBOX-{t['id']}", "nonce": crypto.new_nonce(), **t["instruction"]}
        key = rogue_priv if t["variant"] == "rogue" else ag["private_pem"]
        req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
        res = rules.verify_action(env, "active", req, ledger_total=0.0)
        out.append({**t, "decision": res["decision"], "rule": res["rule"], "code": res["code"], "reason": res["reason"], "pass": res["decision"] == t["expect"] and res["rule"] == t["expect_rule"]})
    return out


def step_recommendation(a: dict, rule_map: dict, sandbox: list[dict], condition: float) -> dict:
    flagged, uncovered = rule_map["flagged"], rule_map["uncovered"]
    failed = [s["id"] for s in sandbox if not s["pass"]]
    pop = bool(a.get("agent") and a["agent"].get("pop_verified"))
    if failed or uncovered or not pop:
        verdict = "REFER"
    elif flagged:
        verdict = "REFER"
    else:
        verdict = "APPROVE WITH CONDITIONS"
    reasons = []
    reasons.append(f"{len(rule_map['rules']) - len(flagged)} of {len(rule_map['rules'])} standards rules satisfied by cited evidence" + (f"; flagged {', '.join(flagged)}" if flagged else ""))
    reasons.append(f"{sum(1 for s in sandbox if s['pass'])} of {len(sandbox)} adversarial tests refused or escalated by the bank engine as expected" + (f"; unexpected {', '.join(failed)}" if failed else ""))
    reasons.append("agent holds its key (signed challenge)" if pop else "agent has not proven possession of its key")
    reasons.append(f"condition to attach: hold instructions above £{condition:,.0f} for the customer's authorising officer")
    note, mode = extraction.draft_file_note(a["ref"], a["fields"], a.get("checks") or [])
    return {"verdict": verdict, "label": "AI recommendation — human decision required", "condition": {"human_confirm_above": condition}, "reasons": reasons, "narrative": note, "narrative_mode": mode,
            "options": ["APPROVE", "APPROVE WITH CONDITIONS", "REFER"], "decides": False}


def run(a: dict, condition: float | None = None) -> dict:
    if not a.get("fields") or not a.get("checks"):
        raise ValueError("application not submitted")
    thr = float(condition if condition is not None else (_v(a["fields"], "mandate", "human_confirm_above_gbp") or rules.pack()["policy"]["human_confirm_above_gbp"]))
    evidence = step_evidence(a)
    rule_map = step_rule_map(a)
    tests = step_tests(a)
    sandbox = step_sandbox(a, tests, thr)
    rec = step_recommendation(a, rule_map, sandbox, thr)
    return {"assistant": "Standards Review Assistant (KYA standards evaluation tool)", "rule_pack": rules.pack()["id"], "condition": thr,
            "steps": [
                {"n": 1, "id": "evidence", "title": "Evidence read", "data": evidence},
                {"n": 2, "id": "rule_map", "title": "Standards rule map", "data": rule_map},
                {"n": 3, "id": "tests", "title": "Adversarial test generation", "data": tests},
                {"n": 4, "id": "sandbox", "title": "Sandbox run (real bank engine)", "data": sandbox},
                {"n": 5, "id": "recommendation", "title": "Recommendation", "data": rec},
                {"n": 6, "id": "signoff", "title": "Human sign-off", "data": {"who": config.OFFICER, "how": "POST /api/applications/{id}/decision", "note": "only this step signs the assurance and activates the passport"}},
            ]}
