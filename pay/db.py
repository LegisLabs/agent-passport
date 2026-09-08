"""SQLite persistence. Standard library only.

Tables
  registrations  an AI product filed on the register, and the bank's admission decision on it
  passports      the bank's passport list: composite envelope parts + lifecycle status
  payments       the bank's ledger of executed (ALLOWed) instructions, for R.8
  audit          append-only, hash-chained decision log with signed receipts
  violations     the exception log (mutable status, unlike the audit chain)
  kv             misc
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS registrations (
  id INTEGER PRIMARY KEY,
  ref TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL,                 -- draft | registered
  created_at TEXT NOT NULL,
  submitted_at TEXT,
  entry_mode TEXT,                      -- form | prefill
  fields_json TEXT,                     -- what the provider filed (what the checks see)
  checks_json TEXT,                     -- results of the F.* filing checks
  registration_jwt TEXT,                -- receipt signed by the register at filing
  review_json TEXT,                     -- the bank's admission review assistant output
  admission_status TEXT,                -- null | info_requested | admitted | declined | suspended | revoked
  admitted_at TEXT,
  officer TEXT,
  officer_note TEXT,
  condition_json TEXT,                  -- the bank's hold condition set at admission
  file_note TEXT
);
CREATE TABLE IF NOT EXISTS passports (
  passport_id TEXT PRIMARY KEY,
  registration_id INTEGER NOT NULL,
  admission_jwt TEXT NOT NULL,
  admission_json TEXT NOT NULL,
  agent_identity_jwt TEXT NOT NULL,
  agent_identity_json TEXT NOT NULL,
  mandate_proposed_json TEXT NOT NULL,  -- the customer's draft
  mandate_jwt TEXT,                     -- null until the customer signs
  mandate_json TEXT,
  mandate_signed_at TEXT,
  status TEXT NOT NULL,                 -- pending | active | suspended | revoked
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  history_json TEXT NOT NULL,           -- [{ts, from, to, officer, reason}]
  vouch_voucher_id TEXT,
  vouch_mode TEXT,                      -- fixture | live | live-fallback
  vouch_status TEXT,                    -- ACTIVE | REVOKED | null
  investigation TEXT,                   -- null | investigating
  agent_json TEXT                       -- the customer's AI agent: key pair (demo), kid, challenge, pop
);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  passport_id TEXT NOT NULL,
  payee_account_ref TEXT NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL,
  invoice_ref TEXT,
  audit_id INTEGER,
  rail TEXT,                            -- local | vouch | vouch-fallback
  rail_ref TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,                   -- registration | check | admission | agent | mandate | issue | lifecycle | verify | incident | vouch | intent | exception | evidence | system
  subject TEXT,
  entry_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  receipt TEXT
);
CREATE TABLE IF NOT EXISTS violations (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  passport_id TEXT NOT NULL,
  agent_id TEXT,
  rule TEXT NOT NULL,                   -- R.x that refused
  code TEXT NOT NULL,
  instruction_json TEXT NOT NULL,       -- what the AI agent tried (signature stripped)
  evidence_json TEXT,                   -- invoice extraction that produced the instruction, if any
  audit_id INTEGER,
  outcome TEXT NOT NULL,                -- DENY
  status TEXT NOT NULL,                 -- OPEN | INVESTIGATING | RESOLVED
  resolution TEXT                       -- revoked | reinstated | null
);
CREATE TABLE IF NOT EXISTS nonces (
  passport_id TEXT NOT NULL,
  nonce TEXT NOT NULL,
  ts TEXT NOT NULL,
  audit_id INTEGER,
  PRIMARY KEY (passport_id, nonce)
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""
_MIGRATIONS = [
    "ALTER TABLE violations ADD COLUMN failure_class TEXT",   # fraud | agent_error
    "ALTER TABLE passports ADD COLUMN mandate_versions_json TEXT",   # superseded and revoked mandate versions, retained
    "ALTER TABLE passports ADD COLUMN mandate_revoked_at TEXT",
    "ALTER TABLE passports ADD COLUMN first_confirmed_version INTEGER",   # the mandate version whose first payment the customer has confirmed
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init() -> None:
    with tx() as con:
        con.executescript(SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                con.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already there


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def j(s: str | None):
    return json.loads(s) if s else None


def row_to_reg(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("fields_json", "checks_json", "condition_json", "review_json"):
        d[k[:-5]] = j(d.pop(k))
    return d


def row_to_passport(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["admission"] = j(d.pop("admission_json"))
    d["agent_identity"] = j(d.pop("agent_identity_json"))
    d["mandate_proposed"] = j(d.pop("mandate_proposed_json"))
    d["mandate"] = j(d.pop("mandate_json"))
    d["mandate_versions"] = j(d.pop("mandate_versions_json", None)) or []
    d["history"] = j(d.pop("history_json")) or []
    d["agent"] = j(d.pop("agent_json"))
    return d


def row_to_audit(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["entry"] = j(d.pop("entry_json"))
    return d


# ── registrations ──────────────────────────────────────────────────────────
def create_registration(ref: str) -> dict:
    with tx() as con:
        con.execute("INSERT INTO registrations(ref,status,created_at) VALUES(?,?,?)", (ref, "draft", now_iso()))
        return get_registration_by_ref(ref, con)


def get_registration(reg_id: int, con=None) -> dict | None:
    def q(c):
        r = c.execute("SELECT * FROM registrations WHERE id=?", (reg_id,)).fetchone()
        return row_to_reg(r) if r else None
    if con:
        return q(con)
    with tx() as c:
        return q(c)


def get_registration_by_ref(ref: str, con=None) -> dict | None:
    def q(c):
        r = c.execute("SELECT * FROM registrations WHERE ref=?", (ref,)).fetchone()
        return row_to_reg(r) if r else None
    if con:
        return q(con)
    with tx() as c:
        return q(c)


def list_registrations() -> list[dict]:
    with tx() as con:
        return [row_to_reg(r) for r in con.execute("SELECT * FROM registrations ORDER BY id DESC")]


def count_registrations() -> int:
    with tx() as con:
        return con.execute("SELECT COUNT(*) FROM registrations").fetchone()[0]


def update_registration(reg_id: int, **cols) -> dict:
    sets, vals = [], []
    for k, v in cols.items():
        if k in ("fields", "checks", "condition", "review"):
            k = k + "_json"
            v = json.dumps(v)
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(reg_id)
    with tx() as con:
        con.execute(f"UPDATE registrations SET {', '.join(sets)} WHERE id=?", vals)
        return get_registration(reg_id, con)


# ── passports (the bank's list) ────────────────────────────────────────────
def create_passport(passport_id: str, registration_id: int, admission_jwt: str, admission: dict,
                    agent_identity_jwt: str, agent_identity: dict, mandate_proposed: dict,
                    expires_at: str, officer: str, agent: dict | None = None, status: str = "active") -> dict:
    hist = [{"ts": now_iso(), "from": None, "to": status, "officer": officer, "reason": "AI agent registered; passport pending the customer's mandate" if status == "pending" else "Issued"}]
    with tx() as con:
        con.execute(
            "INSERT INTO passports(passport_id,registration_id,admission_jwt,admission_json,agent_identity_jwt,agent_identity_json,"
            "mandate_proposed_json,status,issued_at,expires_at,history_json,agent_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (passport_id, registration_id, admission_jwt, json.dumps(admission), agent_identity_jwt, json.dumps(agent_identity),
             json.dumps(mandate_proposed), status, now_iso(), expires_at, json.dumps(hist), json.dumps(agent) if agent else None),
        )
        return get_passport(passport_id, con)


def count_passports() -> int:
    with tx() as con:
        return con.execute("SELECT COUNT(*) FROM passports").fetchone()[0]


def passports_for_registration(registration_id: int) -> list[dict]:
    with tx() as con:
        return [row_to_passport(r) for r in con.execute("SELECT * FROM passports WHERE registration_id=? ORDER BY issued_at DESC", (registration_id,))]


def rename_passport(old_id: str, new_id: str) -> None:
    """The agent record becomes the passport when the customer signs: the row keeps its history under the new id."""
    with tx() as con:
        con.execute("UPDATE passports SET passport_id=? WHERE passport_id=?", (new_id, old_id))
        for t in ("payments", "violations"):
            con.execute(f"UPDATE {t} SET passport_id=? WHERE passport_id=?", (new_id, old_id))


def set_passport_agent(passport_id: str, agent: dict) -> dict:
    with tx() as con:
        con.execute("UPDATE passports SET agent_json=? WHERE passport_id=?", (json.dumps(agent), passport_id))
        return get_passport(passport_id, con)


def set_passport_admission(passport_id: str, admission_jwt: str, admission: dict) -> dict:
    with tx() as con:
        con.execute("UPDATE passports SET admission_jwt=?, admission_json=?, issued_at=? WHERE passport_id=?", (admission_jwt, json.dumps(admission), now_iso(), passport_id))
        return get_passport(passport_id, con)


def set_mandate_proposed(passport_id: str, mandate_proposed: dict) -> dict:
    with tx() as con:
        con.execute("UPDATE passports SET mandate_proposed_json=? WHERE passport_id=?", (json.dumps(mandate_proposed), passport_id))
        return get_passport(passport_id, con)


def get_passport(passport_id: str, con=None) -> dict | None:
    def q(c):
        r = c.execute("SELECT * FROM passports WHERE passport_id=?", (passport_id,)).fetchone()
        return row_to_passport(r) if r else None
    if con:
        return q(con)
    with tx() as c:
        return q(c)


def list_passports() -> list[dict]:
    with tx() as con:
        return [row_to_passport(r) for r in con.execute("SELECT * FROM passports ORDER BY issued_at DESC, rowid DESC")]


def set_mandate(passport_id: str, mandate_jwt: str, mandate: dict) -> dict:
    with tx() as con:
        con.execute("UPDATE passports SET mandate_jwt=?, mandate_json=?, mandate_signed_at=? WHERE passport_id=?",
                    (mandate_jwt, json.dumps(mandate), now_iso(), passport_id))
        return get_passport(passport_id, con)


def supersede_mandate(passport_id: str, mandate_jwt: str, mandate: dict) -> dict:
    """A new customer-signed version replaces the current one; the previous version is retained, never deleted."""
    with tx() as con:
        p = get_passport(passport_id, con)
        prev = {"version": (p.get("mandate") or {}).get("version", 1), "jwt": p.get("mandate_jwt"), "mandate": p.get("mandate"), "signed_at": p.get("mandate_signed_at"), "superseded_at": now_iso()}
        con.execute("UPDATE passports SET mandate_jwt=?, mandate_json=?, mandate_signed_at=?, mandate_versions_json=? WHERE passport_id=?",
                    (mandate_jwt, json.dumps(mandate), now_iso(), json.dumps((p.get("mandate_versions") or []) + [prev]), passport_id))
        return get_passport(passport_id, con)


def revoke_mandate(passport_id: str) -> dict:
    """The customer ends its mandate. The signed version stays on record; the verifier no longer sees it."""
    with tx() as con:
        p = get_passport(passport_id, con)
        prev = {"version": (p.get("mandate") or {}).get("version", 1), "jwt": p.get("mandate_jwt"), "mandate": p.get("mandate"), "signed_at": p.get("mandate_signed_at"), "revoked_at": now_iso()}
        con.execute("UPDATE passports SET mandate_revoked_at=?, mandate_versions_json=? WHERE passport_id=?",
                    (now_iso(), json.dumps((p.get("mandate_versions") or []) + [prev]), passport_id))
        return get_passport(passport_id, con)


def set_first_confirmed(passport_id: str, version: int) -> dict:
    """The customer confirmed the first payment under this mandate version; later payments inside it need no person."""
    with tx() as con:
        con.execute("UPDATE passports SET first_confirmed_version=? WHERE passport_id=?", (int(version), passport_id))
        return get_passport(passport_id, con)


def set_passport_status(passport_id: str, status: str, officer: str, reason: str) -> dict:
    with tx() as con:
        p = get_passport(passport_id, con)
        if not p:
            raise KeyError(passport_id)
        hist = p["history"] + [{"ts": now_iso(), "from": p["status"], "to": status, "officer": officer, "reason": reason}]
        con.execute("UPDATE passports SET status=?, history_json=? WHERE passport_id=?", (status, json.dumps(hist), passport_id))
        return get_passport(passport_id, con)


def set_investigation(passport_id: str, state: str | None) -> dict:
    with tx() as con:
        con.execute("UPDATE passports SET investigation=? WHERE passport_id=?", (state, passport_id))
        return get_passport(passport_id, con)


def set_vouch(passport_id: str, voucher_id: str | None, mode: str, status: str | None) -> dict:
    with tx() as con:
        con.execute("UPDATE passports SET vouch_voucher_id=?, vouch_mode=?, vouch_status=? WHERE passport_id=?",
                    (voucher_id, mode, status, passport_id))
        return get_passport(passport_id, con)


# ── payments ledger (the bank's state for R.8) ─────────────────────────────
def ledger_total(passport_id: str, payee_account_ref: str, window_days: int = 30, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=window_days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with tx() as con:
        r = con.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE passport_id=? AND payee_account_ref=? AND ts>=?",
                        (passport_id, payee_account_ref, since)).fetchone()
        return float(r[0])


def ledger_totals(passport_id: str, window_days: int = 30) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with tx() as con:
        rows = con.execute("SELECT payee_account_ref, SUM(amount) AS total, COUNT(*) AS n FROM payments WHERE passport_id=? AND ts>=? GROUP BY payee_account_ref",
                           (passport_id, since)).fetchall()
        return {r["payee_account_ref"]: {"total": float(r["total"]), "count": r["n"]} for r in rows}


def insert_payment(passport_id: str, payee_account_ref: str, amount: float, currency: str, invoice_ref: str | None,
                   audit_id: int | None, rail: str, rail_ref: str | None) -> dict:
    with tx() as con:
        cur = con.execute("INSERT INTO payments(ts,passport_id,payee_account_ref,amount,currency,invoice_ref,audit_id,rail,rail_ref) VALUES(?,?,?,?,?,?,?,?,?)",
                          (now_iso(), passport_id, payee_account_ref, amount, currency, invoice_ref, audit_id, rail, rail_ref))
        return dict(con.execute("SELECT * FROM payments WHERE id=?", (cur.lastrowid,)).fetchone())


def list_payments(passport_id: str | None = None, limit: int = 200) -> list[dict]:
    with tx() as con:
        if passport_id:
            rows = con.execute("SELECT * FROM payments WHERE passport_id=? ORDER BY id DESC LIMIT ?", (passport_id, limit))
        else:
            rows = con.execute("SELECT * FROM payments ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


def daily_count(passport_id: str, window_hours: int = 24) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with tx() as con:
        return con.execute("SELECT COUNT(*) FROM payments WHERE passport_id=? AND ts>=?", (passport_id, since)).fetchone()[0]


def nonce_seen(passport_id: str, nonce: str | None) -> bool:
    if not nonce:
        return False
    with tx() as con:
        return con.execute("SELECT 1 FROM nonces WHERE passport_id=? AND nonce=?", (passport_id, nonce)).fetchone() is not None


def remember_nonce(passport_id: str, nonce: str | None, audit_id: int | None) -> None:
    if not nonce:
        return
    with tx() as con:
        con.execute("INSERT OR IGNORE INTO nonces(passport_id,nonce,ts,audit_id) VALUES(?,?,?,?)", (passport_id, nonce, now_iso(), audit_id))


def count_payments(passport_id: str) -> int:
    with tx() as con:
        return con.execute("SELECT COUNT(*) FROM payments WHERE passport_id=?", (passport_id,)).fetchone()[0]


# ── audit ──────────────────────────────────────────────────────────────────
def last_audit_hash(con) -> str:
    r = con.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    return r["hash"] if r else "genesis"


def insert_audit(kind: str, subject: str | None, entry: dict, prev_hash: str, h: str, receipt: str | None) -> dict:
    with tx() as con:
        cur = con.execute(
            "INSERT INTO audit(ts,kind,subject,entry_json,prev_hash,hash,receipt) VALUES(?,?,?,?,?,?,?)",
            (entry["ts"], kind, subject, json.dumps(entry), prev_hash, h, receipt),
        )
        r = con.execute("SELECT * FROM audit WHERE id=?", (cur.lastrowid,)).fetchone()
        return row_to_audit(r)


def list_audit(limit: int = 500, kind: str | None = None, subject: str | None = None) -> list[dict]:
    with tx() as con:
        q, args = "SELECT * FROM audit", []
        where = []
        if kind:
            where.append("kind=?"); args.append(kind)
        if subject:
            where.append("subject=?"); args.append(subject)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
        return [row_to_audit(r) for r in con.execute(q, args)]


def get_audit(audit_id: int) -> dict | None:
    with tx() as con:
        r = con.execute("SELECT * FROM audit WHERE id=?", (audit_id,)).fetchone()
        return row_to_audit(r) if r else None


def denies_since_last_incident(passport_id: str) -> int:
    """DENY verifications for this passport after the most recent incident row."""
    with tx() as con:
        last = con.execute("SELECT id FROM audit WHERE kind='incident' AND subject=? ORDER BY id DESC LIMIT 1", (passport_id,)).fetchone()
        after = last["id"] if last else 0
        rows = con.execute("SELECT entry_json FROM audit WHERE kind='verify' AND subject=? AND id>?", (passport_id, after)).fetchall()
        return sum(1 for r in rows if (lambda e: e.get("failed_check") or e.get("decision") == "DENY")(json.loads(r["entry_json"])))


# ── violations (the exception log; mutable status, unlike the audit chain) ──
def row_to_violation(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["instruction"] = j(d.pop("instruction_json"))
    d["evidence"] = j(d.pop("evidence_json"))
    return d


def insert_violation(passport_id: str, agent_id: str | None, rule: str, code: str, instruction: dict, evidence: dict | None, audit_id: int | None, failure_class: str | None = None) -> dict:
    inst = {k: v for k, v in instruction.items() if k != "agent_signature"}
    with tx() as con:
        cur = con.execute("INSERT INTO violations(ts,passport_id,agent_id,rule,code,instruction_json,evidence_json,audit_id,outcome,status,failure_class) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (now_iso(), passport_id, agent_id, rule, code, json.dumps(inst), json.dumps(evidence) if evidence else None, audit_id, "DENY", "OPEN", failure_class))
        return row_to_violation(con.execute("SELECT * FROM violations WHERE id=?", (cur.lastrowid,)).fetchone())


def list_violations(passport_id: str | None = None, limit: int = 200) -> list[dict]:
    with tx() as con:
        if passport_id:
            rows = con.execute("SELECT * FROM violations WHERE passport_id=? ORDER BY id DESC LIMIT ?", (passport_id, limit))
        else:
            rows = con.execute("SELECT * FROM violations ORDER BY id DESC LIMIT ?", (limit,))
        return [row_to_violation(r) for r in rows]


def get_violation(vid: int) -> dict | None:
    with tx() as con:
        r = con.execute("SELECT * FROM violations WHERE id=?", (vid,)).fetchone()
        return row_to_violation(r) if r else None


def set_violation_status(passport_id: str, status: str, resolution: str | None = None, only_status: tuple[str, ...] = ("OPEN", "INVESTIGATING")) -> int:
    with tx() as con:
        q = f"UPDATE violations SET status=?, resolution=COALESCE(?, resolution) WHERE passport_id=? AND status IN ({','.join('?' * len(only_status))})"
        return con.execute(q, (status, resolution, passport_id, *only_status)).rowcount


def set_violation_status_by_id(vid: int, status: str, resolution: str | None = None) -> int:
    with tx() as con:
        return con.execute("UPDATE violations SET status=?, resolution=COALESCE(?, resolution) WHERE id=?", (status, resolution, vid)).rowcount


def pattern_alerts(count: int, window_hours: int) -> list[dict]:
    """Passports with >= count violations of the same rule inside the window. One alert per (passport, rule)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat(timespec="seconds").replace("+00:00", "Z")
    with tx() as con:
        rows = con.execute("SELECT passport_id, rule, code, COUNT(*) AS n, MAX(ts) AS last_ts, MIN(ts) AS first_ts FROM violations WHERE ts>=? GROUP BY passport_id, rule HAVING n>=? ORDER BY last_ts DESC",
                           (since, count)).fetchall()
        return [dict(r) for r in rows]


def reset_all() -> None:
    with tx() as con:
        for t in ("registrations", "passports", "payments", "audit", "violations", "nonces", "kv"):
            con.execute(f"DELETE FROM {t}")
