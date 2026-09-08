"""Append-only, hash-chained audit log with bank-signed receipts.

hash = sha256(prev_hash + canonical(entry)). Not a blockchain: one writer,
one chain, tamper-evident. Every verification result also gets a receipt:
a JWT signed by the bank over the decision and the chain hash, so the
AI agent, the customer and the bank all hold proof of what was decided and why,
and a supervisor can verify it later without trusting the bank's database.
"""
from __future__ import annotations

from . import crypto, db


def record(kind: str, subject: str | None, entry: dict, receipt_for: dict | None = None) -> dict:
    entry = dict(entry)
    entry["ts"] = db.now_iso()
    with db.tx() as con:
        prev = db.last_audit_hash(con)
    h = crypto.sha256_hex(prev + crypto.canonical(entry))
    receipt = None
    if receipt_for is not None:
        receipt = crypto.sign_jwt("bank", {
            "typ": "agent-passport-receipt",
            "iss": crypto.signer("bank")["kid"],
            "iat": crypto.now_ts(),
            "audit_hash": h,
            "prev_hash": prev,
            **receipt_for,
        }, typ="receipt+jwt")
    return db.insert_audit(kind, subject, entry, prev, h, receipt)


def verify_chain(rows: list[dict]) -> dict:
    """rows in ascending id order. Recomputes every hash."""
    prev = "genesis"
    for r in rows:
        expect = crypto.sha256_hex(prev + crypto.canonical(r["entry"]))
        if r["prev_hash"] != prev or r["hash"] != expect:
            return {"ok": False, "broken_at": r["id"]}
        prev = r["hash"]
    return {"ok": True, "length": len(rows), "head": prev}
