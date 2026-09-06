#!/usr/bin/env bash
# Restore the exact pre-demo baseline between video takes (passport ACTIVE, mandate signed, no payments, no violations).
#   bash scripts/demo_reset.sh                 # local server on :8014
#   bash scripts/demo_reset.sh https://pay.cdir.legislabs.uk
#   STAGE=submitted bash scripts/demo_reset.sh # stop before approval, ready for Stage 1 (Standards Review Assistant)
set -euo pipefail
BASE=${1:-http://127.0.0.1:8014}
curl -sS -X POST "$BASE/api/demo/seed?stage=${STAGE:-issued}"; echo
