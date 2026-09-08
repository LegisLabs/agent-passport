# Agent Passport

Bank-side verification of AI agent payments. Legis Labs entry to the C:\>DIR Global 'Agentic Regulator' Hackathon 2026, Know Your Agent problem space.

Live demo: **https://cdir.legislabs.uk** (public, no login). Proposed industry standard: [APS 1001, revision 5](pay/static/APS_1001.pdf). Project summary: [PROJECT_SUMMARY.pdf](PROJECT_SUMMARY.pdf). Mentor feedback audit: [AUDIT_REPORT.md](AUDIT_REPORT.md).

**Identity is not authority.** An AI agent that can be identified can still act beyond what its principal allowed. Agent Passport separates the two and puts the check where the money and the liability are: at the bank.

## What the prototype does

Agent Passport is a pre-authorisation checkpoint for payments initiated by AI agents. It sits inside a bank's existing payment pipeline, alongside fraud detection and sanctions screening and before settlement, and replaces none of them. Before the bank moves money on an instruction from an AI agent, it verifies three signed documents and nine ordered checks. If a check fails, the instruction is held for a person and money does not move. Every event is written to a hash-chained evidence trail the bank owns, with a bank-signed receipt on every decision.

The buyer is the bank, which offers the capability to its business customers. The regulator is involved only by exception: it reads evidence when it asks for it. Nothing in the product approves, certifies, licenses or endorses anything on a regulator's behalf, and no regulator operates any part of it.

| Layer | Who | What | How often |
|---|---|---|---|
| 1 Register | The bank (Meridian Bank, demo) | Registers an AI product on its register: the provider's identity, an accountable principal with a signed declaration, insurance, the payment intent the product is filed for, its UK data protection declaration and retention period, and Independent Assurance Evidence at a declared assurance level. Seven completeness checks, F.1 to F.7, run and are recorded with a signed receipt. Registration records accountability; it does not certify quality. | Once |
| 2 Approve | The bank | A named officer approves the product for the bank's list, or not, with ceilings every mandate must sit within and a hold condition. A deterministic review assistant recommends; it never decides. "Bank approved" means approved by that bank alone. | Once |
| 3 Mandate | The customer (Northgate Joinery Ltd) | Inside its bank's app: picks a bank approved product, registers its AI agent deployment (a key pair the agent alone holds, proof of possession, configuration hash), signs a mandate (payee accounts checked against Companies House, per-payment limit, 30-day limit per payee account, payments per day, expiry, currency) within the lower of the bank's ceilings and the account-type tier. The passport is issued at signing. A mandate can be amended (a new signed version, the old one retained) or revoked. | Once per version |
| 4 Check | The bank | Verifies the passport and the mandate on every instruction, R.1 to R.9. A failed check holds the instruction for a person, who approves or declines it with a note. A signed chain entry is written either way. | Every payment |

## The four mandatory guardrails, where they live in the code

| Guardrail | What the prototype does | Where |
|---|---|---|
| Human in the loop | A person signs every mandate. The first payment under each mandate version is held for the customer to confirm. Any payment above the bank's hold condition, and any payment that fails a check, is held for a named person who approves or declines it with a note. Both outcomes are receipted chain entries naming who decided, when, and on what. | `pay/main.py` (`sign_mandate`, `decide_held`, `confirm_first`), `pay/rules.py` (R.9 and `_result`), the bank and customer dashboards |
| Auditability and traceability | Every event is one entry in a hash chain (each hash covers the previous hash and the canonical entry). Verifications and human decisions carry a receipt signed by the bank's Ed25519 key. Each verification stores the exact inputs it used, so any decision can be replayed and shown identical. Evidence bundles for a passport or a refusal are exported on request, and the export is itself chained. | `pay/audit.py`, `pay/db.py` (`audit` table), `/api/audit`, `/api/audit/{id}/replay`, `/api/evidence/*`, the Evidence trail card on `/bank` |
| Safety and governance controls | Deny by default, no model inference at execution time. The rule pack is data, not code, and every rule is labelled CURRENT or PROTOTYPE. Ceilings are the bank's; mandates are contained within them at signing and at amendment; every instruction carries a nonce so a replay is refused; refusals are classed as fraud indicator or agent error and routed differently. The language model reads invoices and drafts file notes only; it never checks, scores, approves or verifies, and it falls back to a deterministic fixture that says so. | `rulepacks/payments-2026.09.json`, `pay/rules.py`, `pay/extraction.py`, `pay/review.py` |
| Cyber risk management | Three independent signers (register, bank, customer), EdDSA over Ed25519; each instruction is signed by the agent's own key bound in the agent identity (RFC 7800 `cnf`) with proof of possession at registration; a copied passport without the key fails R.4; a replayed instruction fails R.4; a stale or revoked mandate fails R.5; suspension and revocation cascade from the product to every passport and to the vouch.finance voucher. Secrets stay in `.env`, never in the repository; all firms, accounts and documents are synthetic. | `pay/crypto.py`, `pay/rules.py` (R.1 to R.5), `pay/main.py` (status cascade), `pay/vouch.py` |

## Architecture overview

```
 Provider supplies filing         Bank registers and approves            Customer (bank app)             Regulator
 (identity, insurance,            /provider  /bank?ref=REG-…             /customer                       (by exception)
  evidence, data protection)      F.1–F.7 checks, receipt                agent key + PoP, mandate         /api/evidence/*
            │                     approval: ceilings, hold                signed with customer key              ▲
            └────────────────────►  register (SQLite) ◄───────────────────────────┘                             │
                                          │                                                                    │
                       AI agent signs an instruction (nonce) ──► POST /api/verify ──► R.1…R.9 (pay/rules.py)   │
                                                                     │  ALLOW / ESCALATE (held) / refused check │
                                                                     ▼                                          │
                                        hash chain + bank-signed receipt (pay/audit.py) ────────────────────────┘
                                                                     │
                                            settlement: local rail or vouch.finance voucher (pay/vouch.py)
```

One FastAPI process, one SQLite file, server-rendered Jinja2 templates with vanilla JavaScript. No framework on the front end, no queue, no external service on the verification path: registration and verification live at the bank, so the checks run where the money is.

| Path | Role |
|---|---|
| `pay/main.py` | Routes and views, the verify gateway, held-payment decisions, mandate sign, amend and revoke, evidence bundles, demo seeds |
| `pay/rules.py` | Filing checks F.1 to F.7, runtime checks R.1 to R.9, ceiling containment, account tiers, refusal classification |
| `pay/crypto.py` | Ed25519 key pairs, JWT sign and verify, envelope verification, nonces, JWK thumbprints |
| `pay/audit.py` | The hash chain and bank-signed receipts; chain verification |
| `pay/db.py` | SQLite schema and migrations: registrations, passports (with mandate versions), payments, audit, violations, nonces |
| `pay/review.py` | The approval review assistant: filing read, requirement map, adversarial tests, sandbox, recommendation; the officer decides |
| `pay/companies_house.py` | Companies House Public Data API with rate-limit backoff and a labelled synthetic fallback |
| `pay/vouch.py` | vouch.finance adapter: voucher mint, settlement, revocation; fixture and live modes |
| `pay/extraction.py` | Invoice reading with Gemini or a deterministic fixture; the filing form fields |
| `pay/fixtures.py`, `fixtures/pay/` | The demo cast, scripted beats, register entries, synthetic company register, invoices, the 20-case oracle |
| `rulepacks/payments-2026.09.json` | The rule pack: rules, reason codes, policy ceilings, account tiers, customer classes, assurance levels, payment intents, retention periods, failure classes |
| `pay/templates/`, `pay/static/` | Landing, How it works, Register a product, Bank dashboard, Customer dashboard, Action Terminal; stylesheets, scripts, brand, the standard as PDF |
| `app/` | The earlier tax demonstrator, frozen (tag `hmrc-v1`), served at `/tax/` behind basic auth |
| `deploy/` | Dockerfiles, Docker Compose, Caddy site files, the publish script |
| `tests/` | `test_pay.py` and `test_rules.py` (86 tests, offline), `ui/walk_bank_first.py` (Playwright walk of the whole journey) |
| `docs/` | APS 1001 revision 5 (`v6_bank_first/`) and the earlier briefs and revisions |

## Setup and run

Requires Python 3.12.

```bash
python3 -m venv .venv && .venv/bin/pip install -r deploy/requirements.txt
cp .env.example .env            # optional keys below; the defaults run fully offline
EXTRACTION_MODE=fixture VOUCH_MODE=fixture PAYMENT_RAIL=local .venv/bin/uvicorn pay.main:app --port 8014
```

Open http://localhost:8014. The app creates its signer keys and SQLite database under `data/pay/` on first start. Reset to the demo baseline at any time with the footer's "Reset demo" link, with `bash scripts/demo_reset.sh`, or with `POST /api/demo/seed?stage=registered|issued|history` (product filed and reviewed; approved with the mandate signed; plus a short payment history with one held payment and both refusal classes).

Optional environment (`.env.example` documents each):

| Variable | Effect |
|---|---|
| `GEMINI_API_KEY`, `EXTRACTION_MODE=gemini` | The AI agent reads invoices with Gemini (JSON mode, temperature 0) and the officer can draft a file note. Without it, `fixture` mode gives the same demo deterministically and the footer says so. |
| `HACKATHON_ORG_API_KEY`, `VOUCH_MODE=live`, `PAYMENT_RAIL=vouch` | Mirrors each mandate as an AI Voucher on the vouch.finance sandbox and settles allowed payments through it. Without them the local rail executes. |
| `COMPANIES_HOUSE_API_KEY` | Live Companies House search and lookup for payees and providers. Without it a labelled synthetic register answers, so the demo never breaks. |

Tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q      # 86 tests, fully offline
```

Browser walk of the whole journey (registration, approval, mandate, terminal, held payments, amendment, revocation, evidence): see `tests/ui/README.md`; `BASE=http://localhost:8014 python tests/ui/walk_bank_first.py`.

The tax demonstrator (`app.main:app`, port 8013) is kept for comparison and is not part of the demo.

## Surfaces

| Route | Who uses it | What it is |
|---|---|---|
| `/` | Everyone | The case, the numbers, the proposal, the result |
| `/terminal` | Everyone | Action Terminal: one altered invoice, two worlds. Before the standard the AI agent pays the changed account; after it, the bank's checks hold the payment at R.6 for a person |
| `/terminal?console=1` | Judges | Expert console: ten scripted instructions (clean, redirected, over limit, above hold, monthly limit, copied passport, out of scope, lifecycle, wrong currency, replay), the raw verifier output |
| `/customer` | A business inside its bank's app | Overview (balance, AI agents, transactions with the agent's payments among the rest), notifications and Needs your attention (the first-payment confirmation, held payments to approve or decline with a note), the evidence trail, the mandate page (sign, amend, revoke) |
| `/bank` | The bank's payments risk team | Activity (every instruction today, why it was processed, held or refused, the nine checks per row), Needs attention (held payments and fraud indicators, with approve and decline), agent network, outcomes, statistics by agent, payment intent, region, model provider and AI product, active AI agents, AI products (the register and approvals), supervisory access exports, the evidence trail with replay |
| `/bank?ref=REG-2026-0014` | The bank officer | Approval decision for one registered product: the filing, the seven checks, the review assistant, ceilings scaled by the assurance level, the hold condition |
| `/provider` | The bank officer | Register an AI product: the filing form with one prefill for the demo |
| `/about` | Policy readers | How it works, the policy context, the passport, the rules, the standards, what this is not |

Test access: the demo is public. The tax demonstrator at `/tax/` is behind basic auth; credentials are in the submission notes on NayaOne. Keep-alive: the host stays up until at least 18 September 2026.

## The passport

An envelope of three Ed25519 JWTs, each signed by the only party entitled to the claim:

```json
{
  "passport_id": "AP-2026-0107",
  "admission":      "<JWT signed by the BANK>      approved product (registration ref, id, pinned version, hash of the register's receipt), assurance level, ceilings, hold condition, validity, binds → agent_identity hash",
  "agent_identity": "<JWT signed by the CUSTOMER>  its deployment: agent id, public key (cnf), product, config SHA-256, key custody, proof of possession",
  "mandate":        "<JWT signed by the CUSTOMER>  actions (the filed payment intent), currency, payee allow-list by account with the register check, per-payment limit, 30-day limit per account, payments per day, expiry, account tier, version (RFC 9396 authorization_details)",
  "status_url": "/api/status/AP-2026-0107",
  "vouch_voucher_id": "…"
}
```

Public keys: `GET /api/signers` (register, bank, customer). Every instruction is signed by the AI agent's key over canonical JSON and carries a nonce; R.4 verifies the bytes and refuses a nonce seen before. Flipping one byte fails it. Plain words: each AI agent deployment holds a key only it can use; the bank challenges that key on every payment, so a copied name or a lookalike model cannot answer.

## Rules (rule pack `payments-2026.09.7`, data not code)

At registration: F.1 provider at Companies House · F.2 accountable principal with signed declaration · F.3 insurance in force at or above the minimum · F.4 product documented with a pinned model version · F.5 Independent Assurance Evidence attached, with its assurance level, covering the use case · F.6 not already on the register · F.7 UK data protection declared (UK GDPR and DPA 2018 compliance, ICO registration, retention period). Completeness only; a flag is recorded, not judged.

| At the bank, in order | A failed check holds for review with |
|---|---|
| R.1 admission signature (bank key) | `ADMISSION_SIGNATURE_INVALID` / `PASSPORT_NOT_ISSUED` |
| R.2 passport active and unexpired (bank's list) | `PASSPORT_NOT_ACTIVE` |
| R.3 agent identity signature (customer key), bound to this admission | `AGENT_IDENTITY_SIGNATURE_INVALID` |
| R.4 instruction signed by the AI agent key in `agent_identity.cnf`, nonce not seen before | `AGENT_SIGNATURE_INVALID` / `REPLAY_DETECTED` |
| R.5 mandate present, customer-signed, unexpired, not revoked | `MANDATE_NOT_SIGNED` / `MANDATE_SIGNATURE_INVALID` / `MANDATE_EXPIRED` / `MANDATE_REVOKED` |
| R.6 action and currency permitted, payee account on the allow-list | `OUT_OF_SCOPE` / `CURRENCY_NOT_PERMITTED` / `PAYEE_NOT_ON_MANDATE` |
| R.7 amount within the per-payment limit | `PER_PAYMENT_LIMIT_EXCEEDED` |
| R.8 30-day total for this account and payments per day within the mandate (bank ledger) | `MONTHLY_LIMIT_EXCEEDED` / `DAILY_COUNT_EXCEEDED` |
| R.9 amount above the bank's hold condition; or the first payment under a mandate version | ESCALATE `HUMAN_CONFIRMATION_REQUIRED` / `FIRST_PAYMENT_CONFIRMATION_REQUIRED` |
| otherwise | ALLOW `WITHIN_MANDATE` |

Nothing is refused silently: a failed check holds the instruction (`ESCALATE` with `failed_check`) for a named person, who approves or declines it with a note; every such decision is a receipted chain entry. Two properties are kept apart: determinism (replaying the recorded inputs of any decision yields the same decision, the replay button) and replay protection (resubmitting the same signed instruction is refused at R.4).

Every held check carries a failure class, mapped once in the rule pack: fraud indicator (a payee not on the mandate, an invalid signature, a passport not in force, a replayed instruction) goes to the bank's Needs attention; agent error (amount, currency, action, frequency, an expired or revoked mandate) is a quality signal for the agent's owner, shown to the customer and never raised as an alarm. Assurance levels (self-declared ×0.25, independently verified ×0.5, independently audited ×1) scale the bank's ceilings; account tiers (personal current, business current, business savings) cap every mandate. `fixtures/pay/oracle.json` holds 20 deterministic cases; `tests/test_pay.py` runs them all offline, plus tamper, replay, cascade, containment, amendment, revocation, decisions, search and evidence tests.

## Evidence for a supervisor

`GET /api/evidence/passports/{id}` and `GET /api/evidence/violations/{id}` return one self-verifying bundle: the register entry and its receipt, the bank's approval, the agent identity, the mandate, every verification with its inputs and bank-signed receipt, the refusals with the invoice extraction that produced them, and the chain status, verifiable with the published keys. The export is read-only and is itself recorded in the chain. Who sees what: the customer sees its own agent's error pattern, the bank sees instructions, checks and verdicts, a supervisor sees evidence on request. Nothing reports automatically to an authority.

## vouch.finance

`pay/vouch.py` mirrors the mandate as an AI Voucher on the hackathon sandbox when the customer signs; revoking the passport or the mandate revokes the voucher, so one action is refused on two rails. With `PAYMENT_RAIL=vouch`, each allowed payment is settled as intent, quote and authorise on a mirror program. `scripts/vouch_kit_replay.py` replays both sponsor kits through the verifier and scores against their labels.

## API

```
POST /api/registrations · /{id}/prefill · PUT /{id}/fields · POST /{id}/submit     the bank registers a product (F.1 to F.7, signed receipt)
POST /api/registrations/{id}/review                                                the approval review assistant (six steps, never decides)
POST /api/registrations/{id}/admission            {decision: admit|request_info|decline, note, hold_above}   the bank's approval
POST /api/registrations/{id}/admission/status     {status: suspended|active|revoked, reason}: cascades to every passport on the product
POST /api/agents                                  {registration_id, agent_name}: the customer registers its AI agent on a bank approved product
POST /api/passports/{id}/mandate/check · /mandate/sign                             ceiling containment; signing issues the passport and mints the voucher
POST /api/passports/{id}/mandate/amend · /mandate/revoke                           a new customer-signed version supersedes the last (retained); revocation ends the mandate
POST /api/passports/{id}/status · /investigation                                   suspend, investigate, revoke, reinstate
GET  /api/passports/{id} · /api/status/{id} · /api/signers
POST /api/agent/act · /api/agent/invoice · /api/agent/replay                        the simulated AI agent signs and presents an instruction, or replays the last one
GET  /api/companies/{number} · /api/companies/search?q=                            Companies House public register, or the labelled demo register
POST /api/verify                                                                   the bank's gateway: decision, rule, code, reason, receipt, rails, settlement
GET  /api/audit · POST /api/audit/{id}/replay · GET /api/receipt/verify?token=
POST /api/audit/{id}/decide {decision: release|refuse, note}                        a held payment, decided by a named person
POST /api/audit/{id}/confirm-first {decision: confirm|refuse}                       the first payment under a mandate version, confirmed by the customer
GET  /api/evidence/passports/{id} · /api/evidence/violations/{id}                   supervisory access
GET  /api/violations · /api/violations/{id} · /api/passports/{id}/vouch · POST /api/registrations/{id}/file-note
GET  /api/state · /api/bank/state · /api/bank/audit · /api/customer/snapshot         what the views read (the bank's other customers are synthetic, in memory only)
POST /api/demo/seed?stage=registered|issued|history · POST /api/reset · GET /api/health · GET /api/rulepack
```

Interactive documentation at `/api/docs`.

## Deploy

```bash
bash deploy/publish.sh bank     # cdir.legislabs.uk: container cdir-bank behind Caddy; the tax demonstrator stays at /tax/
```

Docker Compose on a single host; Caddy terminates TLS. The publish script rsyncs the tree, builds, restarts the container, reloads Caddy and checks health. Only the variables the containers read are copied from the local `.env`.

## Third-party components and licences

| Component | Use | Licence |
|---|---|---|
| Python 3.12 | Runtime | PSF |
| FastAPI 0.141, Starlette | Web framework | MIT, BSD-3 |
| Uvicorn 0.52 | ASGI server | BSD-3 |
| Jinja2 3.1 | Templates | BSD-3 |
| Pydantic 2.13 | Request models | MIT |
| python-multipart | Form parsing | Apache-2.0 |
| cryptography 50 | Ed25519 keys and signatures | Apache-2.0 / BSD-3 |
| PyJWT 2.10 | JWT encoding and verification (EdDSA) | MIT |
| httpx 0.28 | HTTP client for vouch.finance and Companies House | BSD-3 |
| google-genai 2.16 | Gemini API client (optional; invoice reading and file-note drafts) | Apache-2.0; Google API terms apply to the service |
| pytest 8.4 | Tests | MIT |
| Playwright (tests only, not shipped) | Browser walk | Apache-2.0 |
| Chart.js (`pay/static/vendor/chart.umd.js`) | Landing and bank statistics charts | MIT |
| Mermaid (`pay/static/vendor/mermaid.min.js`) | The problem diagram on the landing page | MIT |
| Plus Jakarta Sans via Google Fonts | Dashboard typeface | SIL Open Font License 1.1 |
| Caddy 2, Docker | Reverse proxy and containers (deployment only) | Apache-2.0 |
| vouch.finance hackathon sandbox | Voucher rail (optional) | Hackathon sandbox terms |
| Companies House Public Data API | Payee and provider register check (optional) | Companies House API terms; data under the Open Government Licence v3 |
| Photo `pay/static/photos/cambridge-kings.jpg` | Landing hero (King's College Chapel, Cambridge) | Supplied by the team; licence to be confirmed before publication |
| Partner logos in `pay/static/logos/` | Hackathon partners strip | Trademarks of their owners, shown as hackathon partners; no endorsement implied |

Everything else in this repository was written by the team during the hackathon. Legis Labs Ltd retains the intellectual property; the organisers hold the licence set out in the participant guide to review, publish and showcase the submission. No open-source licence has been attached yet.

## Data

All firms, people, accounts, invoices, keys and records are synthetic and generated by the app. No real personal data, confidential supervisory information or proprietary dataset is used or included. API keys live in `.env`, which is not committed; `.env.example` documents them. The bank's "other customers" on the dashboard are in-memory synthetic rows and are never written to the database.

## Not claimed

That any bank or register operates this today; that a passport replaces the provider's authorisation, the customer's contract or the bank's own mandate; that Independent Assurance Evidence proves an AI agent is safe or correct; that a valid passport compels a bank to execute; that any regulator has approved, certified or endorsed anything here; that this is production cryptographic infrastructure. Developed alongside Cambridge academic and industry partners.
