#!/usr/bin/env bash
set -e

LOG=/dev/stdout
HA_CONFIG=""
# Ny Supervisor mapper HA-configuration til /homeassistant, ældre til /config.
if [ -d "/homeassistant" ] && touch "/homeassistant/.mb_wtest" 2>/dev/null; then
  rm -f "/homeassistant/.mb_wtest"
  HA_CONFIG="/homeassistant"
  LOG="/homeassistant/meebook_bridge_install.log"
elif [ -d "/config" ] && touch "/config/.mb_wtest" 2>/dev/null; then
  rm -f "/config/.mb_wtest"
  HA_CONFIG="/config"
  LOG="/config/meebook_bridge_install.log"
fi

{
  echo "[$(date -Is)] Meebook Bridge starter (v1.0.11)"
  if [ -n "$HA_CONFIG" ]; then
    if [ -d "/app/custom_components" ]; then
      mkdir -p "$HA_CONFIG/custom_components/meebook_bridge"
      if cp -r /app/custom_components/meebook_bridge/. "$HA_CONFIG/custom_components/meebook_bridge/" 2>/tmp/cp.err; then
        echo "Integration installeret i $HA_CONFIG/custom_components/meebook_bridge"
      else
        echo "ADVARSEL: kunne ikke kopiere integration - $(cat /tmp/cp.err)"
      fi
    else
      echo "/app/custom_components mangler"
    fi
  else
    echo "Ingen skrivbar HA-configuration-mappe fundet - integration installeres ikke automatisk"
  fi
} >> "$LOG" 2>&1 || true

python3 /app/app.py