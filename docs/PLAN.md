# Agent Passport — v1 skeleton build plan (4 Sept 2026)

Canonical spec: `docs/Demo Vertical Alignment and Fields for Skeleton.pdf` (Bernard).
Technology reference: `docs/BRIEF_v2.md`, `docs/Tax_Field_Research_CDIR.md`.
Frozen product spec: `context/01_team_agent_passport/AgentPassport_Validated_Spec_v1.0_20260903.pdf`.

## Goal

A deployed, testable, end-to-end skeleton at https://cdir.legislabs.uk that the team iterates on until the 8 Sept submission. HMRC Self Assessment demo. Four parties, one path: **Apply → Review & issue → Act & check → Maintain**.

## Design inputs applied

- **Bernard:** SA100, tax year 2025/26, submit-only vs submit-and-amend, client UTR list with 64-8 status and consent to automated processing, agent public key + signed challenge at application, per-action request signed by the agent, ordered runtime checks (signature → status → agent signature → scope → client), signed receipt on every result, suspend/revoke/renew with officer reason, minimal passport with no personal data for the relying party.
- **Marko Katavic (clinic 3):** split the decision, collapse to structured facts at every handover, LLM at the edges only, deterministic middle, replayable evidence not reasoning traces.
- **Caroline Malcolm (clinics 1–2):** non-bespoke, rules as data, resource-constrained regulators, high trust bar, human accountability, agent identity is the urgent gap.
- **Penwarden (FCA):** audit trail as a product; "where is the human and could they say no"; what could someone make your agent do.
- **Spec v1.0:** CURRENT / PROTOTYPE / FUTURE labels on every rule, reason codes not `verified=true`, no black-box score, no HMRC overclaim.

## Where the LLM sits (Gemini, JSON mode)

1. **Extraction (edge, reading in).** The operator's evidence pack (five synthetic documents) is read by Gemini into a fixed schema. Every extracted fact carries `source_doc` and a verbatim `quote`. The operator reviews and can edit before submitting. Rules never see raw text. Fixture mode (`EXTRACTION_MODE=fixture`) returns the same schema deterministically so tests and the demo do not depend on the API.
2. **Drafting (edge, phrasing out).** Officer can ask for a plain-English file note drafted from the structured check results. Labelled draft, editable, never a decision.

Nothing else touches a model. Application checks and runtime verification are pure functions over structured facts plus registry lookups.

## Architecture

```
FastAPI (Python 3.12) · SQLite (stdlib) · Jinja2 + vanilla JS · cryptography (Ed25519) · PyJWT · google-genai
app/main.py        routes: views + JSON API
app/db.py          schema + helpers (applications, documents, passports, agents, registry, audit)
app/crypto.py      authority + agent keys (Ed25519), JWT sign/verify, nonces
app/rules.py       rule pack loader, application checks (A.*), runtime verify (R.*)
app/audit.py       hash-chained audit log + signed receipts + replay
app/extraction.py  Gemini extraction + drafting, fixture fallback
app/fixtures.py    synthetic firm, clients, documents, authority registry
rulepacks/hmrc-sa-2026.09.json   rules as data with CURRENT/PROTOTYPE/FUTURE + source
fixtures/documents/*.txt          the evidence pack
fixtures/oracle.json              Jean's deterministic test cases
tests/                            rules oracle, crypto, audit replay, API flow
deploy/                           Dockerfile, compose, Caddy drop-in, publish.sh
```

## Views

- **/operator** — evidence pack → "Read documents" (Gemini) → extracted fields with provenance → agent key generated, challenge signed → submit.
- **/regulator** — queue → application: fields, automated checks A.1–A.10 with source and CURRENT/PROTOTYPE label, flagged items, officer decision (approve / request information / reject) with required note → passport card + decoded JWT → lifecycle (suspend / reinstate / revoke / renew) with reason → draft file note.
- **/relying** — minimal passport (no personal data) → seven proposed actions, each signed by the agent → ordered checks → ALLOW / ESCALATE / DENY with reason codes → signed receipt → terminal log.
- **/audit** — hash chain, receipts, "replay" re-runs any decision from stored inputs and confirms identical output.
- **/about** — what is real, what is not, standards, what we do not claim.

## Rules

Application (A.*): A.1 ASA reference active · A.2 Government Gateway agent ID present · A.3 Companies House number resolves to firm · A.4 accountable person named with role, body and declaration · A.5 AML supervision confirmed · A.6 each client 64-8/handshake confirmed · A.7 each client consent to automated processing · A.8 requested scope within policy (task, tax year, action type, validity ≤ tax-year end) · A.9 agent key proof-of-possession · A.10 software recognised (PROTOTYPE).

Runtime (R.*), ordered, deny by default: R.1 passport signature · R.2 status active and unexpired (registry) · R.3 request signed by the passport's agent key · R.4 action within scope (task, tax year, action type) · R.5 client authorised for this firm (registry, by UTR reference) · R.6 value above escalation threshold → ESCALATE · else ALLOW.

## Demo beats (relying party)

1. Submit SA100, Maya Okafor, 2025/26, £2,100 → ALLOW
2. Submit, Daniel Reyes, £14,800 → ESCALATE R.6
3. Amend, Maya → DENY R.4 (submit only)
4. Submit, unauthorised UTR → DENY R.5
5. Submit, Maya, tax year 2024/25 → DENY R.4
6. Submit signed with a rogue key (stolen passport) → DENY R.3
7. Officer suspends → DENY R.2 · reinstates → ALLOW · revokes → DENY R.2

## Defaults chosen (no questions asked)

Value threshold = tax due, £10,000. Missing consent = flag for officer, not hard fail. Renew and request-information = recorded actions, no second passport in v1. No transferability beat in v1. No auth gate on the URL. Persistence = SQLite volume on the server, one shared demo state with a reset button.

## Done when

`pytest` green · `uvicorn app.main:app` self-seeds · all seven beats produce the expected verdicts through the UI · Gemini extraction works live with fixture fallback · deployed at cdir.legislabs.uk via Docker behind the shared Caddy · README documents run, API, rules, beats.
