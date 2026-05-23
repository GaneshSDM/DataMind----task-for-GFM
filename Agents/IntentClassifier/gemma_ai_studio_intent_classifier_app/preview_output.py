"""Runs 4 sample scenarios and prints a formatted preview of the output."""
from core.intent_processor import IntentProcessor
from core.report_generator import ReportGenerator

SAMPLES = [
    {
        "id": "S01", "name": "Invoice Dispute with Contract Verification", "domain": "Finance",
        "query": (
            "Customer says the invoice amount for order ORD-4589 is incorrect; "
            "check the invoice and payment records, compare them with the contract terms, "
            "and create a correction request if the contract supports the discount."
        ),
    },
    {
        "id": "S07", "name": "Cancellation Root Cause with Customer Feedback", "domain": "Sales",
        "query": (
            "List all cancellation requests received in the last 30 days. "
            "Identify the top 3 cancellation reasons from customer feedback documents "
            "and prepare a summary report for the sales director."
        ),
    },
    {
        "id": "S12", "name": "SLA Breach Investigation with Root Cause Escalation", "domain": "Operations",
        "query": (
            "Identify all customer support tickets that breached SLA in the last 7 days. "
            "Retrieve root cause details from incident reports, categorize breach types, "
            "and escalate any team with more than 3 repeat SLA breaches to the Operations VP."
        ),
    },
    {
        "id": "S20", "name": "Cross-Domain Board Executive Summary", "domain": "Multi-Domain",
        "query": (
            "Prepare an executive board summary covering: Q2 2025 sales bookings vs target "
            "with top 3 underperforming regions, the five most overdue receivables and their "
            "aging breakdown, any open regulatory compliance issues from the legal archive, "
            "and the three most critical operational incidents from this quarter with root causes. "
            "Include a recommended action item for each area."
        ),
    },
]

proc = IntentProcessor()
reporter = ReportGenerator()
results = []

COL_W = {
    "Scenario":  30, "Intent #": 8, "Description": 48, "Domain": 12,
    "Sub-Domain": 18, "Data Source": 14, "Business View": 36,
    "Unstructured Source": 32, "Intent Types": 22,
    "Fetch": 7, "Reason": 7, "Action": 7,
}

def sep():
    print("+" + "+".join("-" * (w + 2) for w in COL_W.values()) + "+")

def row(*vals):
    cells = []
    for val, w in zip(vals, COL_W.values()):
        s = str(val)
        cells.append(f" {s[:w]:<{w}} ")
    print("|" + "|".join(cells) + "|")

sep()
row(*COL_W.keys())
sep()

for s in SAMPLES:
    print(f"\n  Processing {s['id']}...", end="", flush=True)
    result = proc.process(s["query"])
    result["scenario_id"] = s["id"]
    result["scenario_name"] = s["name"]
    result["primary_domain"] = s["domain"]
    results.append(result)
    print(f" {result['total_intents']} intents")

    for i in result["intents"]:
        scenario_label = f"[{s['id']}] {s['name']}"
        row(
            scenario_label,
            i["intent_id"],
            i["description"],
            i["domain"],
            i["sub_domain"],
            i["data_source"],
            i.get("structured_view") or "—",
            i.get("unstructured_source") or "—",
            ", ".join(i["intent_types"]),
            "Yes" if i["requires_data_fetch"] else "No",
            "Yes" if i["requires_reasoning"] else "No",
            "Yes" if i["requires_action"] else "No",
        )
    sep()

# Save sample Excel
excel = reporter.generate(results)
out = "sample_output.xlsx"
with open(out, "wb") as f:
    f.write(excel)
print(f"\nSample Excel saved → {out}")
