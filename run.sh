#!/usr/bin/env bashio
set -e

export DISPLAY=:99

Xvfb :99 -screen 0 1440x900x24 -ac &
XVFB_PID=$!
sleep 2

if bashio::config.has_value 'vnc_password'; then
    x11vnc -forever -shared -nopw -passwd "$(bashio::config 'vnc_password')" -rfbport 5900 -display :99 -auth guess &
else
    x11vnc -forever -shared -nopw -rfbport 5900 -display :99 -auth guess &
fi
VNC_PID=$!

python3 /app/app.py