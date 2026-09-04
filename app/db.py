"""SQLite persistence. Small enough to keep on the standard library.

Tables
  applications  the operator's application and everything derived from it
  passports     issued credentials + lifecycle status (the registry)
  audit         append-only, hash-chained decision log with signed receipts
  kv            misc (schema version, demo flags)
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
  id INTEGER PRIMARY KEY,
  ref TEXT UNIQUE NOT NULL,
  status TEXT NOT NULL,                 -- draft | submitted | info_requested | approved | rejected
  created_at TEXT NOT NULL,
  submitted_at TEXT,
  decided_at TEXT,
  extraction_mode TEXT,                 -- gemini | fixture | gemini-fallback
  extraction_json TEXT,                 -- structured facts with provenance
  fields_json TEXT,                     -- reviewed/edited fields (what the rules see)
  documents_json TEXT,                  -- [{name, text}]
  agent_json TEXT,                      -- {agent_id, public_pem, private_pem(demo), jwk, kid, challenge, challenge_sig, pop_verified}
  checks_json TEXT,                     -- results of A.* rules
  officer TEXT,
  officer_note TEXT,
  file_note TEXT
);
CREATE TABLE IF NOT EXISTS passports (
  jti TEXT PRIMARY KEY,
  application_id INTEGER NOT NULL,
  jwt TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,                 -- active | suspended | revoked | expired
  issued_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  history_json TEXT NOT NULL            -- [{ts, from, to, officer, reason}]
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,                   -- application | check | decision | issue | lifecycle | verify
  subject TEXT,
  entry_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL,
  receipt TEXT                          -- authority-signed JWT over {hash, decision...}
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


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


def row_to_app(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("extraction_json", "fields_json", "documents_json", "agent_json", "checks_json"):
        d[k[:-5]] = j(d.pop(k))
    return d


def row_to_passport(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["payload"] = j(d.pop("payload_json"))
    d["history"] = j(d.pop("history_json")) or []
    return d


def row_to_audit(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["entry"] = j(d.pop("entry_json"))
    return d


# ── applications ───────────────────────────────────────────────────────────
def create_application(ref: str, documents: list[dict]) -> dict:
    with tx() as con:
        con.execute(
            "INSERT INTO applications(ref,status,created_at,documents_json) VALUES(?,?,?,?)",
            (ref, "draft", now_iso(), json.dumps(documents)),
        )
        return get_application_by_ref(ref, con)


def get_application(app_id: int, con=None) -> dict | None:
    def q(c):
        r = c.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
        return row_to_app(r) if r else None
    if con:
        return q(con)
    with tx() as c:
        return q(c)


def get_application_by_ref(ref: str, con=None) -> dict | None:
    def q(c):
        r = c.execute("SELECT * FROM applications WHERE ref=?", (ref,)).fetchone()
        return row_to_app(r) if r else None
    if con:
        return q(con)
    with tx() as c:
        return q(c)


def list_applications() -> list[dict]:
    with tx() as con:
        return [row_to_app(r) for r in con.execute("SELECT * FROM applications ORDER BY id DESC")]


def update_application(app_id: int, **cols) -> dict:
    sets, vals = [], []
    for k, v in cols.items():
        if k in ("extraction", "fields", "documents", "agent", "checks"):
            k = k + "_json"
            v = json.dumps(v)
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(app_id)
    with tx() as con:
        con.execute(f"UPDATE applications SET {', '.join(sets)} WHERE id=?", vals)
        return get_application(app_id, con)


# ── passports ──────────────────────────────────────────────────────────────
def create_passport(jti: str, application_id: int, token: str, payload: dict, expires_at: str, officer: str) -> dict:
    hist = [{"ts": now_iso(), "from": None, "to": "active", "officer": officer, "reason": "Issued"}]
    with tx() as con:
        con.execute(
            "INSERT INTO passports(jti,application_id,jwt,payload_json,status,issued_at,expires_at,history_json) VALUES(?,?,?,?,?,?,?,?)",
            (jti, application_id, token, json.dumps(payload), "active", now_iso(), expires_at, json.dumps(hist)),
        )
        return get_passport(jti, con)


def get_passport(jti: str, con=None) -> dict | None:
    def q(c):
        r = c.execute("SELECT * FROM passports WHERE jti=?", (jti,)).fetchone()
        return row_to_passport(r) if r else None
    if con:
        return q(con)
    with tx() as c:
        return q(c)


def list_passports() -> list[dict]:
    with tx() as con:
        return [row_to_passport(r) for r in con.execute("SELECT * FROM passports ORDER BY issued_at DESC")]


def set_passport_status(jti: str, status: str, officer: str, reason: str) -> dict:
    with tx() as con:
        p = get_passport(jti, con)
        if not p:
            raise KeyError(jti)
        hist = p["history"] + [{"ts": now_iso(), "from": p["status"], "to": status, "officer": officer, "reason": reason}]
        con.execute("UPDATE passports SET status=?, history_json=? WHERE jti=?", (status, json.dumps(hist), jti))
        return get_passport(jti, con)


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


def list_audit(limit: int = 500) -> list[dict]:
    with tx() as con:
        return [row_to_audit(r) for r in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]


def get_audit(audit_id: int) -> dict | None:
    with tx() as con:
        r = con.execute("SELECT * FROM audit WHERE id=?", (audit_id,)).fetchone()
        return row_to_audit(r) if r else None


def reset_all() -> None:
    with tx() as con:
        for t in ("applications", "passports", "audit", "kv"):
            con.execute(f"DELETE FROM {t}")
