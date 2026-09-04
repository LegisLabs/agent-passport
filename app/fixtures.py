"""Synthetic seed data and the demo beats."""
from __future__ import annotations

from . import config


def evidence_pack() -> list[dict]:
    docs = []
    for p in sorted((config.FIXTURES_DIR / "documents").glob("*.txt")):
        docs.append({"name": p.name, "text": p.read_text()})
    return docs


# The seven console beats. `signer` = agent (bound key) or rogue (stolen passport).
BEATS = [
    {"n": 1, "label": "Submit SA100 · Maya Okafor · 2025/26 · tax due £2,100", "action": "submit_sa100", "utr": "1234567890", "tax_year": "2025/26", "tax_due": 2100, "signer": "agent", "expect": "ALLOW"},
    {"n": 2, "label": "Submit SA100 · Daniel Reyes · 2025/26 · tax due £14,800", "action": "submit_sa100", "utr": "2345678901", "tax_year": "2025/26", "tax_due": 14800, "signer": "agent", "expect": "ESCALATE R.6"},
    {"n": 3, "label": "Amend SA100 · Maya Okafor · 2025/26", "action": "amend_sa100", "utr": "1234567890", "tax_year": "2025/26", "tax_due": 2100, "signer": "agent", "expect": "DENY R.4"},
    {"n": 4, "label": "Submit SA100 · UTR 9988776655 (not this firm's client)", "action": "submit_sa100", "utr": "9988776655", "tax_year": "2025/26", "tax_due": 900, "signer": "agent", "expect": "DENY R.5"},
    {"n": 5, "label": "Submit SA100 · Maya Okafor · tax year 2024/25", "action": "submit_sa100", "utr": "1234567890", "tax_year": "2024/25", "tax_due": 2100, "signer": "agent", "expect": "DENY R.4"},
    {"n": 6, "label": "Submit SA100 · Maya Okafor · signed with a different key (copied passport)", "action": "submit_sa100", "utr": "1234567890", "tax_year": "2025/26", "tax_due": 2100, "signer": "rogue", "expect": "DENY R.3"},
    {"n": 7, "label": "Submit SA100 · Priya Nair (handshake still pending)", "action": "submit_sa100", "utr": "3456789012", "tax_year": "2025/26", "tax_due": 1200, "signer": "agent", "expect": "DENY R.5"},
]
