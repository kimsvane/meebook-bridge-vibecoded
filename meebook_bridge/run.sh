#!/usr/bin/env bash
set -e

# Best-effort: installér custom integration i HA-config, hvis mappen er mountet
# (ny Supervisor: /homeassistant, ældre: /config). Ellers sker installation
# manuelt (se README).
LOG=/dev/stdout
HA_CONFIG=""
if [ -d "/homeassistant" ] && touch "/homeassistant/.mb_wtest" 2>/dev/null; then
  rm -f "/homeassistant/.mb_wtest"
  HA_CONFIG="/homeassistant"
  LOG="/homeassistant/meebook_bridge_install.log"
elif [ -d "/config" ] && touch "/config/.mb_wtest" 2>/dev/null; then
  rm -f "/config/.mb_wtest"
  HA_CONFIG="/config"
  LOG="/config/meebook_bridge_install.log"
fi

if [ -n "$HA_CONFIG" ]; then
  {
    echo "[$(date -Is)] Meebook Bridge starter (v1.0.13)"
    mkdir -p "$HA_CONFIG/custom_components/meebook_bridge"
    cp -r /app/custom_components/meebook_bridge/. "$HA_CONFIG/custom_components/meebook_bridge/" 2>/tmp/cp.err && \
      echo "Integration installeret i $HA_CONFIG/custom_components/meebook_bridge" || \
      echo "Kunne ikke installere integration automatisk: $(cat /tmp/cp.err)"
  } >> "$LOG" 2>&1 || true
fi

python3 /app/app.py