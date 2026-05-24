#!/usr/bin/env python3
"""Web UI for Vector DB Agent — manage vector embeddings in Supabase RAG tables."""

import json
import sys
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from flask import Flask, render_template, request, jsonify
from vector_agent.manager import VectorManager

app = Flask(__name__)

_mgr = None

def _get_mgr():
    global _mgr
    if _mgr is None:
        _mgr = VectorManager()
    return _mgr

# ── Pages ──
@app.route("/")
def index():
    return render_template("index.html")

# ── API: Schema ──
@app.route("/api/schema")
def api_schema():
    try:
        mgr = _get_mgr()
        schema = mgr.discover_schema()
        return jsonify(schema)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ── API: Embedding Status ──
@app.route("/api/status")
def api_status():
    mgr = _get_mgr()
    status = mgr.check_embeddings()
    cat_stats = mgr.check_by_category()
    for row in cat_stats:
        total = row["total"]
        have = row["with_embedding"]
        row["pct"] = round(100 * have / max(total, 1), 1)
    return jsonify({
        "status": status,
        "by_category": cat_stats,
    })

# ── API: Create Embeddings ──
@app.route("/api/create", methods=["POST"])
def api_create():
    mgr = _get_mgr()
    data = request.get_json() or {}
    limit = data.get("limit")
    dry_run = data.get("dry_run", False)
    result = mgr.create_embeddings(limit=limit, dry_run=dry_run)
    return jsonify(result)

# ── API: Validate ──
@app.route("/api/validate", methods=["POST"])
def api_validate():
    mgr = _get_mgr()
    data = request.get_json() or {}
    sample = data.get("sample", 20)
    result = mgr.validate_embeddings(sample_size=sample)
    return jsonify(result)

# ── API: Full Report ──
@app.route("/api/report")
def api_report():
    mgr = _get_mgr()
    report = mgr.full_report()
    return jsonify({"report": report})

if __name__ == "__main__":
    # On WSL, bind to 0.0.0.0 so Windows browser can reach via WSL IP
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5051"))
    app.run(debug=False, host=host, port=port, threaded=True)
