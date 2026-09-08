"""Synthetic seed data and the expert console beats."""
from __future__ import annotations

from . import config


def register_entries() -> list[dict]:
    """Entries already on the register (synthetic), shown on the Provider surface and in the bank's register view."""
    import json
    return json.loads((config.FIXTURES_DIR / "register.json").read_text())["products"]


FENWICK = "60-11-22 10101010"
ASHBY = "30-98-76 22334455"
COASTLINE = "20-13-57 77665544"

# The accounts-payable task queue: what the AI agent was asked to do, known BEFORE it opens the document. The grounds
# declaration is built from this and the mandate (the registered account for that supplier), never from the document.
INVOICE_TASKS = {
    "INV-9001-clean": {"invoice_ref": "INV-9001", "supplier_name": "Fenwick Timber Ltd"},
    "INV-9001-poisoned": {"invoice_ref": "INV-9001", "supplier_name": "Fenwick Timber Ltd"},
}

# The expert console beats, in demo order. `signer` = agent (bound key) or rogue (copied passport).
# `repeat` fires the same instruction up to N times and stops at the first non-ALLOW.
BEATS = [
    {"n": 1, "label": "Pay Fenwick Timber Ltd · invoice FT-1042 · £3,200", "hint": "on the allowlist, within every limit",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "invoice_ref": "FT-1042", "signer": "agent", "expect": "ALLOW"},
    {"n": 2, "label": "Pay Fenwick Timber Ltd · invoice FT-1043 · £2,750 · account 60-11-22 99887766", "hint": "same supplier name, different account: invoice redirection fraud",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 99887766", "amount": 2750, "invoice_ref": "FT-1043", "signer": "agent", "expect": "DENY R.6"},
    {"n": 3, "label": "Pay Ashby Ironmongery Ltd · invoice AI-3310 · £12,000", "hint": "above the £10,000 per-payment limit",
     "action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": ASHBY, "amount": 12000, "invoice_ref": "AI-3310", "signer": "agent", "expect": "DENY R.7"},
    {"n": 4, "label": "Pay Coastline Glass Ltd · invoice CG-0871 · £5,600", "hint": "within the limit, above the bank's £5,000 hold condition",
     "action_type": "pay_invoice", "supplier_name": "Coastline Glass Ltd", "payee_account_ref": COASTLINE, "amount": 5600, "invoice_ref": "CG-0871", "signer": "agent", "expect": "ESCALATE R.9"},
    {"n": 5, "label": "Pay Fenwick Timber Ltd · £4,900 · repeated", "hint": "each one is allowed until the 30-day total for that account passes £20,000",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 4900, "invoice_ref": "FT-1044", "signer": "agent", "repeat": 5, "expect": "ALLOW… then DENY R.8"},
    {"n": 6, "label": "Pay Fenwick Timber Ltd · invoice FT-1045 · £1,150 · signed with a different key", "hint": "a copied passport presented by something that does not hold the AI agent's key",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 1150, "invoice_ref": "FT-1045", "signer": "rogue", "expect": "DENY R.4"},
    {"n": 7, "label": "Refund Fenwick Timber Ltd · £3,200", "hint": "a known payee, but an action the mandate never granted",
     "action_type": "refund", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "invoice_ref": "FT-1042", "signer": "agent", "expect": "DENY R.6"},
    {"n": 8, "label": "Pay Ashby Ironmongery Ltd · invoice AI-3311 · £900", "hint": "lifecycle probe: run it after the bank suspends, reinstates or revokes the passport in the Bank console",
     "action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": ASHBY, "amount": 900, "invoice_ref": "AI-3311", "signer": "agent", "expect": "ALLOW · DENY R.2 after suspend or revoke"},
    {"n": 9, "label": "Pay Fenwick Timber Ltd · invoice FT-1046 · $3,200 USD", "hint": "the mandate operates in GBP; any other currency is refused, so there is no silent foreign-exchange exposure",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "currency": "USD", "invoice_ref": "FT-1046", "signer": "agent", "expect": "DENY R.6 currency"},
    {"n": 10, "label": "Replay the previous instruction, byte for byte", "hint": "a genuine signature presented twice: the nonce was spent the first time",
     "replay": True, "action_type": "pay_invoice", "supplier_name": "(the last instruction)", "payee_account_ref": "", "amount": 0, "signer": "agent", "expect": "DENY R.4 replay"},
]


# Chain beats (shown only when the delegation chain is on). The orchestrator delegates a
# narrowed scope to the execution agent, which signs the instruction. S_action ⊆ S_1 ⊆ S_0.
CHAIN_BEATS = [
    {"n": 1, "label": "Orchestrator delegates Fenwick Timber Ltd · ceiling £4,000 · execution agent pays £3,200", "hint": "a valid chain: delegation narrows the £10,000 root, the action sits inside it",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "invoice_ref": "FT-2001", "signer": "agent", "delegate_amount": 4000, "expect": "ALLOW · C.a C.b C.c ✓"},
    {"n": 2, "label": "Same £4,000 delegation · execution agent attempts £4,500", "hint": "the action steps outside the narrowest scope",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 4500, "invoice_ref": "FT-2002", "signer": "agent", "delegate_amount": 4000, "expect": "DENY C.c"},
    {"n": 3, "label": "Orchestrator delegates a £12,000 ceiling (root is £10,000) · execution agent pays £3,200", "hint": "a delegation that expands scope is refused before the action is even looked at",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "invoice_ref": "FT-2003", "signer": "agent", "delegate_amount": 12000, "expect": "DENY C.b"},
    {"n": 4, "label": "Orchestrator delegates account 60-11-22 99887766 (not on the mandate) · £2,500", "hint": "the poisoned-invoice chain: the orchestrator narrows to a beneficiary the customer never signed for",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 99887766", "amount": 2500, "invoice_ref": "INV-9001", "signer": "agent", "delegate_amount": 4000, "expect": "DENY C.b"},
]
