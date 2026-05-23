"""
20 enterprise-level test scenarios covering all domains and data source types.
Each scenario is designed to produce 2–6 decomposed intents.
"""

TEST_SCENARIOS: list[dict] = [
    # ── Finance ────────────────────────────────────────────────────────────────
    {
        "id": "S01",
        "name": "Invoice Dispute with Contract Verification",
        "domain": "Finance",
        "complexity": "High",
        "query": (
            "Customer says the invoice amount for order ORD-4589 is incorrect; "
            "check the invoice and payment records, compare them with the contract terms, "
            "and create a correction request if the contract supports the discount."
        ),
    },
    {
        "id": "S02",
        "name": "Overdue Payment Reconciliation with Credit Terms Check",
        "domain": "Finance",
        "complexity": "High",
        "query": (
            "Reconcile all outstanding payments for Q2 2025. "
            "Identify accounts overdue by more than 60 days, review the credit terms "
            "in each customer contract, and send dunning letters to qualifying accounts."
        ),
    },
    {
        "id": "S03",
        "name": "Budget vs Actuals Variance with Justification Notes",
        "domain": "Finance",
        "complexity": "Medium",
        "query": (
            "Compare Q2 2025 budgeted vs actual expenses for each department. "
            "Highlight departments that exceeded their budget by more than 15% and "
            "retrieve the variance justification notes from the finance review documents."
        ),
    },
    {
        "id": "S04",
        "name": "Asset Maintenance Scheduling with Policy Check",
        "domain": "Finance",
        "complexity": "Medium",
        "query": (
            "List all assets due for maintenance in Q3 2025, verify their maintenance "
            "budget allocation in the Finance system, and check if the equipment manuals "
            "require a certified third-party vendor for the procedures."
        ),
    },
    {
        "id": "S05",
        "name": "Tax Compliance Audit for High-Value Transactions",
        "domain": "Finance",
        "complexity": "Medium",
        "query": (
            "Extract all transactions above $10,000 from Q3 2025. "
            "Cross-check each transaction against the tax compliance archive to confirm "
            "proper tax certificates were filed, and flag any non-compliant transactions."
        ),
    },
    # ── Sales ──────────────────────────────────────────────────────────────────
    {
        "id": "S06",
        "name": "Q1 Booking Performance with Delivery Delay Flag",
        "domain": "Sales",
        "complexity": "Medium",
        "query": (
            "Show all bookings from Q1 2025 in the North America region above $500K "
            "and flag those where delivery was delayed by more than 7 days."
        ),
    },
    {
        "id": "S07",
        "name": "Cancellation Root Cause with Customer Feedback",
        "domain": "Sales",
        "complexity": "Medium",
        "query": (
            "List all cancellation requests received in the last 30 days. "
            "Identify the top 3 cancellation reasons from customer feedback documents "
            "and prepare a summary report for the sales director."
        ),
    },
    {
        "id": "S08",
        "name": "Contract Renewal Automation with Pricing Clause Review",
        "domain": "Sales",
        "complexity": "High",
        "query": (
            "Find all customer contracts expiring within 60 days. "
            "Review the renewal terms and pricing clauses from each contract document, "
            "and create renewal tasks assigned to the respective account managers."
        ),
    },
    {
        "id": "S09",
        "name": "Q4 Sales Forecast with At-Risk Deal Analysis",
        "domain": "Sales",
        "complexity": "High",
        "query": (
            "Generate a Q4 2025 sales forecast based on current pipeline bookings and "
            "historical win rates. Identify the top 10 at-risk deals by value, extract "
            "the risk factors from CRM notes, and suggest next-best-actions for each deal."
        ),
    },
    {
        "id": "S10",
        "name": "Multi-Order Shipment Tracking with Escalation",
        "domain": "Sales",
        "complexity": "Medium",
        "query": (
            "Track shipment status for orders ORD-1234, ORD-1235, and ORD-1236. "
            "For any shipment delayed by more than 3 days, send a notification to the "
            "logistics manager and create an escalation ticket with the carrier."
        ),
    },
    # ── Operations ────────────────────────────────────────────────────────────
    {
        "id": "S11",
        "name": "Order Modification with Stock Verification",
        "domain": "Operations",
        "complexity": "Medium",
        "query": (
            "Customer for order ORD-7823 wants to change the delivery address to Chicago "
            "and add 5 more units to their order. Check if the order is still in editable "
            "status, verify stock availability, update the order, and confirm the revised "
            "delivery date to the customer."
        ),
    },
    {
        "id": "S12",
        "name": "SLA Breach Investigation with Root Cause Escalation",
        "domain": "Operations",
        "complexity": "High",
        "query": (
            "Identify all customer support tickets that breached SLA in the last 7 days. "
            "Retrieve root cause details from incident reports, categorize breach types, "
            "and escalate any team with more than 3 repeat SLA breaches to the Operations VP."
        ),
    },
    {
        "id": "S13",
        "name": "Product Returns Defect Pattern with Supplier Flag",
        "domain": "Operations",
        "complexity": "High",
        "query": (
            "Analyze all Electronics category product returns in Q2 2025. "
            "Identify recurring defect patterns from customer return notes and quality "
            "inspection reports. If a specific supplier is responsible for more than 30% "
            "of defects, raise a formal quality issue and notify the procurement team."
        ),
    },
    # ── Logistics ─────────────────────────────────────────────────────────────
    {
        "id": "S14",
        "name": "Inventory Reorder with Procurement Trigger",
        "domain": "Logistics",
        "complexity": "Medium",
        "query": (
            "Check current inventory levels for all SKUs in the Electronics category "
            "across all warehouses. For any SKU below the minimum reorder threshold, "
            "automatically create a purchase requisition and notify the procurement team."
        ),
    },
    {
        "id": "S15",
        "name": "Regulatory Compliance Audit for International Shipments",
        "domain": "Logistics",
        "complexity": "Medium",
        "query": (
            "Verify that all international shipments in the last quarter comply with "
            "export control regulations. Cross-reference shipment records with the "
            "regulatory compliance documents and generate a compliance audit report for "
            "the legal team."
        ),
    },
    # ── Procurement ───────────────────────────────────────────────────────────
    {
        "id": "S16",
        "name": "Stalled PO Approval with Policy Escalation",
        "domain": "Procurement",
        "complexity": "Medium",
        "query": (
            "Find all purchase orders pending approval for more than 5 business days. "
            "Check the procurement policy document for escalation rules and automatically "
            "escalate qualifying POs to the department head."
        ),
    },
    {
        "id": "S17",
        "name": "Vendor Payment Validation with Discrepancy Hold",
        "domain": "Procurement",
        "complexity": "High",
        "query": (
            "Process all vendor payments due this week. Validate each payment against "
            "the approved purchase order and invoice records in the Finance system. "
            "For any discrepancy above 5%, hold the payment and notify the vendor for "
            "clarification before proceeding."
        ),
    },
    # ── Marketing ─────────────────────────────────────────────────────────────
    {
        "id": "S18",
        "name": "Campaign-to-Booking Revenue Attribution",
        "domain": "Marketing",
        "complexity": "Medium",
        "query": (
            "Identify which marketing campaigns in H1 2025 generated the highest booking "
            "revenue. Cross-reference campaign performance data with sales booking records "
            "and rank the top 5 campaigns by conversion value and ROI."
        ),
    },
    # ── Multi-Domain / Complex ────────────────────────────────────────────────
    {
        "id": "S19",
        "name": "At-Risk Customer Retention Plan",
        "domain": "Sales",
        "complexity": "Very High",
        "query": (
            "Account ACCT-2891 has shown churn risk signals. Pull their complete order "
            "history, payment behavior, open disputes, and all CRM interaction notes. "
            "Assess the churn risk level, identify the primary drivers from the data, "
            "and create a personalized retention action plan with offers based on "
            "their contract tier and purchase history."
        ),
    },
    {
        "id": "S20",
        "name": "Cross-Domain Board Executive Summary",
        "domain": "Multi-Domain",
        "complexity": "Very High",
        "query": (
            "Prepare an executive board summary covering: Q2 2025 sales bookings vs "
            "target with top 3 underperforming regions, the five most overdue receivables "
            "and their aging breakdown, any open regulatory compliance issues from the "
            "legal archive, and the three most critical operational incidents from this "
            "quarter with root causes. Include a recommended action item for each area."
        ),
    },
]
