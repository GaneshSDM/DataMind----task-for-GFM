from pathlib import Path
import json

f = Path("batch_checkpoint.json")
if f.exists():
    data = json.loads(f.read_text())
    results = data.get("results", [])
    print(f"Checkpoint found: {len(results)} scenarios, saved at {data.get('saved_at')}")
    for r in results:
        print(f"  {r['scenario_id']} | {r['scenario_name']} | {r.get('total_intents')} intents")
else:
    print("No checkpoint found")
