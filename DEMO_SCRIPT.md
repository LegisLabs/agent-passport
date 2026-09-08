# Agent Passport: three-minute demo script

Order: the world as it is today (Action Terminal, Before), the customer applies for its AI agent and approves a payment, the bank's dashboard and the payment in the evidence trail, then the world with Agent Passport (Action Terminal, After). About 430 spoken words. Times are cumulative.

Before recording: open https://cdir.legislabs.uk, press "Reset demo" in the footer (this seeds the demo and opens the Action Terminal), switch "simulated traffic" off on the bank dashboard once, and close other tabs. Record at 1400 px wide.

---

**0:00 to 0:35 · Action Terminal, "Before the standard" (press play)**

Say: "Businesses are handing their invoices to AI agents that read, decide and pay. This is how it goes today. An invoice lands. It looks genuine, but a line says the supplier's bank details have changed. The agent reads it and pays the new account. The bank sees an instruction and three green ticks. Money gone. The bank could not tell which agent acted, on whose authority, or even that an AI agent had typed it. Last year £576 million left UK accounts this way, and since 2024 the sending bank pays it back."

**0:35 to 1:20 · Customer dashboard (`/customer`): apply for the agent, approve a payment**

Say: "With Agent Passport, the customer's AI agent gets its authority from the customer, inside the bank's own app. Northgate Joinery picks a product its bank has approved, names the deployment, and the app gives the agent a key only it holds. Then the finance director writes the mandate: which suppliers, checked against Companies House; how much per payment; how much per month; until when. She signs it. That signature issues the passport."

Clicks: "Add an AI agent", pick PayGPT 6.0, continue; on the mandate page press "Prefill demo data" and "Sign mandate".

Say: "The first payment under a new mandate waits for her. Here it is: twelve thousand pounds to Ashby Ironmongery, held because it is more than the mandate allows. She reads it, writes a note, approves. Her name and her note go on the record. Payments inside the mandate flow on their own from here."

Clicks: open "Needs your attention", open the held payment, type a note, press "Approve payment".

**1:20 to 2:00 · Bank dashboard (`/bank`)**

Say: "This is the bank's side. Every instruction today, and why it was processed, held or refused. What needs a person sits first: a held payment and a fraud indicator. Agent errors, the agent's own mistakes inside its remit, stay out of that strip; they are a quality signal for the customer, not an alarm. An officer approves or declines with a note, and the decision is signed into the chain."

Clicks: on the held payment press "Approve", then confirm; point at the row now reading "Processed · released by approver".

Say: "And here is the customer's twelve thousand pound payment in the evidence trail: who asked to pay whom, how much, the nine checks, the hold, the approval with the finance director's name, each entry hashed onto the one before it. Replay any decision from its recorded inputs and it comes out identical. A supervisor asks for this after an incident and reads it. Nothing reports to a regulator automatically."

Clicks: scroll to the Evidence trail card, open the Ashby row, press "Replay every verification".

**2:00 to 2:45 · Action Terminal, "After the standard" (switch tab, press play)**

Say: "Now the same invoice, the same agent, with a passport. The instruction is signed with the agent's own key. The bank runs nine checks in order. The product is approved, the passport is active, the identity and the signature are genuine, the mandate is signed. Check six: the account is not on the mandate the customer signed. Held. The document changed the destination, not the agent, and nothing left the account. A person decides, and the record shows exactly why."

**2:45 to 3:00 · Landing page, "The result"**

Say: "Identity is not authority. Agent Passport puts the check where the money and the liability are: at the bank. Registration, approval and evidence stay with the bank; the regulator reads the evidence when it asks. Legis Labs."

---

## vouch.finance insert (about 20 seconds, for the sponsor prize)

The integration runs on the live host: the mandate is mirrored as an AI Voucher when the customer signs, every allowed payment settles on the vouch rail, and revoking the passport or the mandate revokes the voucher. Two stops make it visible without changing the story.

**At 1:15, right after the mandate is signed (customer page, the green signature block)**

Say: "The signed mandate is also minted as an AI Voucher on vouch.finance, so the bank's checks and the rail's policy engine hold the same limits."

Point at the line in the signature block: "the voucher is minted on the vouch rail".

**At 1:50, on the bank dashboard, open the passport (`/bank?passport=AP-2026-0107`)**

Say: "Here is the passport on both rails: the bank's list says active, and the voucher on vouch.finance says active. Suspend or revoke here and the voucher goes with it, so the next instruction is refused on two rails."

Clicks: scroll to "Mandate on the vouch rail", press "Re-check on rail" (it queries the sandbox live and shows the voucher id and status). If time allows, press "Revoke" with a reason, then run beat 8 in the expert console: the verdict reads "two rails refuse".

If the sandbox is slow on the day, the panel shows "live-fallback (fixture)" and says so; the story still holds, and the fallback is honest on screen.

## Fallbacks

- If the terminal's After world shows "seeded", the passport was reset mid-take: press "Reset demo" and start again.
- If Needs attention on the bank dashboard is empty, `POST /api/demo/seed?stage=history` restores a held payment and a fraud indicator.
- If the customer's first-payment confirmation is not waiting, sign the mandate again on a fresh agent; the first instruction under it is always held for the customer.
- The whole take runs offline in fixture mode; nothing depends on Gemini, vouch.finance or Companies House being reachable.

## What the video shows, mapped to the mandatory guardrails

- Human in the loop: the customer's mandate signature, the customer's approval with a note, the officer's approve-and-confirm.
- Auditability and traceability: the chained, receipted entries and the replay.
- Safety and governance: deny by default, nine ordered checks, two refusal classes routed differently.
- Cyber risk: the agent's own key on every instruction; a copied passport or a replayed instruction is refused.
