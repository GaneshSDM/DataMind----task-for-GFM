"""Meltano wrapper for DataMind DataFlow.

This module is intentionally isolated from app.py so Meltano is purely
optional.  If Meltano is not installed, calls to run_meltano() return a
helpful message and the app can fall back to the built-in CSV loader.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
MELTANO_DIR = BASE / "meltano"
SAMPLE_DIR = BASE / "sample_data"
UPLOAD_DIR = BASE / "uploads"

# Columns used as primary keys for each sample table.
_KEYS: dict[str, list[str]] = {
    "categories": ["category_id"],
    "customers": ["customer_id"],
    "products": ["product_id"],
    "transactions": ["txn_id"],
}


def _parse_url(url: str) -> dict[str, Any]:
    """Parse a PostgreSQL DATABASE_URL into components for Meltano target-postgres."""
    pattern = re.compile(
        r"^postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:/]+)(?::(?P<port>\d+))?/(?P<database>.+)$"
    )
    m = pattern.match(url)
    if not m:
        raise ValueError("DATABASE_URL is not in the expected postgresql://user:pass@host:port/db format")
    return {
        "user": m.group("user"),
        "password": m.group("password"),
        "host": m.group("host"),
        "port": int(m.group("port") or 5432),
        "database": m.group("database"),
    }


def _build_tap_csv_config(source: str, table_filter: list[str] | None = None) -> dict[str, Any]:
    """Build a tap-csv file list pointing at source CSVs."""
    files: list[dict[str, Any]] = []

    if source == "sample_data" or source == "all":
        for csv_file in sorted(SAMPLE_DIR.glob("*.csv")):
            if table_filter and csv_file.stem not in table_filter:
                continue
            files.append(
                {
                    "entity": csv_file.stem,
                    "path": str(csv_file.resolve()),
                    "keys": _KEYS.get(csv_file.stem, []),
                }
            )

    if source == "uploads" or source == "all_uploads" or source == "all":
        for csv_file in sorted(UPLOAD_DIR.glob("*.csv")):
            if table_filter and csv_file.stem not in table_filter:
                continue
            files.append(
                {
                    "entity": csv_file.stem,
                    "path": str(csv_file.resolve()),
                    "keys": _KEYS.get(csv_file.stem, []),
                }
            )

    if not files:
        raise FileNotFoundError(f"No CSV files found for source '{source}'")

    return {"files": files}


def _has_meltano() -> bool:
    return shutil.which("meltano") is not None


def _run_meltano_command(args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    if not _has_meltano():
        return {
            "ok": False,
            "stdout": "",
            "stderr": "Meltano is not installed or not on PATH. Install it with: pip install meltano",
        }

    cmd = ["meltano", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(MELTANO_DIR),
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Meltano command timed out (>5 min)."}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "stdout": "", "stderr": str(exc)}


def install_plugins() -> dict[str, Any]:
    """Install Meltano plugins declared in meltano.yml."""
    return _run_meltano_command(["install"])


def run_meltano(
    source: str = "sample_data",
    table_filter: list[str] | None = None,
    loader: str = "target-postgres",
) -> dict[str, Any]:
    """Run the Meltano tap-csv -> target-* pipeline.

    Args:
        source: one of 'sample_data', 'uploads', 'all'.
        table_filter: optional list of table names to include.
        loader: Meltano loader plugin name, e.g. 'target-postgres' or 'target-jsonl'.
    """
    load_dotenv(BASE / ".env")
    schema = os.getenv("TARGET_SCHEMA", "dataflow_demo")

    # Ensure plugins are installed; best-effort, ignore failure.
    _run_meltano_command(["install"])

    # Build dynamic tap-csv config.
    tap_config = _build_tap_csv_config(source, table_filter)
    _write_tap_csv_config(tap_config)

    env: dict[str, str] = {}
    if loader == "target-postgres":
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return {"ok": False, "stdout": "", "stderr": "DATABASE_URL is not set"}
        creds = _parse_url(db_url)
        env.update(
            {
                "MELTANO_TARGET_POSTGRES_HOST": creds["host"],
                "MELTANO_TARGET_POSTGRES_PORT": str(creds["port"]),
                "MELTANO_TARGET_POSTGRES_USER": creds["user"],
                "MELTANO_TARGET_POSTGRES_PASSWORD": creds["password"],
                "MELTANO_TARGET_POSTGRES_DB": creds["database"],
                "MELTANO_TARGET_POSTGRES_SCHEMA": schema,
            }
        )

    return _run_meltano_command(
        [
            "run",
            "--no-partial-parse",
            f"tap-csv-{loader.replace('target-', '')}",
        ],
        env=env,
    )


def _write_tap_csv_config(config: dict[str, Any]) -> None:
    import json

    config_path = MELTANO_DIR / "tap-csv-config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
