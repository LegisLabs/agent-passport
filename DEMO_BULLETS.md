# Demo bullets

Prep
- Open https://cdir.legislabs.uk, press Reset demo in the footer
- Bank dashboard: simulated traffic off
- 1400 px wide, no other tabs

1. Action Terminal, Before (0:00 to 0:35)
- Businesses hand invoices to AI agents that read, decide and pay
- An invoice lands; a line says the bank details have changed
- The agent pays the new account; the bank sees three green ticks
- Money gone; the bank cannot tell which agent, on whose authority, or that an agent typed it
- £576m APP fraud last year; since 2024 the sending bank pays it back

2. Customer dashboard (0:35 to 1:20)
- Add an AI agent: pick PayGPT 6.0, a bank approved product; name it; the agent gets a key only it holds
- Prefill and sign the mandate: suppliers checked against Companies House, per payment, per month, until when
- The signature issues the passport (and mints the voucher on vouch.finance)
- Needs your attention: £12,000 to Ashby Ironmongery held, more than the mandate allows
- Write a note, Approve payment; name and note go on the record
- Payments inside the mandate flow on their own from here

3. Bank dashboard (1:20 to 2:00)
- Activity: every instruction today and why it was processed, held or refused
- Needs attention first: a held payment and a fraud indicator
- Agent errors stay out of the strip: a quality signal for the customer, not an alarm
- Approve, confirm: the decision is signed into the chain
- Evidence trail: the Ashby payment, nine checks, the hold, the approval with her name, each entry hashed onto the last
- Replay every verification: identical
- A supervisor reads this after an incident; nothing reports automatically
- Optional: passport page, Mandate on the vouch rail, Re-check on rail: active on both rails

4. Action Terminal, After (2:00 to 2:45)
- Same invoice, same agent, with a passport; the instruction is signed with the agent's own key
- Nine checks in order: product approved, passport active, identity and signature genuine, mandate signed
- Check six: the account is not on the mandate; held
- The document changed the destination, not the agent; nothing left the account
- A person decides; the record shows why

5. Landing, The result (2:45 to 3:00)
- Identity is not authority
- The check sits where the money and the liability are: at the bank
- Registration, approval and evidence stay with the bank; the regulator reads the evidence when it asks
- Legis Labs

Guardrails shown
- Human in the loop: mandate signature, customer approval with a note, officer approve and confirm
- Auditability: chained, receipted entries; replay
- Safety and governance: deny by default, nine ordered checks, two refusal classes
- Cyber risk: the agent's own key on every instruction; copied passport and replay refused

Fallbacks
- After world says "seeded": Reset demo and start again
- Needs attention empty: POST /api/demo/seed?stage=history
- No first-payment confirmation waiting: sign a fresh mandate
- Everything runs in fixture mode; nothing depends on Gemini, vouch or Companies House
