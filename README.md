# Agent Passport

Bank-side verification of AI agent payments. Lexis Labs entry to the C:\>DIR Global 'Agentic Regulator' Hackathon 2026, Know Your Agent problem space. Live at **https://cdir.legislabs.uk**. Proposed industry standard: [APS 1001, revision 4](pay/static/APS_1001.pdf).

**Identity is not authority.** An AI agent that can be identified can still act beyond what its principal allowed. Agent Passport separates the two and puts the check where the money and the liability are: at the bank.

## The model

| Layer | Who | What | How often |
|---|---|---|---|
| 1 Register | The provider (OpenPay Ltd) | Files its AI product on an industry register: identity, accountable principal, insurance, Independent Assurance Evidence for the use case. Completeness checks F.1 to F.6 are recorded; the register signs a receipt. Nobody reviews it. | Once |
| 2 Admit | The bank (Meridian Bank, demo) | Decides which registered products its customers may delegate to, with ceilings and a hold condition. A commercial risk decision by a named officer, assisted by a deterministic review tool that never decides. | Once |
| 3 Mandate | The customer (Northgate Joinery Ltd) | Inside its bank's app: picks an admitted product, a key pair is generated and possession proven, signs a mandate (payee accounts, per-payment limit, 30-day limit per account, expiry) within the bank's ceilings. The passport is issued at signing. | Once |
| 4 Check | The bank | Verifies passport and mandate on every instruction, R.1 to R.9, deny by default, and writes a signed audit entry either way. | Every payment |

The regulator appears in exactly one place: a supervisory access layer. Through normal supervisory and incident processes it can request one self-verifying evidence bundle per passport. It does not operate, approve, certify or license anything here.

One sentence: **the register does not certify that AI agents are good; it guarantees that someone is accountable when they are bad.**

### Where this sits in UK policy

HM Treasury's consultation [Modernising Payment Services Regulation](https://www.gov.uk/government/consultations/modernising-payment-services-regulation/modernising-payment-services-regulation-consultation) (14 July to 6 October 2026) says in section 3.2 that the Payment Services Regulations 2017 may not fully facilitate agentic payments and asks in question 15 how authentication, consent and liability should adapt. This prototype is one working answer: the passport (authentication), the signed mandate (consent), the evidence trail (liability). Its Open Banking chapter describes the governance we propose: an industry Future Entity sets the standard, banks adopt it commercially, the FCA sets guardrails and receives evidence. The FCA AI Lab's Supercharged Sandbox, whose 2026 cohort prioritises agentic payments, is the intended testing route, not an approver.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r deploy/requirements.txt
cp .env.example .env            # GEMINI_API_KEY, optional HACKATHON_ORG_API_KEY; or EXTRACTION_MODE=fixture
.venv/bin/uvicorn pay.main:app --reload --port 8014       # Agent Passport, bank-first
.venv/bin/uvicorn app.main:app --reload --port 8013       # the tax demonstrator (frozen, git tag hmrc-v1)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q   # 86 tests, fully offline
```

The app self-seeds signer keys into `data/pay/keys/` and SQLite alongside. `bash scripts/demo_reset.sh` (or the footer link, which seeds `stage=history`) restores the demo baseline: one product filed and admitted, one mandate signed, one passport ACTIVE; the history stage adds the customer's first-payment confirmation, one payment, its replay refused, one wrong-currency instruction refused and one payment held for the approver. Browser walk: `tests/ui/walk_bank_first.py` (Playwright).

## Surfaces

| Route | Who uses it | What it is |
|---|---|---|
| `/customer` | A business inside its bank's app | My AI agents: choose a product from the bank's list, sign the mandate, see activity |
| `/bank` | The bank's payments risk team | Bank console: live AI agents, registrations awaiting admission, admitted products, the register, flagged and blocked instructions, incidents, evidence export for supervisory access |
| `/terminal` | Everyone | Action Terminal: one invoice, two worlds. Before the standard the AI agent pays a mule account; after it, the bank's nine checks refuse it at R.6 |
| `/terminal?console=1` | Judges | Expert console: eight scripted instructions, the delegation chain, the raw verifier output |
| `/bank#bd-trail` | The bank, a supervisor | Evidence trail on the bank dashboard: hash chain, signed receipts, replay |
| `/provider` | An AI company | Register an AI product: a filing with completeness checks, not a review queue |
| `/about` | Policy readers | How it works, policy alignment, rules, standards, what is not claimed |

## The passport

An envelope of three Ed25519 JWTs, each signed by the only party entitled to the claim:

```json
{
  "passport_id": "AP-2026-0107",
  "admission":      "<JWT signed by the BANK>      admitted product (registration ref, id, pinned version, hash of the register's receipt), ceilings, hold condition, validity, binds → agent_identity hash",
  "agent_identity": "<JWT signed by the CUSTOMER>  its deployment: agent id, public key (cnf), product, config SHA-256, key custody, proof of possession",
  "mandate":        "<JWT signed by the CUSTOMER>  payee allowlist by account, per-payment limit, 30-day limit per account, expiry (RFC 9396 authorization_details)",
  "status_url": "/api/status/AP-2026-0107",
  "vouch_voucher_id": "…"
}
```

Public keys: `GET /api/signers` (register, bank, customer). Every instruction is signed by the AI agent's key over canonical JSON; R.4 verifies the bytes. Flipping one byte fails it.

## Rules (rule pack `payments-2026.09.6`, data not code)

On the register at filing: F.1 provider at Companies House · F.2 accountable principal with signed declaration · F.3 insurance in force at or above the minimum · F.4 product documented with a pinned model version · F.5 Independent Assurance Evidence attached and covering the use case · F.6 not already on the register. Completeness only; a flag is recorded, not judged.

| At the bank, in order | Fails to |
|---|---|
| R.1 admission signature (bank key) | DENY `ADMISSION_SIGNATURE_INVALID` / `PASSPORT_NOT_ISSUED` |
| R.2 passport active and unexpired (bank's list) | DENY `PASSPORT_NOT_ACTIVE` |
| R.3 agent identity signature (customer key), bound to this admission | DENY `AGENT_IDENTITY_SIGNATURE_INVALID` |
| R.4 instruction signed by the AI agent key in `agent_identity.cnf`, nonce not seen before | DENY `AGENT_SIGNATURE_INVALID` / `REPLAY_DETECTED` |
| R.5 mandate present, customer-signed, unexpired | DENY `MANDATE_NOT_SIGNED` / `MANDATE_SIGNATURE_INVALID` / `MANDATE_EXPIRED` |
| R.6 action and currency permitted, payee account on the allowlist | DENY `OUT_OF_SCOPE` / `CURRENCY_NOT_PERMITTED` / `PAYEE_NOT_ON_MANDATE` |
| R.7 amount within the per-payment limit | DENY `PER_PAYMENT_LIMIT_EXCEEDED` |
| R.8 amount + 30-day total for this account within the limit, payments per day within the mandate (bank ledger) | DENY `MONTHLY_LIMIT_EXCEEDED` / `DAILY_COUNT_EXCEEDED` |
| R.9 amount above the bank's hold condition; or the first payment under a mandate version | ESCALATE `HUMAN_CONFIRMATION_REQUIRED` / `FIRST_PAYMENT_CONFIRMATION_REQUIRED` |
| otherwise | ALLOW `WITHIN_MANDATE` |

**The people in the loop, graduated.** A person signs the mandate; a person confirms the first payment under each mandate version (held at R.9, `FIRST_PAYMENT_CONFIRMATION_REQUIRED`, decided by the customer in its bank app through `POST /api/audit/{id}/confirm-first`); a person decides anything above the bank's hold condition (held at R.9, decided by a named officer through `POST /api/audit/{id}/decide`, with a confirm step naming who records it); everything inside the mandate between those points flows on its own. Every one of those decisions is a receipted chain entry.

**Fewer, more meaningful rows.** The bank console leads with what needs a person (held payments and fraud-class refusals) and with the numbers: the tiles add this session's rows to totals carried forward from before the session (`fixtures/pay/opening_stats.json`, synthetic, stated as such next to the counters); the log is a thin recent-activity strip with the full log one click away; arriving instructions show their checks ticking through before the status lands (a "paced arrivals" toggle makes it instant). The customer hears about what matters to it, in the class's tone (fraud indicator, agent error, held, mandate lifecycle); routine payments stay in Transactions and in the full trail.

Every refusal carries a failure class: fraud indicator (redirection, copied passport, replay, forged claim), agent error (wrong amount, currency, action or frequency inside the agent's own remit) or passport status. Provider filings declare an assurance level (self-declared, independently verified, independently audited) that scales the bank's admission ceilings; every mandate is also capped by the account-type tier (agent-channel limit). Payees and providers are checked against Companies House (`COMPANIES_HOUSE_API_KEY`; without it, a labelled synthetic register answers).

`fixtures/pay/oracle.json` holds 20 deterministic cases; `tests/test_pay.py` runs them all offline, plus tamper tests, cascade, containment, the grounds declaration and the evidence bundle.

## Evidence for a supervisor

`GET /api/evidence/passports/{id}` and `GET /api/evidence/violations/{id}` return one bundle: the register filing and its receipt, the bank's admission decision, the agent identity, the mandate, every verification with its inputs and bank-signed receipt, the refusals with the invoice extraction that produced them, and the hash chain segment, verifiable with the published keys. The export is read-only and is itself recorded in the chain.

## vouch.finance

`pay/vouch.py` mirrors the mandate as an AI Voucher on the hackathon sandbox when the customer signs; revoking the passport revokes the voucher, so one action by the bank is refused on two rails. `VOUCH_MODE=fixture|live`, `PAYMENT_RAIL=local|vouch` (each ALLOW also settled as intent → quote → authorize on a mirror program). `scripts/vouch_kit_replay.py` replays both sponsor kits through the verifier and scores against their labels.

## API

```
POST /api/registrations · /{id}/prefill · PUT /{id}/fields · POST /{id}/submit     the provider files (F.1 to F.6, register receipt)
POST /api/registrations/{id}/review                                                the bank's admission review assistant (six steps, never decides)
POST /api/registrations/{id}/admission            {decision: admit|request_info|decline, note, hold_above}
POST /api/registrations/{id}/admission/status     {status: suspended|active|revoked, reason}: cascades to every passport on the product
POST /api/agents                                  {registration_id, agent_name}: the customer registers its AI agent on an admitted product
POST /api/passports/{id}/mandate/check · /mandate/sign                             ceiling containment; signing issues the passport and mints the voucher
POST /api/passports/{id}/mandate/amend · /mandate/revoke                           a new customer-signed version supersedes the last (retained); revocation ends the mandate, own chain entry
POST /api/audit/{id}/decide                                                        a named person releases or refuses a held payment; receipted chain entry
POST /api/passports/{id}/status · /investigation                                   suspend, investigate, revoke, reinstate
GET  /api/passports/{id} · /api/status/{id} · /api/signers
POST /api/agent/act · /api/agent/invoice · /api/agent/replay                        the simulated AI agent signs and presents an instruction, or replays the last one
GET  /api/companies/{number} · /api/companies/search?q=                            Companies House public register, or the labelled demo register
POST /api/verify                                                                   the bank's gateway: decision, rule, code, reason, receipt, rails, settlement
GET  /api/audit · POST /api/audit/{id}/replay · GET /api/receipt/verify?token=
POST /api/audit/{id}/decide {decision: release|refuse}              a held payment (R.9 hold condition), decided by a named person
POST /api/audit/{id}/confirm-first {decision: confirm|refuse}       the first payment under a mandate version, confirmed by the customer
GET  /api/evidence/passports/{id} · /api/evidence/violations/{id}                   supervisory access
POST /api/demo/seed?stage=registered|issued
```

## Deploy

```bash
bash deploy/publish.sh bank     # cdir.legislabs.uk: container cdir-bank; the tax demonstrator stays reachable at /tax/ behind basic-auth
bash deploy/publish.sh pay      # pay.cdir.legislabs.uk: the pre-pivot payments demo, left running for comparison
```

## Layout

```
pay/          the app: main.py · rules.py · crypto.py · review.py · vouch.py · audit.py · extraction.py · db.py · fixtures.py · templates/ · static/
app/          the tax demonstrator (frozen, tag hmrc-v1; now prefix-aware for /tax/)
rulepacks/    payments-2026.09.json (rule pack payments-2026.09.6) · hmrc-sa-2026.09.json
fixtures/pay/ registration_fixture.json · register.json · registry.json · customer/ · invoices/ · oracle.json · agent_config.json · vouch_kits/
scripts/      demo_reset.sh · vouch_kit_replay.py
tests/        test_pay.py · test_rules.py (offline) · ui/walk_bank_first.py (Playwright)
deploy/       Dockerfile · pay.Dockerfile · docker-compose.yml · *.caddy · publish.sh
docs/         v6_bank_first/APS_1001 (revision 4) · earlier briefs and revisions
```

## Where the model sits

Registration is a form. Gemini (JSON mode, temperature 0) is used by the AI agent to read invoices into payment instructions with a verbatim quote per fact, and optionally by the bank's officer for a draft file note. It never checks, scores, admits or verifies. `EXTRACTION_MODE=fixture` replaces both with deterministic stand-ins.

## Not claimed

That any bank or register operates this today; that a passport replaces the provider's authorisation, the customer's contract or the bank's own mandate; that Independent Assurance Evidence proves an AI agent is safe or correct; that a valid passport compels a bank to execute; that any regulator has approved, certified or endorsed anything here; that this is production cryptographic infrastructure. All firms, registers, accounts and documents are synthetic. Developed alongside Cambridge academic and industry partners.
