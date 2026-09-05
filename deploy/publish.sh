#!/usr/bin/env bash
# Publish Agent Passport to the shared Hetzner box.
#   bash deploy/publish.sh            # both verticals
#   bash deploy/publish.sh hmrc       # cdir.legislabs.uk only
#   bash deploy/publish.sh pay        # pay.cdir.legislabs.uk only
# Conventions (compass/DEPLOY.md §0): app in /opt/cdir, never touch /opt/compass,
# Caddy drop-ins in /opt/caddy-sites, zero-downtime caddy reload, never `down -v`.
# First publish needs DEMO_PASSWORD=... to create the basic-auth gate; later runs reuse the hash.
set -euo pipefail
WHICH=${1:-all}
HOST=${SERVER:-root@37.27.202.168}
APP_DIR=/opt/cdir
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> rsync sources to $HOST:$APP_DIR"
ssh "$HOST" "mkdir -p $APP_DIR"
rsync -az --delete --exclude .env --exclude .venv --exclude data --exclude __pycache__ --exclude .pytest_cache \
  "$ROOT/app" "$ROOT/pay" "$ROOT/rulepacks" "$ROOT/fixtures" "$ROOT/deploy" "$ROOT/scripts" "$ROOT/docs" "$ROOT/README.md" "$HOST:$APP_DIR/"

echo "==> server .env from the local .env (only the keys the containers read)"
KEYS="GEMINI_API_KEY GEMINI_MODEL EXTRACTION_MODE HACKATHON_ORG_API_KEY API_BASE_URL VOUCH_MODE PAYMENT_RAIL VOUCH_PROGRAM_ID VOUCH_PRIVY_USER_ID VOUCH_MERCHANTS VOUCH_CATEGORY"
TMP_ENV=$(mktemp)
for VAR in $KEYS; do
  VAL=$(grep "^$VAR=" "$ROOT/.env" | head -1 | cut -d= -f2- || true)
  [ -n "$VAL" ] && printf '%s=%s\n' "$VAR" "$VAL" >> "$TMP_ENV"
done
grep -q '^GEMINI_API_KEY=' "$TMP_ENV" || { echo "no GEMINI_API_KEY in $ROOT/.env"; rm -f "$TMP_ENV"; exit 1; }
grep -q '^EXTRACTION_MODE=' "$TMP_ENV" || echo 'EXTRACTION_MODE=gemini' >> "$TMP_ENV"
scp -q "$TMP_ENV" "$HOST:$APP_DIR/deploy/.env" && rm -f "$TMP_ENV"

SERVICES=""
[ "$WHICH" = all ] || [ "$WHICH" = hmrc ] && SERVICES="$SERVICES cdir"
[ "$WHICH" = all ] || [ "$WHICH" = pay ] && SERVICES="$SERVICES cdir-pay"
echo "==> build + start:$SERVICES"
ssh "$HOST" "cd $APP_DIR/deploy && docker compose build $SERVICES && docker compose up -d $SERVICES"

echo "==> caddy drop-ins (basic-auth gate) + reload"
if [ -n "${DEMO_PASSWORD:-}" ]; then
  HASH=$(ssh "$HOST" "cd /opt/compass/deploy && docker compose exec -T caddy caddy hash-password --plaintext '$DEMO_PASSWORD'" | tr -d '\r')
  echo "    gate password set/rotated (user: lexis)"
elif ssh "$HOST" "grep -q 'lexis [$]2' /opt/caddy-sites/cdir-legislabs.caddy 2>/dev/null"; then
  HASH=$(ssh "$HOST" "awk '/lexis /{print \$2; exit}' /opt/caddy-sites/cdir-legislabs.caddy" | tr -d '\r')
else
  echo "ERROR: first publish with the gate needs DEMO_PASSWORD=... to create it"; exit 1
fi
for SITE in cdir-legislabs pay-cdir-legislabs; do  # pay drop-in has no placeholder: copied as is
  case "$WHICH:$SITE" in hmrc:pay-*|pay:cdir-*) continue;; esac
  ssh "$HOST" "rm -rf /opt/caddy-sites/$SITE; sed 's|__PASSWORD_HASH__|$HASH|' $APP_DIR/deploy/$SITE.caddy > /opt/caddy-sites/$SITE.caddy"
done
ssh "$HOST" "cd /opt/compass/deploy && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile"

echo "==> health"
sleep 3
for S in $SERVICES; do
  PORT=8013; [ "$S" = cdir-pay ] && PORT=8014
  ssh "$HOST" "docker exec $S curl -sf http://localhost:$PORT/api/health && echo"
done
[ "$WHICH" = pay ] || curl -sS -o /dev/null -w "https://cdir.legislabs.uk      HTTP %{http_code} (expect 401 without login)\n" --max-time 30 https://cdir.legislabs.uk/api/health || true
[ "$WHICH" = hmrc ] || curl -sS -o /dev/null -w "https://pay.cdir.legislabs.uk  HTTP %{http_code} (public; expect 200)\n" --max-time 30 https://pay.cdir.legislabs.uk/api/health || true
