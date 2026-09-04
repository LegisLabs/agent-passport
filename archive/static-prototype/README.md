# Agent Passport — lightweight frontend prototype

Team baseline for the C:\>DIR hackathon. **Static, no backend.** Everything runs in the browser so the team can click through the story and iterate on copy, flow and visuals before the real build.

Live: **https://cdir.legislabs.uk** (drop-in site on the shared Hetzner Caddy).

## Run locally

```bash
cd prototype/site && python3 -m http.server 8765   # then open http://127.0.0.1:8765
```

No build step, no dependencies. Needs a browser with WebCrypto Ed25519 (Chrome 137+, Firefox 130+, Safari 17+); older browsers fall back to ES256 automatically and the UI says so.

## Publish

```bash
bash prototype/publish.sh    # rsync site/ + Caddy drop-in to the box, graceful reload
```

DNS: `cdir.legislabs.uk` must have an A record → `37.27.202.168`. Caddy issues the certificate itself once the record resolves.

## What is real

- **The credential.** A JWT signed in-browser with an Ed25519 key (WebCrypto), verified against the public key before every gateway decision. Tampered tokens fail. Header/payload/compact token shown decoded in the Regulator view.
- **The rules.** Ordered, deterministic, deny-by-default: `0.1` status active → `0.2` signature + validity → `5.2` client on 64-8 list → `4.1` action in scope → `4.2` per-filing limit → `4.3` cumulative 30-day limit (stateful, held by the gateway, never in the token) → `4.5` escalation threshold → ALLOW.
- **Revocation.** A registry flag. Revoke in the Regulator view and the next verification denies on `0.1` before any other rule runs.
- **The audit line.** Every decision is `sha256(prev_hash + entry)` chained to the previous one and pinned to `rule pack hmrc-rules-2026.09`. Tamper-evident. Not a blockchain.

## What is not real

Registers (synthetic), HMRC involvement (none), persistence (localStorage only), holder binding (`cnf: null`, Rung 2), sanctions screening, any server.

## The seven demo beats (Verification console)

| # | Action | Expected |
|---|---|---|
| 1 | VAT return £1,400, client on list | ALLOW |
| 2 | Quarterly update £4,200 | ESCALATE 4.5 (above £3,500 human threshold) |
| 3 | VAT return £900, client not on 64-8 list | DENY 5.2 |
| 4 | VAT return £9,400 | DENY 4.2 (per-filing cap £5,000) |
| 5 | View client records | ALLOW |
| 6 | VAT return £3,400, repeated | ALLOW ×5, then DENY 4.3 at £20,000 (structuring caught) |
| 7 | Amend prior return | DENY 4.1 (unknown action, deny by default) |
| — | Revoke in Regulator view, retry any | DENY 0.1 |

## Files

```
prototype/
├── site/index.html   three tabs + About
├── site/app.css      GOV.UK-style world, terminal console
├── site/app.js       data, WebCrypto signing, rules, audit chain, rendering
├── cdir-legislabs.caddy
├── publish.sh
└── README.md
```

Debug handle in the console: `AP.S` (state), `AP.fire(i)`, `AP.approve()`, `AP.revoke()`. Double-click the rule-pack label in the footer to reset the whole demo.

## Source documents

`../BRIEF_v2.md` (build brief) and `../Tax_Field_Research_CDIR.md` (UK tax-agent trust chain, standards crosswalk). Deviations from the brief: no FastAPI/SQLite (team asked for frontend-only); everything the brief put in the backend now runs in the browser with the same rule ids and API shape.
