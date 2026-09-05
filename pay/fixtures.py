"""Synthetic seed data and the bank console beats."""
from __future__ import annotations

from . import config


def evidence_pack() -> list[dict]:
    docs = []
    for p in sorted((config.FIXTURES_DIR / "documents").glob("*.txt")):
        docs.append({"name": p.name, "text": p.read_text()})
    return docs


FENWICK = "60-11-22 44556677"
ASHBY = "30-98-76 22334455"
COASTLINE = "20-13-57 99887766"

# The bank console beats, in demo order. `signer` = agent (bound key) or rogue (copied passport).
# `repeat` fires the same instruction up to N times and stops at the first non-ALLOW.
BEATS = [
    {"n": 1, "label": "Pay Fenwick Timber Ltd · invoice FT-1042 · £3,200", "hint": "on the allowlist, within every limit",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "invoice_ref": "FT-1042", "signer": "agent", "expect": "ALLOW"},
    {"n": 2, "label": "Pay Fenwick Timber Ltd · invoice FT-1043 · £2,750 · account 60-11-22 10101010", "hint": "same supplier name, different account: invoice redirection fraud",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": "60-11-22 10101010", "amount": 2750, "invoice_ref": "FT-1043", "signer": "agent", "expect": "DENY R.6"},
    {"n": 3, "label": "Pay Ashby Ironmongery Ltd · invoice AI-3310 · £11,400", "hint": "above the £10,000 per-payment cap",
     "action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": ASHBY, "amount": 11400, "invoice_ref": "AI-3310", "signer": "agent", "expect": "DENY R.7"},
    {"n": 4, "label": "Pay Coastline Glass Ltd · invoice CG-0871 · £5,600", "hint": "within the cap, above the supervisor's £5,000 condition",
     "action_type": "pay_invoice", "supplier_name": "Coastline Glass Ltd", "payee_account_ref": COASTLINE, "amount": 5600, "invoice_ref": "CG-0871", "signer": "agent", "expect": "ESCALATE R.9"},
    {"n": 5, "label": "Pay Fenwick Timber Ltd · £4,900 · repeated", "hint": "each one is allowed until the 30-day total for that account passes £20,000",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 4900, "invoice_ref": "FT-1044", "signer": "agent", "repeat": 5, "expect": "ALLOW… then DENY R.8"},
    {"n": 6, "label": "Pay Fenwick Timber Ltd · invoice FT-1045 · £1,150 · signed with a different key", "hint": "a copied passport presented by something that does not hold the agent's key",
     "action_type": "pay_invoice", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 1150, "invoice_ref": "FT-1045", "signer": "rogue", "expect": "DENY R.4"},
    {"n": 7, "label": "Refund Fenwick Timber Ltd · £3,200", "hint": "a known payee, but an action the mandate never granted",
     "action_type": "refund", "supplier_name": "Fenwick Timber Ltd", "payee_account_ref": FENWICK, "amount": 3200, "invoice_ref": "FT-1042", "signer": "agent", "expect": "DENY R.6"},
    {"n": 8, "label": "Pay Ashby Ironmongery Ltd · invoice AI-3311 · £900", "hint": "lifecycle probe: run it after the officer suspends, reinstates or revokes in Review & issue",
     "action_type": "pay_invoice", "supplier_name": "Ashby Ironmongery Ltd", "payee_account_ref": ASHBY, "amount": 900, "invoice_ref": "AI-3311", "signer": "agent", "expect": "ALLOW · DENY R.2 after suspend or revoke"},
]
