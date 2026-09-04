#!/usr/bin/env bash
# Publish the Agent Passport prototype to cdir.legislabs.uk.
# Idempotent. Modeled on website/publish.sh — static files + Caddy drop-in,
# graceful reload of the shared Caddy. Never touches /opt/compass or volumes.
set -euo pipefail
SERVER="${SERVER:-root@37.27.202.168}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "── 1/3 sync site + caddy drop-in"
ssh "$SERVER" 'mkdir -p /opt/caddy-sites/cdir-legislabs'
rsync -az --delete "$HERE/site/" "$SERVER:/opt/caddy-sites/cdir-legislabs/"
rsync -az "$HERE/cdir-legislabs.caddy" "$SERVER:/opt/caddy-sites/cdir-legislabs.caddy"

echo "── 2/3 graceful caddy reload"
ssh "$SERVER" 'cd /opt/compass/deploy && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile'

echo "── 3/3 verify"
sleep 3
curl -sS -o /dev/null -w "https://cdir.legislabs.uk  HTTP %{http_code}\n" --max-time 30 https://cdir.legislabs.uk/ \
  || echo "  (needs DNS A record cdir.legislabs.uk -> 37.27.202.168; cert issues automatically once it resolves)"
