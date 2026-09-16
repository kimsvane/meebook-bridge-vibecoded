#!/usr/bin/env bash
set -e

export DISPLAY=:99

Xvfb :99 -screen 0 1440x900x24 -ac &
XVFB_PID=$!
sleep 2

VNC_PASS=""
if [ -f /data/options.json ]; then
  VNC_PASS="$(python3 -c "import json; print(json.load(open('/data/options.json')).get('vnc_password', '') or '')" 2>/dev/null || true)"
fi

if [ -n "$VNC_PASS" ]; then
  x11vnc -forever -shared -rfbport 5900 -display :99 -auth guess -passwd "$VNC_PASS" &
else
  x11vnc -forever -shared -nopw -rfbport 5900 -display :99 -auth guess &
fi
VNC_PID=$!

trap 'kill $XVFB_PID $VNC_PID 2>/dev/null || true' EXIT

python3 /app/app.py