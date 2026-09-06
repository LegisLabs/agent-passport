# Agent Passport — Iteration 3 Work Order
**Repo:** `LegisLabs/agent-passport`, branch `main`, baseline: v0.2.0 (iteration 2 complete)
**Scope:** Everything in Builder Guide v9 Part A EXCEPT Gap 5 (Grounds Declaration / J-rules), which is deferred to iteration 4. Target end state: the 8-stage demo (minus Stage 7b) runs clean end to end and matches the A7b 3-minute script.
**Date:** 6 September 2026. Submission 8 September 23:59 AOE.

---

## 0. Ground rules

1. **Small scoped commits**, one task (or sub-task) per commit. Never regenerate working files. Any task revertable with one `git revert`.
2. **Full pytest suite stays green after every commit.** Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`. New behaviour gets new tests.
3. **Rule numbering: the repo wins.** Guide v9 says "R.3 beneficiary check" against an older numbering. In this repo the payee allowlist is **R.6** (`PAYEE_NOT_ON_MANDATE`); R.3 is the agent identity binding check; R.4 is the instruction signature check. Never renumber. Wherever the guide says R.3 for beneficiary, implement and label against R.6.
4. **R.1–R.9 semantics do not change.** This iteration adds verification hardening, wiring confirmation, labels, copy, and demo support. The decision logic in `pay/rules.py` and `rulepacks/payments-2026.09.json` stays as is.
5. **Offline mode keeps working.** Clone with no keys (`EXTRACTION_MODE=fixture`, local rail) must run every demo stage. Live mode (Gemini + vouch) must reproduce fixture outcomes.
6. **`app/` (tax vertical) stays frozen.** Do not touch it or tag `hmrc-v1`.
7. **Vouch integration untouched** except copy additions named below.
8. **Honesty copy stays.** Everything simulated stays labelled simulated. "Proposed framework / design prototype, not a current legal requirement" language survives every edit.
9. **Do NOT build:** Gap 5 J-rules, HOLD state, `approved_input_channels`, `check_grounds()` (iteration 4). Alex's three-artefact refactor (labels only, Task 6). Part B agent handoff chain (separate gated task, Section 9, only if everything else is done and verified). HMRC scenario.

---

## 1. Task 1 — Poisoned invoice end-to-end (P0, do first, ~2h)

v9 marks this CONFIRM, not build: the button INV-9001-poisoned exists. Verify the full chain actually fires, and fix whatever does not.

**The chain that must work, in order:**

1. Action Terminal: operator selects `INV-9001-poisoned`.
2. Live LLM extraction (`pay/extraction.py`, Gemini JSON mode, temp 0, verbatim-quote schema) reads the poisoned document and extracts account **99887766** (clean version extracts 10101010). Fixture mode returns the same values deterministically.
3. **On-screen sequence, four steps, in this order** (the defining demo moment):
   a. Extracted invoice text with the poisoned account number visible.
   b. The agent's generated payment instruction, wrong account highlighted red.
   c. Bank denial panel: **R.6** highlighted red, reason `PAYEE_NOT_ON_MANDATE`, FATF note visible: "Named-beneficiary mandate check (FATF 2025 AML/CFT alignment)".
   d. Caption verbatim: "The AI read a manipulated invoice and would have paid the wrong account. The mandate stopped it."
4. Violation row appended to the Anomaly Detection & Escalation panel (Regulator Panel), status OPEN.
5. Audit trail: the denial appends a hash-chained entry (`sha256(prev_hash + entry)`); chain verifies INTACT afterwards; replay of the decision reproduces the identical outcome.
6. Second poisoned run inside 24h triggers the existing threshold alert banner.

**Tests:** poisoned fixture extraction correctness; poisoned flow → DENY R.6 + violation row + audit entry + chain INTACT; clean flow → ALLOW; two runs → alert. Extend `fixtures/pay/oracle.json` if beat outcomes change.

**Acceptance:** one uninterrupted click-through in fixture mode covering steps 1–6; then the same spot-checked in live mode on the deployed site. Record the terminal output — it appears in the video.

---

## 2. Task 2 — Instruction-level signature verification (P0, Bernard's Q2, ~1–2h)

Bernard's open question: is each payment instruction individually signed by the agent's key, or does the bank only verify the passport? APS 1001 R.4 requires the former. Make the build unambiguous:

1. **Confirm or implement:** every payment instruction submitted by the agent is signed with the agent's Ed25519 private key (the key named in `agent_identity` via RFC 7800 cnf). The bank's R.4 check calls the real signature verify function (PyNaCl `VerifyKey.verify` or equivalent) on the **instruction bytes**, using the agent public key from the passport. Not field matching. Not presence checking.
2. **Canonical signing payload:** define exactly what is signed (e.g. canonical JSON of `{instruction_id, payee_account, amount, currency, reference, timestamp, passport_id}`), document it in the README/About, and use the same canonicalisation on sign and verify.
3. **UI evidence:** in the Action Terminal result panel, add one line per decision: "R.4 instruction signature: VERIFIED (Ed25519)" with the key fingerprint. On the happy path this is visible proof for judges.
4. **Tamper test (the credibility point):** a test that flips one byte of the signed instruction payload and asserts R.4 DENY. Same for a signature produced by a rogue key. If a judge says "show me the signature verification", `git grep verify` must land on real crypto.
5. Same standard for the envelope: authority, provider, and customer signatures verified with real Ed25519 calls (v9 says ALL THREE VERIFY is already live — add the tamper tests if missing).

**Acceptance:** tamper tests pass; UI shows instruction-level verification; one-sentence answer ready for Bernard: "Yes — every instruction is individually signed by the agent key and verified at R.4 with a real Ed25519 check; flipping one byte fails it."

---

## 3. Task 3 — A3a / A3b framing on the panels (~1h)

Copy and labels only; the Issuance Flow v4 panels already exist.

1. **Provider Panel:** intro line: "Phase 1 — Provider registers the agent model once: model documentation (model and version, benchmarks, training type), agent public key, configuration hash, insurance. No customer data."
2. **Regulator Panel:** header label: "Regulatory Assurance (proposed PSR 2017 Agent Assurance function — design prototype)." Intro line: "This demonstrates what agent certification within the PSR 2017 framework would look like. Phase 2 — the authority approves the model once and sets policy ceilings; it does not see or approve individual customer mandates."
3. **Customer Panel:** intro line: "Phase 3 — The customer writes and signs its own mandate (payees, per-payment size, monthly ceiling, expiry) within the policy ceilings. Live immediately; no authority review."
4. **Action Terminal:** one line under the header: "The bank verifies every payment (R.1–R.9, deny by default, sub-10ms). The regulator sees patterns and escalations, never individual payments."
5. Verify the ceiling containment check ("mandate ceilings within policy ceilings", the iteration-2 A.7 restatement) runs at mandate signing and is labelled on the Customer Panel.

---

## 4. Task 4 — Vouch Rail interoperability line (~15 min)

Tab/section 5 header, add verbatim: "Mandate anchored as AI Voucher on vouch.finance — demonstrating interoperability with the open agent-authorisation ecosystem." Nothing else changes.

---

## 5. Task 5 — About page: v9 A9 copy (~1h)

Replace the About page with the v9 A9 copy (What it is / What it is not / Why it matters now / Technical standards / Regulatory context), with these adjustments:

1. Rule references use repo numbering (beneficiary check = R.6).
2. The "Important distinction" paragraph: keep the R.1–R.9 sentence and the regulator-acts-on-patterns sentence; rephrase the Grounds Declaration sentence to roadmap tense: "A planned Grounds Declaration layer (J.1–J.8) will additionally escalate source-integrity concerns to a named human." Do not describe it as implemented.
3. Keep the existing "what we do not claim" honesty list; merge with v9's "What it is not" (including: mandate enforces money destination and authority, not invoice semantic accuracy).
4. B2B framing per A3c: lead with AML compliance (PSR 2017) and market access; APP fraud named as the consumer/SME incentive context, not the B2B driver.
5. Add the Chase/Zelle sentence: "JPMorgan Chase already adds friction to detect intent signals on payments; Agent Passport makes that determination cryptographically provable, not behavioural."

---

## 6. Task 6 — Standards labels completion + five-layer mapping (P2, ~1h)

v9 marks badges DONE; this is a verification-and-gaps pass, plus Alex's framework as labels.

1. Confirm present, add where missing: Tab 1 badge row (OAuth 2.0 RFC 9396 · W3C VC JWT · RFC 7800 cnf · Ed25519 RFC 8037); mandate panel label "Payment Mandate (OAuth 2.0 RFC 9396 Rich Authorization Request)"; JWT header label "JWT (OIDC-compatible)"; SPIFFE-equivalence tooltip on the agent key; Action Terminal header "Zero Trust — deny by default (R.1–R.9)"; FATF note on R.6 refusals.
2. **Five-layer mapping as labels, no refactor:** small caption or tooltip per surface: Layer A agent assurance = authority signature (Regulator Panel); Layer B principal mandate = customer mandate (Customer Panel); Layer C transaction intent = instruction signed by the agent key (Action Terminal, ties to Task 2); Layer D runtime policy decision = R.1–R.9 check (Action Terminal); Layer E regulatory supervision = anomaly/escalation feed (Regulator Panel). One About line: "The three-signature envelope realises the Passport / Principal Mandate / Action Intent Manifest model."

---

## 7. Task 7 — Demo readiness (P0 for the video, ~2h)

1. **Demo state reset:** one command or admin control that restores the exact pre-demo state: passport ACTIVE, empty violations table, audit chain at its baseline entries, replay counter untouched, clean/poisoned invoices ready. Must be runnable between video takes. Document it in the README.
2. **Punch list closure:** footer typo "Lexis Labs" → "Legis Labs"; R.9 label quirk on ALLOW verdicts fixed; replay counter exercised so it shows a non-zero real value.
3. **Playwright walk updated** to the 8-stage demo (Stage 7b excluded): Stage 1 Standards Review Assistant run → Stage 2 issuance view with badges → Stage 3 clean payment ALLOW → Stage 4 £12,000 boundary DENY (amount ceiling rule) → Stage 5 vouch mirror → Stage 7 poisoned invoice DENY R.6 with the four-step sequence → Stage 8 violation → suspend → revoke → subsequent payment DENY R.2, voucher deleted. Clean at desktop and 390px.
4. **Script fidelity check:** walk the A7b 3-minute script against the build; every named on-screen element (badge row, ALL THREE VERIFY, DENY panel, FATF note, caption, alert banner, REVOKE control) exists and is legible on video resolution.

---

## 8. Explicitly out of scope (iteration 4 and later)

- **Gap 5 Grounds Declaration:** J.1–J.8, HOLD state, `approved_input_channels`, `check_grounds()`, Stage 7b, grounds fixture payloads. Reserve nothing in the schema now; it attaches additively later.
- **Part B** (Orchestrator/Execution split + `verify_chain`): only after this entire work order is done and verified, behind a config flag, default off — see iteration 2 work order Task 5 for the spec if reached.
- HMRC vertical, desloping/visual redesign beyond items named above.

---

## 9. Definition of done

1. Full pytest suite green, including new tamper tests.
2. Fixture-mode uninterrupted walk of the 8-stage demo (minus 7b) matching Section 7.3.
3. Poisoned invoice confirmed end to end in live mode on the deployed site (`bash deploy/publish.sh pay`), terminal output legible.
4. Instruction-level Ed25519 verification visible in UI and proven by tamper tests; answer sent to Bernard.
5. About page carries v9 A9 copy (adjusted per Task 5); all standards labels and five-layer captions visible.
6. Demo reset works twice in a row producing identical baselines.
7. Playwright clean at desktop and 390px.
