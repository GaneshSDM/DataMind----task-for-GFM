#!/usr/bin/env bash
# SAGE entrypoint: wait for ARIA to publish the shared schema file, then start SAGE.
# SCHEMA_FILE_PATH=/shared/schema_reference.json is set in docker-compose.yml.
set -e
cd /app/Agents/SQLGenerator

SCHEMA="${SCHEMA_FILE_PATH:-/shared/schema_reference.json}"
echo "[sage] Waiting for shared schema at $SCHEMA ..."
for i in $(seq 1 60); do
  [ -f "$SCHEMA" ] && { echo "[sage] Schema found."; break; }
  sleep 2
done
[ -f "$SCHEMA" ] || echo "[sage] WARNING: schema not found after wait — SAGE may fail to resolve tables"

echo "[sage] Starting SAGE on 0.0.0.0:8003"
exec python sage.py
