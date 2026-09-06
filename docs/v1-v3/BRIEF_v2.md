# Agent Passport — Lightweight Demo Build Brief v2

**For:** Claude Code (run the `impeccable` pass on all UI — no AI-slop visuals)
**Target:** `prototype/` in the current repo · deployable to a Linux box behind Caddy with `uvicorn main:app`
**Purpose:** clickable team baseline + demo-day foundation. Small enough to read in 15 minutes.

---

## 1 · Context in five sentences

We are hackathon finalists building **Agent Passport**: a tax authority verifies an accounting firm's autonomous AI filing agent and issues a signed, expiring, revocable credential defining exactly what it may do; the authority's gateway then checks every proposed agent action against it and returns **ALLOW / ESCALATE / DENY with a rule citation**. The passport is a **fourth trust layer** on top of three that already exist in the UK — AML supervision, HMRC agent registration (ASA/ARN, now MMTAR), and per-client authorisation (64-8 / digital handshake) — and must never be presented as replacing them. The regulator owns the rules; a named human signs every issuance; the check sits with the authority, outside the agent, so a hijacked agent cannot ignore the rail refusing it. Everything is assembled from recognised standards (JWT, Ed25519, RFC 9396 authorization_details, status-list revocation) — no invented crypto, and never the word "blockchain". No LLM anywhere in this demo; all checks deterministic.

## 2 · Stack

FastAPI (Python 3.11+), SQLite, Jinja2, vanilla JS. Libraries: `pyjwt[crypto]` (Ed25519 via `cryptography`). No auth, no React, no websockets, no external APIs. Self-seeds on first run. Ed25519 keypair generated at startup into `keys/` (gitignored, `.pem` never committed).

## 3 · What makes v2 different — the passport is now REAL

Unlike a mock, the passport is an actual **Ed25519-signed JWT** (`alg: EdDSA`):

```json
{
  "iss": "uk-tax-authority-demo",
  "jti": "AP-2026-0091",
  "nbf": <now>, "exp": <2027-01-31>,
  "rule_pack_version": "hmrc-rules-2026.09",
  "subject": {
    "agent_id": "fg-filing-agent-01",
    "operator": {"firm": "Fenland & Grey LLP", "arn": "ARN4471220",
                 "aml_supervisor": "ICAEW", "mmtar_ref": "MMTAR-2026-8812"},
    "accountable_person": "Margaret Osei, Head of Tax",
    "model_provider": "Anthropic (Claude)"
  },
  "authorization_details": [{
    "type": "uk_tax_filing",
    "actions": ["submit_vat_return", "submit_quarterly_update", "view_client_records"],
    "client_coverage": "per-64-8-list",
    "per_filing_limit": {"amount": 5000, "currency": "GBP"},
    "cumulative_limit": {"amount": 20000, "currency": "GBP", "window": "P30D"},
    "escalation_threshold": {"amount": 3500, "currency": "GBP"}
  }],
  "status": {"registry": "/api/status/AP-2026-0091"}
}
```

Scope uses the **RFC 9396 authorization_details** shape. Show the decoded JWT and its signature verification in the UI — that IS the demo's technical credibility.

**Key architectural rule (judges will probe this):** the token carries the LIMITS; the gateway holds the running TOTALS in SQLite (per agent_id, 30-day window). Never imply cumulative state lives in the token. Revocation likewise lives in the registry, not the token: a `status` table; revoking flips one row and the very next verification denies.

## 4 · Three views (tabs), one shared state

**`/operator` — accounting firm.** Pre-filled application as a GOV.UK summary list using the fields above. "Submit application" → reference AP-2026-0091, under review.

**`/regulator` — case officer.** Seven automated checks, each pass with rule ref + source: firm registration matches record (1.1 · registration extract); ARN valid and active (1.2 · ASA record); MMTAR registration current (1.3 · MMTAR register); AML supervision confirmed — ICAEW (2.2 · supervisor register); accountable person named and evidenced (2.1 · appointment letter); model provider not restricted (3.2 · provider register); requested scopes and limits within policy ceilings (4.1/4.4 · policy table). Then the human decision: **"Approve and issue passport"** (logs supervisor "M. Whitcombe", mints and signs the JWT) / "Reject with reasons" (stub). After issuance: passport card with ACTIVE stamp + **decoded JWT panel** (header/payload pretty-printed, signature "verified ✓ Ed25519") + **Revoke** button (flips status registry, logs supervisory action) + re-activate for demo convenience.

**`/relying` — verification console (authority gateway).** Status strip: passport ID · status · filings count · cumulative meter (£X of £20,000, %). Buttons firing POST `/api/verify`:

| Button | Expected |
|---|---|
| VAT return · £1,400 · client on 64-8 list | ALLOW (rules 4.1–4.4, 5.2) |
| Quarterly update · £4,200 · on list | ESCALATE — above £3,500 human threshold (4.5) |
| VAT return · £900 · client NOT on list | DENY — not on 64-8 authorisation list (5.2) |
| VAT return · £9,400 · on list | DENY — exceeds per-filing limit £5,000 (4.2) |
| View client records · on list | ALLOW (4.1) |
| repeat allowed filings past £20,000 | DENY — cumulative limit (4.3), *structuring caught* |
| anything after revocation | DENY — passport not active (0.1) |

Terminal-style log, each line: timestamp · action · verdict · rule id · reason · audit ref (sha256 chain: `hash(prev_hash + entry)` — hash-chained, tamper-evident, say "not blockchain" in the README) · "rule pack v2026.09 — decision replayable".

## 5 · API contract (the real deliverable)

```
POST /api/verify
{"agent_id": str, "action_type": "submit_vat_return"|"submit_quarterly_update"|"view_client_records",
 "amount": number, "client_on_64_8": bool}
→ {"decision": "ALLOW"|"ESCALATE"|"DENY", "rule_id": str, "reason": str, "audit_ref": str}

GET /api/status/{passport_id} → {"status": "active"|"revoked"}
GET /api/passport/{passport_id} → the signed JWT (compact) + decoded payload
```

Ordered evaluation in `rules.py`, one plain function per rule, **deny-by-default** for unknown actions:
signature/expiry valid → status active → holder authorised (64-8 flag) → action in scopes → per-filing limit → cumulative limit (stateful) → escalation threshold → ALLOW.

## 6 · Visual direction (impeccable pass target)

GOV.UK service language — the pitch is "deployable by a UK authority tomorrow": white, Arial, #0b0c0c text; black masthead "Agent Passport" with thick #00703c underline; blue PROTOTYPE phase banner ("Internal baseline — synthetic data only"); green action buttons with 2px dark bottom shadow, red #d4351c revoke, #ffdd00 focus outlines; summary-list tables with hairline bottom borders; status tags green/amber/red. **Zero border-radius, zero gradients, zero dark-SaaS, zero purple, no card grids with soft shadows.** Spend all boldness in one place: the verification console as black monospace terminal, verdicts stamping in colour (green ALLOW / amber ESCALATE / red DENY). Copy in GOV.UK voice: sentence case, buttons say what they do.

## 7 · Non-goals

No login, no DPoP/key-binding (Rung 2 — leave a `cnf` field in the JWT as null with a comment), no real HMRC APIs, no sanctions screening, no VC/JSON-LD wrapper, no LLM, no websockets, no CSS framework, no admin CRUD, no blockchain (word or tech).

## 8 · Definition of done

`pip install -r requirements.txt && uvicorn main:app` starts clean and seeds itself; all seven console beats work in sequence; the decoded-JWT panel shows a genuinely verified Ed25519 signature; revocation flips the next decision to DENY; `prototype/README.md` documents run steps, the API contract, the rule list, and the seven demo beats in order (doubles as the video storyboard).
