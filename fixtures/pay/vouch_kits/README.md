Vouch.finance hackathon kit material, vendored so `scripts/vouch_kit_replay.py` runs offline.

- `kya-licence.json`, `agent-mandate.json`: manifests copied verbatim from github.com/finternet-ecosystem/hackathon-kits (branch feat/generalise-kits, MIT).
- `labels/<kit>.labels.jsonl`: ground truth written by their `run-stream.ts` when we replayed both kits against the sandbox on 5 Sept 2026 (runs lexis-am-1 and lexis-kya-2, org "Legis Labs Ltd Hackathon").
- `agent-passport-northgate.json`: our own manifest, seeded on the rail with `scripts/vouch_complete_seed.ts`, mirroring the demo mandate (three suppliers, £10,000 cap, PayGPT 6.0). `PAYMENT_RAIL=vouch` settles ALLOWed instructions against it.
