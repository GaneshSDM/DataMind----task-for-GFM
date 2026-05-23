#!/usr/bin/env python3
"""
SQL Validator Agent — Ganesh
================================

Main entry point. Orchestrates:
- Loading persona and role boundaries
- Schema + RLS/CLS config
- Synthetic data generation
- SQL validation with structured reporting

Usage:
    # Validate a SQL query
    python agent.py validate --sql "SELECT * FROM sales_deals" --user alice --role sales_rep

    # Generate synthetic data
    python agent.py generate --domain sales --subdomain deals --rows 50

    # Generate all synthetic data CSVs
    python agent.py generate-all --rows 30

    # Batch validate from a file
    python agent.py batch --input queries.txt --output results.jsonl

    # Show persona
    python agent.py persona
"""

import argparse
import json
import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger("sql-validator")

from dotenv import load_dotenv

load_dotenv()

from sql_validator import SQLValidator, SchemaStore
from synthetic_data import (
    generate,
    generate_all,
    save_all_to_csvs,
    generate_with_groq,
)
from groq_client import GroqClient


def load_persona() -> str:
    """Load the agent persona document."""
    persona_path = os.path.join(os.path.dirname(__file__), "persona.md")
    if os.path.exists(persona_path):
        with open(persona_path) as f:
            return f.read()
    return "Persona not found."


def get_schema() -> SchemaStore:
    """Initialize the schema store."""
    base = os.path.dirname(__file__)
    return SchemaStore(
        schema_path=os.path.join(base, "schemas", "domain_schema.json"),
        config_path=os.path.join(base, "config.yaml"),
    )


def get_groq() -> GroqClient:
    import yaml
    base = os.path.dirname(__file__)
    with open(os.path.join(base, "config.yaml")) as f:
        config = yaml.safe_load(f)
    groq_cfg = config.get("groq", {})
    api_key = (
        groq_cfg.get("api_key", "")
        .replace("${GROQ_API_KEY}", "")
        .strip()
    )
    return GroqClient(
        api_key=api_key or os.getenv("GROQ_API_KEY", ""),
        model=groq_cfg.get("model", "deepseek-r1-distill-llama-70b"),
        temperature=groq_cfg.get("temperature", 0.0),
        max_tokens=groq_cfg.get("max_tokens", 4096),
    )


def cmd_persona():
    """Display agent persona and role boundary."""
    print(load_persona())


def cmd_validate(args):
    """Validate a single SQL query."""
    schema = get_schema()
    validator = SQLValidator(schema)

    use_groq = args.groq
    groq = get_groq() if use_groq else None

    sql = args.sql
    if args.file:
        with open(args.file) as f:
            sql = f.read()

    result = validator.validate(
        sql=sql,
        user_id=args.user,
        role=args.role,
        tenant_id=args.tenant or "default",
        domain=args.domain or "",
        subdomain=args.subdomain or "",
        use_groq=use_groq,
        groq_client=groq,
    )

    report = validator.format_report(result)
    print(report)

    if args.json:
        print("\n--- JSON Output ---")
        print(json.dumps(result, indent=2, default=str))

    return 0 if result["status"] == "pass" else 1


def cmd_generate(args):
    """Generate synthetic data for a domain/subdomain."""
    schema = get_schema()

    if args.groq:
        groq = get_groq()
        columns = schema.get_columns_for_domain(args.domain, args.subdomain)
        rows = generate_with_groq(
            groq, args.domain, args.subdomain, columns, args.rows
        )
    else:
        rows = generate(args.domain, args.subdomain, args.rows)

    output = args.output or f"data/{args.domain}_{args.subdomain}.json"
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w") as f:
        json.dump(rows, f, indent=2, default=str)

    print(f"Generated {len(rows)} rows → {output}")

    # Preview first 3 rows
    print("\nPreview (first 3 rows):")
    for i, row in enumerate(rows[:3], 1):
        print(f"  {i}. {json.dumps(row, default=str)}")


def cmd_generate_all(args):
    """Generate synthetic data for all domains and save as CSVs."""
    save_all_to_csvs(output_dir=args.output or "data", n=args.rows)


def cmd_batch(args):
    """Validate multiple queries from a file (one query per line, or JSONL)."""
    schema = get_schema()
    validator = SQLValidator(schema)
    groq = get_groq() if args.groq else None

    with open(args.input) as f:
        raw = f.read()

    # Try JSONL
    queries = []
    if raw.strip().startswith("{"):
        for line in raw.strip().split("\n"):
            queries.append(json.loads(line))
    else:
        # Plain SQL, one per line
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("--"):
                queries.append({"sql": line, "user": args.user, "role": args.role, "tenant": args.tenant})

    results = []
    passes = 0
    for i, q in enumerate(queries):
        result = validator.validate(
            sql=q.get("sql", q.get("query", "")),
            user_id=q.get("user", args.user),
            role=q.get("role", args.role),
            tenant_id=q.get("tenant", args.tenant or "default"),
            domain=q.get("domain", ""),
            subdomain=q.get("subdomain", ""),
            use_groq=args.groq,
            groq_client=groq,
        )
        results.append(result)
        if result["status"] == "pass":
            passes += 1
        print(f"  [{i+1}/{len(queries)}] {result['status'].upper():6s} — {result['fingerprint']}")

    output = args.output or "batch_results.jsonl"
    with open(output, "w") as f:
        for r in results:
            f.write(json.dumps(r, default=str) + "\n")

    print(f"\nBatch complete: {passes}/{len(queries)} passed → {output}")


def main():
    parser = argparse.ArgumentParser(
        description="SQL Validator Agent — Ganesh",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py persona                    # Show agent persona
  python agent.py validate --sql "SELECT * FROM hr_employees WHERE salary > 100000" --user alice --role sales_rep
  python agent.py validate --file query.sql --user bob --role manager --groq
  python agent.py generate --domain sales --subdomain deals --rows 50
  python agent.py generate-all --rows 30
  python agent.py batch --input queries.txt --user charlie --role analyst
""",
    )

    sub = parser.add_subparsers(dest="command")

    # persona
    sub.add_parser("persona", help="Display agent persona and role boundary")

    # validate
    p_val = sub.add_parser("validate", help="Validate a SQL query")
    p_val.add_argument("--sql", help="SQL query to validate")
    p_val.add_argument("--file", help="Read SQL from file")
    p_val.add_argument("--user", required=True, help="User ID executing the query")
    p_val.add_argument("--role", required=True, help="User role (admin, manager, sales_rep, analyst, support_agent, viewer)")
    p_val.add_argument("--tenant", help="Tenant ID")
    p_val.add_argument("--domain", help="Data domain (finance, hr, sales, inventory, support, engineering)")
    p_val.add_argument("--subdomain", help="Data subdomain")
    p_val.add_argument("--groq", action="store_true", help="Use Groq LLM for additional analysis")
    p_val.add_argument("--json", action="store_true", help="Also output raw JSON result")

    # generate
    p_gen = sub.add_parser("generate", help="Generate synthetic data")
    p_gen.add_argument("--domain", required=True, help="Data domain")
    p_gen.add_argument("--subdomain", required=True, help="Data subdomain")
    p_gen.add_argument("--rows", type=int, default=20, help="Number of rows")
    p_gen.add_argument("--output", help="Output file path")
    p_gen.add_argument("--groq", action="store_true", help="Use Groq LLM for generation")

    # generate-all
    p_ga = sub.add_parser("generate-all", help="Generate all synthetic data as CSVs")
    p_ga.add_argument("--rows", type=int, default=20, help="Rows per table")
    p_ga.add_argument("--output", default="data", help="Output directory")

    # batch
    p_batch = sub.add_parser("batch", help="Validate multiple queries from a file")
    p_batch.add_argument("--input", required=True, help="Input file (JSONL or one-query-per-line)")
    p_batch.add_argument("--output", help="Output JSONL file")
    p_batch.add_argument("--user", required=True, help="Default user ID")
    p_batch.add_argument("--role", required=True, help="Default user role")
    p_batch.add_argument("--tenant", help="Default tenant ID")
    p_batch.add_argument("--groq", action="store_true", help="Use Groq LLM for analysis")

    args = parser.parse_args()

    if args.command == "persona":
        cmd_persona()
    elif args.command == "validate":
        sys.exit(cmd_validate(args))
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "generate-all":
        cmd_generate_all(args)
    elif args.command == "batch":
        cmd_batch(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
