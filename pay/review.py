"""Standards Review Assistant (the brief's KYA standards evaluation tool), model-register edition.

Six visible steps the authority's copilot runs when an officer opens a submitted MODEL registration. Every step is
deterministic over structured facts; the sandbox run uses the bank's own rules.verify_action against a hypothetical
passport built on this model under the proposed ceilings. The model may phrase a summary (extraction.draft_file_note,
verdict vocabulary rejected); it never scores, decides or signs. Only the officer's own POST /decision approves the
model, sets the policy ceilings and the supervisor condition.

  1 EVIDENCE READ           what the model company registered, what customers will authorise, what the authority certifies
  2 STANDARDS RULE MAP      each M-rule in the versioned pack mapped to the evidence that satisfies it
  3 ADVERSARIAL TESTS       five instructions any future passport on this model must survive
  4 SANDBOX RUN             each test through the real R.1–R.9 engine on a sandbox-signed hypothetical passport
  5 RECOMMENDATION          APPROVE WITH CONDITIONS / REFER, labelled "AI recommendation — human decision required"
  6 HUMAN SIGN-OFF          the officer approves the MODEL and sets ceilings and the condition; nothing here approves anything
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config, crypto, extraction, rules

RULE_EVIDENCE = {"M.1": ("company", "companies_house_number"), "M.2": ("model", "version"), "M.3": ("model", "benchmarks"), "M.4": None}
SANDBOX_PAYEE = {"supplier_id": "SANDBOX-1", "name": "Sandbox Supplier Ltd", "account_ref": "60-00-00 00000001"}


def _v(fields, *path):
    return rules._v(fields, *path)


def ceilings() -> dict:
    pol = rules.pack()["policy"]
    return {"per_payment_ceiling": {"amount": float(pol["per_payment_ceiling_gbp"]), "currency": pol["currency"]},
            "monthly_per_account_ceiling": {"amount": float(pol["monthly_per_account_ceiling_gbp"]), "currency": pol["currency"], "window": pol["monthly_window"]},
            "max_validity": pol["max_validity"], "action_types": list(pol["action_types"])}


def step_evidence(a: dict) -> dict:
    f = a["fields"]
    pol = rules.pack()["policy"]
    return {
        "company_registers": {"legal_name": _v(f, "company", "legal_name"), "companies_house_number": _v(f, "company", "companies_house_number"),
                              "model": f"{_v(f, 'model', 'name')} {_v(f, 'model', 'version')} (pinned)", "training_type": _v(f, "model", "training_type"),
                              "benchmarks": _v(f, "model", "benchmarks"), "documentation": _v(f, "model", "documentation_ref"),
                              "liability": "answers only for the accuracy of this documentation; no deployment, no agent, no customer, no insurance"},
        "customers_will_authorise": {"note": "No customer data in the registration. A customer creates an agent by giving this model a mandate: its own agent key, its own deployment attestation, payees and limits within the ceilings. Live at once; the bank checks it on every payment."},
        "authority_certifies": {"model_approval": "company identity, model documentation, benchmarks and the publisher's attestation verified against records",
                                "policy_ceilings": f"per payment ≤ £{pol['per_payment_ceiling_gbp']:,.0f}; per account in 30 days ≤ £{pol['monthly_per_account_ceiling_gbp']:,.0f}; expiry ≤ {pol['max_validity']}; actions {', '.join(pol['action_types'])}",
                                "condition_default": float(pol["human_confirm_above_gbp"])},
        "documents": [], "registration": "fields entered by the model company on the Model Register" + (" (prefilled for the demo)" if a.get("extraction_mode") == "prefill" else ""), "extraction_mode": a.get("extraction_mode"),
    }


def step_rule_map(a: dict) -> dict:
    checks = {c["id"]: c for c in a.get("checks") or []}
    f = a["fields"]
    rows = []
    for r in rules.pack()["model_rules"]:
        c = checks.get(r["id"])
        path = RULE_EVIDENCE.get(r["id"])
        fact = f.get(path[0], {}).get(path[1]) if path else None
        ev = {"value": fact.get("value"), "source_doc": fact.get("source_doc"), "quote": fact.get("quote")} if isinstance(fact, dict) else ({"value": "publisher signature", "source_doc": "submitted registration", "quote": None} if r["id"] == "M.4" else None)
        rows.append({"id": r["id"], "title": r["title"], "status": r["status"], "source": r["source"], "result": c["result"] if c else "not run", "detail": c["detail"] if c else "", "evidence": ev,
                     "covered": bool(ev and ev.get("value") not in (None, "")) and bool(c)})
    return {"rule_pack": rules.pack()["id"], "rules": rows, "uncovered": [r["id"] for r in rows if not r["covered"]], "flagged": [r["id"] for r in rows if r["result"] == "flag"]}


def step_tests(a: dict, condition: float) -> list[dict]:
    """Five adversarial instructions any future passport on this model must survive, at the proposed ceilings."""
    pol = rules.pack()["policy"]
    cap = float(pol["per_payment_ceiling_gbp"])
    thr = float(condition)
    return [
        {"id": "T1", "title": "Payment to a non-mandated supplier", "expect": "DENY", "expect_rule": "R.6", "instruction": {"supplier_name": "Unlisted Courier Ltd", "payee_account_ref": "60-11-22 20202020", "amount": min(cap, 2500.0)}, "variant": "normal"},
        {"id": "T2", "title": f"Amount £1 above the policy ceiling (£{cap:,.0f})", "expect": "DENY", "expect_rule": "R.7", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": cap + 1}, "variant": "normal"},
        {"id": "T3", "title": "Expired approval presented", "expect": "DENY", "expect_rule": "R.2", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": 100.0}, "variant": "expired"},
        {"id": "T4", "title": "Instruction signed with a rogue key", "expect": "DENY", "expect_rule": "R.4", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": 100.0}, "variant": "rogue"},
        {"id": "T5", "title": f"Amount above the supervisor condition (£{thr:,.0f}) but within the ceiling", "expect": "ESCALATE", "expect_rule": "R.9", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": min(cap, thr + 100)}, "variant": "normal"},
    ]


def model_id_for(a: dict) -> str:
    f = a["fields"]
    return f"MODEL-{str(_v(f, 'company', 'legal_name') or 'co').split()[0].lower()}-{str(_v(f, 'model', 'name') or 'model').lower()}-{_v(f, 'model', 'version')}"


def _sandbox_envelope(a: dict, condition: float, expired: bool, agent_priv: str, agent_jwk: dict) -> dict:
    """A hypothetical passport on this model, signed by the real keys but for SANDBOX ids never entered in any registry."""
    f = a["fields"]
    pol = rules.pack()["policy"]
    mid = model_id_for(a)
    pid = f"SANDBOX-{a['ref']}"
    valid_until = (date.today() - timedelta(days=1)).isoformat() if expired else pol["max_validity"]
    assurance = crypto.sign_jwt("authority", {"iss": config.ISSUER, "typ": "assurance", "sandbox": True, "jti": f"{mid}-SANDBOX", "iat": crypto.now_ts(), "valid_until": valid_until,
                                              "model": {"model_id": mid, "name": _v(f, "model", "name"), "version": _v(f, "model", "version"), "company": _v(f, "company", "legal_name")},
                                              "policy_ceilings": ceilings(), "condition": {"human_confirm_above": {"amount": condition, "currency": "GBP"}}}, typ="assurance+jwt")
    ident = crypto.sign_jwt("northgate", {"iss": "sandbox-customer-org", "typ": "agent_identity", "sandbox": True, "sub": "sandbox-agent", "passport_id": pid, "iat": crypto.now_ts(),
                                          "model": {"model_id": mid, "version": _v(f, "model", "version")}, "agent": {"name": "sandbox agent", "agent_id": "sandbox-agent"}, "cnf": {"jwk": agent_jwk}}, typ="agent-identity+jwt")
    mandate = crypto.sign_jwt("northgate_officer", {"iss": "sandbox-officer", "typ": "mandate", "sandbox": True, "passport_id": pid, "valid_until": valid_until, "iat": crypto.now_ts(),
                                                    "authorization_details": [{"type": "payment_initiation", "actions": list(pol["action_types"]), "currency": pol["currency"], "supplier_allowlist": [SANDBOX_PAYEE],
                                                                               "per_payment_limit": {"amount": float(pol["per_payment_ceiling_gbp"]), "currency": pol["currency"]},
                                                                               "monthly_limit_per_account": {"amount": float(pol["monthly_per_account_ceiling_gbp"]), "currency": pol["currency"], "window": pol["monthly_window"]}}]}, typ="mandate+jwt")
    return {"passport_id": pid, "assurance": assurance, "agent_identity": ident, "mandate": mandate}


def step_sandbox(a: dict, tests: list[dict], condition: float) -> list[dict]:
    """Same code path as the bank: rules.verify_action over a sandbox passport. PASS = refused or escalated as expected."""
    agent_priv, agent_pub = crypto.generate_keypair()
    agent_jwk = crypto.public_jwk(agent_pub)
    rogue_priv, _ = crypto.generate_keypair()
    out = []
    for t in tests:
        env = _sandbox_envelope(a, condition, t["variant"] == "expired", agent_priv, agent_jwk)
        req = {"passport_id": env["passport_id"], "action_type": "pay_invoice", "currency": "GBP", "invoice_ref": f"SANDBOX-{t['id']}", "nonce": crypto.new_nonce(), **t["instruction"]}
        key = rogue_priv if t["variant"] == "rogue" else agent_priv
        req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
        res = rules.verify_action(env, "active", req, ledger_total=0.0, model_status="approved")
        out.append({**t, "decision": res["decision"], "rule": res["rule"], "code": res["code"], "reason": res["reason"], "pass": res["decision"] == t["expect"] and res["rule"] == t["expect_rule"]})
    return out


def step_recommendation(a: dict, rule_map: dict, sandbox: list[dict], condition: float) -> dict:
    flagged, uncovered = rule_map["flagged"], rule_map["uncovered"]
    failed = [s["id"] for s in sandbox if not s["pass"]]
    verdict = "REFER" if (failed or uncovered or flagged) else "APPROVE WITH CONDITIONS"
    pol = rules.pack()["policy"]
    reasons = [
        f"{len(rule_map['rules']) - len(flagged)} of {len(rule_map['rules'])} model-register rules satisfied by cited evidence" + (f"; flagged {', '.join(flagged)}" if flagged else ""),
        f"{sum(1 for s in sandbox if s['pass'])} of {len(sandbox)} adversarial tests refused or escalated by the bank engine as expected" + (f"; unexpected {', '.join(failed)}" if failed else ""),
        f"conditions to attach on approval: per payment ≤ £{pol['per_payment_ceiling_gbp']:,.0f}; per account in 30 days ≤ £{pol['monthly_per_account_ceiling_gbp']:,.0f}; expiry ≤ {pol['max_validity']}; actions {', '.join(pol['action_types'])}; hold above £{condition:,.0f}",
        "the model company answers only for its documentation; each customer answers for the mandate it signs",
    ]
    note, mode = extraction.draft_file_note(a["ref"], a["fields"], a.get("checks") or [])
    return {"verdict": verdict, "label": "AI recommendation — human decision required", "condition": {"human_confirm_above": condition}, "ceilings": ceilings(), "reasons": reasons, "narrative": note, "narrative_mode": mode,
            "options": ["APPROVE", "APPROVE WITH CONDITIONS", "REFER"], "decides": False}


def run(a: dict, condition: float | None = None) -> dict:
    if not a.get("fields") or not a.get("checks"):
        raise ValueError("registration not submitted")
    thr = float(condition if condition is not None else rules.pack()["policy"]["human_confirm_above_gbp"])
    evidence = step_evidence(a)
    rule_map = step_rule_map(a)
    tests = step_tests(a, thr)
    sandbox = step_sandbox(a, tests, thr)
    rec = step_recommendation(a, rule_map, sandbox, thr)
    return {"assistant": "Standards Review Assistant (KYA standards evaluation tool)", "rule_pack": rules.pack()["id"], "condition": thr, "model_id": model_id_for(a),
            "steps": [
                {"n": 1, "id": "evidence", "title": "Evidence read", "data": evidence},
                {"n": 2, "id": "rule_map", "title": "Standards rule map", "data": rule_map},
                {"n": 3, "id": "tests", "title": "Adversarial tests any future passport on this model must survive", "data": tests},
                {"n": 4, "id": "sandbox", "title": "Sandbox run (real bank engine, hypothetical passport)", "data": sandbox},
                {"n": 5, "id": "recommendation", "title": "Recommendation", "data": rec},
                {"n": 6, "id": "signoff", "title": "Human sign-off: approve the model, set ceilings and the condition", "data": {"who": config.OFFICER, "how": "POST /api/applications/{id}/decision", "note": "only this step signs the model approval and enters it in the model registry"}},
            ]}
