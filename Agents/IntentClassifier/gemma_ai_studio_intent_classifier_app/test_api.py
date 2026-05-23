"""Quick API smoke test — run once to verify GEMMA 4 connectivity."""
import json
from core.intent_processor import IntentProcessor

proc = IntentProcessor()
result = proc.process(
    "Customer says the invoice amount for order ORD-4589 is incorrect; "
    "check the invoice and payment records, compare them with the contract terms, "
    "and create a correction request if the contract supports the discount."
)

print(f"Total intents: {result['total_intents']}")
print()
for i in result["intents"]:
    print(f"  [{i['intent_id']}] {i['domain']}/{i['sub_domain']} | {i['data_source']} | {i['intent_types']}")
    print(f"       {i['description']}")
    print()

print("--- Raw JSON ---")
print(json.dumps(result, indent=2))
