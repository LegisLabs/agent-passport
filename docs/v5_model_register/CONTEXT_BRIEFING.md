# Agent Passport — Context Briefing for Claude Code
Read this before MODEL_REGISTER_GOAL.md. It explains what this product is, who every party is, why it exists, and why we are restructuring the issuance flow. You are fine-tuning a working system two days before a hackathon submission — understand it before touching it.

---

## 1. What this is

**Agent Passport** is our entry to the C:\>DIR Global "Agentic Regulator" Hackathon (Problem Statement 4: Know Your Agent), built by team Legis Labs. Submission deadline: 8 September 2026, 23:59 AOE — deck, 3-minute demo video, and this repo as a testable prototype that judges' humans AND agents will actually clone, run, and compare against what the video claims.

**The problem:** companies are starting to let AI agents pay their invoices. A bank receiving a payment instruction today cannot tell whether it came from a human treasury manager or an autonomous AI agent, whether that agent was permitted to send it, or who answers when it goes wrong. JPMorgan Chase already adds behavioural friction to payments ("you only know this person through social media") because it cannot infer intent — and it still cannot distinguish human from agent.

**Our answer in one line:** *identity is not authority.* An agent can be perfectly authentic and still be manipulated into an action its human never approved. So we separate the two: a cryptographic passport proves who the agent is AND what it is allowed to do, and the bank verifies both on every single payment, deterministically, before money moves.

**The one thing the demo must prove:** a valid agent, from a registered provider, carrying a customer mandate, is manipulated by a poisoned invoice into requesting payment to an attacker's account. The mandate stops it (bank rule R.6, payee not on the customer-signed allowlist). The system records the violation. A human supervisor decides. That moment is the whole pitch.

---

## 2. Who is who (the four parties)

All firms, banks, accounts and people are SYNTHETIC — fixture data, clearly labelled. No real entity appears.

- **Model company — "OpenPay Ltd", maker of "PayGPT 6.0"** (which runs on a pinned foundation model). In the NEW flow this company only registers its model: documentation, benchmarks, training type, pinned version. A named person attests the documentation is accurate — a truthfulness declaration, nothing more. The company carries NO liability for what any agent later does. Its incentive: banks only execute payments from passported agents, so registration = market access; "passport-eligible" is a selling point.

- **Authority — "National Payments Supervisor (demo)"**, a fictional regulator representing a proposed Agent Assurance function under the UK Payment Services Regulations 2017. It approves the model ONCE (AI-assisted review, human officer decides and signs — the officer is fixture "A. Ferreira"), sets policy ceilings (max limits any mandate may contain) and a supervisor condition (hold payments above £5,000 for human confirmation). It maintains two registries: approved models and live passports. It NEVER sees individual mandates or transactions. It acts on patterns, escalation alerts, and bank reports, and can revoke a passport or a whole model (cascade).

- **Customer — "Northgate Joinery Ltd"**, authorising officer "Helen Marsh, Finance Director". The customer turns an approved model into THEIR agent: picks it from the register, an agent key is generated for their deployment (proof of possession, config hash), and they write and sign their own payment mandate — allowlisted payee accounts, per-payment cap, rolling 30-day cap per account, expiry — within the authority's ceilings. Live immediately, no review. The governing sentence of the whole redesign: **a model becomes an agent when a customer gives it a mandate.**

- **Bank — "Northgate's bank (demo)"**, the relying party. On EVERY instruction it runs nine ordered, deny-by-default rules (R.1–R.9): signature checks on all three envelope components, registry status lookup, instruction signed by the agent's own key, mandate validity, payee allowlist, per-payment limit, 30-day rolling limit, supervisor condition (ESCALATE). Deterministic, sub-10ms, no AI inference, no human in the loop at execution. Answers ALLOW / ESCALATE / DENY with a rule citation and an authority-signed receipt. The bank is liable if it executes without checking.

**The liability tree (all UI copy must be consistent with this):** model company answers only for documentation accuracy · customer answers for the mandate they signed and their deployment · bank answers for the check · authority holds the registries that make any failure reconstructable. Nobody loses except the attacker.

---

## 3. What the passport actually is (the crypto)

An envelope of three signed JWTs (Ed25519 / RFC 8037, real signature verification — flipping one byte fails it):

1. **Assurance** — signed by the AUTHORITY. In the new flow it covers the approved MODEL plus the policy ceilings and the condition.
2. **Agent identity** — binds the agent's public key (RFC 7800 cnf), the approved model reference, and the deployment config hash. In the new flow the CUSTOMER side signs this (their deployment of the approved model).
3. **Mandate** — signed by the customer's authorising officer. An OAuth 2.0 RFC 9396 Rich Authorization Request: payee allowlist by account, per-payment ceiling, 30-day ceiling, expiry.

Each party signs only what it is entitled to say; no party can alter another's claim. Every instruction is itself signed by the agent's key over a canonical JSON payload (R.4 verifies the bytes). Standards visibly labelled in the UI: RFC 9396, W3C VC JWT profile, RFC 7800 cnf, Ed25519 RFC 8037, Zero Trust deny-by-default (NIST NCCoE 2026), FATF 2025 AML alignment on the payee check. Everything is honest about being a prototype: CURRENT vs PROTOTYPE labels on rules, "design prototype", "no supervisor requires this today".

**Supporting machinery that already works and must keep working:** hash-chained audit log (sha256(prev_hash + entry)) where every decision is replayable from stored inputs; mandate mirrored as an "AI Voucher" on vouch.finance (revocation makes two rails refuse); anomaly detection panel (repeat violations raise a supervisor alert); suspend / investigate / revoke / reinstate lifecycle; a Gemini-based extraction layer that ONLY reads documents into fixed schemas with a verbatim quote per fact and drafts file notes — it never checks, scores, or decides ("models read and draft; rules decide; humans sign"); fixture mode that runs the entire demo offline with no API keys.

---

## 4. Why we are restructuring (the history, so you understand the leftovers)

**Old flow (what much of the current code/copy reflects):** a payment institution ("PayRail Ltd") applied to deploy a specific agent for a specific customer — the application even contained the customer's limits, an accountable person accepting responsibility for the agent's actions, and the provider's insurance. The authority effectively reviewed mandate content.

**Why that was wrong (team decision, adopted by everyone):** it made the provider author what only the customer should say; it required one authority review per customer (unscalable); and it put the authority's eyes on mandate content it has no need to see. Bernard's Builder Guide v9 formally adopted the separation ("architecturally wrong: bottleneck, mixed provider certification with customer authorisation").

**The final step (Tim's model-register proposal, what you are implementing):** go one further — the registrant is not an agent operator at all, it is the MODEL COMPANY, and it registers only the model. The agent does not exist at registration time. The customer creates the agent by giving the model a mandate. Consequences: insurance and "accepts responsibility for the agent's actions" leave the registration phase entirely (no owner for them there); the accountable person remains but their declaration becomes documentation-accuracy only; all deployment-specific material (agent key, PoP, config hash, key custody) moves to the customer's agent-creation step; the authority approves models, not deployments.

**Expect leftovers** from both older flows in copy, fixture documents, field names, and rule descriptions ("PayRail", "applies to deploy", customer limits inside applications, insurance evidence, responsibility declarations). Part of your job is a consistency sweep: every page must tell the three-phase story — register model → approve with ceilings → customer creates agent and mandate → bank enforces.

---

## 5. What must not change

- Bank behaviour on the demo beats: clean payment ALLOW; poisoned invoice (INV-9001, account swapped 10101010 → 99887766) DENY on the payee rule with the four-step on-screen sequence and the caption "The AI read a manipulated invoice and would have paid the wrong account. The mandate stopped it."; over-ceiling DENY; over-condition ESCALATE; rolling-limit DENY; rogue-key DENY; revoked-passport DENY; the full suspend/investigate/revoke/reinstate loop.
- Real cryptography everywhere it exists now (no field-matching), the audit chain, replay, vouch mirroring, fixture/offline mode, honesty labels.
- The tax vertical (`app/`, frozen), the planned J-rules layer (not built yet, roadmap tense only), Part B delegation chain (config flag, default off).
- Rule numbering follows THE REPO, not any guide document (in this repo the payee allowlist check is R.6; older team documents call it R.3 — never renumber).
- Test suite green after every commit; small revertable commits; new behaviour gets tests.

## 6. Where judgment is yours

Field-level composition of the model registration form (keep it substantial — adapt the existing check pattern to model scope, don't gut it), exact M-rule set replacing the current A-rules, panel naming and copy, how the model registry and cascade are stored, envelope payload shapes for the re-pointed signatures, and the order of migration commits. When a detail conflicts, resolve toward: the liability tree (Section 2), the governing sentence, and the unchanged bank beats (Section 5).
