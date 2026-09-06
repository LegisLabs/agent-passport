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

### Iteration 2: the agentic loop and the manipulation moment

- **Malicious invoice** (`/bank`): Agent 247 reads `INV-9001-clean` or `INV-9001-poisoned` with the model, signs the instruction it derived, and the bank decides. Clean pays the signed-for account; poisoned would pay 60-11-22 10101010 and is refused at R.6. Fixture mode reproduces the extraction exactly.
- **Standards Review Assistant** (`/regulator`, `POST /api/applications/{id}/review`): evidence read, rule map, five adversarial tests, sandbox run through the real engine, labelled recommendation, human sign-off. Only the officer's decision signs.
- **Anomaly Detection & Escalation** (`/regulator`, `GET /api/violations`, `POST /api/passports/{id}/investigation`): violations with status, a 2-in-24h same-rule alert, suspend → investigate → revoke or reinstate.

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
| `PAYMENT_RAIL` | `local` (default) · `vouch` | vouch additionally settles each ALLOW as intent → quote → authorize on the mirror program; a 403 is a rail-side decline, a fault falls back to the local rail. Needs `VOUCH_PROGRAM_ID`, `VOUCH_PRIVY_USER_ID`, `VOUCH_MERCHANTS`, `VOUCH_CATEGORY` (see Settling on the rail) |

Approval → `POST /ai-vouchers` (passport id in metadata, voucher id in the envelope). Revoke → `DELETE /ai-vouchers/{id}`. "Re-check on rail" → `GET /ai-vouchers/{id}`. Verdicts come from HTTP responses, never the SSE stream. Verified live against the sandbox on 5 Sept 2026 (mint, status, revoke).

**Kit replay, scored against their ground truth.** Both sponsor kits are seeded in our hackathon org and their `run-stream.ts` was run against the sandbox (runs `lexis-am-1`, `lexis-kya-2`); the `labels.jsonl` files it wrote are vendored in `fixtures/pay/vouch_kits/labels/`. `scripts/vouch_kit_replay.py` turns each kit into Agent Passport terms (allowlisted merchants become payee accounts on a customer-signed mandate, the kit's per-transaction cap the per-payment limit, each actor's quota the 30-day limit, each actor its own agent key and three signed JWTs), runs every scripted instruction through `pay.rules.verify_action` with a running ledger, and scores against those labels:

```bash
.venv/bin/python scripts/vouch_kit_replay.py                 # offline: vendored manifests + vendored labels
.venv/bin/python scripts/vouch_kit_replay.py --verbose --json report.json
```

| Kit | Precision | Recall | Caught | Missed, and why |
|---|---|---|---|---|
| kya-licence | 100% | 86% | unapproved counterparty (R.6), revoked mandate reused (R.2) | delegation-depth abuse: a mandate op, no sub-agents in v1 |
| agent-mandate | 100% | 50% | over-limit (R.7), unapproved counterparty (R.6), delegation overspend (R.7) | out-of-category, out-of-hours, count-based structuring: a v1 mandate carries payees and amounts, not categories, hours or transaction counts |

Nothing compliant was refused. The field mapping is a proposed compatibility profile: `docs/KYA_extension_for_purpose_bound_value.md`.

**Settling on the rail.** `fixtures/pay/vouch_kits/agent-passport-northgate.json` is our own manifest in the sponsor's kit format, mirroring the demo mandate on the rail (program, the three suppliers as merchants, Agent 247 with a spending mandate, a rule hook for the allowlist and the £10,000 cap). `scripts/vouch_complete_seed.ts` seeds it from a clone of their repo, since their seeder only accepts its four built-in kits:

```bash
git clone -b feat/generalise-kits https://github.com/finternet-ecosystem/hackathon-kits && cd hackathon-kits && npm install
cp ../CDIR/fixtures/pay/vouch_kits/agent-passport-northgate.json kits/ && cp ../CDIR/scripts/vouch_complete_seed.ts .
HACKATHON_ORG_API_KEY=sk_test_… API_BASE_URL=https://cdir.vouch.finance/api/v1 npx tsx vouch_complete_seed.ts agent-passport-northgate
```

Then set `PAYMENT_RAIL=vouch` with `VOUCH_PROGRAM_ID`, `VOUCH_PRIVY_USER_ID` (the agent's identity on the rail) and `VOUCH_MERCHANTS` (JSON map of payee account to merchant id) from the state file it writes. Every instruction the bank ALLOWs is then quoted and authorized on the rail as a second, independent enforcement of the same allowlist and cap. A 403 from the rail is shown as a rail-side decline; a rail fault (5xx, unreachable) never contradicts the bank's decision: the instruction executes on the local rail and the console says so. Verified live on 5 Sept 2026: the rail declines £11,400 at quote (`cart.total lte check failed: got 11400, expected 10000`) and has no merchant for a redirected account.

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
