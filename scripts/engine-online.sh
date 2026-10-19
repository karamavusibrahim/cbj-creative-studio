#!/bin/zsh
# Put the studio engine on the internet for the deployed site (web/ on Vercel), 2026-10-18.
#
#   scripts/engine-online.sh            # start (or reuse) the public engine on :8766, open a tunnel, point Vercel at it, redeploy
#   scripts/engine-online.sh status     # show the engine, the tunnel URL and the Vercel env
#   scripts/engine-online.sh stop       # stop the tunnel and the public engine (the site falls back to the showcase)
#   scripts/engine-online.sh restart-engine   # reload the engine code, keep the tunnel (never kill by port: it kills the tunnel)
#
# What it does: a second engine instance (`uv run cbj ui --port 8766`) with CBJ_API_TOKEN (random, kept in
# .engine-token), CBJ_ALLOWED_HOSTS=*.trycloudflare.com and CBJ_CORS_ORIGINS=<the site>; a Cloudflare quick
# tunnel to it (a new https://xxx.trycloudflare.com name on every start, no account needed); the tunnel URL and
# the token written to the Vercel project's production env (ENGINE_URL, ENGINE_TOKEN) and a production redeploy
# so the running site picks them up (env changes need a redeploy on Vercel). Your usual `cbj ui` on :8765 is not
# touched. Both instances share studio/ and the game player: make one creative at a time.
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PORT=${PORT:-8766}
SITE=${SITE_ORIGIN:-https://cbj-creative-studio.vercel.app}
LOG=$ROOT/logs
mkdir -p "$LOG"
[ -f .engine-token ] || openssl rand -hex 24 > .engine-token
TOKEN=$(cat .engine-token)

tunnel_url() { grep -a -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG/tunnel.log" 2>/dev/null | head -1; }

case "${1:-start}" in
  status)
    echo "engine :$PORT  $(lsof -ti :$PORT >/dev/null && echo running || echo stopped)"
    echo "tunnel      $(pgrep -f "cloudflared tunnel --url http://127.0.0.1:$PORT" >/dev/null && echo "$(tunnel_url)" || echo stopped)"
    (cd web && vercel env ls production 2>/dev/null | grep -E "ENGINE_URL|ENGINE_TOKEN|STUDIO_PASSCODE" || true)
    ;;
  stop)
    pkill -f "cloudflared tunnel --url http://127.0.0.1:$PORT" 2>/dev/null || true
    pkill -f "cbj ui --port $PORT" 2>/dev/null || true
    echo "stopped; the site now shows the showcase only"
    ;;
  restart-engine)
    # Restart only the engine (after a code change) and keep the tunnel. NEVER kill by port (lsof -ti :$PORT):
    # that also kills cloudflared's connection and the tunnel name is lost (2026-10-18).
    pkill -f "cbj ui --port $PORT" 2>/dev/null || true; sleep 1
    CBJ_API_TOKEN="$TOKEN" CBJ_ALLOWED_HOSTS='*.trycloudflare.com' \
    CBJ_CORS_ORIGINS="$SITE,http://localhost:3105,http://localhost:3000" \
    CBJ_PLANNER="${CBJ_PLANNER:-claude}" \
    nohup uv run cbj ui --port $PORT > "$LOG/engine-$PORT.log" 2>&1 &
    for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:$PORT/api/health && break; sleep 1; done
    echo "engine restarted on :$PORT; tunnel $(tunnel_url) $(curl -s -o /dev/null -w '%{http_code}' "$(tunnel_url)/api/health")"
    ;;
  start)
    if ! lsof -ti :$PORT >/dev/null; then
      echo "starting the public engine on :$PORT (log: logs/engine-$PORT.log)"
      CBJ_API_TOKEN="$TOKEN" CBJ_ALLOWED_HOSTS='*.trycloudflare.com' \
      CBJ_CORS_ORIGINS="$SITE,http://localhost:3105,http://localhost:3000" \
      CBJ_PLANNER="${CBJ_PLANNER:-claude}" \
      nohup uv run cbj ui --port $PORT > "$LOG/engine-$PORT.log" 2>&1 &
      for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:$PORT/api/health && break; sleep 1; done
    fi
    curl -s http://127.0.0.1:$PORT/api/health || { echo "the engine did not answer on :$PORT"; exit 1; }; echo
    pkill -f "cloudflared tunnel --url http://127.0.0.1:$PORT" 2>/dev/null || true
    : > "$LOG/tunnel.log"
    nohup cloudflared tunnel --url http://127.0.0.1:$PORT --no-autoupdate > "$LOG/tunnel.log" 2>&1 &
    URL=""
    for i in $(seq 1 40); do URL=$(tunnel_url); [ -n "$URL" ] && break; sleep 1; done
    [ -n "$URL" ] || { echo "no tunnel URL after 40 s; see logs/tunnel.log"; exit 1; }
    for i in $(seq 1 30); do curl -s -o /dev/null -w "%{http_code}" "$URL/api/health" | grep -q 200 && break; sleep 2; done
    echo "tunnel: $URL  ($(curl -s "$URL/api/health"))"
    cd web
    for k in ENGINE_URL ENGINE_TOKEN; do vercel env rm $k production --yes >/dev/null 2>&1 || true; done
    printf "%s" "$URL"   | vercel env add ENGINE_URL production >/dev/null
    printf "%s" "$TOKEN" | vercel env add ENGINE_TOKEN production >/dev/null
    echo "Vercel env updated; redeploying production..."
    vercel --prod --yes 2>&1 | tail -3
    echo "done: the site talks to $URL (keep this terminal's processes alive; 'scripts/engine-online.sh stop' to end)"
    ;;
  *) echo "usage: $0 [start|status|stop|restart-engine]"; exit 2;;
esac
