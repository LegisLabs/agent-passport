# Agent Passport — product state

**As of:** 6 September 2026, iteration 2, `main` (see git log; baseline `e266b2c`) · **Team:** Lexis Labs (Timotej Cvikl tech, Alexandra Tran product, Bernard Liu law/policy, Jean Burnazyan data/tests) · **Hackathon:** C:\>DIR Global 'Agentic Regulator', Know Your Agent problem space · **Submission:** 8 Sept 2026 23:59 AOE on NayaOne (deck, 3-minute video, GitLab repo, live URL kept up until 18 Sept) · **Demo and vote:** 16 Sept 12:00–15:00 BST · **Winners:** 18 Sept, Cambridge.

## 1. What the product is

Agent Passport is regulator-side infrastructure for autonomous AI agents: an authority verifies an operator's evidence, a human officer approves with conditions, and the result is a signed, scoped, expiring, revocable credential that a relying party checks at the moment the agent tries to act. The relying party gets ALLOW, ESCALATE or DENY with a rule id, a reason code and a signed receipt. Every decision replays identically later.

Four design rules hold everywhere: the LLM only extracts facts from documents; versioned rule packs, stored as data, decide; a named human signs; an append-only hash chain records and replays. The passport carries permission, never personal data. Nothing is described as blockchain: signatures, a registry and a hash-chained log.

Pitch line: **identity is not authority.**

## 2. Two verticals, one engine

| | Payments (primary, built 5–6 Sept) | UK Self Assessment (transferability beat, built 4 Sept) |
|---|---|---|
| Live | https://pay.cdir.legislabs.uk, public | https://cdir.legislabs.uk, basic-auth `lexis` |
| Code | `pay/` | `app/` (frozen, git tag `hmrc-v1`) |
| Rule pack | `rulepacks/payments-2026.09.json` | `rulepacks/hmrc-sa-2026.09.json` |
| Authority | National Payments Supervisor (demo) | UK Tax Authority (demo) |
| Operator / agent | OpenPay Ltd (licensed payment-initiation provider) / PayGPT 6.0 | Smith & Co Accountants / smithco-sa-agent-01 |
| Principal | Northgate Joinery Ltd, finance director signs the mandate | Taxpayers with 64-8 / digital-handshake authorisation |
| Relying party | Northgate's bank | HMRC filing gateway |
| Credential | Envelope of three JWTs (authority, provider, customer) | One authority-signed JWT |
| External rail | vouch.finance sandbox (live) | none |

The tax vertical exists to show the same engine with a swapped rule pack. It has not been changed since 4 Sept and is not described further here; see `README.md` and `docs/PLAN.md`.

## 3. The payments scenario

Northgate Joinery Ltd pays suppliers through OpenPay Ltd, whose accounts-payable agent, PayGPT 6.0, reads invoices and initiates payments. Before deployment OpenPay applies to the payments supervisor with five synthetic documents: licence register extract, agent technical description (with the SHA-256 of the agent's configuration file), professional-indemnity insurance summary, accountable-person appointment letter, Northgate service agreement (supplier allowlist, limits, expiry). Eight automated checks run; officer A. Ferreira approves with a condition (hold anything above £5,000); the authority signs the assurance. Northgate's finance director signs the mandate. The bank verifies every instruction. The supervisor can suspend or revoke; three refused instructions raise an incident.

All firms, registers, accounts and documents are synthetic. Copy everywhere says this is a proposed framework, not a current legal requirement.

## 4. The composite passport

```
{
  "passport_id": "AP-2026-0107",
  "assurance":      JWT signed by the AUTHORITY  · provider, licence ref, KY-A status, checks passed/flagged,
                                                   condition {human_confirm_above}, accountable person, validity,
                                                   binds → sha256 of the agent_identity JWT
  "agent_identity": JWT signed by PAYRAIL        · agent name and id, public key (cnf.jwk), software, config sha256
  "mandate":        JWT signed by NORTHGATE      · supplier allowlist by account, per_payment_limit £10,000,
                                                   monthly_limit_per_account £20,000 P30D, expiry, passport_id
  "status_url": "/api/status/AP-2026-0107",
  "vouch_voucher_id": "<live voucher id>",
  "cnf": null
}
```

Each party signs only what it is entitled to say. The assurance is bound to the exact agent identity it was issued for; the mandate names its passport. Until the customer signs, the envelope is incomplete and the bank refuses at R.5. Public keys: `GET /api/signers`. Ed25519 (RFC 8037), JWT (RFC 7519), scope in RFC 9396 `authorization_details` shape, key binding in the RFC 7800 `cnf` pattern, registry status as status-list-style revocation.

## 5. Rules

**At application (authority):** A.1 licence resolves and active · A.2 Companies House resolves · A.3 accountable person with signed declaration · A.4 insurance evidenced, cover ≥ £1m, in force · A.5 agent key proof-of-possession (signed challenge) · A.6 customer agreement evidenced · A.7 limits within policy ceilings · A.8 software recognised and declared config hash equals the deployed file's hash. Every rule carries a CURRENT or PROTOTYPE label and a source. Failures flag for the officer; they do not block.

**At the bank, ordered, deny by default:**

| Rule | Check | Fails to |
|---|---|---|
| R.1 | assurance signature (authority key) | DENY `ASSURANCE_SIGNATURE_INVALID` |
| R.2 | registry status active, validity not ended | DENY `ASSURANCE_NOT_ACTIVE` |
| R.3 | agent identity signature (provider key), bound to this assurance | DENY `AGENT_IDENTITY_SIGNATURE_INVALID` |
| R.4 | instruction signed by the agent key in `agent_identity.cnf` | DENY `AGENT_SIGNATURE_INVALID` |
| R.5 | mandate present, customer-signed, unexpired, for this passport | DENY `MANDATE_NOT_SIGNED` / `MANDATE_SIGNATURE_INVALID` / `MANDATE_EXPIRED` |
| R.6 | action and currency granted; payee account on the allowlist | DENY `OUT_OF_SCOPE` / `PAYEE_NOT_ON_MANDATE` |
| R.7 | amount ≤ per-payment limit | DENY `PER_PAYMENT_LIMIT_EXCEEDED` |
| R.8 | 30-day total for this payee account + amount ≤ monthly limit (bank-held ledger) | DENY `MONTHLY_LIMIT_EXCEEDED` |
| R.9 | amount ≤ supervisor condition | ESCALATE `HUMAN_CONFIRMATION_REQUIRED` |
| | otherwise | ALLOW `WITHIN_MANDATE` |

The limit lives in the mandate; the running total lives at the bank, and the total at decision time is stored in the audit entry so replay is exact. Three DENYs on one passport write an "escalated to supervisor" incident row, visible in the bank terminal and the regulator's incident feed.

## 5c. 7 Sept: product-demo cut

- Names: the provider is OpenPay Ltd, the agent PayGPT 6.0 (agent id `openpay-paygpt-6`, provider signer `openpay`). Earlier registrations OpenPay 5.5 and 5.6 appear on the Provider Panel as synthetic history.
- Provider Panel is a hand-filled registration form with a Prefill (demo) button. The evidence pack and document extraction are gone: no automation on the regulatory side. Submitting carries the accountable person's acceptance of responsibility; the separate checkbox is gone. The sidebar shows only the provider's registered models.
- Header is a GOV.UK-style blue bar with a GOV·DEMO logo (square, not the crown).

## 5b. Iteration 3 (6 Sept): Issuance Flow v4, signature evidence, demo readiness

- Registration carries no customer data; A.6 and A.7 now check model documentation and key management. The assurance carries policy ceilings. The customer writes and signs its own mandate on the Customer Panel (prefilled from `fixtures/pay/customer/mandate_draft.json`), gated only by ceiling containment. The regulator's envelope panel shows the mandate as customer-signed with counts, never its content.
- Every verdict carries the R.4 signature result, the agent key fingerprint and the payload hash; tamper tests cover payload bytes, signature bits, rogue keys and each envelope JWT.
- Fixtures realigned to the script: Fenwick 10101010, poisoned invoice 99887766, boundary £12,000. Labels: interoperability line, ALL THREE VERIFY, credential format, five-layer captions. About carries the v9 A9 copy with the four adjustments.
- `POST /api/demo/seed?stage=issued|submitted` and `scripts/demo_reset.sh` restore a deterministic baseline; the audit page replays every verification on load. Tests: 69. Walks: `tests/ui/walk_eight_stages.py` plus the iteration-2, beats and chain walks.
- Deviation from the work order: it said the Issuance Flow v4 panels already existed. They did not; Task 3 built them.

## 5a. Iteration 2 (6 Sept): the agentic loop, the manipulation moment, the exception loop

- **Malicious invoice demo** (`/bank`, top panel). PayGPT 6.0 reads a clean or a poisoned invoice through the model (verbatim quote per field), signs the instruction it derived, and presents it. Four visible steps: what it read (account marked), the instruction it generated (wrong account in red), the bank's decision (R.6 with the FATF named-beneficiary note), and the caption "The AI read a manipulated invoice and would have paid the wrong account. The mandate stopped it." Every bank DENY now writes a violation row.
- **Standards Review Assistant** (`/regulator`, runs on opening a submitted case). Six visible steps: evidence read, standards rule map against the versioned pack, five adversarial tests, a sandbox run of those tests through the real R.1 to R.9 engine on a sandbox-signed envelope, a recommendation labelled "AI recommendation, human decision required", and the officer's existing sign-off. Nothing auto-approves.
- **Anomaly Detection & Escalation** (`/regulator`). Violations table with OPEN / INVESTIGATING / RESOLVED, a supervisor alert when the same rule is refused twice within 24 hours on one passport (policy `pattern_threshold`), and a panel-driven loop: suspend, open investigation (reads the extraction evidence), revoke or reinstate. INVESTIGATING blocks nothing by itself; the registry status does.
- **Standards labels** on the issuance surfaces (RFC 9396, W3C VC JWT, RFC 7800 cnf, Ed25519 RFC 8037, SPIFFE tooltip, OIDC-compatible JWT), "Regulatory Assurance (proposed FCA Agent Assurance addendum, PSR 2017 extension)" on the regulator, "Cryptographic Delegation Verifier, Zero Trust, deny by default" on the bank, About rewritten in the What it is / What it is not / Why now / Technical standards / Regulatory context structure. Tagline: delegation can only narrow authority, never expand it.
- **Delegation chain (Part B, off by default).** A toggle on the bank console splits the agent into an AP Orchestrator Agent (the key bound in `agent_identity`) and a Payment Execution Agent with its own key. The orchestrator signs a delegation JWT with a narrowed scope (one beneficiary, a ceiling, default £4,000); the execution agent signs the instruction. R.4 then verifies both signatures, and three chain checks run between R.5 and R.6: C.a root scope valid, C.b delegation ⊆ root (beneficiaries, ceiling, actions, validity), C.c action ⊆ delegation. Invariant shown as S_action ⊆ S_1 ⊆ S_0. Four boundary beats: valid chain ALLOW; £4,500 under a £4,000 delegation DENY C.c; a £12,000 delegation under a £10,000 root DENY C.b; a delegation to the poisoned account DENY C.b. The poisoned invoice with the chain on fails at C.b, because the orchestrator itself narrows to a beneficiary outside the root; the work order expected C.c, which is the case where a valid delegation is then exceeded (beat 2).
- Decision logic R.1 to R.9 unchanged; chain checks are additive and only run when a delegation is presented. Tests: 62. The Builder Guide A9 copy was not in the repo; the About text follows its structure and should be replaced verbatim by Bernard if wanted.

## 6. Views and demo beats

Views: `/provider` apply · `/regulator` review, condition, issue, lifecycle, vouch rail panel, incident feed, file note · `/customer` sign mandate · `/bank` verification console with status strip, per-account 30-day meters, both rails on every line · `/audit` hash chain and replay · `/about`. GOV.UK-adjacent visual language; the bank console is a black terminal.

Beats on `/bank`, in order (the video storyboard):

| # | Instruction | Result |
|---|---|---|
| 0 | anything before the customer signs | DENY R.5 |
| 1 | Fenwick Timber £3,200 | ALLOW, receipt, settled on the vouch rail |
| 2 | Fenwick Timber £2,750 to an unregistered account | DENY R.6, invoice redirection fraud |
| 3 | Ashby Ironmongery £11,400 | DENY R.7 |
| 4 | Coastline Glass £5,600 | ESCALATE R.9 |
| 5 | Fenwick Timber £4,900 repeated | ALLOW ×3 then DENY R.8 |
| 6 | Fenwick Timber £1,150 signed with a rogue key | DENY R.4 |
| 7 | Refund Fenwick Timber £3,200 | DENY R.6, action never granted |
| 8 | Ashby Ironmongery £900, lifecycle probe | ALLOW; after suspend DENY R.2; reinstate ALLOW; revoke DENY R.2 with the vouch voucher revoked too |

## 7. vouch.finance integration (live from the deployed site)

1. **Mandate lifecycle.** Approval mints an AI Voucher (`POST /ai-vouchers`) with our passport id in its metadata; the voucher id goes into the envelope. Revocation deletes it (`DELETE /ai-vouchers/{id}`). "Re-check on rail" reads `GET /ai-vouchers/{id}`. The bank console prints "authority registry revoked · vouch rail REVOKED · one supervisory action, two rails refuse".
2. **Payment settlement.** Our own manifest `fixtures/pay/vouch_kits/agent-passport-northgate.json` is seeded on the rail (`scripts/vouch_complete_seed.ts`): a program with the three suppliers as merchants, PayGPT 6.0 as actor with a mandate, and a rule hook for the allowlist and the £10,000 cap. With `PAYMENT_RAIL=vouch` every bank ALLOW is sent as intent → quote → authorize. Their policy engine independently enforces the same allowlist and cap. Refused instructions never reach the rail.
3. **Kit replay.** The sponsor's `kya-licence` and `agent-mandate` kits are seeded in our org and their stream was run; the ground-truth labels are vendored. `scripts/vouch_kit_replay.py` replays every scripted scenario through our verifier with signed envelopes and scores it: kya-licence precision 100%, recall 86%; agent-mandate precision 100%, recall 50%. Misses are named: delegation depth, merchant category, business hours, count-based structuring. Nothing compliant was refused.

Compatibility profile: `docs/KYA_extension_for_purpose_bound_value.md`. Not used: MCP, sub-agent delegation, `simulate_policy`, SSE, the arena scorer, the other two kits.

Known behaviour of their sandbox: the authorize step returns intermittent HTTP 500s (their own streams show the same). The adapter retries once, then executes on the local rail and says so on the console line. A 403 is shown as a rail-side decline. The bank's decision is never contradicted by a rail fault.

## 8. Where the model sits

Gemini 2.5 Flash, JSON mode, temperature 0, used twice: reading the evidence pack into a fixed schema with a source document and verbatim quote per fact, and drafting the officer's file note (verdict vocabulary rejected). It never checks, scores or decides. `EXTRACTION_MODE=fixture` replaces both with deterministic stand-ins; on API failure the system falls back and labels the result `gemini-fallback`. Live extraction reproduces the fixture value for value.

## 9. Verification status

| What | How | Result |
|---|---|---|
| Rules, envelope, ledger, incidents, replay, adapter, API contract | `pytest`, offline, both verticals | 48 passed |
| Every view and beat in demo order, desktop | Playwright walk-through against a local server | 45 checks, no problems |
| Six pages at 390px | same | no horizontal overflow |
| UI anti-pattern scan | impeccable detector | clean |
| Extraction | live Gemini on the five documents | matches fixture |
| Vouch | live mint, status, revoke, quote decline, authorize | confirmed; authorize intermittent on their side |
| Production | scripted API run inside the deployed container | all beats correct, live mint, live revoke, live settlement, chain intact, replay identical |

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`.

## 10. Operations

- **Hosting:** one Hetzner box (37.27.202.168), shared Caddy owned by the Compass deploy. Containers `cdir` (port 8013) and `cdir-pay` (port 8014) on the `deploy_default` network; Caddy drop-ins in `/opt/caddy-sites/`. SQLite and signer keys in Docker volumes; each app self-seeds on first run.
- **Publish:** `bash deploy/publish.sh [all|hmrc|pay]` rsyncs sources, ships a filtered `.env` (Gemini key, vouch key and rail ids), builds and restarts, reloads Caddy, checks health.
- **Environment (server):** `EXTRACTION_MODE=gemini`, `VOUCH_MODE=live`, `PAYMENT_RAIL=vouch`, `VOUCH_PROGRAM_ID`, `VOUCH_PRIVY_USER_ID`, `VOUCH_MERCHANTS`, `VOUCH_CATEGORY`. Defaults in code are fixture and local, so a clone with no keys runs the full demo offline.
- **Demo state:** shared server state, one "reset demo" link in the footer, public. Reset clears our database; it does not touch the vouch rail (programs there cannot be wiped).
- **Sandbox org:** "Legis Labs Ltd Hackathon" on cdir-portal.vouch.finance. Key in `.env` as `HACKATHON_ORG_API_KEY`, never committed; `context/` is gitignored because it holds NayaOne credentials.
- **Repos:** develop on GitHub `LegisLabs/agent-passport`; the deliverable must be pushed to the NayaOne GitLab sandpit before the deadline.

## 11. Repository map

```
pay/            payments vertical: main.py routes · rules.py · crypto.py (three signers, verify_envelope) · vouch.py · audit.py · extraction.py · db.py · fixtures.py · templates · static
app/            tax vertical, frozen
rulepacks/      payments-2026.09.json · hmrc-sa-2026.09.json
fixtures/pay/   documents/ · registry.json · extraction_fixture.json · oracle.json (18 cases) · agent_config.json · vouch_kits/ (manifests, labels, mirror program)
scripts/        vouch_kit_replay.py · vouch_complete_seed.ts
tests/          test_pay.py · test_rules.py
deploy/         Dockerfile · pay.Dockerfile · docker-compose.yml · *.caddy · publish.sh · requirements.txt
docs/           PRODUCT_STATE.md (this file) · PLAN.md · BRIEF_v3_Payments_Conversion.md · KYA_extension_for_purpose_bound_value.md · Demo Vertical Alignment (Bernard) · Tax_Field_Research · BRIEF_v2
```

## 12. Decisions taken during the build

- HMRC stays deployed and untouched as the transferability beat; payments is the primary story. Bernard's alignment note warned against sounding like a payments team; the framing throughout is a jurisdiction-neutral supervisor and a non-payment refusal (the refund beat) is in the script.
- Beat numbers as the brief settled them: cap £10,000, condition £5,000, monthly £20,000 per account.
- Unknown action types are refused at R.6 with `OUT_OF_SCOPE`.
- Incident after three refusals is a log row, not a workflow. The counter restarts after each incident.
- The payments site is public; the tax site keeps its gate.
- Production settles on the vouch rail despite their intermittent authorize fault, because the fallback is visible and the bank's decision stands.
- The eyebrow caption above headings from the tax build was dropped in the payments UI (impeccable craft floor); everything else keeps the GOV.UK-adjacent world.

## 13. Open items

1. **Submission package:** deck on the organisers' template, 3-minute video (the beat table is the storyboard), push to NayaOne GitLab, live URL until 18 Sept. Not started in this repo.
2. **Tax site gate:** still basic-auth; decide whether judges get the password or the gate comes off.
3. **Rail flakiness:** authorize 500s on the sandbox. Mitigated, not fixed; worth one message to hackathon@cdir.global or the Finternet Discord.
4. **Vouch key was pasted in chat once.** Rotate in the portal and republish if that matters.
5. **Recall gaps versus the agent-mandate kit** (categories, hours, count velocity) are documented as v1 limits. A v2 mandate could carry them; not planned before the deadline.
6. **Roadmap, stated on /about:** sub-agent delegation, multi-bank totals, an incident workflow, runtime attestation of the agent software, a JSON-LD verifiable-credential wrapper.

## 14. What we do not claim

That any supervisor issues agent passports today; that the passport replaces the provider's licence, the customer's contract or the bank's own mandate; that a signature proves an agent is safe or correct; that a valid passport compels a bank to execute; that this is production cryptographic infrastructure; that the tax demo is an HMRC integration.
