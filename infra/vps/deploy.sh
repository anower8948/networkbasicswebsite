#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Single-host deploy.
#
#   sudo ./deploy.sh /path/to/checkout
#
# Deliberately boring: build, migrate, swap, reload, verify, and roll back if
# the health check fails. The frontend is swapped by moving a symlink, so the
# window in which a visitor could receive half a build is zero.
# ---------------------------------------------------------------------------
set -euo pipefail

SOURCE="${1:-$(pwd)}"
APP_ROOT=/opt/nlp
RELEASES="$APP_ROOT/releases"
STAMP="$(date +%Y%m%d%H%M%S)"
RELEASE="$RELEASES/$STAMP"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Run as root."
[ -d "$SOURCE/backend" ] || fail "No backend/ directory in $SOURCE."

log "Preparing release $STAMP"
mkdir -p "$RELEASE" "$RELEASES"
cp -R "$SOURCE/backend" "$RELEASE/backend"
cp -R "$SOURCE/frontend" "$RELEASE/frontend-src"

log "Building the API virtualenv"
python3.12 -m venv "$RELEASE/venv"
"$RELEASE/venv/bin/pip" install --quiet --upgrade pip
"$RELEASE/venv/bin/pip" install --quiet "$RELEASE/backend"
"$RELEASE/venv/bin/pip" install --quiet gunicorn uvicorn

log "Building the frontend bundle"
(cd "$RELEASE/frontend-src" && npm ci --silent && npm run build --silent)
mv "$RELEASE/frontend-src/dist" "$RELEASE/frontend"
rm -rf "$RELEASE/frontend-src"

# Migrations run before the new code starts, and are expected to be backward
# compatible with the release still serving traffic — that is what makes the
# restart below safe rather than a coordinated outage.
log "Running migrations"
set -a; . /etc/nlp/api.env; set +a
(cd "$RELEASE/backend" && "$RELEASE/venv/bin/alembic" upgrade head)

log "Swapping symlinks"
PREVIOUS="$(readlink -f "$APP_ROOT/backend" 2>/dev/null || true)"
ln -sfn "$RELEASE/backend" "$APP_ROOT/backend"
ln -sfn "$RELEASE/venv" "$APP_ROOT/venv"
ln -sfn "$RELEASE/frontend" "$APP_ROOT/frontend"
chown -R nlp:nlp "$RELEASE"

log "Restarting the API"
systemctl restart nlp-api

log "Waiting for health"
healthy=false
for _ in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then healthy=true; break; fi
    sleep 2
done

if [ "$healthy" != true ]; then
    log "Unhealthy — rolling back"
    if [ -n "$PREVIOUS" ]; then
        PREV_RELEASE="$(dirname "$PREVIOUS")"
        ln -sfn "$PREVIOUS" "$APP_ROOT/backend"
        ln -sfn "$PREV_RELEASE/venv" "$APP_ROOT/venv"
        ln -sfn "$PREV_RELEASE/frontend" "$APP_ROOT/frontend"
        systemctl restart nlp-api
    fi
    fail "Deploy failed; previous release restored. Check: journalctl -u nlp-api -n 100"
fi

log "Reloading nginx"
nginx -t && systemctl reload nginx

# Five releases is enough to roll back through a bad week without filling the
# disk with node_modules-sized directories.
log "Pruning old releases"
ls -1dt "$RELEASES"/*/ 2>/dev/null | tail -n +6 | xargs -r rm -rf

log "Deployed $STAMP"
