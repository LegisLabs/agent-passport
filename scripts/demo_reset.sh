#!/usr/bin/env bash
# Restore the exact pre-demo baseline between takes (product filed and admitted, mandate signed, passport ACTIVE, no payments, no refusals).
#   bash scripts/demo_reset.sh                 # local server on :8014
#   bash scripts/demo_reset.sh https://cdir.legislabs.uk
#   STAGE=registered bash scripts/demo_reset.sh # stop before the bank's admission decision
set -euo pipefail
BASE=${1:-http://127.0.0.1:8014}
curl -sS -X POST "$BASE/api/demo/seed?stage=${STAGE:-issued}"; echo
