# Agent Passport demo: visual audit (mentor-feedback checkpoints)

Site: http://localhost:8016 · viewport 1400x900 (phone shots 390x844) · headless Chromium via Playwright · 8 Sept 2026, 19:46–20:02.
Seeds used: `stage=registered` for steps 1–4, `stage=history` for steps 5–6. Passport `AP-2026-0107`, registration `REG-2026-0014`.

## 0. Caveat that changes how to read this audit

The working tree was being edited while the audit ran. `git status` was clean at the start (HEAD `eacb32d`, one commit above `096fcfc`); during the first pass `pay/templates/customer.html` (19:48:26), `pay/templates/bank.html` (19:49:24), `pay/static/app.js` (19:50:11) and a new `pay/static/dashboard.css` (19:52–19:56) were saved by another session, and the server runs with `--reload`. Consequences:

- Shots 01–33 (landing, About, provider, admission, mandate form, terminal, console) are pages no edit touched; they match the committed code.
- Shots 34–60 (bank dashboard, passport page, customer dashboard, phone) show the **uncommitted "Meridian" dashboard redesign** (`.fx` layout, Plus Jakarta Sans, greeting, balance card), **not** commit `096fcfc`. Every layout defect in section 4 below is against that redesign; re-check after it is committed.
- The first pass caught the broken intermediate state (new template calling `AP.dashExtras()` before the new `app.js` was saved): see section 2. It did not reproduce once the files settled.

## 1. Screenshots

| File | What it shows |
|---|---|
| 01-landing-hero.png | Landing, viewport: hero "Know the AI agent before it pays.", CTAs Customer dashboard / Bank dashboard / How it works, partner logos |
| 02-landing-full.png | Landing, full length: The shift (agentic-commerce chart), The numbers (APP fraud bars, £576m), The problem (diagram), Our proposal, The result (evidence record), Powered by vouch.finance |
| 03-about-full.png | About, full length (8,467px tall; use 03b–03e to read) |
| 03b-about-what-this-is-not.png | About: "Where the model sits", "What this is not", "What we do not claim" |
| 03c-about-where-it-sits-in-the-bank.png | About: "Payees and the public register", "Where it sits in the bank" (integration story) |
| 03d-about-who-sees-what.png | About: "Who sees what" / "What a regulator gets" |
| 03e-about-top.png | About: opening paragraph "Identity is not authority…" |
| 04-provider-index.png | /provider without a ref: "Register an AI product", products-on-the-register table, blank filing form |
| 05-provider-filed-registration.png | /provider?ref=REG-2026-0014: filed form, green "On the register" block, completeness checks F.1–F.6 all PASS, receipt |
| 06-bank-dashboard-pending-admission.png | /bank at stage=registered: amber to-do "PayGPT 6.0 … awaits your admission decision", empty Needs attention, empty Recent activity, zero statistics |
| 07-bank-admission-review-steps.png | Admission review assistant: six steps (filing read, requirement map, adversarial tests, sandbox 5 of 5, recommendation, officer decision) |
| 08-bank-admission-page-full.png | /bank?ref: What the provider filed, Filing checks, review assistant, Your decision, History |
| 09-bank-decision-card-empty.png | "Your decision" card with EMPTY hold condition and officer note; ceilings line incl. account-type maxima |
| 10-bank-context-panel.png | Context panel after "Prefill demo data" (Meridian Bank, A. Ferreira) |
| 11-bank-decision-card-filled.png | Decision card after prefill: hold 5000, officer note |
| 12-bank-admitted-product.png | "On the bank's list · ADMITTED": product, admitted by A. Ferreira, ceilings, hold condition, product control (Suspend / Remove) |
| 13-customer-landing-before-agent.png | /customer before any agent (new Meridian layout) |
| 14-customer-add-agent-picker.png | Add an AI agent: product picker |
| 15-customer-mandate-form-empty.png | EMPTY mandate form: agent record (kid, POSSESSION PROVEN, PENDING), account, "Most you can grant" (**"undefined payments a day"**), limits, Currency GBP, empty supplier list, Sign mandate disabled |
| 16-customer-context-panel.png | Customer context panel (Northgate Joinery, Helen Marsh) |
| 17-customer-mandate-form-filled.png | Filled form: £10,000 / £20,000 / 10 a day / 31 Mar 2027 / GBP, three suppliers each "checked against the public register", green containment note, Sign mandate enabled |
| 18-customer-supplier-name-search.png | Name-first search: typing "coast" lists register matches |
| 19-customer-supplier-picked.png | Match picked: Coastline Glass number, legal name, status filled |
| 20-customer-mandate-over-ceiling-refusal.png | £12,000 per payment: red "Outside the agent-channel limits… per-payment limit £12,000 must be between £1 and the agent-channel limit £10,000", Sign disabled |
| 21-customer-mandate-signed.png | Signature block: "Signed 8 Sept 2026 at 19:55:07 by Helen Marsh… The bank issued the passport, the list shows ACTIVE and the voucher is minted on the vouch rail" |
| 21b-customer-mandate-signed-suppliers.png | Signed supplier list with register check and Confirmation-of-Payee note |
| 21c-customer-mandate-signed-kv.png | Signed mandate key facts (limits, velocity, currency) |
| 22-customer-dashboard-after-signing.png | Customer dashboard right after signing |
| 23-customer-agents-card.png | Agents card after signing |
| 24-customer-evidence-trail.png | Customer evidence trail after signing |
| 25-terminal-opening.png | Action Terminal opening: Before/After switch, "An invoice lands on your desk.", the invoice PDF with the "URGENT: our bank details have changed" box |
| 26-terminal-opening-full.png | Same, full page |
| 27-terminal-before-world-end.png | Before the standard, end state: agent reads 60-11-22 99887766, bank form, 3 green checks, "Executed… Money gone", "The bank could not tell an AI agent had typed it" |
| 28-terminal-after-world-end.png | After the standard, end state: passport lookup, list answers, R.1–R.5 ✓, R.6 ✗ red, R.7–R.9 grey, "Denied", "Money never moved." |
| 29-console-opening.png | Expert console: ten beats with expected outcomes, Genuine / Altered invoice buttons |
| 30-console-beat1-allowed.png | Beat 1 judgment: R.1–R.8 ✓, R.9 amber, ESCALATE FIRST_PAYMENT_CONFIRMATION_REQUIRED (not ALLOW on a fresh mandate) |
| 30b-console-beat1-viewport.png | Beat 1, viewport |
| 30b-console-beat1-gauntlet.png | Beat 1 judgment panel, first pass (same content) |
| 31-console-beat2-redirected-refused.png | Beat 2 judgment: R.6 ✗ payee 60-11-22 99887766 not on the allowlist, DENY, FRAUD INDICATOR chip |
| 31b-console-beat2-viewport.png / 31b-console-beat2-gauntlet.png | Beat 2, viewport / panel |
| 32-console-beat9-usd-refused.png | Beat 9: USD instruction DENY R.6 CURRENCY_NOT_PERMITTED, agent error |
| 33-console-beat10-replay-refused.png | Beat 10: replay DENY R.4 REPLAY_DETECTED, FRAUD INDICATOR (header reads "pay_invoice · replayed instruction · · £0") |
| 33b-console-full-after-beats.png | Console full page after the four beats |
| 34-bank-dashboard-full.png | Bank dashboard, history seed, sim off: greeting, At a glance, Statistics, Needs attention, Supervisory access, Active AI agents, Recent activity, Evidence trail, Admissions accordion |
| 35-bank-needs-attention-strip.png | Needs attention: "1 held · 1 fraud indicator", legend line, fraud row (red) and held row (amber) with Approve and release / Refuse and record |
| 36-bank-today-tiles.png | At a glance: Value moved £2,419,350, 1,848 processed, 1 awaiting a person, 8 fraud, 42 agent error, 39 agents |
| 37-bank-agents-and-log.png | Statistics + Recent activity + Needs attention + Supervisory access + Active AI agents + Evidence trail in one frame |
| 37b-bank-agents-card.png | Active AI agents card |
| 37c-bank-log-card.png | Recent activity (5 rows) with STATUS column |
| 38-bank-log-row-expanded-replay.png | Element capture of the expanded replay row (capture artefact: use 38b) |
| 38b-bank-log-row-expanded-viewport.png | Expanded replay row in the viewport: instruction, nonce "already spent", nine checks, DENY R.4, Proof (right column clipped) |
| 39-bank-statistics.png | Statistics: 9 instructions / 5 processed / £12,900 / 3 held / 2 fraud / 1 error, per-minute bars, per-agent table (right columns clipped) |
| 40-bank-evidence-trail.png | Evidence trail after Replay every verification: "30 entries · chain intact · 9 of 9 replayed identically" |
| 41-bank-details-register-supervisory.png | Admissions and the register: Admitted products, The register (assurance level, your decision) |
| 42-bank-release-confirm-step.png | Element capture of the confirm step inside the Needs-attention column (clipped) |
| 42b-bank-release-confirm-viewport.png | Same, viewport: confirm panel overflowing past the right edge, "Confirm and release the p…" cut |
| 42c-bank-release-confirm-scrolled.png | Same, scrolled to the panel |
| 43-bank-released-result-strip.png | After release: "0 held · 1 fraud indicator", green "Released by A. Ferreira… for Helen Marsh · chain entry #16… executed by the bank" |
| 44-bank-released-log-row.png | Log: "Processed · released by approver" £5,600 at top |
| 45-bank-new-held-payment.png | New held £5,100 Coastline Glass awaiting decision |
| 46-bank-refuse-confirm-step.png | Confirm step before refusing |
| 47-bank-refused-by-approver-result.png | After refusal: green "Refused by A. Ferreira… nothing moved" |
| 48-bank-log-after-both-decisions.png | Log: Refused · by approver, Processed · released by approver, Refused · agent error, Refused · fraud indicator, Processed, Processed · confirmed by the customer |
| 49-bank-passport-page.png | /bank?passport=AP-2026-0107: three-signer envelope (Admission / Agent identity / Mandate, all Verified), ALL THREE VERIFY, vouch rail, ACTIVE controls, refusals table with Agent error / Fraud indicator classes, Incidents, History |
| 50-customer-dashboard-history.png | Customer dashboard after the decisions: "Good evening, Helen.", balance card, AI agents card, Statistics (£6,650 / 3 / 1 stopped / 1 agent errors), Evidence trail, Needs your attention (5 items) |
| 51-customer-notifications.png | Needs your attention panel |
| 52-customer-agent-card-counts.png | Agent card: limits, "first payment confirmed", Amend mandate · Revoke mandate, paid £6,650 in 3, held 0, refused 2 |
| 53-customer-mandate-detail.png | /customer?ref=AP-2026-0107 |
| 54-customer-amend-form-prefilled.png | "Amend the mandate (version 2)" prefilled with 10000 / 20000 / 10 / 31 Mar 2027 / GBP and the three suppliers |
| 55-customer-amend-cancelled.png | After Cancel |
| 56-phone-landing.png / 56b-phone-landing-full.png | Landing at 390px (viewport / full) |
| 57-phone-bank-dashboard.png / 57b-phone-bank-dashboard-full.png | Bank dashboard at 390px (viewport / full) |
| 58-phone-menu-open.png | Phone header Menu open |
| 59-customer-transactions-tab.png | Customer "Transactions" tab: AI-agent lines alongside ordinary account lines with running balance |
| 60-customer-full-trail.png | Customer evidence trail expanded ("Show full trail") |

## 2. Console and page errors per page

Second pass (files settled, 19:54–19:59) and follow-ups (19:59–20:02): **no console errors and no page errors on any page** (/, /about, /provider, /provider?ref, /bank, /bank?ref, /bank?passport, /customer, /customer?ref, /terminal, /terminal?console=1, phone / and /bank). A fresh-browser reload test (3 loads each of /bank, /customer, /bank?passport, /customer?ref) was also clean.

First pass (19:46–19:50, while the templates were being saved ahead of app.js):
- /customer (history), /customer?ref: `pageerror: AP.customerExtras is not a function`
- /bank, /bank?ref, /bank?passport (sweep): `pageerror: AP.dashExtras is not a function`
Cause: `bank.html` / `customer.html` gained `AP.dashExtras()` / `AP.customerExtras()` calls before `app.js` exported them. Not reproducible after 19:50. If the deploy ever ships templates and JS in separate steps, this is what a viewer sees in between.

Links: every internal `<a href>` on every page returned 200 with a non-empty body (incl. /api/docs, /api/evidence/passports/…, /api/evidence/violations/1,2, /static/APS_1001.pdf). External links (salesforce, juniperresearch, digitalcommerce360, ukfinance, gov.uk, vouch.finance, legislabs.uk, openpay.example, brightwater.example) not visited. One `href="#"`: `#btn-evidence` "Export the evidence bundle" in the passport panel markup on /bank and /bank?ref; it is inside the hidden passport section on those views and is filled in on /bank?passport, so it is not a visible dead link.

Buttons: no visible-but-disabled buttons without explanation. "Sign mandate" is disabled while the form is empty or outside the ceilings, and the containment note says why. The sweep's click-timeout entries (Dismiss ×5, replay ×3, fx-eye, cu-trail-toggle, btn-note, the Altered-invoice button) are buttons inside collapsed or hidden panels or long-running beats, not dead buttons; "Transactions" was a false positive (shot 59 shows it works).

## 3. Checkpoint verdicts (would a non-technical banker or regulator see and understand it?)

| # | Checkpoint | Verdict | Evidence |
|---|---|---|---|
| A1 | No approval step visible | **PASS** | Provider page opens "A registration is a filing, not an approval… Nobody reviews it" (05); the bank page is titled "Admission decision" / "Your decision" and the assistant says "the officer decides" (08). No regulator screen exists. |
| A2 | Regulator only in the exception path | **PASS** | Supervisory access card on the bank dashboard: "A regulator does not operate this dashboard and approves nothing in it. Through normal supervisory and incident processes it can request the evidence for a passport or a refusal; each export is itself recorded in the chain." with per-refusal Export links (34, 06). Refusal cards: "Recorded for its risk team; a supervisor can request the evidence" (50). |
| A4 | No approval language on screen | **PASS (one caveat)** | No "approved by the authority/regulator" wording anywhere. The only "approve" verbs are the bank officer's "Approve and release" button for a held payment (35) and the customer's "approval threshold" (51); both are the bank/customer, not a regulator. A strict reader might still prefer "Release" to "Approve". |
| B1 | Hero frames a checkpoint inside the bank pipeline | **PARTIAL** | Hero (01): "…the bank cannot see which agent acted, on whose authority, or who answers for it. Agent Passport gives the bank those three answers before money moves" — bank-side, but the words checkpoint / pipeline / alongside fraud screening only appear on About (03c). Landing "Our proposal" says "The bank checks. Every payment." (02). |
| B2 | Customer flow reads as "your bank" | **PASS** | Customer dashboard (50, 59): "Good evening, Helen.", "Business Current Account at Meridian Bank (demo)", MERIDIAN balance card, Transactions tab with rent, salaries, HMRC, EDF lines and a running balance. Seam: the mandate form (15, 17) is still the old grey utility layout with `kid fHTPG1C7MMpGDufU · config 0742d2a29aaa…` and the Legis Labs masthead sits above the Meridian app. |
| B3 | "What this is not" section visible | **PARTIAL** | Present and clear on About (03b: not a payments rail, not AML/sanctions, not a regulator's operating tool, not model certification) but about 6,000px down an 8,500px page; nothing on the landing. |
| B4 | APP fraud figure visible | **PASS** | Landing "The numbers" (02): "Of the £1.28 billion taken from UK customers last year, £576 million was authorised push payment fraud, up 19% in a year…" with a 2021–2025 bar chart, source UK Finance. |
| C1 | Bank view vs customer view differ | **PASS** | Bank (34): across-all-customers totals (1,848 payments, £2.4m), Needs attention with Approve/Refuse, per-agent statistics, log with rule ids and proofs, evidence chain, Supervisory access exports, Admissions and the register. Customer (50): own balance, own agent card with limits and Amend/Revoke, own-agent statistics (£6,650 paid / 3 payments / 1 stopped by the bank / 1 agent error), notifications, own trail, Transactions. Caveat: both now share the same template (greeting, lime pill nav, Meridian card), so at a glance they look like one product with two logins. |
| C2 | Owner's screening-tool label present | **PARTIAL** | Wording exists: "Agent error: the agent's own mistake inside its remit; a quality signal for its owner, not a report to anyone" (35, 50) and "This may point to an agent quality issue worth raising with your provider" (51). No explicit "screening tool" label; the tile is just "Refused · agent error". |
| D1 | Both flag types together, different colour AND label | **PASS** | Needs attention (35): red "Refused · fraud indicator" and amber "Held" in one strip with a legend line; log (48): red "Refused · fraud indicator" vs grey "Refused · agent error"; passport page (49): "Agent error" grey vs "Fraud indicator" red. Defect: customer notifications (50) give the agent-error refusal a green tick icon (same icon as "Released by approver"), while the fraud one gets a red lock. |
| E1 | Status column | **PASS** | STATUS column (37c, 44, 48): Processed · released by approver / Refused · by approver / Refused · agent error / Refused · fraud indicator / Processed / Processed · confirmed by the customer / Held. |
| E2 | Exceptions first at the top | **PARTIAL** | Needs attention is above the fold but top-right; the eye lands first on "Value moved £2,419,350" (34). The column is the narrowest on the page: agent name wraps to three lines, the amount and the "Refused · fraud indicator" chip run past the card edge (35, 47). |
| E3 | Approve and refuse worked with before/after | **PARTIAL** | Functionally yes: held £5,600 (35) → confirm (42) → "Released by A. Ferreira… for Helen Marsh… executed by the bank" and log "Processed · released by approver" (43, 44); held £5,100 (45) → "Refused by A. Ferreira… nothing moved" and "Refused · by approver" (47, 48). Visually the confirm step is broken: it renders inside the 309px column, its content is 1,469px wide, the "Confirm and release the payment" button's right edge is at x=1460 on a 1400px viewport, so the label reads "Confirm and release the p…" and the instruction/nine-checks detail is clipped (42b). |
| E4 | Statistics view | **PARTIAL** | Card exists with tiles, per-minute bars and a per-agent table (39). Defects: the table's Value / Held / Refused columns are clipped ("£", "£2,4"); y-axis labels are clipped ("7,000"); the chart's times (18:56–18:58) are an hour behind the log rows (19:56) — UTC vs local; the pending-state chart draws a £0–£1 axis for no data (06). |
| F1 | Currency field on the mandate | **PASS** | "Currency: GBP — payments in any other currency are refused" on the form (15, 17, 54); signed facts say GBP only (52). The select is greyed with GBP as its only value, which reads like a disabled placeholder. |
| F2 | Account-type / customer-class maximum shown | **PASS (one bug)** | Form (17): "Most you can grant: Business current account, Small or medium enterprise: agent ceiling up to £10,000 a payment, £50,000 per supplier account in 30 days, 20 payments a day, GBP only, to 2027-03-31. The lower of the account-type tier and the bank's admission ceiling…"; admission card (09): Personal £2,500 · Business current £10,000 · Business savings £25,000. Bug: before prefill the same line reads "**undefined payments a day**" (15). |
| G1 | Plain-language identity-verification sentence | **PASS** | Hero (01): "When one of them pays, the bank cannot see which agent acted, on whose authority, or who answers for it. Agent Passport gives the bank those three answers before money moves." About opening (03e): "Identity is not authority. Knowing who an AI agent is tells you nothing about what it may do…". In the terminal (28): "R.3 ✓ Agent identity · R.4 ✓ Signed by the AI agent's key". |
| G2 | Injected invoice caught | **PASS** | Terminal After world (28): R.6 ✗ "payee account 60-11-22 99887766 is not on the customer-signed allowlist", big red "Denied", "Declared 10101010, attempted 99887766. The document changed the destination, not the AI agent.", "Money never moved." Contrast Before (27): "Money gone". |
| G3 | Integration story on About | **PASS** | 03c: "Agent Passport is a pre-authorisation checkpoint inside the bank's existing payment pipeline. It runs alongside fraud detection and sanctions screening, before settlement, and replaces none of them. Instructions map to … ISO 20022 pain.001 … UK Faster Payments…" |
| H1 | Invoice scenario as the entry story | **PARTIAL** | The Action Terminal opens perfectly ("An invoice lands on your desk.", the PDF with the URGENT box, 25) but it is a header link; the landing hero (01) leads with the abstract claim and its CTAs are Customer dashboard / Bank dashboard / How it works. The invoice only appears on the landing as "The result" evidence record near the bottom (02). |
| H2 | Technical terms on primary surfaces | see list below | |
| H4 | Dead buttons, empty states, placeholders, half-built | see list below | |

### H2: technical terms a banker would stumble on (primary surfaces)

- Landing hero: none. Landing lower (02): "chain entry #17", "Ed25519", "the live bundle carries every signature and hash"; footer on every page: "rule pack payments-2026.09.6", "Invoice reading fixture · vouch fixture · rail local", "Built on OAuth 2.0 RFC 9396, W3C Verifiable Credentials, RFC 7800, Ed25519".
- Bank dashboard (34, 37c, 38b, 40): "R.9 human confirmation required", "R.6 currency not permitted", "R.4 replay detected", "all nine", "#15 e308c4bc58 · receipt", "chain intact · head e308c4bc5845", "hash-chained", "Nonce … already spent", "Instruction hash", "Rule pack", "Envelope", "REPLAY_DETECTED", "CURRENCY_NOT_PERMITTED", "PAYEE_NOT_ON_MANDATE", "list status active", "paced arrivals", "simulated traffic", "voucher minted on the vouch rail (fixture)".
- Customer dashboard (50): "R.6 CURRENCY_NOT_PERMITTED", "R.4 REPLAY_DETECTED", "#18 b0a7cc584c · receipt", "AP-2026-0107", "mandate version 1", "evidence bundle", "chain".
- Mandate form (15, 17): "kid fHTPG1C7MMpGDufU · POSSESSION PROVEN · config 0742d2a29aaa…", "northgate-openpay-paygpt-6-01", "claude-sonnet-5", "SUP-001", "agent channel".
- Admission page (08): "pay_invoice", "openpay-paygpt-6", "claude-sonnet-5", receipt "eyJhbGciOiJFZERTQSIs…", "sandbox run", "T1 PASS DENY R.6 PAYEE_NOT_ON_MANDATE", "HUMAN_CONFIRMATION_REQUIRED", "the verifier returns ESCALATE".
- Action Terminal, public tab (28): "GET /api/status/AP-2026-0107 · live", "customer-signed allowlist", "Evidence entry #12 797cbbf817".
- Expert console (30–33): "pay_invoice", "kid", "nonce", "FIRST_PAYMENT_CONFIRMATION_REQUIRED", "ESCALATE", "DENY", "violation #4 recorded OPEN", "stopped at R.9".
- Passport page (49): "OAuth 2.0 RFC 9396 authorization_details", "W3C VC JWT", "RFC 7800 cnf", "Ed25519 RFC 8037", "Config SHA-256", "Decoded envelope (three JWTs, EdDSA / Ed25519)", "Key custody", "Bound to agent identity f86cf0577dee…".

### H4: dead buttons, empty states, placeholder text, half-built

1. **"undefined payments a day"** in "Most you can grant" on the empty mandate form (15).
2. **Fixed "Powered by vouch.finance" badge overlaps content on every page**: over the mandate-form copy (17, 54), Supervisory access text (34, 37), a customer notification (50), the Transactions table (59), the evidence trail's last row (40), the register table (41), the About text (03b, 03c), the phone dashboard totals (57, 58) and the phone hero photo (56).
3. **Confirm step overflows the page** (42b): panel 1,469px wide in a 309px column; "Confirm and release the p…" cut; the "Held for a person / Why / Mandate / Who decides / Decision" table clipped.
4. **Expanded log row clipped** (38b): the nine-checks column is cut at the card edge ("Admission signature genuine (bank…", "instruction replayed: its nonce was al…"), the nonce value overprints the "already spent" note.
5. **Needs-attention rows clipped** (35, 47): amount "£4…", chip "Refused · fraud indicato…", agent name over three lines.
6. **Statistics table and axis clipped** (39, 34): "£", "£2,4", "7,000".
7. **Clock mismatch**: chart x-axis 18:56 vs log/live 19:56 (39, 34, 06).
8. Pending-state statistics chart draws a £0–£1 axis for zero data (06).
9. Console replay beat header "pay_invoice · replayed instruction · · £0" (33): empty separators and a £0 amount.
10. Customer notification icon: green tick on a refused agent-error item (50).
11. Two brands on the customer screen: Legis Labs masthead over a MERIDIAN account (50, 59); mandate form still in the old grey style inside the new app (15/17 vs 50).
12. Demo controls on the bank's primary surface: "simulated traffic" and "paced arrivals" checkboxes next to the Live clock (34, 57).
13. Phone bank dashboard (57): nav pills overflow ("Activi…"), the Live/simulated/paced controls wrap into three lines.
14. The Currency select is greyed with a single value (15).
15. `#btn-evidence` carries `href="#"` in hidden markup on /bank and /bank?ref (not visible; filled on /bank?passport).
16. Beat 1, sold as "allowed", first shows ESCALATE (first payment under a new mandate held for the customer); the label warns "ALLOW · ESCALATE R.9 once", but a presenter clicking it for an ALLOW gets a hold (30).

Otherwise no empty states or placeholder text were seen; the pending dashboard's empties are labelled ("No AI agent holds a passport on this bank yet", "Nothing to export yet", "Nothing needs attention", 06).
