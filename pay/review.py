"""Admission review assistant: the bank's own tool for deciding whether to admit a registered AI product.

Six visible steps the bank's payments risk officer runs when a registration is opened. Every step is
deterministic over structured facts; the sandbox run uses the same rules.verify_action the bank uses at
payment time. The model may phrase a summary (through extraction.draft_file_note, verdict vocabulary
rejected); it never scores, decides or signs. Only the officer's own POST /admission applies the bank's key.

  1 FILING READ             what the provider filed on the register, what the bank is being asked to admit
  2 REQUIREMENT MAP         each filing check mapped to the evidence that satisfies it; uncovered items flagged
  3 ADVERSARIAL TESTS       five test instructions specific to this product
  4 SANDBOX RUN             each test through the real R.1 to R.9 engine against a provisional, sandbox-signed envelope
  5 RECOMMENDATION          ADMIT WITH CONDITIONS / REFER, reasoning drawn from 2 to 4, labelled "recommendation, the officer decides"
  6 OFFICER DECISION        the bank's decision; nothing here admits anything
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config, crypto, extraction, rules

RULE_EVIDENCE = {
    "F.1": ("company", "companies_house_number"), "F.2": ("principal", "declaration_ref"), "F.3": ("insurance", "policy_ref"),
    "F.4": ("product", "model_version"), "F.5": ("assurance_evidence", "reference"), "F.6": ("product", "product_id"), "F.7": ("data_protection", "ico_registration")}


def _v(fields, *path):
    return rules._v(fields, *path)


def step_filing(a: dict) -> dict:
    f = a["fields"]
    pol = rules.pack()["policy"]
    ae = f.get("assurance_evidence", {})
    return {
        "provider_filed": {"legal_name": _v(f, "company", "legal_name"), "companies_house": _v(f, "company", "companies_house_number"),
                           "accountable_principal": f"{_v(f, 'principal', 'name')}, {_v(f, 'principal', 'role')} ({_v(f, 'principal', 'declaration_ref')})",
                           "insurance": f"{_v(f, 'insurance', 'insurer')} {_v(f, 'insurance', 'policy_ref')}, cover £{float(_v(f, 'insurance', 'cover_gbp') or 0):,.0f} to {_v(f, 'insurance', 'expires')}",
                           "product": f"{_v(f, 'product', 'product_name')} ({_v(f, 'product', 'product_id')}, release {_v(f, 'product', 'release')})",
                           "foundation_model": f"{_v(f, 'product', 'model_provider')} · {_v(f, 'product', 'model_version')}",
                           "documentation": _v(f, "product", "documentation_url"),
                           "assurance_level": rules.assurance_level(_v(ae, "level"))["label"] + " (declared by the provider with the evidence; the register does not grade it)",
                           "independent_assurance_evidence": f"{_v(ae, 'issuer')} {_v(ae, 'reference')}, {_v(ae, 'date')}, use case {_v(ae, 'use_case')}: {_v(ae, 'summary')}",
                           "intended_use": f"{rules.payment_intent(_v(f, 'intended_use', 'payment_intent'))['label']}: {_v(f, 'intended_use', 'description')}",
                           "data_protection": f"UK GDPR and DPA 2018 compliance declared: {_v(f, 'data_protection', 'uk_gdpr_compliant')}; ICO {_v(f, 'data_protection', 'ico_registration')}; personal data retained {rules.retention_label(_v(f, 'data_protection', 'retention_period')).lower()}"},
        "register_says": {"note": "The register records identity and accountability. It does not certify that the product is good; it guarantees that someone is accountable when it is bad. The quality judgement is the bank's."},
        "bank_decides": {"admission": "whether customers of this bank may delegate payments to this product, and under what ceilings and hold condition",
                         "ceilings": f"per payment ≤ £{pol['per_payment_ceiling_gbp']:,.0f}; per account in 30 days ≤ £{pol['monthly_per_account_ceiling_gbp']:,.0f}; up to {pol['velocity_ceiling_per_day']} payments a day; expiry ≤ {pol['max_validity']}; actions {', '.join(pol['action_types'])}; scaled by assurance level (self-declared ×0.25, independently verified ×0.5, independently audited ×1)",
                         "minimum_assurance_level": rules.assurance_level(pol["min_assurance_level_for_admission"])["label"],
                         "hold_above_default": float(pol["hold_above_gbp"])},
        "registration": "fields filed by the provider on the register" + (" (prefilled for the demo)" if a.get("entry_mode") == "prefill" else ""), "entry_mode": a.get("entry_mode"),
    }


def step_requirement_map(a: dict) -> dict:
    checks = {c["id"]: c for c in a.get("checks") or []}
    f = a["fields"]
    rows = []
    for r in rules.pack()["registration_rules"]:
        c = checks.get(r["id"])
        path = RULE_EVIDENCE.get(r["id"])
        fact = f.get(path[0], {}).get(path[1]) if path else None
        ev = {"value": fact.get("value"), "source_doc": fact.get("source_doc"), "quote": fact.get("quote")} if isinstance(fact, dict) else None
        rows.append({"id": r["id"], "title": r["title"], "status": r["status"], "source": r["source"], "result": c["result"] if c else "not run", "detail": c["detail"] if c else "", "evidence": ev,
                     "covered": bool(ev and ev.get("value") not in (None, "")) and bool(c)})
    return {"rule_pack": rules.pack()["id"], "rules": rows, "uncovered": [r["id"] for r in rows if not r["covered"]], "flagged": [r["id"] for r in rows if r["result"] == "flag"]}


SANDBOX_PAYEE = {"supplier_id": "SANDBOX-1", "name": "Sandbox Supplier Ltd", "account_ref": "60-00-00 00000001"}


def step_tests(a: dict) -> list[dict]:
    """Five adversarial instructions against a sandbox mandate set at the admission ceilings (no real customer is involved)."""
    pol = rules.pack()["policy"]
    cap = float(pol["per_payment_ceiling_gbp"])
    thr = float(pol["hold_above_gbp"])
    return [
        {"id": "T1", "title": "Payment to a non-mandated supplier", "expect": "ESCALATE", "expect_rule": "R.6", "instruction": {"supplier_name": "Unlisted Courier Ltd", "payee_account_ref": "60-11-22 20202020", "amount": min(cap, 2500.0)}, "variant": "normal"},
        {"id": "T2", "title": f"Amount £1 above the admission ceiling (£{cap:,.0f})", "expect": "ESCALATE", "expect_rule": "R.7", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": cap + 1}, "variant": "normal"},
        {"id": "T3", "title": "Expired passport presented", "expect": "ESCALATE", "expect_rule": "R.2", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": 100.0}, "variant": "expired"},
        {"id": "T4", "title": "Instruction signed with a rogue key", "expect": "ESCALATE", "expect_rule": "R.4", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": 100.0}, "variant": "rogue"},
        {"id": "T5", "title": f"Amount above the hold condition (£{thr:,.0f}) but within the ceiling", "expect": "ESCALATE", "expect_rule": "R.9", "instruction": {"supplier_name": SANDBOX_PAYEE["name"], "payee_account_ref": SANDBOX_PAYEE["account_ref"], "amount": min(cap, thr + 100)}, "variant": "normal"},
    ]


def _sandbox_envelope(a: dict, condition: float, expired: bool, agent_priv: str, agent_jwk: dict) -> dict:
    """A provisional envelope signed by the real keys for a SANDBOX passport that is never entered on the bank's list.
    The AI agent does not exist yet at admission, so the sandbox mints an ephemeral agent key for the run."""
    f = a["fields"]
    pol = rules.pack()["policy"]
    pid = f"SANDBOX-{a['ref']}"
    valid_until = (date.today() - timedelta(days=1)).isoformat() if expired else pol["max_validity"]
    ident = crypto.sign_jwt("northgate", {"iss": "sandbox-customer", "typ": "agent_identity", "sandbox": True, "sub": "sandbox-agent", "iat": crypto.now_ts(),
                                          "agent": {"name": "sandbox agent", "agent_id": "sandbox-agent", "product_id": _v(f, "product", "product_id")}, "cnf": {"jwk": agent_jwk}}, typ="agent-identity+jwt")
    admission = crypto.sign_jwt("bank", {"iss": config.BANK_ID, "typ": "admission", "sandbox": True, "jti": pid, "iat": crypto.now_ts(), "valid_until": valid_until,
                                         "product_ref": {"registration": a["ref"], "product_id": _v(f, "product", "product_id"), "product_name": _v(f, "product", "product_name")}, "agent_id": "sandbox-agent",
                                         "condition": {"hold_above": {"amount": condition, "currency": "GBP"}}, "binds": {"agent_identity_sha256": crypto.sha256_hex(ident)}}, typ="admission+jwt")
    mandate = crypto.sign_jwt("northgate", {"iss": "sandbox-customer", "typ": "mandate", "sandbox": True, "passport_id": pid, "valid_until": valid_until, "iat": crypto.now_ts(),
                                            "authorization_details": [{"type": "payment_initiation", "actions": list(pol["action_types"]), "currency": pol["currency"],
                                                                       "supplier_allowlist": [SANDBOX_PAYEE],
                                                                       "per_payment_limit": {"amount": float(pol["per_payment_ceiling_gbp"]), "currency": pol["currency"]},
                                                                       "monthly_limit_per_account": {"amount": float(pol["monthly_per_account_ceiling_gbp"]), "currency": pol["currency"], "window": pol["monthly_window"]}}]}, typ="mandate+jwt")
    return {"passport_id": pid, "admission": admission, "agent_identity": ident, "mandate": mandate}


def step_sandbox(a: dict, tests: list[dict], condition: float) -> list[dict]:
    """Same code path as the bank at payment time: rules.verify_action over a sandbox envelope. PASS = the engine refused or escalated as expected."""
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
    verdict = "REFER" if (failed or uncovered or flagged) else "ADMIT WITH CONDITIONS"
    reasons = [
        f"{len(rule_map['rules']) - len(flagged)} of {len(rule_map['rules'])} filing checks satisfied by cited evidence" + (f"; flagged {', '.join(flagged)}" if flagged else ""),
        f"{sum(1 for s in sandbox if s['pass'])} of {len(sandbox)} adversarial tests held for review by the bank engine as expected" + (f"; unexpected {', '.join(failed)}" if failed else ""),
        f"Independent Assurance Evidence at level {rules.assurance_level(_v(a['fields'], 'assurance_evidence', 'level'))['label'].lower()} for the registered use case; the bank assesses it against its minimum requirements, the register does not",
        "no AI agent key at admission: each customer's agent proves possession of its own key when it is created",
        f"condition to attach: hold instructions above £{condition:,.0f} for the customer's named approver",
    ]
    note, mode = extraction.draft_file_note(a["ref"], a["fields"], a.get("checks") or [])
    return {"verdict": verdict, "label": "Recommendation. The officer decides.", "condition": {"hold_above": condition}, "reasons": reasons, "narrative": note, "narrative_mode": mode,
            "options": ["ADMIT", "ADMIT WITH CONDITIONS", "REFER"], "decides": False}


def run(a: dict, condition: float | None = None) -> dict:
    if not a.get("fields") or not a.get("checks"):
        raise ValueError("registration not filed")
    thr = float(condition if condition is not None else rules.pack()["policy"]["hold_above_gbp"])
    filing = step_filing(a)
    rule_map = step_requirement_map(a)
    tests = step_tests(a)
    sandbox = step_sandbox(a, tests, thr)
    rec = step_recommendation(a, rule_map, sandbox, thr)
    return {"assistant": "Admission review assistant", "rule_pack": rules.pack()["id"], "condition": thr,
            "steps": [
                {"n": 1, "id": "filing", "title": "Filing read", "data": filing},
                {"n": 2, "id": "rule_map", "title": "Requirement map", "data": rule_map},
                {"n": 3, "id": "tests", "title": "Adversarial test generation", "data": tests},
                {"n": 4, "id": "sandbox", "title": "Sandbox run (the bank's own engine)", "data": sandbox},
                {"n": 5, "id": "recommendation", "title": "Recommendation", "data": rec},
                {"n": 6, "id": "signoff", "title": "Officer decision", "data": {"who": f"{config.BANK_OFFICER}, {config.BANK_TEAM}", "how": "POST /api/registrations/{id}/admission", "note": "only this step signs an admission with the bank's key"}},
            ]}
