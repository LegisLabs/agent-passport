# KY-A extension for purpose-bound value: Agent Passport ↔ vouch.finance AI Vouchers

**Status:** proposed compatibility profile, prototype. Written for the C:\>DIR hackathon; not a standard.

## The two objects

| | Agent Passport envelope (this repo) | vouch.finance AI Voucher |
|---|---|---|
| Issued by | three parties, each signing its own claim: the authority (`assurance`), the provider (`agent_identity`), the customer (`mandate`) | the org that holds the API key, via `POST /ai-vouchers` |
| Says | who assured the provider, which agent key, and what the customer allows: allowlist, per-payment and 30-day limits, expiry | a spending mandate: `policy.quota`, delegation depth, expiry; enforced at `/payments/quote` and `/payments/authorize` |
| Enforced by | the relying party (the bank) with ordered rules R.1–R.9; limit in the mandate, running total at the bank | the vouch rail's policy engine at transaction time |
| Revoked by | the authority: registry status flips, next verification fails R.2 | `DELETE /ai-vouchers/{id}`; children of a revoked parent are refused |

They are complementary: the passport answers *is this agent recognised, by whom, and for what*; the voucher carries *purpose-bound value* on a rail that will refuse to move it outside the mandate.

## Field mapping

Passport → voucher (`POST /ai-vouchers` body):

| Envelope field | Voucher field | Note |
|---|---|---|
| `passport_id` | `metadata.passport_id` | the join key in both directions |
| `assurance.iss` | `metadata.issuer` | which authority assured the provider |
| `agent_identity.agent.agent_id` | `metadata.agent_id` | |
| `mandate.customer.legal_name` | `metadata.customer` | |
| `mandate.authorization_details[0].monthly_limit_per_account.amount` | `policy.quota.totalCostUsd` | the voucher's quota is denominated by the rail; the currency is recorded in `metadata.currency` |
| `mandate.authorization_details[0].per_payment_limit.amount` | `metadata.per_payment_limit` | the rail's per-transaction cap lives in the program policy, not the voucher |
| `assurance.status.registry` | `metadata.status_url` | where the rail could re-check authority status |

Voucher → passport:

| Voucher field | Envelope field |
|---|---|
| `id` | `vouch_voucher_id` |
| `status` (via `GET /ai-vouchers/{id}/ledger`) | shown beside the registry status in the regulator and bank views |

## Lifecycle, one supervisory action, two rails

1. Officer approves → authority signs `assurance` → `mint_mandate()` creates the voucher with the mapping above.
2. Customer signs `mandate` → envelope complete → the bank starts allowing instructions.
3. Officer revokes → registry status `revoked` → `revoke_mandate()` deletes the voucher. The next instruction fails R.2 at the bank and is refused at quote on the vouch rail.

## What this profile does not do

- It does not put the voucher's running spend into the passport. A signed credential cannot carry a running total; both systems keep totals at the enforcement point.
- It does not delegate: v1 has no sub-agents, so the voucher's `delegation` policy is unused.
- It does not bind the voucher to the agent key. The rail authenticates the org API key, not the agent; the passport does the agent binding (R.4). A future profile could carry `agent_identity.cnf.jwk` thumbprint in voucher metadata and have the rail check a per-instruction signature.

## The mirror program

`fixtures/pay/vouch_kits/agent-passport-northgate.json` is a kit manifest in the sponsor's own format that reproduces the demo mandate on the rail: a program "Northgate Joinery supplier payments", the three allowlisted suppliers as merchants, one actor (Agent 247) with a spending mandate, and a pre-redemption rule hook `merchant.id in [the three] and cart.total <= 10000`. `scripts/vouch_complete_seed.ts` seeds it (their seeder only accepts its four built-in kit ids). With `PAYMENT_RAIL=vouch` every instruction the bank ALLOWs is then settled as intent → quote → authorize under that program, so the rail's own policy engine is a second, independent enforcement of the same allowlist and cap. A payee the customer never signed for has no merchant on the rail at all.

## Modes in this repo

`VOUCH_MODE=fixture` (default) records deterministic voucher ids and never calls the network. `VOUCH_MODE=live` calls `https://cdir.vouch.finance/api/v1` with the org's `sk_test_` key and falls back to the fixture answer, visibly labelled, on any failure. `PAYMENT_RAIL=vouch` additionally settles each ALLOW as intent → quote → authorize on the rail; a 403 there is reported as a rail-side decline, never as an error.
