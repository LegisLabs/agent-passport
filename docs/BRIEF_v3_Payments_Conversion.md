# Agent Passport — Payments Vertical Conversion Brief (v3)

**For:** Claude Code, working in the existing repo (the deployed HMRC build). Run the `impeccable` pass on all UI.
**Goal:** convert the HMRC Self Assessment vertical into the B2B payments vertical described below, reusing the engine. The HMRC build stays deployed untouched at its current URL as the transferability beat; the new vertical deploys alongside it (same box, new app path or subdomain, e.g. pay.cdir.legislabs.uk or cdir.legislabs.uk with a vertical switch).
**Deadline reality:** submission 8 Sept 23:59. Floor first, stretch second. Anything ambiguous: pick the simplest option and note it in the README.

---

## 1 · The scenario (canonical, use these names everywhere)

**Northgate Joinery Ltd** (small business, the customer) pays suppliers through **PayRail Ltd** (licensed payment-initiation provider, the operator). PayRail runs an AI accounts-payable agent, **Agent 247**, that reads invoices and initiates payments. Before deployment, PayRail submits evidence to the **payments authority** (jurisdiction-neutral; the UK demo says "the national payments supervisor"). The authority runs automated KY-A checks, a human officer approves with a condition, and a passport is issued. **Northgate's bank** verifies the passport on every payment instruction before executing. The authority can suspend or revoke at any time; serious violations escalate back to it.

Framing rules (bake into copy and README):
- This demonstrates a **proposed** KY-A assurance framework, not a current legal requirement. Never imply the FCA requires this today.
- The passport carries permission, never personal data.
- Synthetic data only, stated in the UI banner and README.
- Never the word "blockchain" about our system. Our layer is signatures + registry + hash-chained log.

## 2 · The composite passport (core change vs HMRC)

Not one JWT. An **envelope of three independently signed Ed25519 JWTs**, each signed by the party entitled to the claim:

```json
{
  "passport_id": "AP-2026-0107",
  "assurance": "<JWT signed by AUTHORITY>",
  "agent_identity": "<JWT signed by PAYRAIL>",
  "mandate": "<JWT signed by NORTHGATE>",
  "status_url": "/api/status/AP-2026-0107",
  "vouch_voucher_id": "<set when minted on the vouch rail, else null>",
  "cnf": null
}
```

**assurance** (authority key): provider legal name, licence ref (synthetic, e.g. "PSP-4471"), KY-A assurance status, supervisor condition `{"human_confirm_above": {"amount": 5000, "currency": "GBP"}}`, accountable person at PayRail (name, role, declaration ref), issue/expiry, rule_pack_version.

**agent_identity** (PayRail key): agent name "Agent 247", agent public key, software name/version, config hash (sha256 of a fixture config file).

**mandate** (Northgate key): customer legal name, authorising officer (finance director name + role), supplier allowlist (list of supplier ids with account refs), per_payment_limit {3,500 GBP escalation is NOT here, see rules; cap 5,000 GBP}, monthly_limit_per_account {20,000 GBP, window P30D}, expiry.

Three keypairs generated at startup into `keys/` (gitignored) plus the agent's own keypair (fourth). Reuse existing crypto.py; add a `verify_envelope()` that checks all three JWTs and returns structured claims or the first failure.

## 3 · Views (five tabs, shared state)

- **/provider** (convert /operator): PayRail applies. Evidence pack (five synthetic docs: licence extract, agent technical description, insurance summary, accountable-person appointment letter, Northgate service agreement) read by Gemini into quote-anchored facts (reuse extraction.py and fixture mode unchanged, new schema + fixtures). Agent key shown, challenge signed. Submit.
- **/regulator** (reuse): queue → application → automated checks A.* with source + CURRENT/PROTOTYPE labels → officer decision (approve / request info / reject) with required note; approval **adds the supervisor condition** and signs the assurance JWT → passport card with decoded envelope (three panels, one per signer, each showing "verified, Ed25519") → lifecycle: suspend / reinstate / revoke with reason → incident feed (see /bank) → draft file note (Gemini, labelled draft).
- **/customer** (new, deliberately minimal, one page): Northgate's finance director sees the proposed mandate (supplier table, limits, expiry) and clicks **"Sign mandate"** (signs the mandate JWT). Before signing, the passport is incomplete and /bank denies with "mandate not signed". After signing, envelope completes.
- **/bank** (convert /relying): verification console. Status strip: passport id, assurance status, mandate status, payments count, per-account monthly meter (£X of £20,000). Buttons fire signed payment instructions at POST /api/verify (see beats). Terminal log: timestamp, action, verdict, rule id, reason, audit ref (hash chain), "decision replayable". Incident counter: 3 DENYs within a session → an "escalated to supervisor" event appears here and in /regulator's incident feed (a log row, no workflow).
- **/audit** (reuse): hash chain, receipts, replay.
- **/about** (reuse, rewrite copy): what is real, what is proposed, standards used (Ed25519, JWT, RFC 9396 shape for scopes, status-list-style revocation), what we do not claim, vouch integration description.

## 4 · Rules

Application checks A.* (authority side, over extracted facts + synthetic registers): A.1 provider licence ref resolves and active [CURRENT-analogue] · A.2 Companies House number resolves [CURRENT] · A.3 accountable person named with role + declaration [PROTOTYPE] · A.4 insurance evidenced [PROTOTYPE] · A.5 agent key proof-of-possession (challenge signature verifies) [CURRENT] · A.6 customer service agreement evidenced [PROTOTYPE] · A.7 requested limits within policy ceilings [PROTOTYPE] · A.8 software/config declared [PROTOTYPE].

Runtime R.* (bank side, ordered, deny by default), each with id + citation string:
- R.1 assurance JWT signature valid (authority key)
- R.2 assurance active and unexpired (registry status lookup)
- R.3 agent_identity JWT signature valid (PayRail key)
- R.4 payment instruction signed by the agent key inside agent_identity (rogue-key beat)
- R.5 mandate JWT signature valid, signed, unexpired (unsigned-mandate beat)
- R.6 supplier (payee account ref) on the mandate allowlist (redirection beat)
- R.7 amount within per_payment_limit
- R.8 amount + 30-day per-account total within monthly_limit_per_account (stateful, bank SQLite; structuring beat)
- R.9 supervisor condition: amount > human_confirm_above → ESCALATE
- else ALLOW. Unknown action types → DENY.

POST /api/verify body: {passport_id, agent_signature, action_type:"pay_invoice", payee_account_ref, supplier_name, amount, currency, invoice_ref} → {decision, rule_id, reason, audit_ref, receipt (signed)}.

## 5 · Vouch.finance adapter (the $25K integration)

New module `app/vouch.py`, env `VOUCH_MODE=fixture|live` (default fixture) and `PAYMENT_RAIL=local|vouch` (default local).

- Interface: `mint_mandate(passport) -> voucher_id`, `revoke_mandate(voucher_id)`, `settle_payment(instruction) -> {settled, rail_reason}` (only used when PAYMENT_RAIL=vouch).
- **fixture mode**: deterministic canned responses (voucher_id "VCH-FIX-001", always succeeds), so demo and tests never depend on their API.
- **live mode**: their hosted API `https://cdir.vouch.finance/api/v1`, key from env `HACKATHON_ORG_API_KEY`. Mint/revoke via the AI-voucher lifecycle routes (or MCP tools issue_agent_mandate / revoke_mandate). Payments (if PAYMENT_RAIL=vouch): intents → quote → authorize with `x-privy-user-id` and `x-sim-time` headers. Treat 403 on violation paths as an expected deny, not an error. Read verdicts from HTTP responses, never their SSE stream.
- Wiring: officer approval → mint (UI shows "mandate mirrored on vouch rail ✓" with voucher id); officer revoke → revoke there too (UI shows both rails refusing on the next beat). Failures in live mode fall back to fixture behaviour with a visible "(fixture)" tag, never crash the flow.
- Standalone script `scripts/vouch_kit_replay.py` (or ts, using their cloned client) documented in README: replays kya-licence + agent-mandate kits, maps steps to our /api/verify semantics, scores against labels.jsonl, prints a table. Not part of the app runtime.
- Repo also gets `docs/KYA_extension_for_purpose_bound_value.md`: one page mapping our envelope fields onto their voucher metadata (passport_id in voucher metadata, voucher_id in envelope), framed as a proposed compatibility standard.

## 6 · Demo beats (the /bank console buttons, in order)

1. Pay supplier "Fenwick Timber", £3,200, on allowlist → ALLOW (receipt shown; if PAYMENT_RAIL=vouch, "settled on vouch rail")
2. Same supplier name, unregistered account ref (redirection fraud) → DENY R.6 "payee not on customer-signed mandate" — narrate as the APP-fraud kill shot
3. £11,400 invoice → DENY R.7 exceeds per-payment cap
4. £4,800 invoice → ESCALATE R.9 supervisor condition (> £5,000 is the cap; use £4,800 vs condition £3,500? NO — condition is human_confirm_above 5,000; make this beat £5,600 → ESCALATE, and keep beat 3 at £11,400 vs cap £5,000 → DENY. Adjust numbers so beats are distinct: cap 10,000, condition 5,000. Final: beat 3 = £11,400 DENY R.7 (cap 10,000); beat 4 = £5,600 ESCALATE R.9.)
5. Repeated allowed payments pushing the 30-day per-account total past £20,000 → DENY R.8 "cumulative limit; structuring pattern caught"
6. Officer revokes in /regulator → next payment DENY R.2; if vouch live, show voucher revoked there too ("one supervisory action, two rails refuse")
7. Instruction signed with a rogue key → DENY R.4
8. Bonus if trivial: /customer un-signed state earlier in the script → DENY R.5 before the mandate is signed

Three DENYs trigger the incident escalation row (beat 2, 3, 5 accumulate).

## 7 · What ports unchanged

engine structure, db.py patterns, audit.py (hash chain, receipts, replay), extraction.py (new schema + fixtures), fixtures.py pattern, tests layout, deploy (Dockerfile, compose, Caddy, publish.sh), GOV.UK-adjacent visual language from the current build (white, #0b0c0c, green actions, red revoke, monospace terminal for /bank, zero border-radius, no gradients). The HMRC app is NOT modified.

## 8 · Non-goals

No delegation/sub-agents (mention in /about as roadmap; the kit replay's delegation-depth cases may simply be reported as "out of scope v1"). No multi-bank cumulative totals (per-account only, say so). No real FCA/bank integration. No login. No websockets. No React. No incident workflow beyond the log row. No VC/JSON-LD wrapper (say "verifiable-credentials pattern, JWT profile" in /about).

## 9 · Definition of done

`pytest` green (rules oracle incl. all beats, envelope verify, audit replay, vouch fixture) · self-seeds on first run · all beats produce expected verdicts through the UI in order · /customer sign flips R.5 · revocation flips R.2 (and vouch in live mode) · extraction works live with fixture fallback · deployed behind Caddy next to the HMRC app · README: run steps, API contract, rule list, beats (doubles as video storyboard), vouch modes + kit replay instructions, the compatibility spec linked.
