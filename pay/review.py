"""Standards Review Assistant (the brief's KYA standards evaluation tool).

Six visible steps the regulator's copilot runs when an officer opens a submitted application. Every step is
deterministic over structured facts; the sandbox run uses the same rules.verify_action the bank uses. The
model may phrase a summary (through extraction.draft_file_note, verdict vocabulary rejected); it never scores,
decides or signs. Only the officer's own POST /decision applies the authority signature.

  1 EVIDENCE READ           what the model company registered, what customers will do with it, what the authority is asked to certify
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
    "M.1": ("company", "companies_house_number"), "M.2": ("attestation", "declaration_ref"), "M.3": ("model", "documentation_ref"),
    "M.4": ("model", "model_version"), "M.5": ("intended_use", "action_type"), "M.6": ("model", "model_id"),
}


def _v(fields, *path):
    return rules._v(fields, *path)


def step_evidence(a: dict) -> dict:
    f = a["fields"]
    pol = rules.pack()["policy"]
    return {
        "company_registers": {"legal_name": _v(f, "company", "legal_name"), "companies_house": _v(f, "company", "companies_house_number"),
                              "model": f"{_v(f, 'model', 'model_name')} ({_v(f, 'model', 'model_id')}, release {_v(f, 'model', 'release')})",
                              "foundation_model": f"{_v(f, 'model', 'model_provider')} · {_v(f, 'model', 'model_version')}",
                              "benchmarks": _v(f, "model", "benchmarks"), "training_type": _v(f, "model", "training_type"), "documentation": _v(f, "model", "documentation_ref"),
                              "attested_by": f"{_v(f, 'attestation', 'name')}, {_v(f, 'attestation', 'role')} ({_v(f, 'attestation', 'declaration_ref')}): documentation accuracy only",
                              "intended_use": f"{_v(f, 'intended_use', 'action_type')}: {_v(f, 'intended_use', 'description')}"},
        "customers_will": {"note": "No customer, no agent, no key at registration. A model becomes an agent when a customer gives it a mandate: the customer creates the agent (own key, proof of possession, configuration hash) and writes and signs its mandate within the policy ceilings."},
        "authority_asked_to_certify": {"model_approval": "company identity, attestation, documentation completeness, pinned version, intended use and register uniqueness verified against records",
                                       "policy_ceilings": f"per payment ≤ £{pol['per_payment_ceiling_gbp']:,.0f}; per account in 30 days ≤ £{pol['monthly_per_account_ceiling_gbp']:,.0f}; expiry ≤ {pol['max_validity']}; actions {', '.join(pol['action_types'])}",
                                       "condition_default": float(pol["human_confirm_above_gbp"])},
        "documents": [], "registration": "fields entered by the model company on the Provider Panel" + (" (prefilled for the demo)" if a.get("extraction_mode") == "prefill" else ""), "extraction_mode": a.get("extraction_mode"),
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


SANDBOX_PAYEE = {"supplier_id": "SANDBOX-1", "name": "Sandbox Supplier Ltd", "account_ref": "60-00-00 00000001"}


def step_tests(a: dict) -> list[dict]:
    """Five adversarial instructions against a sandbox mandate set at the policy ceilings (no real customer is involved)."""
    f = a["fields"]
    pol = rules.pack()["policy"]
    cap = float(pol["per_payment_ceiling_gbp"])
    thr = float(pol["human_confirm_above_gbp"])
    return [
        {"id": "T1", "title": "Payment to a non-mandated supplier", "expect": "DENY", "expect_rule": "R.6", "instruction": {"supplier_name": "Unlisted Courier Ltd", "payee_account_ref": "60-11-22 20202020", "amount": min(cap, 2500.0)}, "variant": "normal"},
        {"id": "T2", "title": f"Amount £1 above the policy ceiling (£{cap:,.0f})", "expect": "DENY", "expect_rule": "R.7", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": cap + 1}, "variant": "normal"},
        {"id": "T3", "title": "Expired passport presented", "expect": "DENY", "expect_rule": "R.2", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": 100.0}, "variant": "expired"},
        {"id": "T4", "title": "Instruction signed with a rogue key", "expect": "DENY", "expect_rule": "R.4", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": 100.0}, "variant": "rogue"},
        {"id": "T5", "title": f"Amount above the supervisor condition (£{thr:,.0f}) but within the ceiling", "expect": "ESCALATE", "expect_rule": "R.9", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": min(cap, thr + 100)}, "variant": "normal"},
    ]


def _sandbox_envelope(a: dict, condition: float, expired: bool, agent_priv: str, agent_jwk: dict) -> dict:
    """A provisional envelope signed by the real keys for a SANDBOX passport that is never entered in the registry.
    The agent does not exist yet at registration, so the sandbox mints an ephemeral agent key for the run."""
    f = a["fields"]
    pol = rules.pack()["policy"]
    pid = f"SANDBOX-{a['ref']}"
    valid_until = (date.today() - timedelta(days=1)).isoformat() if expired else pol["max_validity"]
    ident = crypto.sign_jwt("northgate", {"iss": "sandbox-customer", "typ": "agent_identity", "sandbox": True, "sub": "sandbox-agent", "iat": crypto.now_ts(),
                                          "agent": {"name": "sandbox agent", "agent_id": "sandbox-agent", "model_id": _v(f, "model", "model_id")}, "cnf": {"jwk": agent_jwk}}, typ="agent-identity+jwt")
    assurance = crypto.sign_jwt("authority", {"iss": config.ISSUER, "typ": "assurance", "sandbox": True, "jti": pid, "iat": crypto.now_ts(), "valid_until": valid_until,
                                              "model_ref": {"registration": a["ref"], "model_id": _v(f, "model", "model_id"), "model_name": _v(f, "model", "model_name")}, "agent_id": "sandbox-agent",
                                              "condition": {"human_confirm_above": {"amount": condition, "currency": "GBP"}}, "binds": {"agent_identity_sha256": crypto.sha256_hex(ident)}}, typ="assurance+jwt")
    mandate = crypto.sign_jwt("northgate", {"iss": "sandbox-customer", "typ": "mandate", "sandbox": True, "passport_id": pid, "valid_until": valid_until, "iat": crypto.now_ts(),
                                            "authorization_details": [{"type": "payment_initiation", "actions": list(pol["action_types"]), "currency": pol["currency"],
                                                                       "supplier_allowlist": [SANDBOX_PAYEE],
                                                                       "per_payment_limit": {"amount": float(pol["per_payment_ceiling_gbp"]), "currency": pol["currency"]},
                                                                       "monthly_limit_per_account": {"amount": float(pol["monthly_per_account_ceiling_gbp"]), "currency": pol["currency"], "window": pol["monthly_window"]}}]}, typ="mandate+jwt")
    return {"passport_id": pid, "assurance": assurance, "agent_identity": ident, "mandate": mandate}


def step_sandbox(a: dict, tests: list[dict], condition: float) -> list[dict]:
    """Same code path as the bank: rules.verify_action over a sandbox envelope. PASS = the engine refused or escalated as expected."""
    agent_priv, agent_pub = crypto.generate_keypair()
    agent_jwk = crypto.public_jwk(agent_pub)
    rogue_priv, _ = crypto.generate_keypair()
    out = []
    for t in tests:
        env = _sandbox_envelope(a, condition, t["variant"] == "expired", agent_priv, agent_jwk)
        req = {"passport_id": env["passport_id"], "action_type": "pay_invoice", "currency": "GBP", "invoice_ref": f"SANDBOX-{t['id']}", "nonce": crypto.new_nonce(), **t["instruction"]}
        key = rogue_priv if t["variant"] == "rogue" else agent_priv
        req["agent_signature"] = crypto.sign_bytes(key, rules.request_signing_input(req))
        res = rules.verify_action(env, "active", req, ledger_total=0.0)
        out.append({**t, "decision": res["decision"], "rule": res["rule"], "code": res["code"], "reason": res["reason"], "pass": res["decision"] == t["expect"] and res["rule"] == t["expect_rule"]})
    return out


def step_recommendation(a: dict, rule_map: dict, sandbox: list[dict], condition: float) -> dict:
    flagged, uncovered = rule_map["flagged"], rule_map["uncovered"]
    failed = [s["id"] for s in sandbox if not s["pass"]]
    if failed or uncovered:
        verdict = "REFER"
    elif flagged:
        verdict = "REFER"
    else:
        verdict = "APPROVE WITH CONDITIONS"
    reasons = []
    reasons.append(f"{len(rule_map['rules']) - len(flagged)} of {len(rule_map['rules'])} standards rules satisfied by cited evidence" + (f"; flagged {', '.join(flagged)}" if flagged else ""))
    reasons.append(f"{sum(1 for s in sandbox if s['pass'])} of {len(sandbox)} adversarial tests refused or escalated by the bank engine as expected" + (f"; unexpected {', '.join(failed)}" if failed else ""))
    reasons.append("no agent key at registration: each customer's agent proves possession of its own key when it is created")
    reasons.append(f"condition to attach: hold instructions above £{condition:,.0f} for the customer's authorising officer")
    note, mode = extraction.draft_file_note(a["ref"], a["fields"], a.get("checks") or [])
    return {"verdict": verdict, "label": "AI recommendation — human decision required", "condition": {"human_confirm_above": condition}, "reasons": reasons, "narrative": note, "narrative_mode": mode,
            "options": ["APPROVE", "APPROVE WITH CONDITIONS", "REFER"], "decides": False}


def run(a: dict, condition: float | None = None) -> dict:
    if not a.get("fields") or not a.get("checks"):
        raise ValueError("application not submitted")
    thr = float(condition if condition is not None else (_v(a["fields"], "requested", "human_confirm_above_gbp") or rules.pack()["policy"]["human_confirm_above_gbp"]))
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
