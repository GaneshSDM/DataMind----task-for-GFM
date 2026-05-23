import ast
from pathlib import Path

files = [
    "app.py",
    "config/settings.py",
    "core/gemma_client.py",
    "core/intent_processor.py",
    "core/report_generator.py",
    "data/test_scenarios.py",
]

all_ok = True
print("--- Syntax Check ---")
for f in files:
    try:
        ast.parse(open(f).read())
        print(f"  [OK]  {f}")
    except SyntaxError as e:
        print(f"  [ERR] {f} -> {e}")
        all_ok = False

print()
print("--- Import Check ---")
from config.settings import STRUCTURED_VIEWS, DOMAIN_TAXONOMY, GEMINI_MODEL, GEMINI_API_KEY
from core.gemma_client import GemmaClient
from core.intent_processor import IntentProcessor
from core.report_generator import ReportGenerator
from data.test_scenarios import TEST_SCENARIOS

print(f"  Model           : {GEMINI_MODEL}")
print(f"  API key set     : {bool(GEMINI_API_KEY)}")
print(f"  Structured views: {len(STRUCTURED_VIEWS)}")
print(f"  Domains         : {list(DOMAIN_TAXONOMY.keys())}")
print(f"  Sub-domains     : {sum(len(v) for v in DOMAIN_TAXONOMY.values())}")
print(f"  Test scenarios  : {len(TEST_SCENARIOS)}")
print(f"  Persona file    : {Path('agent_persona/enterprise_analyst.md').exists()}")

print()
print("--- File Presence ---")
required = [
    "app.py", ".env", "requirements.txt",
    "agent_persona/enterprise_analyst.md",
    "config/settings.py", "config/__init__.py",
    "core/gemma_client.py", "core/intent_processor.py",
    "core/report_generator.py", "core/__init__.py",
    "data/test_scenarios.py", "data/__init__.py",
]
for f in required:
    exists = Path(f).exists()
    print(f"  {'[OK]' if exists else '[MISSING]'}  {f}")
    if not exists:
        all_ok = False

print()
print("ALL SYSTEMS READY" if all_ok else "ISSUES FOUND — review above before running.")
