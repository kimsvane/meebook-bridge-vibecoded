#!/usr/bin/env bash
set -e

LOG=/config/meebook_bridge_install.log
{
  echo "[$(date -Is)] Meebook Bridge starter (v1.0.10)"
  if [ -d "/app/custom_components" ] && [ -d "/config" ]; then
    mkdir -p /config/custom_components/meebook_bridge
    if cp -r /app/custom_components/meebook_bridge/. /config/custom_components/meebook_bridge/ 2>/tmp/cp.err; then
      echo "[$(date -Is)] Integration installeret i /config/custom_components/meebook_bridge"
    else
      echo "[$(date -Is)] ADVARSEL: kunne ikke kopiere integration - $(cat /tmp/cp.err)"
    fi
  else
    echo "[$(date -Is)] Skriver ikke integration: /app/custom_components eller /config mangler"
  fi
} >> "$LOG" 2>&1

python3 /app/app.py