# Agent Passport — Model Register Restructure: Goal Statement
**Repo:** `LegisLabs/agent-passport`, payments vertical (`pay/`) only. Baseline: current v0.2.x.
This document states the intent. You (Claude Code) decide the field-level details, rule numbering, and UI arrangement — fine-tune the existing system rather than rebuilding it. Preserve everything that already works.

## The goal

Restructure the issuance flow so that:

1. **The model company registers its MODEL, not an agent.** It provides the information it would publish anyway: company identity, model name and pinned version, benchmarks, training type, documentation. A named person at the company attests that the registered documentation is ACCURATE (a truthfulness declaration, like a Companies House filing) — but the company carries NO liability for what any agent later does with the model. No insurance at this phase. Registration is their market access: banks only execute payments from passported agents, so being on the register is how a model gets sold. "Passport-eligible" is their selling point.

2. **The authority approves the model once** and sets the policy ceilings and the supervisor condition. It maintains the registries (approved models, live passports). It never reviews mandates or transactions — it acts on patterns, escalations, and bank reports, and can revoke a model (cascading to all passports on it) or a single passport.

3. **The customer turns the model into THEIR agent.** They pick an approved model, an agent key is generated for their deployment (proof of possession, config hash, key custody — all the deployment-specific material lives here), and they write and sign their own mandate within the ceilings. Live at once, no review. The governing sentence, use it in the UI and About: **a model becomes an agent when a customer gives it a mandate.**

4. **The bank stays exactly as it is.** R-rule semantics at payment time unchanged in effect; re-point what the signatures cover only as far as the new envelope requires. The demo beats (clean payment, poisoned invoice, boundary tests, revocation) must all still run identically.

## Liability tree (drive all copy from this)
- Model company: answers only for the accuracy of its registered documentation.
- Customer: answers for the mandate they signed and their deployment of the agent.
- Bank: answers if it executes without checking.
- Authority: holds the registries that make any failure reconstructable.

## Constraints
- Keep the three-signature envelope, real Ed25519 verification, PoP, hash-chained audit, replay, vouch mirroring, ceiling containment at signing, and the honesty labelling (CURRENT vs PROTOTYPE, "design prototype", synthetic data).
- Keep the registration checks meaningful — adapt the existing A.1–A.8 pattern to model scope rather than gutting it. Judge each existing field: move it to the phase where it now belongs, reword it, or drop it only if it has no owner in the new model.
- Tests green after every commit; new behaviour gets tests; fixture mode runs everything offline; small revertable commits.
- Do not touch the tax vertical, the J-rules (future), or Part B (config flag, default off).
- Update About, panel names, and intro copy to tell the three-phase story consistently. Sweep for leftover wording from the old flow.

## Definition of done
Full fixture-mode walk: register model → approve with ceilings → customer creates agent + signs mandate → all bank demo beats behave as today → model-level revoke cascades, passport-level revoke unchanged → audit intact, replay identical. Deployed and spot-checked.
