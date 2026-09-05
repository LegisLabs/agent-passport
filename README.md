# Agent Passport

Regulator-issued, scoped, revocable credentials for autonomous AI agents. Lexis Labs entry to the C:\>DIR Global 'Agentic Regulator' Hackathon, Know Your Agent problem space. One engine, two verticals, two rule packs:

| Vertical | Live | Code | What it shows |
|---|---|---|---|
| **B2B payments** (primary) | **https://pay.cdir.legislabs.uk** | `pay/` | A payment-initiation provider's AI agent pays a small business's suppliers. Three-signer passport envelope, bank-side verification, cumulative limits, incidents, vouch.finance rail. |
| UK Self Assessment (transferability beat) | https://cdir.legislabs.uk | `app/` | The same engine, a tax rule pack: an accounting firm's filing agent, unchanged since the v1 skeleton (git tag `hmrc-v1`). |

The payments site is public. The tax site sits behind a basic-auth gate (user `lexis`; password supplied with the submission). API docs at `/api/docs` on each. Plan and briefs in `docs/`.

**Identity is not authority.** The LLM only extracts facts from documents; versioned rule packs decide; a named human signs; every decision replays. Never the word "blockchain": signatures, a registry and a hash-chained log.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r deploy/requirements.txt
cp .env.example .env            # GEMINI_API_KEY, optional HACKATHON_ORG_API_KEY; or EXTRACTION_MODE=fixture
.venv/bin/uvicorn pay.main:app --reload --port 8014     # payments vertical
.venv/bin/uvicorn app.main:app --reload --port 8013     # tax vertical
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q   # 46 tests, fully offline
```

Each app self-seeds on first run: signer keys into `data/pay/keys/` (or `data/keys/`), SQLite alongside. Nothing else to configure.

## The payments scenario

**Northgate Joinery Ltd** (customer) pays suppliers through **PayRail Ltd** (licensed payment-initiation provider, the operator). PayRail runs an accounts-payable agent, **Agent 247**, that reads invoices and initiates payments. Before deployment PayRail submits evidence to the **national payments supervisor (demo)**. Automated KY-A checks run, an officer approves with a condition, and an assurance is issued. Northgate's finance director signs the mandate. **Northgate's bank** verifies the passport on every instruction before executing. The supervisor can suspend or revoke at any time; three refusals raise an incident.

All names, registers, accounts and documents are synthetic. This is a proposed assurance framework, not a current legal requirement.

### The path

1. **Apply** (`/provider`). PayRail's evidence pack (five synthetic documents) loads. "Read documents into facts" sends them to Gemini in JSON mode; every value comes back with its source document and a verbatim quote. Correct anything, generate the agent's key, have the agent sign the authority's challenge (proof of possession). On submission PayRail signs the `agent_identity` claim with its own key and checks A.1–A.8 run.
2. **Review & issue** (`/regulator`). Eight checks with rule id, source and CURRENT/PROTOTYPE label. Optional model-drafted file note. The officer sets the condition (hold above £5,000), writes a required note and approves, requests information or rejects. Approval signs the `assurance` with the authority key, enters the passport in the registry as ACTIVE and mirrors the mandate on the vouch rail. Lifecycle: suspend, reinstate, revoke, each with a reason. Incident feed.
3. **Sign mandate** (`/customer`). Northgate's finance director sees the supplier allowlist, the limits and the expiry, and signs the `mandate` with the company key. Before that the envelope is incomplete and the bank refuses everything at R.5.
4. **Act & check** (`/bank`). Eight proposed instructions. The simulated agent signs each; the bank runs R.1–R.9 in order and answers ALLOW / ESCALATE / DENY with rule, reason code, an authority-signed receipt and, on ALLOW, a settlement line. Per-account 30-day meters, and both rails (authority registry, vouch voucher) on every line, so after a revocation the console shows two rails refusing. Three refusals raise an incident.
5. **Audit** (`/audit`). Hash chain over every event. Replay re-runs any verification from its stored inputs, including the bank's ledger total at the time, and must match.

### The composite passport

Not one JWT. An envelope of three independently signed Ed25519 JWTs, each signed by the party entitled to the claim:

```json
{
  "passport_id": "AP-2026-0107",
  "assurance":      "<JWT signed by the AUTHORITY>   provider, licence, KY-A status, condition, accountable person, validity, binds → agent_identity hash",
  "agent_identity": "<JWT signed by PAYRAIL>         agent name, agent public key (cnf), software, config SHA-256",
  "mandate":        "<JWT signed by NORTHGATE>       supplier allowlist by account, per-payment limit, 30-day limit per account, expiry",
  "status_url": "/api/status/AP-2026-0107",
  "vouch_voucher_id": "VCH-… or the live voucher id",
  "cnf": null
}
```

Public keys for all three signers: `GET /api/signers`. Remove any one signature and the bank refuses.

### Rules (rule pack `payments-2026.09`, data not code)

Application, authority side: A.1 licence resolves and active · A.2 Companies House resolves · A.3 accountable person with signed declaration · A.4 insurance evidenced · A.5 agent key proof-of-possession · A.6 customer agreement evidenced · A.7 limits within policy ceilings · A.8 software declared and config hash matches the deployed file.

| Bank side, in order | Fails to |
|---|---|
| R.1 assurance signature (authority key) | DENY `ASSURANCE_SIGNATURE_INVALID` |
| R.2 assurance active and unexpired (registry lookup) | DENY `ASSURANCE_NOT_ACTIVE` |
| R.3 agent identity signature (provider key), bound to this assurance | DENY `AGENT_IDENTITY_SIGNATURE_INVALID` |
| R.4 instruction signed by the agent key in `agent_identity.cnf` | DENY `AGENT_SIGNATURE_INVALID` |
| R.5 mandate present, signed by the customer, unexpired | DENY `MANDATE_NOT_SIGNED` / `MANDATE_SIGNATURE_INVALID` / `MANDATE_EXPIRED` |
| R.6 action permitted and payee account on the allowlist | DENY `OUT_OF_SCOPE` / `PAYEE_NOT_ON_MANDATE` |
| R.7 amount within per-payment limit | DENY `PER_PAYMENT_LIMIT_EXCEEDED` |
| R.8 amount + 30-day total for this account within the monthly limit (bank ledger) | DENY `MONTHLY_LIMIT_EXCEEDED` |
| R.9 amount above the supervisor condition | ESCALATE `HUMAN_CONFIRMATION_REQUIRED` |
| otherwise | ALLOW `WITHIN_MANDATE` |

The limit lives in the mandate; the running total lives at the bank. `fixtures/pay/oracle.json` holds 18 deterministic cases; `tests/test_pay.py` runs them all offline.

### Demo beats (the `/bank` console, in order; doubles as the video storyboard)

| # | Instruction | Expected |
|---|---|---|
| 0 | Any instruction before the customer signs | DENY R.5 mandate not signed |
| 1 | Fenwick Timber Ltd · £3,200 · on the allowlist | ALLOW, receipt, settled |
| 2 | Fenwick Timber Ltd · £2,750 · account 60-11-22 10101010 | DENY R.6 · invoice redirection fraud stopped by the customer-signed allowlist |
| 3 | Ashby Ironmongery Ltd · £11,400 | DENY R.7 · above the £10,000 cap |
| 4 | Coastline Glass Ltd · £5,600 | ESCALATE R.9 · above the £5,000 supervisor condition |
| 5 | Fenwick Timber Ltd · £4,900 · repeated | ALLOW ×3, then DENY R.8 when the 30-day total would pass £20,000 |
| 6 | Fenwick Timber Ltd · £1,150 · signed with a rogue key | DENY R.4 · copied passport |
| 7 | Refund Fenwick Timber Ltd · £3,200 | DENY R.6 · known payee, action never granted |
| 8 | Ashby Ironmongery Ltd · £900 · lifecycle probe | ALLOW; after suspend DENY R.2; after reinstate ALLOW; after revoke DENY R.2 and the vouch voucher is revoked too |

Three refusals raise "escalated to supervisor" in the terminal and in the regulator's incident feed.

## vouch.finance integration

`pay/vouch.py` mirrors the passport's mandate as an AI Voucher on the hackathon sandbox.

| Env | Values | Effect |
|---|---|---|
| `VOUCH_MODE` | `fixture` (default) · `live` | fixture records deterministic voucher ids, no network; live calls `https://cdir.vouch.finance/api/v1` with `HACKATHON_ORG_API_KEY` and falls back to fixture, visibly labelled, on any failure |
| `PAYMENT_RAIL` | `local` (default) · `vouch` | vouch additionally settles each ALLOW as intent → quote → authorize; a 403 is a rail-side decline, not an error. Needs `VOUCH_PROGRAM_ID`, `VOUCH_MERCHANT_ID`, `VOUCH_PRIVY_USER_ID` from a seeded kit |

Approval → `POST /ai-vouchers` (passport id in metadata, voucher id in the envelope). Revoke → `DELETE /ai-vouchers/{id}`. "Re-check on rail" → `GET /ai-vouchers/{id}`. Verdicts come from HTTP responses, never the SSE stream. Verified live against the sandbox on 5 Sept 2026 (mint, status, revoke).

**Kit replay.** `scripts/vouch_kit_replay.py` replays the sponsor's `kya-licence` and `agent-mandate` kits through our verifier. It turns each kit into Agent Passport terms (allowlisted merchants become payee accounts on a customer-signed mandate, the kit's per-transaction cap becomes the per-payment limit, each actor's quota the 30-day limit, each actor its own agent key and three signed JWTs), expands every scripted scenario, runs each instruction through `pay.rules.verify_action` with a running ledger, and scores against the scripted ground truth:

```bash
.venv/bin/python scripts/vouch_kit_replay.py                              # offline, vendored manifests
.venv/bin/python scripts/vouch_kit_replay.py --labels ../hackathon-kits/artifacts/runs/<runId>/labels.jsonl --json report.json
```

Result on 5 Sept 2026, condition £5,000: **kya-licence precision 100%, recall 86%** (miss: delegation-depth abuse, a mandate op outside v1); **agent-mandate precision 100%, recall 50%** (caught: over-limit, unapproved counterparty, delegation overspend; missed: out-of-category, out-of-hours, count-based structuring, because a v1 mandate carries payees and amounts, not categories, hours or transaction counts). Nothing compliant was refused. The field mapping is a proposed compatibility profile: `docs/KYA_extension_for_purpose_bound_value.md`.

## API (payments vertical)

```
POST /api/applications                        start (loads the evidence pack)
POST /api/applications/{id}/extract           Gemini → structured facts with provenance
PUT  /api/applications/{id}/fields            provider corrections
POST /api/applications/{id}/agent-key         agent key pair + authority challenge
POST /api/applications/{id}/sign-challenge    agent signs; authority verifies possession
POST /api/applications/{id}/submit            provider signs agent_identity; runs A.*
POST /api/applications/{id}/decision          {decision: approve|request_info|reject, note, human_confirm_above}
POST /api/applications/{id}/file-note         model-drafted note (never a decision)
POST /api/passports/{id}/mandate/sign         customer signs the mandate; envelope complete
POST /api/passports/{id}/status               {status: suspended|active|revoked, reason}; revoke also revokes on the vouch rail
GET  /api/passports/{id}                      envelope + per-part verification + minimal (bank) view
GET  /api/passports/{id}/vouch                voucher status re-read from the rail
GET  /api/status/{id}                         real-time registry status
GET  /api/signers                             the three public keys
POST /api/agent/act                           simulated agent signs and presents an instruction
POST /api/verify                              flat {passport_id, agent_signature, action_type, payee_account_ref, supplier_name, amount, currency, invoice_ref, nonce}
                                              or nested {passport_id, instruction, passport?} → {decision, rule_id, code, reason, audit_ref, receipt, rails, settlement, incident}
GET  /api/audit · POST /api/audit/{id}/replay · GET /api/receipt/verify?token=
```

## Where the model sits

Gemini (JSON mode, temperature 0) reads documents into a fixed schema and drafts the officer's file note. It never checks, scores or decides. `EXTRACTION_MODE=fixture` replaces both calls with deterministic stand-ins; on API failure the system falls back to the fixture and labels the result `gemini-fallback`.

## Deploy

```bash
bash deploy/publish.sh          # both containers on the shared Hetzner box, Caddy drop-ins, reload
bash deploy/publish.sh pay      # payments only
```

## Layout

```
pay/          payments vertical: main.py · rules.py · crypto.py (three signers, verify_envelope) · vouch.py · audit.py · extraction.py · db.py · fixtures.py · templates/ · static/
app/          tax vertical (unchanged, tag hmrc-v1)
rulepacks/    payments-2026.09.json · hmrc-sa-2026.09.json
fixtures/pay/ documents/ (evidence pack) · registry.json · extraction_fixture.json · oracle.json · agent_config.json · vouch_kits/
fixtures/     the tax vertical's fixtures
scripts/      vouch_kit_replay.py
tests/        test_pay.py · test_rules.py, offline
deploy/       Dockerfile · pay.Dockerfile · docker-compose.yml · *.caddy · publish.sh · requirements.txt
docs/         PLAN.md · BRIEF_v3_Payments_Conversion.md · KYA_extension_for_purpose_bound_value.md · Bernard's spec · earlier briefs
```

## Third-party components

FastAPI, Uvicorn, Jinja2, Pydantic (MIT) · cryptography (Apache-2.0/BSD) · PyJWT (MIT) · google-genai (Apache-2.0) · vouch.finance hackathon kit manifests (MIT, vendored in `fixtures/pay/vouch_kits/`). No real personal data anywhere; all registers, firms, accounts and documents are synthetic.

## Not claimed

That any supervisor issues agent passports today; that the passport replaces the provider's licence, the customer's contract or the bank's own mandate; that a signature proves an agent is safe or correct; that a valid passport compels a bank to execute; that this is production cryptographic infrastructure.
