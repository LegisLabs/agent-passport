# Agent Passport: mentor feedback implementation audit

Audited 8 September 2026 against the mentor checkpoint list. Repository `/home/timotej/LegisLabs/CDIR`, branch `bank-first-pivot`. Code citations are from commit `eacb32d` (one layout commit after `096fcfc`). Site audited at `http://localhost:8016` running the same tree, because `https://cdir.legislabs.uk` was unreachable during the audit (the host's Caddy proxy and sibling containers were stopped at 19:15; a developer restarted them at about 20:05 and the host answers again). Screenshots: `audit-screenshots/` (80 images, named `NN-slug.png`). Raw findings from the two passes: `audit-screenshots/code-findings.md`, `audit-screenshots/visual-findings.md`.

Audit only. Nothing was changed.

## Read this first: the audit ran on a moving target

Another session was editing the console files while the visual pass ran. Between 19:48 and 19:56 it saved `pay/templates/bank.html`, `pay/templates/customer.html`, `pay/static/app.js` and a new `pay/static/dashboard.css` (a "Meridian" dashboard redesign: greeting, balance card, new nav, Plus Jakarta Sans). Those edits were committed as `5a8b149` at the end of the audit and are what the live host now serves. Consequences:

- Screenshots 01 to 33 (landing, About, provider, admission, mandate form, terminal, expert console) show the committed code.
- Screenshots 34 to 60 (bank dashboard, passport page, customer dashboard, phone) show the uncommitted redesign, not `eacb32d`. Every layout defect listed under E and H4 is against that redesign and must be re-checked once it is committed.
- The first pass caught the half-applied state as page errors (`AP.dashExtras is not a function` on `/bank`, `AP.customerExtras is not a function` on `/customer`). They did not recur once the files settled, and a fresh-browser reload test was clean on every page. If templates and JS are ever deployed in separate steps, viewers see exactly that.

## 1. Summary

| # | Verdict | Note |
|---|---|---|
| A1 | PASS | Filing is completeness only; admission is the bank's; issuance at signing; no regulator gate anywhere in code or UI. |
| A2 | PASS | `/regulator` and `/audit` redirect to the bank; supervisor appears only in evidence export, each export chained. |
| A3 | PARTIAL | Every decision logged with time, rule, outcome, receipt, replayable inputs; agent id and mandate version live inside JWT strings, not as fields. |
| A4 | PASS | No approval, certification or licence language toward a regulator. Two nits: "Approve and release" button, "Organisers and regulators" logo row on the landing. |
| B1 | PARTIAL | Exact positioning on About; the landing hero never says "checkpoint alongside fraud and sanctions checks" and foregrounds the standard PDF. |
| B2 | PASS | Customer flow reads as the bank's own app. "Offered by the bank as a service" is implied, not stated. |
| B3 | PARTIAL | Section exists and is clear; "not consumer-facing" missing; sits 6,000px down the About page. |
| B4 | PASS | £576m APP fraud, up 19%, sending bank reimburses since 2024, with chart and UK Finance source. |
| C1 | PARTIAL | Bank and customer views differ in content, but the bank's passport exception view and the expert console show the agent's verbatim document quotes. |
| C2 | FAIL | No surface is labelled as the agent owner's screening tool; the intent exists only in prose. |
| C3 | FAIL | No role filtering in the data layer: every API returns everything to any caller. Visual only. |
| C4 | FAIL | An incident bundle returns the whole passport history, full mandate with every payee, the register filing and the officer's note. |
| D1 | PASS | Red "Refused · fraud indicator" vs grey "Refused · agent error", amber "Held", with a legend line; one icon bug on the customer side. |
| D2 | PASS | Two classes mapped once in the rule pack, stored per violation, routed differently (bank attention vs customer trail); first-payment holds route to the customer. |
| E1 | PASS | One derived status per instruction: Processed, Held, Refused with class, decided holds. |
| E2 | PARTIAL | Needs attention is first in the committed markup; in the uncommitted redesign it sits top-right in the narrowest column and clips. |
| E3 | PARTIAL | Release and refuse work and are chained with officer, approver, time, reason, receipt; the confirm step clips off-screen in the redesign. |
| E4 | PARTIAL | Statistics exist (totals, per-minute chart, per-agent table); table and axis clip; chart clock is an hour behind the log. |
| F1 | PASS | Currency on the mandate; R.6 refuses any other currency; USD beat demonstrates it. |
| F2 | PARTIAL | Tiers by account type work and are shown; customer classes (individual, micro, sme, large) carry no limits of their own; "undefined payments a day" before prefill. |
| F3 | PASS | Actions, currency, allow-list, per-payment, 30-day per account, daily count, expiry, signature, revocation all checked in `verify_action`. |
| G1 | PASS / PARTIAL | Key binding, proof of possession, nonce and R.3/R.4 implemented; the one-sentence explanation exists on About only. |
| G2 | PASS / PARTIAL | Injected invoice caught end to end; the hidden-text line shown in the terminal mock-up is not in the invoice the model actually reads. |
| G3 | PARTIAL | ISO 20022, Faster Payments and "checks run at the bank" on About; nothing on API integration for modern vs legacy stacks. |
| H1 | PARTIAL | The terminal opens with "An invoice lands on your desk"; the landing hero does not lead with it. |
| H2 | PARTIAL | Uppercase reason codes, R.x numbers, hashes, key ids and RFC numbers on primary surfaces. |
| H3 | PARTIAL | W3C VC compatibility stated; registry federation absent; cross-border explicitly disclaimed. |
| H4 | PARTIAL | No dead links, no placeholder text; several half-states, listed in section 4. |

## 2. Per-checkpoint detail

### A. Registration model, not approval

**A1. PASS.** Provider filing fields: `fixtures/pay/registration_fixture.json:3-139` and `pay/extraction.py:90-93` (company, accountable principal with declaration, insurance, product with pinned model version, Independent Assurance Evidence with level, intended use). Checks F.1 to F.6 are completeness only, `pay/rules.py:70-110`; `submit()` sets `registered` regardless of flags, `pay/main.py:243-265`. Admission is the bank officer's decision, `pay/main.py:297-329`, the only gate being the bank's own minimum assurance level. Issuance at mandate signing, `pay/main.py:609-645`, with no further step. No `approved_by_regulator` or equivalent exists. Agent key, proof of possession and config hash sit on the customer's deployment record by design (`pay/main.py:401-414`, APS 1001 s3.1). Screenshots `05-provider-filed-registration.png` ("A registration is a filing, not an approval"), `08-bank-admission-page-full.png`, `12-bank-admitted-product.png`. Note: there is no benchmark or error-rate field; the assurance evidence summary describes it in prose.

**A2. PASS.** `/regulator` redirects to `/bank` (`pay/main.py:82-84`); `/audit` to `/bank#bd-trail` (`:76-79`); no regulator template. Supervisor appears only in `evidence_passport` and `evidence_violation` (`pay/main.py:1124-1139`), each export itself chained. Bank copy: "A regulator does not operate this dashboard and approves nothing in it" (`bank.html:66`). Screenshot `34-bank-dashboard-full.png` (Supervisory access card), `06-bank-dashboard-pending-admission.png`.

**A3. PARTIAL.** Verify entry (`pay/main.py:940-942`): instruction with signature, passport status, presented envelope, ledger and daily counters, nonce state, instruction hash, decision, rule, code, reason, failure class, full per-rule trace, rule pack; `ts`, `prev_hash`, `hash` and a bank-signed receipt from `pay/audit.py:16-29`. Human decisions are separate `decision` entries with officer, approver, outcome, reason and receipt (`pay/main.py:1014-1019`). Missing as fields: agent id and key thumbprint (computed at `:945-952` but not written), mandate version (only inside the JWT). Smallest fix: add `agent_id`, `agent_kid`, `mandate_version` to the entry dict at `pay/main.py:940`. Screenshot `40-bank-evidence-trail.png`, `38b-bank-log-row-expanded-viewport.png`.

**A4. PASS.** Every hit of approve/certify/licence/endorse is a negation or the bank's or customer's own act (`provider.html:5-6`, `about.html:11,24,25,38,69,70`, `bank.html:66`, `README.md:16,22,147`). Two nits: the "Approve and release" button (`app.js:245, 371`) is the only "approve" verb in the routine flow, and the landing logo row is labelled "Organisers and regulators" (`home.html:16-22`, `pay/main.py:51`) with the no-endorsement line only on About. Smallest fix: rename the button to "Release", relabel the row "Hackathon organisers". Screenshot `01-landing-hero.png`, `35-bank-needs-attention-strip.png`.

### B. Bank-as-buyer positioning

**B1. PARTIAL.** About has the exact sentence: "a pre-authorisation checkpoint inside the bank's existing payment pipeline. It runs alongside fraud detection and sanctions screening, before settlement, and replaces none of them" (`about.html:47-48`, screenshot `03c-about-where-it-sits-in-the-bank.png`). The landing hero (`home.html:7-8`) speaks to the bank but never says checkpoint or pipeline, and "Our proposal" (`home.html:57-69`) foregrounds APS 1001 and the PDF, which is the standard pitch the mentor warned against. Smallest fix: one sentence in the hero ("It sits in your payment pipeline next to fraud and sanctions checks, before settlement, and replaces none of them") and demote the APS block below "The result". Screenshot `01-landing-hero.png`, `02-landing-full.png`.

**B2. PASS.** Customer page is the bank's app: account header, balance, Transactions tab with ordinary lines and a running balance, "your bank", "for your confirmation" (`customer.html:4-17,31,80,101`, `app.js:668-675,776`). Screenshots `50-customer-dashboard-history.png`, `59-customer-transactions-tab.png`. Not stated anywhere: that the bank offers this to business clients as a service. Smallest fix: one line in `about.html:20` or `customer.html:31`. Seam: the mandate form (`15`, `17`) still uses the old utility layout inside the redesigned app, and the Legis Labs masthead sits over a "Meridian" account.

**B3. PARTIAL.** `about.html:65-71`: not a payments rail; not an AML or sanctions system; not a regulator's operating tool; not model certification. Missing "not consumer-facing" (and the rule pack ships a `personal_current` tier and `individual` class, `rulepacks/payments-2026.09.json:53-58,73-76`, which undercuts the claim unless stated). Bullet 2 names AML and sanctions, not the fraud engine. Screenshot `03b-about-what-this-is-not.png`, about 6,000px down an 8,500px page. Smallest fix: add the fifth bullet, add "not a replacement for the fraud engine" to bullet 2, and link the section from the landing.

**B4. PASS.** `home.html:33-36` "£1.28 billion taken from UK customers last year, £576 million was authorised push payment fraud, up 19% ... since 2024 the sending bank carries the loss" with a 2021 to 2025 chart and source; `about.html:20,26`. Screenshot `02-landing-full.png`.

### C. Privacy and data minimisation

**C1. PARTIAL.** The routine bank log row (`app.js:387-397`) is minimal: instruction, payee, amount, nonce, hash, the nine checks. But the bank's passport exception view renders every extracted fact with its verbatim quote (`app.js:543-547`), and the expert console shows the full invoice text and quotes (`app.js:986-1017`). The customer sees a plain-language summary in-page (`app.js:662-695`) but is linked to the same raw violation bundle (`app.js:709`). Screenshots `34-bank-dashboard-full.png` vs `50-customer-dashboard-history.png` (content differs: bank shows population totals, attention, per-agent statistics, supervisory exports; customer shows own balance, own agent, own counts, notifications). Caveat from the redesign: both pages now share one template so they look like one product with two logins. Smallest fix: drop the `<q>` quotes from the bank's `renderEvidence` (`app.js:547`).

**C2. FAIL.** No surface is labelled as the agent owner's internal screening tool. Nearest wording: "a quality signal for its owner, not a report to anyone" (legend line) and "worth raising with your provider" (`app.js:675`). Smallest fix: a one-line caption on the customer's agent-error notification and on the console's extraction block. Screenshots `51-customer-notifications.png`, `35-bank-needs-attention-strip.png`.

**C3. FAIL.** `/api/state` (`pay/main.py:118-136`), `/api/audit` (`:976-980`), `/api/violations` (`:518-526`), `/api/evidence/*` (`:1124-1139`) and `/api/passports/{id}` (`:728-739`) return everything to any caller; there is no auth, session or role parameter anywhere. Every view calls the same two endpoints and chooses what to render (`app.js:74,165,221,607,636`). If a judge asks "does the bank technically receive the agent's reasoning", the honest answer today is yes, and so does anyone with the URL. Smallest fix that makes the claim true: a role parameter or header on `/api/state` and `/api/audit` that strips `presented_envelope`, `violations[].evidence` and other subjects for the customer role, and limits the supervisor role to `/api/evidence/*`.

**C4. FAIL.** `evidence_bundle()` (`pay/main.py:1093-1121`) returns every audit entry for the passport, the whole mandate with all payee accounts, the register filing, the officer's note, all three JWTs and the payments list even when asked for one violation; only the violations list is narrowed (`:1102-1105`). Smallest fix: when `violation_ids` is given, restrict rows to the violation's audit entry, its intent entry and the nearest mandate and issue entries, and include only the matching supplier. Screenshot `34-bank-dashboard-full.png` (Supervisory access exports).

### D. Flag separation

**D1. PASS.** Screenshots `35-bank-needs-attention-strip.png` (red "Refused · fraud indicator" beside amber "Held", legend line), `48-bank-log-after-both-decisions.png` (red vs grey "Refused · agent error"), `49-bank-passport-page.png`. Labels always accompany colour. Defect: the customer notification gives an agent-error refusal a green tick icon, the same as a released payment (`50-customer-dashboard-history.png`, redesign).

**D2. PASS.** Two classes in `rulepacks/payments-2026.09.json:280-309`, mapped once by `classify_refusal` (`pay/rules.py:148-155`), stored in `violations.failure_class` (`pay/db.py:106,461-465`). Routing: attention strip is held plus fraud only (`app.js:228,238-239`); customer trail carries both with distinct notes (`app.js:667-675`); first-payment holds go to the customer's confirm (`pay/rules.py:302-305`, `pay/main.py:1040-1070`), hold-above to the bank's decide (`pay/main.py:993-1025`). Nit: the three delegation-chain codes are unmapped and default to agent error.

### E. Bank dashboard mechanics

**E1. PASS.** `statusChip` (`app.js:42-52`): Processed, Held, Held · first payment, Processed · released by approver, Processed · confirmed by the customer, Refused · by approver, Refused · by the customer, Refused · fraud indicator, Refused · agent error. Derived at render from the immutable audit row plus the decision entries; not stored as a column. Screenshot `48-bank-log-after-both-decisions.png`.

**E2. PARTIAL.** Committed markup puts Needs attention first (`bank.html:12-19`), newest first, held and fraud only (`app.js:238-241`). In the uncommitted redesign it sits top-right in the narrowest column; the eye lands on "Value moved £2,419,350" and the row content clips (`34-bank-dashboard-full.png`, `35`, `47`). Fix: re-check after the redesign is committed; give the strip the full width above the tiles.

**E3. PARTIAL.** `POST /api/audit/{id}/decide` (`pay/main.py:993-1025`): only undecided ESCALATE entries, release or refuse, chain entry with officer, the customer's named approver, outcome, hold condition, reason and a bank receipt; release executes the payment. Both paths were exercised: `35` before, `42` confirm, `43`/`44` after release; `45`, `46`, `47`, `48` after refusal. Defect in the redesign: the confirm panel renders 1,469px wide inside a 309px column, so "Confirm and release the payment" reads "Confirm and release the p…" on a 1400px viewport (`42b-bank-release-confirm-viewport.png`). This is the moment mentors will watch. Caveat: the officer is a constant (`config.BANK_OFFICER`); there is no login.

**E4. PARTIAL.** "At a glance" tiles with carried-forward synthetic totals and the seam stated (`bank.html:20-24`, `fixtures/pay/opening_stats.json`), and a Statistics card with session totals, a per-minute volume chart and a per-agent table (`bank.html:26-32`, `app.js:299-320`). Screenshot `39-bank-statistics.png`. Defects: Value, Held and Refused columns clip ("£", "£2,4"), the y-axis clips, the chart's x-axis is in UTC (18:56) while the log and Live clock show local time (19:56), and the empty state draws a £0 to £1 axis (`06`). Fix: local-time labels in `renderStats`, column widths in the card.

### F. Mandate fields

**F1. PASS.** Form field `customer.html:77` (GBP, "payments in any other currency are refused"); payload `pay/main.py:600`; containment at signing `pay/rules.py:389-390`; R.6 `CURRENCY_NOT_PERMITTED` at `pay/rules.py:271-273`. Demonstrated by beat 9 (`32-console-beat9-usd-refused.png`). The select is greyed with a single value; reads like a disabled placeholder.

**F2. PARTIAL.** Tiers by account type in the rule pack (`:52-71`: personal current £2,500, business current £10,000, business savings £25,000) and enforced as the lower of tier and admission ceiling (`pay/rules.py:139-151`). Shown on the form as "Most you can grant: Business current account, Small or medium enterprise: agent ceiling up to £10,000 a payment ..." (`17-customer-mandate-form-filled.png`) and on the admission card (`09`). Customer classes individual, micro, sme, large exist (`:72-89`) but carry no limits, only a default account type, and there is no account-type selector on the form. Bug: before prefill the line reads "undefined payments a day" (`15-customer-mandate-form-empty.png`). Smallest fix: give classes their own ceilings and take the minimum in `effective_limits`; guard the empty-form line.

**F3. PASS.** One instruction through `verify_action` (`pay/rules.py:187-315`): R.1 admission signature; R.2 list status and admission validity; R.3 agent identity signature bound to the admission; R.4 instruction signature against `cnf.jwk` and a fresh nonce; R.5 not revoked, present, customer-signed, for this passport, unexpired; R.6 action, currency, payee on the allow-list; R.7 per-payment limit; R.8 30-day total per account and daily count; R.9 hold condition and first payment. Amendment replaces the stored JWT so the newest version is enforced (`pay/db.py:298-305`). Gap: if a caller presents its own envelope (`VerifyIn.passport`), a validly signed earlier version would pass R.5; compare `mandate.version` with the stored one.

### G. Verification and identity

**G1. PASS for mechanism, PARTIAL for explanation.** `cnf` key in the agent identity JWT (`pay/main.py:414`), proof of possession by challenge (`:404-407`), config hash recorded (`:408,412`) but never checked at runtime, R.3 and R.4 (`pay/rules.py:215-243`), public keys at `/api/signers`. The one-sentence explanation exists on About only: "Each AI agent deployment holds a key only it can use; the bank challenges that key on every payment, so a copied name or a lookalike model cannot answer" (`about.html:35`). The hero's "the bank cannot see which agent acted, on whose authority, or who answers for it" states the problem, not the mechanism. Smallest fix: reuse the About sentence under the customer's agent record and above the bank's envelope.

**G2. PASS for the path, PARTIAL for fidelity.** `POST /api/agent/invoice` (`pay/main.py:846-890`): intent declared before reading, extraction, signed instruction, R.6 refusal classed fraud. Terminal After world: R.6 ✗, "Denied", "The document changed the destination, not the AI agent. Money never moved." (`28-terminal-after-world-end.png`; Before world `27` ends "Money gone"). Discrepancy: the terminal's rendered invoice shows an "URGENT" notice and a hidden white-on-white "Note to automated processing" line (`terminal.html:46-49`) that do not exist in the text the model reads (`fixtures/pay/invoices/INV-9001-poisoned.txt`), and the terminal's "Reads amount/account" facts are static HTML. The injection is depicted, the redirection is demonstrated. Smallest fix: add the two lines to the fixture invoice.

**G3. PARTIAL.** `about.html:48` (ISO 20022 pain.001 fields, Faster Payments, checks at the bank), README API table, `/api/docs`. Nothing on modern vs legacy integration patterns. Smallest fix: one sentence naming one synchronous `POST /api/verify` per instruction that a gateway or a legacy batch pre-processor can call before release. Screenshot `03c-about-where-it-sits-in-the-bank.png`.

### H. Narrative and simplicity

**H1. PARTIAL.** Terminal opens "An invoice lands on your desk." with Before and After (`25-terminal-opening.png`). The landing hero leads with the abstract claim and its buttons are the two dashboards and How it works (`home.html:7-9`); the invoice appears only in the problem diagram and the evidence record lower down. Smallest fix: make the first hero button go to the terminal.

**H2. PARTIAL.** Technical terms on primary surfaces: uppercase reason codes and R.x numbers in the bank log, expanded row and the customer's own trail (`app.js:199,393,1048`), "R.1 to R.8 ... held at R.9" in the customer's confirm box (`:721`), nonce, instruction hash, chain entry, receipt hash prefixes, "kid ... config ..." on the mandate form (`:771`), model id `claude-sonnet-5`, `pay_invoice`, `openpay-paygpt-6`, "GET /api/status/..." in the public terminal, the footer's RFC list on every page (`base.html:70`), and the demo controls "simulated traffic" and "paced arrivals" beside the Live clock. Full list in `audit-screenshots/visual-findings.md` section H2. Smallest fix: a code-to-phrase map next to `CLASSES` in `app.js:32` used by the log, the detail row and the trail; drop the rule range from the confirm box.

**H3. PARTIAL.** W3C Verifiable Credentials JWT profile and did:key compatibility stated (`about.html:60`, `base.html:70`, `bank.html:141`); the JWTs carry custom claims rather than a `vc` shape, so it is a compatibility claim. Registry federation appears nowhere; cross-border mutual recognition is explicitly disclaimed (`about.html:74`). Smallest fix: a two-line roadmap paragraph after the planned-fields note naming registry federation and cross-border recognition as the next revisions.

**H4. PARTIAL.** No dead links (every internal href returned 200), no "TODO" or placeholder copy, no disabled button without an explanation. Half-states: `/provider` has no button to start a registration since `096fcfc` (`provider.html`, `app.js:129`), so the provider layer cannot be walked from the UI without a seed; "Confirmation of Payee ... planned" on the signed mandate; PROTOTYPE tags on every runtime rule in the About list; the redesign defects in section 4. Full list in section 4 and `visual-findings.md` H4.

## 3. Prioritised fix list

Effort: S under an hour, M half a day, L a day or more.

Blocks or embarrasses the live demo on the 17th:

1. Commit or revert the uncommitted dashboard redesign, then re-run this audit's shots 34 to 60. Until then the deployed state is undefined. S to decide, M to finish.
2. Confirm step clipped off-screen in the redesign (`42b`). The approve moment must be visible on a 1400px projector. S.
3. Fixed "Powered by vouch.finance" badge overlapping content on every page, including the confirm panel and the phone view. S.
4. Needs attention clipped and demoted in the redesign (E2). S.
5. "undefined payments a day" on the empty mandate form (F2). S.
6. Expanded log row and statistics table clipped; chart clock an hour behind the log (E4, `38b`, `39`). S.
7. `/provider` has no entry point since `096fcfc`; a mentor asking to see the provider filing from scratch cannot. S (restore the button or link the seeded filing prominently).
8. Beat 1 in the expert console is labelled "allowed" but a fresh mandate holds the first payment for the customer (`30`). Either present it as the first-payment confirmation or seed the console with a confirmed mandate. S.

Mentor-visible (they will look for their own suggestion):

9. C2 owner's screening-tool label (ABZ). S.
10. C4 incident-only evidence bundle (ABZ, CSIS). M.
11. C3 role filtering in the data layer, at least a role parameter (ABZ, CSIS). M.
12. B1 hero sentence "checkpoint alongside fraud and sanctions checks", demote the PDF block; H1 first hero button to the terminal (Antoinette, Ronel). S.
13. B3 "not consumer-facing" bullet and a landing link to the section (Ronel). S.
14. F2 customer classes with their own limits and an account-type selector (Juan). M.
15. H2 code-to-phrase map so the bank log and the customer trail speak English (all). S.
16. G1 identity sentence on the customer and bank pages (Ronel). S.
17. G3 one integration sentence, modern and legacy (Ronel). S.
18. H3 federation and cross-border roadmap line (all). S.
19. A4 nits: "Release" instead of "Approve and release"; relabel the regulator logo row (William). S.
20. G2 fidelity: put the injected lines into the fixture invoice the model reads. S.
21. A3 agent id, key thumbprint and mandate version as fields in the verify entry. S.
22. D1 icon bug: agent-error refusal shown with a green tick on the customer side. S.

Cosmetic:

23. Console replay beat header "· · £0". S.
24. Empty-state statistics chart drawing a £0 to £1 axis. S.
25. Two brands on the customer page (Legis Labs masthead over a Meridian account) and the old-style mandate form inside the new app. M.
26. Phone bank dashboard nav pills overflow; demo controls wrap. S.
27. Greyed single-value currency select. S.
28. Dead `.bd-filter` handlers in `app.js:398`; hidden lifecycle buttons in `bank.html:144`. S.

## 4. Demo-day risk list

- The public host went down for about 50 minutes during this audit: Caddy and every sibling container stopped at 19:15 while two sessions were deploying, and came back at about 20:05. Nobody has explained the stop. Before the 17th, agree who deploys and confirm that `publish.sh` is the only thing touching the compose project.
- Two sessions edit and deploy from one working tree. The publish script rsyncs the working tree, so an uncommitted half-edit goes live. The `AP.dashExtras is not a function` page error seen at 19:48 is what that looks like to a viewer. Agree one deployer, and deploy only from a commit.
- Console errors: none on any page once files settled; a fresh-browser reload test was clean. Re-run after the redesign is committed.
- Seed data that looks fake: the "At a glance" tiles add carried-forward synthetic totals (£2.4m, 1,848 processed) to a session with nine instructions; the seam line explains it, but a banker reading the tiles then the log will ask. The landing evidence record hard-codes chain entry #17 and the terminal's seeded fallback uses the same id. All labelled synthetic.
- Timing: the bank dashboard polls every 5 seconds and status chips on held rows update only after a poll; the terminal's After world uses the live verifier only when an active signed passport exists. Reset the demo (footer "Reset demo" seeds the history stage) before presenting.
- Companies House runs in labelled demo mode on the live host (no API key in the deployed environment). A live lookup of a real company will fall back to the synthetic register.
- Extraction mode: the footer shows "Invoice reading fixture" locally; the live host runs Gemini. A Gemini outage falls back to the fixture and says so.
- Local network to the host drops TLS connections intermittently; the live walk needed one retry each run today.

## 5. Screenshots

All 80 images are in `audit-screenshots/`, named in journey order: 01 to 03 landing and About; 04 to 05 provider; 06 to 12 bank admission; 13 to 24 customer mandate; 25 to 33 Action Terminal and expert console; 34 to 49 bank dashboard, decisions and passport page; 50 to 55 customer dashboard and amendment; 56 to 58 phone; 59 to 60 transactions and full trail. The per-page error log and link sweep are in `audit-screenshots/_audit-log.json` and `_followup-log.json`.

## 6. Per-mentor incorporation

Status vocabulary: Done (in code and visible), Partial (in code or in copy, but not both, or incomplete), Not done, Deck only (agreed not to build).

### William (FCA, strategy and architecture)

| Point | Status | Where |
|---|---|---|
| Registration-based model, no approval database, no pre-approval | Done | A1, A2: filing checks are completeness only, admission is the bank's, `/regulator` redirects to the bank. Provider page opens "A registration is a filing, not an approval." |
| Regulators need high-quality, specific data to investigate | Partial | A3: every decision is chained with time, rule, outcome, receipt and replayable inputs, but agent id and mandate version are not first-class fields, and the incident bundle is passport-wide, not incident-scoped (C4). |
| Both the infrastructure concept and a narrative of the flow | Done | Landing (concept, proposal, result) plus the Action Terminal (Before and After the standard). H1 notes the landing does not lead with the story. |
| Strong evidence trails; tech choice open, blockchain an open question | Done | Hash chain with bank-signed receipts and replay (`pay/audit.py`, bank dashboard Evidence trail). The site claims a hash chain, not a blockchain. |
| Stay on the core proposal, no systemic or cyber detours | Done | No such sections on the site. |
| Regulator vernacular (registration, delegation, evidence trail, supervisory) | Done, with nits | A4: consistent; "Approve and release" and the "Organisers and regulators" logo row are the two things to rename. |
| FCA AI Lab as the post-hackathon route | Done | About: "the FCA AI Lab is a natural testing environment for this evidence model ... implies no FCA involvement or endorsement." |

### Antoinette (tech policy and regulation)

| Point | Status | Where |
|---|---|---|
| No regulator oversight of individual transactions; no regulator ownership | Done | A2; Supervisory access card on the bank dashboard; "Not a regulator's operating tool" on About. |
| Model on UK open banking / OBIE, industry-led standards | Done | About "Where this sits in UK policy": Future Entity, voluntary adoption, precedent of the OBIE under the CMA Order; APS 1001 written as a candidate industry standard. |
| Bank reporting obligations differ from reporting every agent error | Done | D2: agent errors are "a quality signal for its owner, not a report to anyone"; fraud indicators go to the bank's risk team. |
| Banks as the audience; commercial interest in fraud reduction and audit trails | Partial | B1, B4: the fraud case and the bank framing exist; the hero does not yet say "checkpoint in your pipeline". |
| Bank maintains the registry and triages; regulator only on incidents | Done | The bank's list and admission decisions; Needs attention; evidence on request. |
| Banking-app model: customer applies to its bank; bank keeps the log | Done | B2: the customer dashboard is the bank's app; mandate signed inside it; the bank holds the chain. |
| Start the demo with the invoice scenario | Partial | H1: the Action Terminal opens with it; the landing does not lead with it. |
| Use UK political interest in scams and fake payments | Done | B4 figures on the landing and About. |
| Cite HM Treasury consultation section 3.2, PSR consultation, FCA sandbox | Done | About "Where this sits in UK policy" cites the consultation, section 3.2 and question 15, the Open Banking chapter, and the AI Lab sandbox cohort. |
| Align vernacular with policy documents | Done | See A4. |

### ABZ (lawyer, privacy)

| Point | Status | Where |
|---|---|---|
| Shares too much with banks and authorities; add privacy-preserving mechanisms | Not done in the data layer | C3: no role filtering; every API returns everything. Visual separation only. |
| Detailed logs are the owner's internal screening tool, not shared with the bank | Partial / Fail | C1, C2: the bank's passport exception view and the expert console still show the agent's verbatim document reading; no surface is labelled as the owner's screening tool. The customer view does carry the owner-side wording ("a quality signal for you, not a report to anyone"). |
| Show as little as possible to each counterparty | Partial | C1: the routine bank row is minimal; the supervisor bundle is not (C4). |
| Distinguish AML/fraud flags from agent error flags, different colour or label and routing | Done | D1, D2: two classes, red vs grey with text labels and a legend, routed to the bank's attention strip vs the customer's trail. One icon bug on the customer side. |
| Verified company register in the whitelist (CompanyWall or equivalent) | Done, beyond the deck-only decision | Companies House Public Data API with name-first search, register check recorded in the signed mandate, labelled synthetic fallback; honest copy that the register holds no bank accounts and Confirmation of Payee is planned. |
| Parallel to mandate agreements and recurring payment authorisations (trajnik) | Not done | The word "mandate" is used throughout and the About page cites RFC 9396 rich authorisation, but no sentence draws the parallel to standing orders or direct-debit mandates. One sentence on About or the customer mandate card would cover it. |
| Side benefit: simplified accounting for businesses and suppliers | Not done | Not mentioned anywhere. |
| EU banks reimburse scam victims; outside the EU unlikely | Partial | The UK 2024 reimbursement rule is cited; no EU or non-EU contrast. |

### Juan (World Bank)

| Point | Status | Where |
|---|---|---|
| Passporting valuable for supervisors; registries matter in emerging markets | Partial | The supervisory value is on About ("What a regulator gets"); emerging markets and industry associations as a distribution path are not mentioned. |
| Fraud as the business case alongside hallucination risk | Done | B4 on the landing; hallucination framed as secondary ("The problem" and the terminal copy "deceived or mistaken"). The dedicated "AI agents also fail honestly" passage was removed on 8 September at the team's request, so hallucination now appears only in passing. |
| Distinguish unintentional agent error from intentional fraud | Done | D1, D2. |
| Fraud statistics back in the pitch | Done | £576m APP fraud, up 19%, chart, UK Finance source. |
| Explicit currency field in the mandate | Done | F1: field, signed payload, R.6 refusal, USD demo beat. |
| Segment limits by customer type and size | Partial | F2: tiers by account type are real and enforced; the classes (individual, micro, sme, large) carry no limits of their own and there is no "medium"; no selector on the form. |
| Narrative flow between sections | Partial | H1, B1: the landing hero, the standard block and the dashboards do not yet tell one story in order; the terminal does. |
| Private-sector-first adoption path | Done | About: "Government expects commercial incentives, not mandates, to drive adoption" and the OBIE precedent. |
| Industry associations as a distribution path | Not done | Not mentioned. |

### Ronel (Cambridge Digital Innovation)

| Point | Status | Where |
|---|---|---|
| Pre-authorisation checkpoint inside the bank's pipeline, alongside fraud and sanctions checks | Partial | B1, G3: exact wording on About; absent from the landing hero. |
| A service banks offer to enterprise clients, B2B, scalable beyond the UK | Partial | B2: the customer flow reads as the bank's app; "offered as a service to business clients" is never stated; "beyond the UK" is disclaimed on About. |
| No late pivots | Observed | The 8 September changes were additive (statistics, amend and revoke, name-first search, empty forms with prefill) plus the dashboard restyle committed at 5a8b149 during this audit. The restyle is the one late visual change; its defects are in section 3, items 1 to 6. |
| Payment status field: processed, flagged, held | Done | E1. |
| Exceptions-first layout | Done in markup, Partial in the restyle | E2. |
| Human-in-the-loop approve and override | Done, one visual defect | E3: release and refuse both work and are chained; the confirm step clips in the restyle. |
| Trend and volume monitoring for banks | Done, with clipping | E4: tiles, per-minute chart, per-agent table. |
| Different user profiles and payment types across clients | Partial | Account tiers and customer classes exist; one customer and one payment type (pay_invoice) are demonstrated. |
| "What it is not" section | Partial | B3: present; missing "not consumer-facing"; deep in the About page. |
| Simplify the identity and model-version verification in plain terms | Partial | G1: the plain sentence exists on About only; the customer and bank pages show key ids and config hashes. |
| Integration approach for legacy and modern stacks, API details | Partial | G3: ISO 20022 and Faster Payments on About, API table in the README, nothing on legacy vs modern patterns. |
| 3 to 5 minute story, depth in the deck | Not assessable here | The site supports it (terminal as the story, About as the depth); the pitch itself is outside this audit. |
| ISO 20022 and UK Faster Payments referenced | Done | About "Where it sits in the bank". |

### Cross-mentor synthesis

| Settled point | Status |
|---|---|
| 1. Registration, not pre-approval; regulator by exception | Done. |
| 2. Bank is the buyer; a service to enterprise clients | Partial: bank-first is everywhere; "sold as a service" is implied, not said. |
| 3. Simplify the narrative; open with the invoice; regulator vernacular | Partial: vernacular done; the landing does not open with the invoice; codes and hashes leak into primary surfaces (H2). |
| 4. Fraud is the business case, hallucination secondary | Done. |
| 5. Evidence trails per incident | Partial: the chain is strong; the per-incident bundle is passport-wide (C4). |
| 6. Data minimisation per counterparty; flag separation | Flags done; minimisation not done in the data layer (C2, C3, C4). This is the one mentor item with no code behind it. |

Build list: currency (done), segmentation (partial), status field (done), exceptions first (done in markup), human in the loop (done), trends (done), flag separation (done), role-based data views (not done), "What it is not" (partial).

Deck-only items: company-register integration was built anyway (Companies House); ISO 20022 and Faster Payments are on About; the federation and cross-border roadmap line is absent (H3); no blockchain claim is made.
