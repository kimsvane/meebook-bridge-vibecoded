#!/usr/bin/env bash
set -e

# Installér custom integration i HA's config-mappe, hvis tilgængelig.
if [ -d "/app/custom_components" ] && [ -d "/config" ]; then
  mkdir -p /config/custom_components/meebook_bridge
  cp -r /app/custom_components/meebook_bridge/. /config/custom_components/meebook_bridge/
fi

python3 /app/app.py