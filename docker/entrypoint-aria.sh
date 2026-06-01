#!/usr/bin/env bash
# ARIA entrypoint: generate schema_reference.json from the live DB, publish it to the
# shared volume (so SAGE can read it), then start ARIA.
set -e
cd /app/Agents/IntentClassifier

echo "[aria] Bootstrapping schema_reference.json from DB..."
python bootstrap_schema.py || echo "[aria] bootstrap failed — ARIA will fall back to built-in taxonomy"

# Publish to the shared volume that SAGE reads (SCHEMA_FILE_PATH=/shared/schema_reference.json)
if [ -f schema_reference.json ]; then
  mkdir -p /shared
  cp schema_reference.json /shared/schema_reference.json
  echo "[aria] Published schema_reference.json -> /shared"
fi

echo "[aria] Starting ARIA on 0.0.0.0:8002"
exec python aria.py
