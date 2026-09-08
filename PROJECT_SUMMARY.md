---
title: "Agent Passport: project summary"
subtitle: "Bank-side verification of AI agent payments. Legis Labs entry to the C:\\>DIR Global 'Agentic Regulator' Hackathon 2026, Know Your Agent problem space."
date: "8 September 2026. Repository state: branch bank-first-pivot at e0a608d, 192 commits. Live at https://cdir.legislabs.uk"
---

# 1. What the product is

Agent Passport is a pre-authorisation checkpoint for payments initiated by AI agents. It sits inside a bank's existing payment pipeline, alongside fraud detection and sanctions screening and before settlement, and replaces none of them. Before the bank moves money on an instruction from an AI agent, it verifies three signed documents and nine ordered checks. If any check fails, money does not move and the refusal is recorded in a hash-chained evidence trail the bank owns. A supervisor can request that evidence after an incident through normal supervisory processes and never operates the system.

The buyer is the bank. The bank offers the capability to its business customers who let AI agents pay suppliers. The commercial reason is authorised push payment fraud: £576 million in the UK last year, up 19 percent, and since 2024 the sending bank reimburses most of it. The regulator is involved only by exception: it reads evidence when it asks for it. Nothing in the product approves, certifies, licenses or endorses anything, and no regulator operates any part of it.

The proposed industry standard behind the product is APS 1001 (2026), revision 4, written as a candidate standard for an industry body on the Open Banking Implementation Entity model. The site is its reference implementation.

# 2. The three-layer model

Three parties sign, one party checks, one party reads.

1. **The provider files the AI product on an industry register.** Once. A filing records the legal entity, an accountable principal with a signed declaration, insurance in force, the product with a pinned model version, Independent Assurance Evidence with a declared assurance level, and the intended use. The register runs six completeness checks, F.1 to F.6, records the results next to the entry and signs a receipt. Nobody reviews the filing for quality. A filing that fails a check is still filed with the flag recorded.
2. **The bank admits the product to its own list.** Once. A named officer at the bank decides whether the bank's customers may delegate payments to the product. The admission sets ceilings every customer mandate must sit within (per payment, per payee account in 30 days, payments per day, expiry, permitted actions, currency) and a hold condition above which an instruction is held for a named person. A deterministic review assistant reads the filing, maps the bank's requirements, runs adversarial tests and a sandbox, and recommends; it never decides. The bank may require a minimum assurance level and scales its ceilings by the level declared.
3. **The customer signs the mandate inside its bank's app.** Once per version. The customer registers its AI agent deployment (a key pair the agent alone holds, proof of possession against a challenge, a configuration hash), writes its mandate (payee accounts, per-payment limit, 30-day limit per payee account, payments per day, expiry, currency) and signs it with the customer key. The bank checks containment against the lower of the admission ceilings and the account-type tier before the signature is accepted. Signing issues the passport: the bank signs the admission, the list shows the passport active, and a voucher is minted on the vouch.finance rail.
4. **The bank checks every payment.** Nine ordered checks, deny by default, no model inference at execution time. Every verification writes a chain entry with a bank-signed receipt and the exact inputs it used, so the decision can be replayed later.
5. **The evidence trail.** Every event is hashed onto the one before it. Refusals reach the bank's risk team as attention items; a supervisor can request the evidence for a passport or a refusal, and each export is itself recorded in the chain.

Who answers for what: the provider for the accuracy of its filing and the insurance it declared; the bank for its admission decision and for executing without checking; the customer for the mandate it signed and its deployment of the agent. The register holds the identities that make any failure attributable. The supervisor holds none of the infrastructure and can still reconstruct any incident.

# 3. The passport envelope

Not one token. Three independently signed JWTs, EdDSA over Ed25519 (RFC 8037), each signed by the only party entitled to the claim:

- **admission**, signed by the bank: the admitted product (registration reference, name, identifier, version, hash of the register's receipt), the assurance level declared, the ceilings scaled by that level, the hold condition, validity, the list pointer, and the hash of the agent identity it was issued for.
- **agent_identity**, signed by the customer: the deployment, its agent key as an RFC 7800 `cnf` claim, proof of possession, configuration hash, key custody.
- **mandate**, signed by the customer: an OAuth 2.0 Rich Authorization Request (RFC 9396) `authorization_details` object with actions, currency, the payee allow-list by account (with the public-register record of each payee where one was checked), per-payment limit, 30-day limit per payee account, maximum payments per day, expiry, the account type and customer class the limits derive from, a version number, and what it supersedes.

The register signs a receipt for the filing that the admission cites by hash. Remove any one signature and the bank refuses. Every instruction the agent then signs carries a nonce, a value used once, so the same signed instruction cannot be presented twice.

Plain words: each AI agent deployment holds a key only it can use; the bank challenges that key on every payment, so a copied name or a lookalike model cannot answer.

# 4. The nine checks at the bank

Rule pack `payments-2026.09.6`, data not code. Evaluated in order; the first failure stops the run.

| Check | What it verifies | Failure codes |
|---|---|---|
| R.1 | Admission signature genuine (bank key) | PASSPORT_NOT_ISSUED, ADMISSION_SIGNATURE_INVALID |
| R.2 | Passport active and unexpired on the bank's list | PASSPORT_NOT_ACTIVE |
| R.3 | Agent identity signature genuine (customer key), bound to this admission | AGENT_IDENTITY_SIGNATURE_INVALID |
| R.4 | Instruction signed by the agent key inside agent_identity, with a nonce not seen before | AGENT_SIGNATURE_INVALID, REPLAY_DETECTED |
| R.5 | Mandate signed by the customer, unexpired, not revoked | MANDATE_NOT_SIGNED, MANDATE_SIGNATURE_INVALID, MANDATE_EXPIRED, MANDATE_REVOKED |
| R.6 | Action and currency permitted, payee account on the customer-signed allow-list | OUT_OF_SCOPE, CURRENCY_NOT_PERMITTED, PAYEE_NOT_ON_MANDATE |
| R.7 | Amount within the per-payment limit | PER_PAYMENT_LIMIT_EXCEEDED |
| R.8 | 30-day total for this payee account and payments per rolling day within the mandate | MONTHLY_LIMIT_EXCEEDED, DAILY_COUNT_EXCEEDED |
| R.9 | Hold conditions: an amount above the hold condition is held for the customer's named approver; the first payment under a mandate version is held for the customer's own confirmation | HUMAN_CONFIRMATION_REQUIRED, FIRST_PAYMENT_CONFIRMATION_REQUIRED (ESCALATE) |

Outcomes: ALLOW (money moves, a payment row is written, settlement on the local rail or vouch.finance), ESCALATE (held for a person), DENY (refused, a violation row is written with its class).

Determinism and replay protection are two different properties. Determinism: replaying the recorded inputs of any decision yields the same decision, which is what the replay button on the evidence trail does. Replay protection: resubmitting the same signed instruction is refused as a duplicate, which is what R.4 does.

# 5. Two classes of refusal

Every refusal carries exactly one class, mapped once in the rule pack next to the rules so the console labels and the About page cannot drift apart.

- **Fraud indicator**: something the customer never authorised. A payee account not on the mandate, an invalid signature, a passport not in force, a replayed instruction, a key or record mismatch. Routed to the bank's Needs attention strip and risk team; a supervisor can request the evidence.
- **Agent error**: the AI agent's own mistake inside its remit. An amount over a ceiling, a wrong currency, action or frequency, an expired or revoked mandate. A quality signal for the agent's owner, not a report to anyone. Never in the bank's attention strip; shown to the customer with a calm grey label.

The two classes have different colours and different text labels, so colour is never the only signal. Nothing reports automatically to an authority.

# 6. Human in the loop

Held payments need a person. The bank's console shows every held instruction and every fraud-class refusal first, newest first, with two verbs on held rows: Approve and release, Refuse and record. A confirm step names the officer, the customer's named approver, the amount and the payee. Either outcome writes its own chain entry with a bank receipt: who decided, when, on what, why; a release executes the payment; a refusal records "held payment refused by approver". The first payment under a new mandate version is held for the customer's own confirmation inside its bank app; after that, payments inside the mandate flow without a person.

# 7. Assurance levels, account tiers, customer classes

Three assurance levels the provider declares with its evidence, none certified by anyone: self-declared (ceiling factor 0.25), independently verified (0.5), independently audited (1.0). The demo bank admits at independently verified or above.

Policy ceilings: £10,000 per payment, £50,000 per payee account in 30 days, hold above £5,000, up to 20 payments a day, expiry no later than 31 March 2027, minimum insurance cover £1,000,000.

Account tiers, because an AI agent is a payment channel on the account: personal current £2,500 a payment, £10,000 per account in 30 days, 10 a day; business current £10,000, £50,000, 20; business savings £25,000, £100,000, 5. Customer classes individual, micro, sme and large carry a default account type. Every mandate sits at or below the lower of the admission ceiling for the product and the tier for the account. The customer's form shows the maximum it can grant before it writes anything.

# 8. Mandate lifecycle

- **Write and sign.** The form starts empty. One "Prefill demo data" action with a context panel fills the demo values. The containment check runs as the customer types; signing is disabled until it passes.
- **Payees, name first.** Type a supplier's name and the public register lists matches (legal name, company number, status, registered office town); pick one and the number, legal name and status fill themselves. Entering a company number directly still works. The customer adds only the sort code and account number, because Companies House holds no bank accounts and reports what companies filed, not that they are legitimate. The check result travels in the signed mandate. Confirmation of Payee is noted as planned, bank-side.
- **Amend.** From the agent card, "Amend mandate" opens the form prefilled with the current values. Signing produces version N+1, signed by the customer, superseding version N, which is retained on record. The chain entry records the version, the signer and every field that changed. The verifier enforces the newest version on the next instruction. Amendments outside the ceilings are refused inline.
- **Revoke.** Ends the mandate at once with its own chain entry; the voucher on the vouch rail is revoked with it; the verifier refuses at R.5 with MANDATE_REVOKED from the next instruction.

# 9. The bank dashboard

The bank's operational view, styled as a fintech app card: a greeting header with tool icons (register a product, customer view, how it works, live indicator), then:

- **At a glance**: value moved, processed, awaiting a person, refused (fraud), refused (agent error), agents on the list, with carried-forward synthetic totals labelled as such.
- **Needs attention**: every held instruction and every fraud-class refusal, newest first, five visible with a count of the rest, the legend line explaining the two classes, and the decide verbs. Empty state: "Nothing needs attention. All AI agent payments inside mandate."
- **Active AI agents**: each passport with its customer, product, assurance badge, limits, processed, held and refused counts split by class, and the last event.
- **Recent activity / full log**: every instruction with a status chip (Processed, Held, Held · first payment, Processed · released by approver, Processed · confirmed by the customer, Refused · by approver, Refused · fraud indicator, Refused · agent error), payee, amount, rule, proof. A row expands to the instruction as signed (including its nonce and hash), the nine checks with their notes, the verdict and class, the hold context and decision, and the proof (chain entry, previous hash, rule pack, receipt).
- **Statistics**: session totals, a payment-volume chart per minute, a per-agent table (payments, value, held, refused fraud, refused error). Caption: these figures are the bank's own operational view; a supervisor sees evidence per incident, not this dashboard.
- **Evidence trail**: every chain entry, chain status and head, "Replay every verification" with the count replayed identically, evidence bundle exports per passport.
- **Admissions, the register and supervisory access**: admitted products with hold and agent counts; the register with assurance badges and the bank's decision per product and a "Register an AI product" button; supervisory access exports with the sentence "A regulator does not operate this dashboard and approves nothing in it."

The admission page for one registration shows what the provider filed, the six filing checks, the review assistant's six steps, the ceilings implied by the declared level and its multiplier, and the decision card, whose inputs start empty with one prefill and a context panel. The passport page shows the three-signer envelope verified live, the vouch rail status, lifecycle controls (suspend with a reason, reinstate, two-step revoke), the refusals table with classes, incidents and history.

# 10. The customer dashboard

The bank's app as the business customer sees it: greeting, balance card with the account number and the bank wordmark, tabs for Overview and Transactions. Left: the AI agents card (product with assurance badge, passport id, limits, currency, expiry, payees, paid this month, held, refused split into own errors and fraud indicators stopped by the bank, Amend and Revoke). Middle: own statistics and the evidence trail with the same status chips, the legend line, and a full-trail toggle. Right: notifications in plain language, including "Your confirmation needed" for the first payment under a mandate with Review and confirm. Transactions tab: ordinary account lines with a running balance and the AI agent's lines among them, refused and held ones marked.

Adding an agent: pick an admitted product (assurance badge shown), name the deployment, and the app generates the key, proves possession against the bank's challenge and records the configuration hash. Then the mandate card and form as in section 8.

# 11. The Action Terminal

The demo story: "An invoice lands on your desk." Two worlds on tabs.

- **Before the standard**: an altered invoice arrives with an urgent notice that the supplier's bank details have changed. The AI agent reads it and pays 60-11-22 99887766. The bank sees an instruction and three green checks. "Executed. Money gone." The bank could not tell an AI agent had typed it.
- **After the standard**: the same invoice. The agent declares first what it intends to pay and to which account the customer signed for, then reads the document, then signs an instruction to the changed account. The bank fetches the passport, R.1 to R.5 pass, R.6 fails: the payee account is not on the customer-signed allow-list. "Denied. The document changed the destination, not the AI agent. Money never moved."

An expert console at /terminal?console=1 runs ten scripted beats against the live verifier: a clean payment, a redirected invoice, an amount over the limit, a payment above the hold, five repeats that exhaust the 30-day limit, a copied passport with a rogue key, an action the mandate never granted, a lifecycle probe after suspension, a USD instruction, and a byte-for-byte replay. Each beat shows the nine checks resolving and the receipt. An optional delegation chain prototype (orchestrator delegates to an execution agent; each hop can only narrow authority) sits behind a switch.

# 12. Evidence and supervision

Every chain entry has a timestamp, kind, subject, the entry body, the previous hash, its own hash and, for verifications and human decisions, a receipt signed by the bank's key over the passport, decision, rule, code, instruction hash and chain hashes. The verification entry stores the instruction as signed, the passport status, the presented envelope, the ledger total and daily count before, whether the nonce had been seen, the instruction hash, the decision, rule, code, reason, class and the full per-rule trace. A replay re-runs the pure verification function from those inputs and reports whether the decision is identical.

Evidence bundles at `/api/evidence/passports/{id}` and `/api/evidence/violations/{id}` return the passport, its register entry with the receipt verified, the envelope with its three signatures verified, the violations, the audit entries and the chain status. Each export is logged as an evidence event with the requester.

Who sees what: the customer, and conceptually the provider, sees its own agent's error pattern; the bank sees instructions, checks and verdicts; a supervisor sees evidence on request. The 8 September audit found that this separation is visual today: the APIs return the same data to any caller, and an incident bundle is passport-wide. Both are listed under known gaps.

# 13. Companies House and vouch.finance

Companies House Public Data API: name search and number lookup with basic-auth from `COMPANIES_HOUSE_API_KEY`, a two-minute backoff on rate limit responses, and a graceful fallback to a labelled synthetic register (`fixtures/pay/registry.json`) when the key or the API is unavailable, so the demo never breaks. Results are always labelled with their source. The live host runs in the labelled demo mode because no key is configured there.

vouch.finance: when the customer signs, the mandate is mirrored as an AI Voucher; when the bank allows a payment, settlement runs through intent, quote and authorise on the vouch rail (PAYMENT_RAIL=vouch) or the local rail; revoking the passport or the mandate revokes the voucher, so one action refuses on two rails. Fixture mode reproduces the rail deterministically.

Gemini is used at the edges only: the AI agent reads invoices into payment instructions with a verbatim quote per fact, and the bank's officer can ask for a draft file note. It never checks, scores, admits or verifies. If the API is unavailable the system falls back to a deterministic fixture and says so in the footer.

# 14. Policy context on the site

- HM Treasury's consultation "Modernising Payment Services Regulation" (published 14 July 2026, closing 6 October 2026), section 3.2 on agentic payments and question 15 on authentication, consent and liability. The passport authenticates the agent, the signed mandate is the customer's consent, the evidence trail is the liability record.
- The consultation's Open Banking chapter as the governance model: a not-for-profit Future Entity sets standards, industry adopts them voluntarily, the FCA sets guardrails and receives information without building or approving the technology. APS 1001 is written for such a body on the precedent of the Open Banking Implementation Entity under the CMA Order.
- The FCA AI Lab's Supercharged Sandbox, whose second cohort names agentic payments as a priority, as the intended testing environment. Stated as an intention; it implies no FCA involvement or endorsement.
- UK Finance: £576 million authorised push payment fraud last year, up 19 percent; the sending bank reimburses most of it since 2024.
- Technical standards: OAuth 2.0 RAR (RFC 9396) in line with NIST NCCoE 2026 guidance, W3C Verifiable Credentials JWT profile (RFC 7519), RFC 7800 key binding equivalent to SPIFFE SVID, Ed25519 (RFC 8037) compatible with did:key, FATF 2025 guidance on AI-enabled circumvention of AML/CFT identity controls, ISO 20022 pain.001 field mapping, UK Faster Payments rail semantics.

What this is not: not a payments rail (it authorises; vouch.finance and the bank's rails settle); not an AML or sanctions system (it runs beside them and reports into neither); not a regulator's operating tool (supervisors read evidence, they run nothing); not model certification (the register files evidence, each bank makes its own admission decision).

# 15. Architecture and code

FastAPI and Jinja2 with SQLite from the standard library, PyJWT and cryptography for Ed25519, vanilla JavaScript, Chart.js and Mermaid vendored. No framework on the front end. Three signing keys, register, bank and customer (Northgate), published at `/api/signers`.

| Path | Role |
|---|---|
| `pay/main.py` | Routes, views, seed, verify, decisions, mandate sign, amend and revoke, evidence bundles |
| `pay/rules.py` | Filing checks F.1 to F.6, runtime checks R.1 to R.9, containment, effective limits, refusal classification |
| `pay/crypto.py` | Ed25519 key pairs, JWT sign and verify, envelope verification, nonces, JWK thumbprints |
| `pay/audit.py` | Hash chain and bank-signed receipts, chain verification |
| `pay/db.py` | Schema: registrations, passports (with mandate versions and revocation), payments, audit, violations, nonces, kv; migrations |
| `pay/review.py` | The admission review assistant: filing read, requirement map, adversarial tests, sandbox, recommendation, officer decision |
| `pay/companies_house.py` | Live API with backoff and labelled synthetic fallback |
| `pay/vouch.py` | Voucher mint, settlement, revocation; fixture and live modes |
| `pay/extraction.py` | Invoice reading via Gemini or fixture, blank and prefilled registration fields |
| `pay/fixtures.py` | Demo beats, chain beats, invoice tasks, register entries, opening statistics |
| `rulepacks/payments-2026.09.json` | The rule pack: rules, codes, policy, tiers, classes, assurance levels, failure classes, planned fields |
| `fixtures/pay/` | Registration fixture, register entries, synthetic company register, customer mandate draft, agent draft, invoices, oracle |
| `pay/templates/` | home, about, provider, bank, customer, terminal, bank_console, base |
| `pay/static/` | app.js, terminal.js, app.css, dashboard.css, fx-pages.css, terminal.css, brand assets, APS 1001 PDF and page images |
| `docs/v6_bank_first/APS_1001.txt` | The standard, revision 4 |
| `deploy/` | Docker Compose, Caddy drop-in, publish script |
| `tests/test_pay.py` | 49 test functions covering the API, rules, oracle cases, seeds, decisions, amendments, revocation, search |
| `tests/ui/walk_bank_first.py` | A Playwright walk of the whole journey, 117 checks, run locally and against the live host |

Routes: `/`, `/about`, `/provider`, `/bank` (dashboard, `?ref=` admission case, `?passport=` passport page, `#bd-trail` evidence trail), `/customer` (`?ref=` mandate card, `&amend=1`), `/terminal` (`?console=1` expert console). `/audit` and `/regulator` redirect to the bank.

API: health, rulepack, signers, state, companies search and lookup, registrations (create, prefill, fields, submit, review, admission, admission status, file note), agents, passports (status, investigation, vouch, mandate check, sign, amend, revoke, get), status lookup, agent act, replay and invoice, verify, audit list, decide, confirm-first, replay, receipt verify, evidence bundles, reset, demo seed. Interactive docs at `/api/docs`.

Demo seed: `POST /api/demo/seed?stage=registered` (product filed, review run, ready for the bank), `issued` (admitted, mandate signed, passport active, no payments), `history` (issued plus a first payment held and confirmed, a processed payment, a refused replay, a refused USD instruction, a held payment above the hold condition). The footer's Reset demo seeds the history stage.

Deployment: Hetzner host 37.27.202.168, Docker Compose, container `cdir-bank` on cdir.legislabs.uk behind Caddy; the earlier tax demonstrator remains at cdir.legislabs.uk/tax/ behind basic auth and the pre-pivot site at pay.cdir.legislabs.uk. `bash deploy/publish.sh bank` rsyncs, builds, restarts and reloads Caddy; the server's environment is filtered from the local `.env` (Gemini, vouch, Companies House keys).

# 16. Cast, all synthetic

OpenPay Ltd files PayGPT 6.0 (registration REG-2026-0014, independently audited). Meridian Bank (demo), Payments Risk officer A. Ferreira, admits it with a £5,000 hold. Northgate Joinery Ltd (business current account 20-45-77 31908822, finance director Helen Marsh) deploys it as passport AP-2026-0107 with suppliers Fenwick Timber Ltd, Ashby Ironmongery Ltd and Coastline Glass Ltd. The register also carries Invoicely Agent 2, Brightwater Payables, LedgerLine Payables 3, OpenPay 5.6 (admitted), Clerk AP 1.4, SettleBot 3 (on the register, no decision), OpenPay 5.5 (lapsed) and OpenPay 5.0 (withdrawn). Supervisory access (demo) reads evidence.

# 17. Design and language rules

GOV.UK-derived component vocabulary from the pre-pivot site with the Legis Labs teal palette and white mark; the two dashboards, the register page and How it works share a fintech app-card shell. No em dashes anywhere in user-facing text. Vocabulary: "AI agent", "register", "filing", "admission", "mandate", "Independent Assurance Evidence", "refused", "held", "processed"; never "approved", "certified" or "licensed" toward a regulator. Every demo form starts empty with one "Prefill demo data" action and a context panel that introduces the cast.

# 18. Mentor feedback and how it was incorporated

Five mentors reviewed the product on 8 September: William (FCA strategy and architecture), Antoinette (technology policy), ABZ (lawyer, privacy), Juan (World Bank) and Ronel (Cambridge Digital Innovation).

Settled and done: registration not pre-approval with the regulator by exception; the bank as the buyer; fraud as the business case with the APP figures; two refusal classes with different colours, labels and routing; a status per payment; exceptions first; human in the loop with chained decisions; a statistics view; a currency field enforced at R.6; account-type tiers; a "What this is not" section; ISO 20022 and Faster Payments; the Companies House register in the payee whitelist; the HM Treasury consultation, the Open Banking precedent and the FCA AI Lab on the About page.

Partial: the landing hero does not yet lead with the invoice story or say "checkpoint alongside your fraud and sanctions checks"; customer classes carry no limits of their own; the plain-language identity sentence is on About only; the integration story lacks legacy-versus-modern detail; technical codes still surface in the bank log and the customer trail.

Not done: data minimisation in the data layer (every API returns everything to any caller; an incident bundle is passport-wide; no surface is labelled as the agent owner's screening tool); a stated "the bank offers this as a service"; a registry federation and cross-border roadmap line; the mandate-agreement parallel and the accounting side benefit; industry associations as a distribution path.

The full audit with 28 checkpoints, code citations, 80 screenshots and a prioritised fix list is in `AUDIT_REPORT.md` and `audit-screenshots/`.

# 19. Known gaps and planned fields

- Role-based filtering in the data layer, and incident-scoped evidence bundles.
- Customer-class ceilings of their own and an account-type selector on the mandate form.
- Delegation chains with attenuation (user to agent to sub-agent, each hop only narrowing authority) as a first-class passport structure; today an optional prototype behind a switch in the expert console.
- The escalation threshold as a first-class passport field the customer can tighten below the bank's hold condition.
- Confirmation of Payee, bank-side, on the account name.
- Registry federation and cross-border mutual recognition.
- Agent id, key thumbprint and mandate version as top-level fields in the verification entry (today inside the JWTs).
- The configuration hash is recorded at registration but not compared at verification time.

# 20. Timeline of the build

- Earlier: tax demonstrator (HMRC self assessment rule pack), then the payments vertical with an authority-approval model, deployed at pay.cdir.legislabs.uk.
- Pivot to bank-first: the authority-approval panel replaced by the industry register, bank admission and customer mandate; Legis Labs identity; deployment at cdir.legislabs.uk preserving the tax demonstrator at /tax/.
- Consolidation: assurance levels; currency, velocity, nonce replay; account-type tiers and customer classes; Companies House check; two failure classes; APS 1001 revision 4.
- Final revision: replay visible everywhere; classes visible everywhere; assurance badge everywhere; planned fields on record.
- Final big update: institutional design pass (later reverted to the pay.cdir vocabulary at the team's request, colours kept); status model; exceptions-first bank console with human decisions; statistics; mandate amendment and revocation; name-first Companies House search; empty forms with prefill and context; About additions (where it sits in the bank, what this is not, per-stakeholder paragraph, identity in one breath).
- Demo tailoring: evidence trail folded into the bank dashboard; register seeded with admitted products; dashboards, register page and How it works in the app-card shell; header menu reduced to Home, Customer dashboard, Bank dashboard, How it works; first-payment confirmation hold.
- 8 September: mentor feedback audit.

# 21. Submission checklist

- Live site: https://cdir.legislabs.uk, reseeded with `stage=history` before presenting, simulated traffic off.
- The standard: `pay/static/APS_1001.pdf`, revision 4.
- The story: the Action Terminal, Before then After, with the three signatures shown between them.
- The depth: the About page and this summary.
- The audit: `AUDIT_REPORT.md` with the fix list; the first eight items are small and should be done before the pitch on 17 September.
- Not claimed: that any regulator has approved, certified or endorsed anything here; that the figures in the demo are real; that the vouch, Gemini or Companies House integrations are production-grade.
