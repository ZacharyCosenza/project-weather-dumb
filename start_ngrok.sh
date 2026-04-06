#!/bin/bash
# Starts an ngrok tunnel to Streamlit (port 8501) and prints the public URL.
# Safe to re-run — kills any existing ngrok process first.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs

pkill -f "ngrok http" || true
sleep 1

nohup ngrok http 8501 >> logs/ngrok.log 2>&1 &

# Poll the ngrok local API until the tunnel URL is available
for i in $(seq 1 15); do
    URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['tunnels'][0]['public_url'])" 2>/dev/null || true)
    if [ -n "$URL" ]; then
        echo "[$(date)] Nowcast live at: $URL"
        exit 0
    fi
    sleep 1
done

echo "[$(date)] ngrok started but URL not yet available — check logs/ngrok.log"
