#!/usr/bin/env bash
# Publish the Agent Passport skeleton to cdir.legislabs.uk on the shared Hetzner box.
# Conventions (compass/DEPLOY.md §0): app in /opt/cdir, never touch /opt/compass,
# Caddy drop-in in /opt/caddy-sites, zero-downtime caddy reload, never `down -v`.
#
#   bash deploy/publish.sh
set -euo pipefail
HOST=${SERVER:-root@37.27.202.168}
APP_DIR=/opt/cdir
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> rsync sources to $HOST:$APP_DIR"
ssh "$HOST" "mkdir -p $APP_DIR"
rsync -az --delete --exclude .env --exclude .venv --exclude data --exclude __pycache__ --exclude .pytest_cache \
  "$ROOT/app" "$ROOT/rulepacks" "$ROOT/fixtures" "$ROOT/deploy" "$ROOT/README.md" "$HOST:$APP_DIR/"

echo "==> ensure server .env (Gemini key)"
if ! ssh "$HOST" "test -s $APP_DIR/deploy/.env"; then
  KEY=$(grep '^GEMINI_API_KEY=' "$ROOT/.env" | cut -d= -f2-)
  [ -n "$KEY" ] || { echo "no GEMINI_API_KEY in $ROOT/.env"; exit 1; }
  ssh "$HOST" "printf 'GEMINI_API_KEY=%s\nGEMINI_MODEL=gemini-2.5-flash\nEXTRACTION_MODE=gemini\n' '$KEY' > $APP_DIR/deploy/.env"
  echo "    wrote new .env"
fi

echo "==> build + start"
ssh "$HOST" "cd $APP_DIR/deploy && docker compose build cdir && docker compose up -d cdir"

echo "==> caddy drop-in (basic-auth gate) + reload"
if [ -n "${DEMO_PASSWORD:-}" ]; then
  HASH=$(ssh "$HOST" "cd /opt/compass/deploy && docker compose exec -T caddy caddy hash-password --plaintext '$DEMO_PASSWORD'" | tr -d '\r')
  echo "    gate password set/rotated (user: lexis)"
elif ssh "$HOST" "grep -q 'lexis [$]2' /opt/caddy-sites/cdir-legislabs.caddy 2>/dev/null"; then
  HASH=$(ssh "$HOST" "awk '/lexis /{print \$2; exit}' /opt/caddy-sites/cdir-legislabs.caddy" | tr -d '\r')
else
  echo "ERROR: first publish with the gate needs DEMO_PASSWORD=... to create it"; exit 1
fi
ssh "$HOST" "rm -rf /opt/caddy-sites/cdir-legislabs; sed 's|__PASSWORD_HASH__|$HASH|' $APP_DIR/deploy/cdir-legislabs.caddy > /opt/caddy-sites/cdir-legislabs.caddy && cd /opt/compass/deploy && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile"

echo "==> health"
sleep 3
ssh "$HOST" "docker exec cdir curl -sf http://localhost:8013/api/health && echo"
curl -sS -o /dev/null -w "https://cdir.legislabs.uk  HTTP %{http_code} (expect 401 without login)\n" --max-time 30 https://cdir.legislabs.uk/api/health || true
