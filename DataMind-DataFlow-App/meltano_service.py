'''Meltano wrapper for DataMind DataFlow.

This module is intentionally isolated from app.py so Meltano is purely
optional.  If Meltano is not installed, calls to run_meltano() return a
helpful message and the app can fall back to the built-in CSV loader.
'''

from __future__ import annotations

import os
import re
import shutil
import subprocess
import json
from pathlib import Path
from typing import Any
from datetime import datetime

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
MELTANO_DIR = BASE / "meltano"
SAMPLE_DIR = BASE / "sample_data"
UPLOAD_DIR = BASE / "uploads"
LOG_DIR = BASE / "meltano_logs"

_KEYS: dict[str, list[str]] = {
    "categories": ["category_id"],
    "customers": ["customer_id"],
    "products": ["product_id"],
    "transactions": ["txn_id"],
}

def _parse_url(url: str) -> dict[str, Any]:
    try:
        if "@" not in url:
            raise ValueError("No '@' found in DATABASE_URL")
        creds_part, host_part = url.split("@", 1)
        creds_part = creds_part.replace("postgresql://", "")
        if ":" in creds_part:
            user, password = creds_part.split(":", 1)
        else:
            user, password = creds_part, ""
        if "/" in host_part:
            host_port, database = host_part.split("/", 1)
        else:
            host_port, database = host_part, "postgres"
        if ":" in host_port:
            host, port = host_port.split(":", 1)
        else:
            host, port = host_port, "5432"
        return {
            "user": user,
            "password": password,
            "host": host,
            "port": int(port),
            "database": database,
        }
    except Exception as e:
        raise ValueError(f"DATABASE_URL parsing failed: {str(e)}")

def _build_tap_csv_config(source: str, table_filter: list[str] | None = None) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    if source == "sample_data" or source == "all":
        for csv_file in sorted(SAMPLE_DIR.glob("*.csv")):
            if table_filter and csv_file.stem not in table_filter:
                continue
            files.append({"entity": csv_file.stem, "path": csv_file.resolve().as_posix(), "keys": _KEYS.get(csv_file.stem, [])})
    if source == "uploads" or source == "all_uploads" or source == "all":
        for csv_file in sorted(UPLOAD_DIR.glob("*.csv")):
            if table_filter and csv_file.stem not in table_filter:
                continue
            files.append({"entity": csv_file.stem, "path": csv_file.resolve().as_posix(), "keys": _KEYS.get(csv_file.stem, [])})
    if not files:
        raise FileNotFoundError(f"No CSV files found for source '{source}'")
    return files

def _has_meltano() -> bool:
    standard = shutil.which("meltano")
    if standard:
        return True
    venv_path = BASE / ".venv" / "Scripts" / "meltano.exe"
    return venv_path.exists()

def _run_meltano_command(args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    if not _has_meltano():
        return {"ok": False, "stdout": "", "stderr": "Meltano is not installed or not on PATH. Install it with: pip install meltano"}

    meltano_bin = str(BASE / ".venv" / "Scripts" / "meltano.exe")

    cmd = [meltano_bin, *args]

    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"meltano_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    try:
        # Run in the meltano directory so it finds meltano.yml
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(MELTANO_DIR),
            env={**os.environ, **(env or {})},
            check=False
        )

        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Stdout:\n{result.stdout}\n")
            f.write(f"Stderr:\n{result.stderr}\n")

        return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr, "log_file": str(log_file)}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}

def run_meltano(source: str, table_filter: list[str] | None = None, loader: str = "target-postgres") -> dict[str, Any]:
    """
    Orchestrates a Meltano run: extract from CSV -> load to Postgres.
    """
    try:
        # 1. Build CSV config
        csv_config = _build_tap_csv_config(source, table_filter)

        # 3. Prepare database configuration for loader
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            return {"ok": False, "stderr": "DATABASE_URL not set in environment"}

        # Convert postgresql:// to postgresql+psycopg2:// for SQLAlchemy
        sqlalchemy_url = db_url.replace("postgresql://", "postgresql+psycopg2://")

        # Explicitly set loader config to ensure it's picked up
        _run_meltano_command(["config", "set", loader, "sqlalchemy_url", sqlalchemy_url])

        # 4. Configure tap-csv files via meltano config set
        # Env var overrides (MELTANO_TAP_CSV_FILES) often fail for complex types like lists of objects.
        config_json = json.dumps(csv_config)
        _run_meltano_command(["config", "set", "tap-csv", "files", config_json])

        try:
            # 5. Run the pipeline
            result = _run_meltano_command(["run", "tap-csv", loader])
        finally:
            # 6. Reset config to avoid leaving specific files/credentials in the project config
            _run_meltano_command(["config", "set", "tap-csv", "files", "[]"])
            _run_meltano_command(["config", "set", loader, "sqlalchemy_url", ""])

        if not result["ok"]:
            return {"ok": False, "stderr": f"DEBUG_PONYTAIL: {result['stderr']}"}

        return {"ok": True, "message": "Meltano run completed successfully", "log_file": result.get("log_file")}

    except Exception as e:
        return {"ok": False, "stderr": str(e)}
