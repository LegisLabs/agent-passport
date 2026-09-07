# Action Terminal — Design Intent
Companion to CONTEXT_BRIEFING.md and MODEL_REGISTER_GOAL.md. This describes what the Action Terminal should BE; you (Claude Code) decide layout, markup, and styling details within it. Presentation only — no changes to `/api/verify` or rule logic.

## The idea in one line

The Action Terminal is the courtroom of the demo: the one place where everything the other panels established gets tested against a live instruction, in public, by rules alone.

## The feeling to aim for

A machine, not an app. Everything above the verdict is evidence; the verdict is short, cited, and signed. No AI opinion anywhere in the decision path, no "maybe". A non-technical viewer should leave with one sentence: every payment faces nine checks, and the mandate — written by the customer — is the law being applied.

## Five parts, in order down the page

### 1. Standing state — what the bank knows
The passport card before anything happens: approved model, the agent the customer created, mandate summary (payees count, per-payment cap, 30-day cap, expiry), supervisor condition, three-signature verification status, live registry status with re-check. Beside it the running state: payments executed, 30-day totals per payee account. Message: the bank holds a complete, verifiable picture before any instruction arrives.

### 2. The actor — who is asking
The agent reads an invoice (clean or poisoned selectable; live LLM extraction shown with a verbatim quote per field) and produces a signed payment instruction. This is the only place AI appears at payment time, and it appears as a supplicant presenting a request — never as a decider. The poisoned path must make the manipulation visible: extracted wrong account highlighted before the bank ever sees it.

### 3. The judgment — nine rules, in order, deny by default
The core visual of the whole product. Every instruction walks the same gauntlet R.1–R.9 and the viewer watches it walk: rules resolve sequentially, evaluation stops at the first failure, later rules are visibly never reached ("not evaluated — denied by default"). The outcome is always one of three words — ALLOW / ESCALATE / DENY — with the deciding rule cited, a one-line reason, and an authority-signed receipt hash.

Two renderings of the same stage:
- **Verification view** (full-screen overlay, staggered sequential reveal, slowed-for-demonstration label): for the video and non-technical viewers.
- **Expert console** (the existing dense log): for judges who want the raw machine. Same API response, same truth, two magnifications.

### 4. The script — eight proposed instructions
Keep the ordered instruction list; it is a teaching script disguised as buttons. Together the eight cover every rule: allowlist pass, invoice-redirection fraud, over-ceiling, escalation above the condition, rolling 30-day limit, rogue key, unpermitted action type, lifecycle probe after suspend/revoke. A viewer who clicks top to bottom experiences the entire rulebook without reading it. Each button states plainly what it will demonstrate and what the expected outcome is.

### 5. The exhaust — consequences leave the room
Every refusal visibly becomes something elsewhere: a violation row on the regulator's anomaly panel, a hash-chained audit entry, sometimes a supervisor alert or incident. Show the handoff (a small confirmation line or link per refusal: "violation recorded → Regulator Panel"). The terminal does not hoard its history; it feeds the system. That is what makes one manipulation attempt turn into detection, escalation, and revocation in the demo's final act.

## Constraints
- Zero decision-logic changes; this is arrangement and presentation of what the API already returns.
- Keep repo rule numbering (payee allowlist = R.6). Keep honesty labels (sub-10ms note, prototype labels, fixture/live indicators).
- Works in fixture mode offline; clean at desktop and 390px; reduced-motion fallback for any animation.
- Tests and the Playwright walk stay green; extend the walk to cover both renderings once.
