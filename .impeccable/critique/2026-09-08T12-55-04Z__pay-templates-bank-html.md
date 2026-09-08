---
target: the bank console
total_score: 24
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 2
target_identity: "file:/home/timotej/LegisLabs/CDIR/pay/templates/bank.html"
target_fingerprint: "sha256:ee33b946602e20dcca0901783a9e4f2ea40a1c6850c860587cfe0305b161387f"
target_path: /home/timotej/LegisLabs/CDIR/pay/templates/bank.html
timestamp: 2026-09-08T12-55-04Z
slug: pay-templates-bank-html
---
Method: dual-agent (A: a727ced48da2b9461 · B: a4a6b93652699aabf)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of System Status | 3 | seeded case never says the six steps already ran |
| 2 | Match System / Real World | 4 | language is the desk's own |
| 3 | User Control and Freedom | 1 | Revoke, Decline, Admit fire on click; no confirm; reason optional |
| 4 | Consistency and Standards | 2 | two Suspend/Revoke groups on the passport page |
| 5 | Error Prevention | 1 | Revoke next to Suspend with no guard |
| 6 | Recognition Rather Than Recall | 3 | rule codes never expanded on the dashboard |
| 7 | Flexibility and Efficiency | 2 | no grouping, filtering or keyboard path on refusals |
| 8 | Aesthetic and Minimalist Design | 3 | case page restates the filing three times |
| 9 | Error Recovery | 2 | raw API messages in red text |
| 10 | Help and Documentation | 3 | no link from a rule code to its text |
| Total | | 24/40 | Adequate |

Design specificity: authored (rules-not-boxes workspace, tabular figures, three-signer envelope); slips in the case page stepper and identical refusal rows. Detector: 3 CLI warnings in shared CSS (menu-panel shadow, marquee), none in bank.html; browser: 0 console errors, 0 overflow, 0 unnamed controls; dashboard th contrast 3.43:1 (--ink-3), textarea #bk-filenote unlabelled.

Priority issues:
- [P0] Irreversible actions unguarded: btn-revoke, btn-pd-revoke, btn-decline, btn-admit post on click; reason optional. Fix: require reason, inline two-step confirm, history highlight. harden
- [P1] Duplicate control surfaces on the passport page (Passport control + exception panel). Fix: one block under the H1. distill
- [P1] Admission decision ~4,000px down the case page; filing restated three times. Fix: decision strip under the lede, collapse steps 1-2. layout
- [P2] Seven identical refusals rendered as seven rows. Fix: group by payee account and rule with count. distill
- [P2] Phone: rulemap letter-wraps, agents table clips, stats wrap ragged. adapt
- [P3] Status vocabulary in three casings. polish

Persona flags: officer cannot annotate or group refusals; cold judge: alert link targets a hidden #exception on the dashboard; supervisor: export list capped at five, no visible record of an export.

Minor: review-note blank on seeded case; step 1 "hold above default: 5000" unformatted; "Paid, 30 days" sums with no date filter; register "lapsed" plain vs "admitted" pill; alert role=alert re-announced each load; passport lede repeats PayGPT 6.0 three times.
