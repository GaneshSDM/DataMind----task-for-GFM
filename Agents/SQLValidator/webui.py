#!/usr/bin/env python3
"""Web UI server for SQL Validator Agent (Ganesh)."""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify

# Ensure project root is on path
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from sql_validator import SQLValidator, SchemaStore
from synthetic_data import generate as gen_synth
from groq_client import GroqClient, get_query_fingerprint

app = Flask(__name__)

# ── Init ──
schema = SchemaStore(
    schema_path=str(PROJECT_DIR / "schemas" / "domain_schema.json"),
    config_path=str(PROJECT_DIR / "config.yaml"),
)
validator = SQLValidator(schema)

ROLES = ["admin", "manager", "sales_rep", "analyst", "support_agent", "viewer"]
DOMAINS = ["sales", "hr", "finance", "inventory", "support", "engineering"]
SUBDOMAINS = {
    "sales": ["leads", "deals", "accounts"],
    "hr": ["employees", "performance", "benefits"],
    "finance": ["budget", "payroll", "transactions"],
    "inventory": ["products", "warehouse"],
    "support": ["tickets"],
    "engineering": ["projects", "bugs"],
}


def _get_groq():
    try:
        import yaml, os
        with open(PROJECT_DIR / "config.yaml") as f:
            cfg = yaml.safe_load(f)
        gc = cfg.get("groq", {})
        key = gc.get("api_key", "").replace("${GROQ_API_KEY}", "").strip() or os.getenv("GROQ_API_KEY", "")
        return GroqClient(
            api_key=key,
            model=gc.get("model", "deepseek-r1-distill-llama-70b"),
            temperature=gc.get("temperature", 0.0),
            max_tokens=gc.get("max_tokens", 4096),
        ) if key else None
    except Exception:
        return None


def _get_persona():
    path = PROJECT_DIR / "persona.md"
    return path.read_text() if path.exists() else "Persona not found."


# ── Routes ──

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/persona")
def api_persona():
    return jsonify({"persona": _get_persona()})


@app.route("/api/roles")
def api_roles():
    return jsonify({"roles": ROLES, "domains": DOMAINS, "subdomains": SUBDOMAINS})


@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json()
    sql = data.get("sql", "").strip()
    role = data.get("role", "viewer")
    user_id = data.get("user_id", "web_user")
    tenant = data.get("tenant", "default")
    domain = data.get("domain", "")
    subdomain = data.get("subdomain", "")
    use_groq = data.get("groq", False)

    if not sql:
        return jsonify({"error": "No SQL provided"}), 400

    groq = _get_groq() if use_groq else None

    result = validator.validate(
        sql=sql, user_id=user_id, role=role, tenant_id=tenant,
        domain=domain, subdomain=subdomain,
        use_groq=use_groq, groq_client=groq,
    )

    result["sql"] = sql
    report = validator.format_report(result)
    return jsonify({**result, "report": report})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    domain = data.get("domain", "")
    subdomain = data.get("subdomain", "")
    rows = int(data.get("rows", 20))
    use_groq = data.get("groq", False)

    if not domain or not subdomain:
        return jsonify({"error": "Domain and subdomain required"}), 400

    try:
        if use_groq:
            groq = _get_groq()
            if not groq:
                return jsonify({"error": "Groq API key not configured"}), 400
            columns = schema.get_columns_for_domain(domain, subdomain)
            rows_data = gen_synth(domain, subdomain, rows)  # fall back to rule-based
        else:
            rows_data = gen_synth(domain, subdomain, rows)

        return jsonify({
            "domain": domain,
            "subdomain": subdomain,
            "row_count": len(rows_data),
            "columns": list(rows_data[0].keys()) if rows_data else [],
            "rows": rows_data,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/columns", methods=["POST"])
def api_columns():
    data = request.get_json()
    domain = data.get("domain", "")
    subdomain = data.get("subdomain", "")
    role = data.get("role", "admin")

    cols = schema.get_columns_for_domain(domain, subdomain) or []
    allowed = schema.get_allowed_columns(role, domain, subdomain) or []
    sensitive = schema.get_sensitive_columns(domain, subdomain) or []

    return jsonify({
        "all_columns": cols,
        "allowed_columns": sorted(set(allowed)) if isinstance(allowed, list) else cols,
        "sensitive_columns": sensitive,
    })


@app.route("/api/batch", methods=["POST"])
def api_batch():
    """Validate multiple SQL queries from an uploaded JSON file."""
    role = request.form.get("role", "viewer")
    user_id = request.form.get("user_id", "web_user")
    tenant = request.form.get("tenant", "default")
    use_groq = request.form.get("groq", "false") == "true"

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    try:
        raw = file.read().decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"error": "File must be UTF-8 text"}), 400

    queries = []
    if raw.strip().startswith("{"):
        # JSONL — one JSON object per line
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                queries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    elif raw.strip().startswith("["):
        # JSON array
        arr = json.loads(raw)
        if isinstance(arr, list):
            queries = arr
        else:
            return jsonify({"error": "JSON root must be an array"}), 400
    else:
        # Plain SQL, one per line
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("--"):
                queries.append({"sql": line})

    if not queries:
        return jsonify({"error": "No queries found in file"}), 400

    groq = _get_groq() if use_groq else None

    results = []
    passes = 0
    for q in queries:
        if isinstance(q, str):
            q = {"sql": q}
        sql = q.get("sql", q.get("query", ""))
        if not sql:
            continue

        result = validator.validate(
            sql=sql,
            user_id=q.get("user", q.get("user_id", user_id)),
            role=q.get("role", role),
            tenant_id=q.get("tenant", tenant),
            domain=q.get("domain", ""),
            subdomain=q.get("subdomain", ""),
            use_groq=use_groq,
            groq_client=groq,
        )
        result["sql"] = sql
        result["report"] = validator.format_report(result)
        results.append(result)
        if result["status"] == "pass":
            passes += 1

    # Build a clean exportable JSON summary
    export = {
        "summary": {"total": len(results), "passed": passes, "failed": len(results) - passes},
        "validated_by": {"role": role, "user_id": user_id, "tenant": tenant},
        "queries": [],
    }
    for r in results:
        entry = {
            "query": r["sql"],
            "user": r["user"],
            "domain": r.get("domain", "auto"),
            "subdomain": r.get("subdomain", "auto"),
            "status": r["status"],
            "verdict_reason": r.get("verdict_reason", ""),
            "violations": r.get("violations", []),
            "fingerprint": r.get("fingerprint", ""),
        }
        export["queries"].append(entry)

    return jsonify({
        "total": len(results),
        "passed": passes,
        "failed": len(results) - passes,
        "results": results,
        "export": export,
    })


if __name__ == "__main__":
    print("\n  Ganesh SQL Validator — Web UI")
    print("  http://127.0.0.1:5000\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
