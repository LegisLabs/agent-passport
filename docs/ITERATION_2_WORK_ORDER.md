# Agent Passport — Iteration 2 Work Order
**Repo:** `LegisLabs/agent-passport`, branch `main`, baseline commit `e266b2c`
**Scope:** Bernard's Builder Guide v4 (Part A gaps 1–4) + team alignment doc, applied to the payments vertical (`pay/`). No desloping, no refactoring, no visual redesign in this iteration. Features only.
**Date:** 6 September 2026. Submission 8 September 23:59 AOE.

---

## 0. Ground rules — read before touching anything

1. **Work in small scoped commits.** One task section per commit (or smaller). Never regenerate whole files that work. `git revert` must be able to undo any single task.
2. **The 48 pytest tests stay green after every commit.** Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`. New behaviour gets new tests.
3. **`app/` (tax vertical) is frozen.** Do not touch it, its rule pack, or git tag `hmrc-v1`.
4. **Offline mode must keep working.** A clone with no keys (`EXTRACTION_MODE=fixture`, local rail) must run every beat including the new ones. Every new LLM call needs a fixture stand-in and the `gemini-fallback` behaviour.
5. **Do not renumber the bank rules.** The Builder Guide v4 was written against an older numbering and calls the payee allowlist check "R.3". In this repo the payee allowlist is **R.6** (`PAYEE_NOT_ON_MANDATE`) and R.3 is the agent identity signature. Keep the repo's numbering everywhere. Where the guide says "R.3 beneficiary check", implement against R.6.
6. **The bank's decision logic does not change.** All four tasks add views, panels, records, labels and one threshold rule. R.1–R.9 semantics stay exactly as in `pay/rules.py` and `rulepacks/payments-2026.09.json`.
7. **Vouch integration stays as is.** Mint on approval, delete on revoke, settlement adapter, retry-then-local fallback: untouched, except that the new revocation flow (Task 3) must call the existing revoke path, not a new one.
8. **Every human-visible claim stays honest.** Anything simulated is labelled simulated. The existing "proposed framework, not a current legal requirement" copy stays everywhere it is now.

---

## 1. Naming alignment (applies across all tasks)

The team alignment doc fixes product language. Use these names in UI copy, About page, and code comments (not in identifiers that already exist):

- The regulator-side pre-issuance copilot is the **Standards Review Assistant** (the brief's "KYA standards evaluation tool"). The Builder Guide calls it "Supervisory Assurance Assistant"; the alignment doc's name wins.
- The bank-side check is the **Cryptographic Delegation Verifier** (the brief's "cryptographic authorization validator"). This is a *label* on the existing R.1–R.9 engine, not new code.
- The one-line principle, used verbatim where a tagline fits: **delegation can only narrow authority, never expand it.**
- Pitch line stays: **identity is not authority.**

---

## 2. Task 1 — Malicious invoice live demo (P0, build first)

**What exists:** beat 2 already denies a payment to an unregistered account (R.6). What's missing is the *visible AI-manipulation moment*: judges must see a live LLM read a poisoned invoice and produce the wrong instruction before the bank stops it.

**Build, in `pay/`:**

1. **Fixtures.** Two invoice documents for supplier Fenwick Timber Ltd: `INV-9001-clean` (account 10101010, £2,500) and `INV-9001-poisoned` (identical except account 99887766). PDF or rendered HTML-as-document, consistent with the existing five synthetic documents in `fixtures/pay/documents/`.
2. **Agent extraction step.** A new view or panel (suggested: on `/bank` or a small `/agent` page reachable from the bank console) where the AP agent "reads" the selected invoice via the existing Gemini extraction path (`pay/extraction.py`, JSON mode, temp 0, verbatim-quote schema). Fixture mode returns deterministic extraction for both invoices. Live mode must reproduce fixture values.
3. **On-screen sequence, four steps in order** (the defining demo moment, per guide Gap 1):
   a. Extracted invoice text with the account number visible (poisoned: 99887766).
   b. The agent's generated payment instruction, wrong account highlighted red.
   c. Bank denial panel: R.6 highlighted, reason `PAYEE_NOT_ON_MANDATE`, with the FATF note (see Task 4).
   d. Caption, verbatim: "The AI read a manipulated invoice and would have paid the wrong account. The mandate stopped it."
4. **Violation record.** The denial writes a violation row consumed by Task 3's exception panel (status OPEN). Use the existing audit/incident machinery in `pay/audit.py` as the base; extend, don't parallel.
5. **Clean-invoice path.** The same flow with `INV-9001-clean` produces a correct instruction and an ALLOW, so the demo can show the agent working properly first. This can reuse/replace beat 1's story.
6. **Tests.** Extraction fixture correctness for both invoices; poisoned flow ends in DENY R.6 + violation row; clean flow ends in ALLOW. Oracle (`fixtures/pay/oracle.json`) extended if the beat table changes.

**Acceptance:** in fixture mode, a viewer can click through clean → ALLOW, then poisoned → wrong extraction shown → DENY R.6 → violation row appears. In live mode, Gemini extraction matches fixtures.

---

## 3. Task 2 — Standards Review Assistant (P0, build second)

**What exists:** `/regulator` runs the eight application checks A.1–A.8 and officer approval with a condition. What's missing is the visible six-step agentic loop that makes this an agentic solution and claims the brief's standards-copilot prototype.

**Build, in `/regulator`:**

Six steps, rendered as a visible sequence (cards or stepper), run when the officer opens a submitted application:

1. **EVIDENCE READ.** Parse the three passport components / five evidence documents (existing extraction). Summary card: what PayRail claims, what Northgate authorised, what the authority is asked to certify.
2. **STANDARDS RULE MAP.** Load `rulepacks/payments-2026.09.json` (versioned, labelled "payments-2026.09" on screen). Map each requirement to evidence; flag anything uncovered. This step carries the label "Standards Review Assistant (KYA standards evaluation tool)".
3. **ADVERSARIAL TEST GENERATION.** Generate 3–5 test cases specific to this passport, shown as cards. Fixed set is fine (fixture mode): "Payment to non-mandated supplier", "Amount £1 above per-payment limit", "Expired passport", "Rogue key signature", "Amount above supervisor condition". If generated via LLM in live mode, fixture mode returns this exact set.
4. **SANDBOX RUN.** Submit each test case to the real bank verification logic (reuse `pay/rules.py` — same code path as `/bank`, not a copy). Record PASS/FAIL per card, where PASS means the engine refused/escalated as expected.
5. **RECOMMENDATION.** Structured output: APPROVE / APPROVE WITH CONDITIONS / REFER, with reasoning drawn from steps 2–4. Label verbatim: "AI recommendation — human decision required." The existing file-note drafting (verdict vocabulary rejected) stays consistent with this.
6. **HUMAN SIGN-OFF.** The existing officer approval. Only the human click applies the authority signature and activates the passport. Wire the recommendation into the same screen; nothing auto-approves.

**Constraints:** the LLM may summarise and draft; it never scores, decides, or signs (design rule in PRODUCT_STATE §1 holds). The sandbox run is deterministic. Officer A. Ferreira's condition flow (£5,000 hold) is unchanged.

**Tests:** six-step run completes in fixture mode; sandbox tests hit the real rules engine and all report expected refusals; approval still requires the human POST; recommendation output shape stable.

**Acceptance:** opening a submitted application walks visibly through all six steps and ends with the officer's existing approve/refer controls, condition intact.

---

## 4. Task 3 — Exception panel, pattern detection, revocation loop (P1)

**What exists:** three refusals on one passport write an incident log row; the regulator has suspend/revoke lifecycle; vouch voucher is deleted on revoke.

**Build:**

1. **Exception panel** on `/regulator`, labelled "Anomaly Detection & Escalation". Violations table, columns: Timestamp | Agent ID | Rule violated | Payment attempted | Outcome | Status (OPEN / INVESTIGATING / RESOLVED). Fed by Task 1's violation records and existing refusal incidents.
2. **Pattern threshold rule:** ≥2 violations of the same rule type within 24h on one passport triggers an automatic supervisor alert banner at the top of `/regulator`. One configurable condition on the violation log (config value in the rule pack or app config, default 2/24h). This is the "detection" element; it coexists with the existing 3-refusal incident counter (keep both; they answer different questions).
3. **Revocation loop, three states**, driven from the exception panel: **SUSPENDED** (payments blocked at R.2, existing behaviour) → **INVESTIGATING** (supervisor reviews the exception detail: which rule, what instruction, extraction evidence from Task 1) → decision: **REVOKE** (existing revoke path: registry REVOKED, vouch voucher deleted, R.2 denies) or **REINSTATE** (false positive; back to ACTIVE). Reuse the existing lifecycle endpoints; add the INVESTIGATING state and the panel-driven flow around them.
4. **Bank console line** on post-revocation denial keeps the existing wording: "authority registry revoked · vouch rail REVOKED · one supervisory action, two rails refuse."

**Tests:** two same-type violations inside the window raise the alert, one does not; INVESTIGATING blocks nothing by itself; SUSPENDED denies at R.2; REINSTATE restores ALLOW; REVOKE denies at R.2 and deletes the voucher (existing test extended); replay of the audit chain still identical.

**Acceptance:** run the poisoned invoice twice → alert banner appears → supervisor suspends → investigates (sees the extraction evidence) → revokes → subsequent payment DENY R.2, vouch voucher gone. Then a fresh pass showing REINSTATE.

---

## 5. Task 4 — Standards labels + About page (P2, do alongside Task 3, ~2h)

Labels only. No behaviour changes.

1. **Tab/view "Passport issuance" (customer + regulator issuance surfaces):** badge row beneath the three signature panels, four badges: `OAuth 2.0 RFC 9396` · `W3C VC JWT` · `RFC 7800 cnf` · `Ed25519 RFC 8037`. Mandate panel labelled: "Payment Mandate (OAuth 2.0 RFC 9396 Rich Authorization Request)". JWT headers labelled "JWT (OIDC-compatible)". Tooltip on agent key: "Agent key binding provides workload-identity guarantees equivalent to SPIFFE SVID."
2. **`/regulator`:** header label "Regulatory Assurance (proposed FCA Agent Assurance addendum, PSR 2017 extension)" plus one intro line to that effect. The Standards Review Assistant label from Task 2.
3. **`/bank`:** header label "Cryptographic Delegation Verifier — Zero Trust, deny by default (R.1–R.9)". On R.6 refusals, note: "Named-beneficiary mandate check (FATF 2025 AML/CFT alignment)". (Guide says R.3; see ground rule 5.)
4. **`/about`:** replace/extend with the Builder Guide A9 copy verbatim (What it is / What it is not / Why it matters now / Technical standards / Regulatory context), adjusted only where A9 conflicts with reality: rule number references use this repo's numbering, and the "what we do not claim" list from PRODUCT_STATE §14 is kept. Add the two-component framing from the alignment doc (Standards Review Assistant + Cryptographic Delegation Verifier, why both) and the one-line delegation principle. Add one sentence: "Agent Passport addresses the same delegation-gap problem as Visa TAP and ERC-8004, within the FCA-regulated payment institution framework." Add the did:key compatibility line: "Agent and authority keys are compatible with W3C did:key resolution. Full DID document support is a production extension."

**Acceptance:** every standard named in the brief's reference list is visible somewhere in the UI, not only on the About page. Playwright walk still clean at desktop and 390px (no overflow from new badges).

---

## 6. Task 5 — Part B: delegation chain + verify_chain (only after Tasks 1–4 are done and verified)

Jean's section; implement only once everything above passes the full demo walk.

1. **Split the agent:** rename the existing AP agent role to **AP Orchestrator Agent**; add a lightweight **Payment Execution Agent**. Orchestrator reads the invoice and delegates: `{ beneficiary, max_gbp: 4000, sig: orchestrator }` ⊆ root mandate. Execution agent signs and submits the payment plus the delegation chain.
2. **`verify_chain` function** in `pay/crypto.py` or `pay/rules.py`: checks (a) root mandate scope valid, (b) each delegation ⊆ its parent (beneficiary set, amount ceiling, purpose), (c) action ∈ narrowest scope. Runs visibly on `/bank` during the boundary-test beat: three checks shown ✓/✗ step by step.
3. **Invariant, displayed:** S_n ⊆ … ⊆ S₁ ⊆ S₀. Poisoned-invoice run with the chain: orchestrator emits delegation with beneficiary 99887766 → verify_chain fails at (c) → DENY.
4. **Tests:** valid chain passes; expanded-scope delegation refused; poisoned chain refused at the right step; single-agent (no chain) path still works so Tasks 1–4 demos are unaffected.

**Acceptance:** demo can run with chain on or off (config flag), default off until the video storyboard decides.

---

## 7. Out of scope for this iteration

- Desloping, CSS consolidation, visual redesign (next iteration).
- Alexandra's explainability/risk-score-per-transaction and CAPTCHA/2FA-bypass ideas: deck and About narrative material, not build. Do not implement.
- Chase/Zelle screenshot: deck cold open, not product.
- HMRC vertical: frozen.
- The known punch list (footer typo "Lexis Labs" → "Legis Labs", replay counter exercise, demo reset before recording, R.9 label quirk on ALLOW): fix the footer typo and the R.9 label quirk in passing if touched files overlap; otherwise they belong to the polish iteration.

## 8. Definition of done for iteration 2

1. Full pytest suite green (48 existing + new).
2. Fixture-mode full walk: clean invoice ALLOW → poisoned invoice with visible extraction → DENY R.6 → violation → second poisoned run → alert → suspend → investigate → revoke → DENY R.2 + vouch revoked → reinstate path shown once.
3. Six-step Standards Review Assistant runs end to end with human sign-off gating issuance.
4. All standards labels visible; About page updated.
5. Playwright walk-through updated for the new beats, clean at desktop and 390px.
6. Live mode spot-checked on the deployed site after `bash deploy/publish.sh pay`.
