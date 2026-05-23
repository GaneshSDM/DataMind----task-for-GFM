"""
Synthetic data generator for SQL Validator Agent.
Generates realistic data across domains (finance, hr, sales, inventory, support, engineering).

Two modes:
1. Rule-based: fast, deterministic, no API calls
2. Groq-assisted: uses LLM for more realistic data generation
"""

import csv
import json
import os
import random
import string
from datetime import date, datetime, timedelta
from typing import Optional

random.seed(42)


def _name() -> str:
    first = random.choice([
        "James", "Maria", "Wei", "Aisha", "Carlos", "Priya", "Olga",
        "Yuki", "Fatima", "David", "Emma", "Ravi", "Sofia", "Hiroshi",
        "Kwame", "Linh", "Ahmed", "Elena", "Raj", "Maya",
    ])
    last = random.choice([
        "Smith", "Garcia", "Chen", "Patel", "Kim", "Johnson", "Williams",
        "Brown", "Jones", "Miller", "Davis", "Rodriguez", "Martinez",
        "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Lee", "Harris",
    ])
    return f"{first} {last}"


def _email(name: str) -> str:
    return name.lower().replace(" ", ".") + "@" + random.choice([
        "company.com", "corp.io", "enterprise.net", "firm.co",
    ])


def _phone() -> str:
    return f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"


def _date_between(start: str, end: str) -> str:
    """Return ISO date string between start and end."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    delta = (e - s).days
    return (s + timedelta(days=random.randint(0, max(1, delta)))).isoformat()


def _ssn() -> str:
    return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"


def _bank_account() -> str:
    return f"{random.randint(100000000,999999999)}"


def _money(low: int, high: int) -> float:
    return round(random.uniform(low, high), 2)


def generate_finance_budgets(n: int = 20) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        allocated = _money(50000, 5000000)
        spent = round(random.uniform(allocated * 0.3, allocated * 1.2), 2)
        rows.append({
            "id": i,
            "department_id": random.randint(1, 15),
            "budget_allocated": allocated,
            "budget_spent": spent,
            "fiscal_year": random.randint(2020, 2026),
            "approved_by": random.randint(100, 999),
            "created_at": _date_between("2020-01-01", "2025-12-31"),
            "updated_at": _date_between("2020-01-01", "2026-05-01"),
        })
    return rows


def generate_finance_payroll(n: int = 20) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        period_start = _date_between("2025-01-01", "2026-03-01")
        period_end_dt = date.fromisoformat(period_start) + timedelta(days=14)
        rows.append({
            "id": i,
            "employee_id": random.randint(1, 100),
            "salary": _money(40000, 250000),
            "bonus": _money(0, 50000),
            "bank_account": _bank_account(),
            "ssn": _ssn(),
            "pay_period_start": period_start,
            "pay_period_end": period_end_dt.isoformat(),
            "created_at": _date_between("2025-01-01", "2026-05-01"),
        })
    return rows


def generate_finance_transactions(n: int = 20) -> list[dict]:
    rows = []
    types = ["invoice", "payment", "refund", "transfer", "adjustment"]
    for i in range(1, n + 1):
        rows.append({
            "id": i,
            "transaction_type": random.choice(types),
            "amount": _money(100, 1000000),
            "currency": random.choice(["USD", "EUR", "GBP", "JPY"]),
            "department_id": random.randint(1, 15),
            "vendor_id": random.randint(1, 50),
            "description": f"Transaction {i} - {random.choice(['Q1', 'Q2', 'Q3', 'Q4'])}",
            "transaction_date": _date_between("2023-01-01", "2026-05-01"),
            "created_at": _date_between("2023-01-01", "2026-05-01"),
        })
    return rows


def generate_hr_employees(n: int = 20) -> list[dict]:
    rows = []
    titles = [
        "Software Engineer", "Product Manager", "Data Analyst",
        "Engineering Manager", "Sales Representative", "HR Coordinator",
        "Finance Analyst", "Support Specialist", "Marketing Manager",
        "DevOps Engineer",
    ]
    for i in range(1, n + 1):
        nm = _name()
        hire_d = _date_between("2015-01-01", "2025-12-31")
        term_d = None
        if random.random() < 0.15:  # 15% have termination dates
            term_d = _date_between(hire_d, "2026-05-01")
        rows.append({
            "id": i,
            "employee_name": nm,
            "email": _email(nm),
            "phone": _phone(),
            "title": random.choice(titles),
            "department_id": random.randint(1, 15),
            "manager_id": random.randint(1, 20),
            "hire_date": hire_d,
            "termination_date": term_d,
            "salary": _money(50000, 300000),
            "ssn": _ssn(),
            "birth_date": _date_between("1960-01-01", "2000-12-31"),
            "created_at": _date_between("2015-01-01", "2026-05-01"),
            "updated_at": _date_between("2015-01-01", "2026-05-01"),
        })
    return rows


def generate_hr_performance(n: int = 20) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "id": i,
            "employee_id": random.randint(1, 100),
            "review_period": random.choice(["2024-H1", "2024-H2", "2025-H1"]),
            "performance_rating": random.randint(1, 5),
            "reviewer_id": random.randint(1, 20),
            "goals_achieved": random.randint(0, 10),
            "notes": f"Performance review notes batch {random.randint(1,5)}",
            "created_at": _date_between("2023-01-01", "2026-05-01"),
        })
    return rows


def generate_hr_benefits(n: int = 20) -> list[dict]:
    rows = []
    benefit_types = ["Health", "Dental", "Vision", "Life", "401k", "HSA"]
    levels = ["Individual", "Family", "Individual+1"]
    for i in range(1, n + 1):
        eff_date = _date_between("2024-01-01", "2026-05-01")
        enrolled = _date_between("2023-01-01", eff_date)
        rows.append({
            "id": i,
            "employee_id": random.randint(1, 100),
            "benefit_type": random.choice(benefit_types),
            "coverage_level": random.choice(levels),
            "premium": _money(50, 1200),
            "enrolled_date": enrolled,
            "effective_date": eff_date,
            "created_at": _date_between("2023-01-01", "2026-05-01"),
        })
    return rows


def generate_sales_leads(n: int = 20) -> list[dict]:
    rows = []
    industries = ["Tech", "Finance", "Healthcare", "Retail", "Manufacturing", "Education"]
    sources = ["Webinar", "Referral", "Cold Call", "Conference", "Website", "Partner"]
    statuses = ["New", "Contacted", "Qualified", "Nurturing", "Disqualified"]
    companies = [
        "Acme Corp", "Globex", "Initech", "Umbrella", "Stark Industries",
        "Wayne Enterprises", "Oscorp", "Cyberdyne", "Massive Dynamic", "Soylent Corp",
    ]
    for i in range(1, n + 1):
        rows.append({
            "id": i,
            "lead_name": _name(),
            "company": random.choice(companies),
            "industry": random.choice(industries),
            "source": random.choice(sources),
            "assigned_to": random.randint(1, 30),
            "status": random.choice(statuses),
            "created_at": _date_between("2024-01-01", "2026-05-01"),
            "updated_at": _date_between("2024-01-01", "2026-05-01"),
        })
    return rows


def generate_sales_deals(n: int = 20) -> list[dict]:
    rows = []
    stages = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
    for i in range(1, n + 1):
        close_d = _date_between("2026-01-01", "2026-12-31")
        rows.append({
            "id": i,
            "lead_id": random.randint(1, 50),
            "deal_stage": random.choice(stages),
            "deal_value": _money(10000, 5000000),
            "margin": round(random.uniform(0.10, 0.60), 2),
            "commission_pct": round(random.uniform(0.02, 0.15), 4),
            "competitor_notes": f"Competitor {random.choice(['A','B','C'])} pricing at {_money(8000,4000000)}",
            "assigned_to": random.randint(1, 30),
            "expected_close_date": close_d,
            "created_at": _date_between("2024-01-01", "2026-05-01"),
            "updated_at": _date_between("2024-01-01", "2026-05-01"),
        })
    return rows


def generate_sales_accounts(n: int = 20) -> list[dict]:
    rows = []
    tiers = ["Basic", "Pro", "Enterprise", "Partner"]
    for i in range(1, n + 1):
        start = _date_between("2022-01-01", "2025-12-31")
        end_dt = date.fromisoformat(start) + timedelta(days=random.choice([365, 730, 1095]))
        rows.append({
            "id": i,
            "company_name": random.choice([
                "Acme Corp", "Globex", "Initech", "Umbrella", "Stark Industries",
                "Wayne Enterprises", "Oscorp", "Cyberdyne", "Massive Dynamic",
            ]),
            "account_owner": random.randint(1, 30),
            "annual_revenue": _money(50000, 50000000),
            "contract_start": start,
            "contract_end": end_dt.isoformat(),
            "tier": random.choice(tiers),
            "created_at": _date_between("2022-01-01", "2026-05-01"),
        })
    return rows


def generate_inventory_products(n: int = 20) -> list[dict]:
    rows = []
    categories = ["Electronics", "Furniture", "Office Supplies", "Software", "Hardware"]
    product_names = [
        "Laptop Pro X", "Monitor UltraWide", "Standing Desk", "Ergo Chair",
        "Wireless Mouse", "Mechanical Keyboard", "USB-C Hub", "Webcam HD",
        "Noise Cancelling Headphones", "Tablet S10", "Server Rack 42U",
        "Network Switch 24P", "Cable Management Kit", "Power Strip 12P",
        "External SSD 2TB", "GPU Workstation", "RAM Kit 64GB", "UPS 1500VA",
        "Conference Speaker", "Document Scanner",
    ]
    for i in range(1, n + 1):
        unit_price = _money(10, 5000)
        cost = round(unit_price * random.uniform(0.3, 0.7), 2)
        rows.append({
            "id": i,
            "product_name": product_names[(i - 1) % len(product_names)],
            "sku": f"SKU-{random.randint(10000,99999)}",
            "category": random.choice(categories),
            "unit_price": unit_price,
            "cost_price": cost,
            "stock_level": random.randint(0, 500),
            "supplier_id": random.randint(1, 20),
            "reorder_point": random.randint(10, 100),
            "created_at": _date_between("2023-01-01", "2026-05-01"),
            "updated_at": _date_between("2023-01-01", "2026-05-01"),
        })
    return rows


def generate_inventory_warehouse(n: int = 20) -> list[dict]:
    rows = []
    wh_names = ["East DC", "West DC", "Central Hub", "South Facility", "North Depot"]
    locations = ["New York, NY", "Los Angeles, CA", "Chicago, IL", "Houston, TX", "Seattle, WA"]
    for i in range(1, n + 1):
        rows.append({
            "id": i,
            "warehouse_name": random.choice(wh_names),
            "location": random.choice(locations),
            "capacity": random.randint(10000, 100000),
            "product_id": random.randint(1, 20),
            "quantity": random.randint(0, 1000),
            "last_restock_date": _date_between("2025-01-01", "2026-05-01"),
            "created_at": _date_between("2023-01-01", "2026-05-01"),
        })
    return rows


def generate_support_tickets(n: int = 20) -> list[dict]:
    rows = []
    statuses = ["Open", "In Progress", "Waiting on Customer", "Resolved", "Closed"]
    priorities = ["Low", "Medium", "High", "Critical"]
    subjects = [
        "Login issue", "Billing discrepancy", "Feature request", "Data export failure",
        "API timeout", "Permission denied", "Slow page load", "Email not sending",
        "Report generation error", "Integration broken",
    ]
    for i in range(1, n + 1):
        nm = _name()
        created = _date_between("2025-01-01", "2026-05-01")
        first_resp = _date_between(created, "2026-05-01")
        resolved = None
        if random.random() < 0.6:
            resolved = _date_between(first_resp, "2026-05-21")
        rows.append({
            "id": i,
            "ticket_subject": random.choice(subjects),
            "customer_name": nm,
            "customer_email": _email(nm),
            "customer_phone": _phone(),
            "status": random.choice(statuses),
            "priority": random.choice(priorities),
            "assigned_to": random.randint(1, 30),
            "first_response_at": first_resp,
            "resolved_at": resolved,
            "sla_breach_log": f"Breach on ticket #{i-1}: response time exceeded" if random.random() < 0.2 else "",
            "internal_notes": f"Customer escalated via phone. Escalation contact: {_name()}",
            "created_at": created,
            "updated_at": _date_between(created, "2026-05-21"),
        })
    return rows


def generate_eng_projects(n: int = 20) -> list[dict]:
    rows = []
    statuses = ["Planning", "In Progress", "Review", "Completed", "On Hold"]
    project_names = [
        "Auth Service v2", "Data Pipeline Redesign", "Mobile App Refresh",
        "API Gateway Migration", "Dashboard 2.0", "Search Engine Upgrade",
        "Notification Service", "CI/CD Overhaul", "Payment Integration",
        "User Onboarding Flow", "Infra Monitoring", "Security Audit Tool",
        "Feature Flags System", "Rate Limiter", "Event Bus v2",
        "Config Manager", "Log Aggregation", "Metrics Platform",
        "Compliance Checker", "Release Automation",
    ]
    for i in range(1, n + 1):
        start = _date_between("2024-01-01", "2025-12-31")
        end = _date_between(start, "2026-12-31") if random.random() < 0.6 else None
        rows.append({
            "id": i,
            "project_name": project_names[(i - 1) % len(project_names)],
            "tech_lead_id": random.randint(1, 20),
            "status": random.choice(statuses),
            "start_date": start,
            "end_date": end,
            "created_at": _date_between("2024-01-01", "2026-05-01"),
            "updated_at": _date_between("2024-01-01", "2026-05-01"),
        })
    return rows


def generate_eng_bugs(n: int = 20) -> list[dict]:
    rows = []
    severities = ["Critical", "High", "Medium", "Low", "Cosmetic"]
    statuses = ["Open", "In Progress", "Fixed", "Verified", "Won't Fix", "Duplicate"]
    bug_titles = [
        "Null pointer in auth middleware", "Memory leak on image upload",
        "Race condition in payment flow", "CSS breaks on mobile viewport",
        "API returns 500 on empty payload", "Timeout on large exports",
        "Incorrect date formatting in reports", "Search returns stale results",
        "Notification not firing on status change", "Login redirects to wrong page",
    ]
    for i in range(1, n + 1):
        rows.append({
            "id": i,
            "bug_title": bug_titles[(i - 1) % len(bug_titles)],
            "severity": random.choice(severities),
            "assigned_to": random.randint(1, 20),
            "reported_by": random.randint(1, 100),
            "project_id": random.randint(1, 20),
            "status": random.choice(statuses),
            "found_in_version": f"v{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,20)}",
            "fixed_in_version": f"v{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,20)}" if random.random() < 0.5 else None,
            "created_at": _date_between("2024-01-01", "2026-05-01"),
            "updated_at": _date_between("2024-01-01", "2026-05-01"),
        })
    return rows


# Registry: domain -> subdomain -> generator
GENERATORS = {
    "finance": {
        "budget": generate_finance_budgets,
        "payroll": generate_finance_payroll,
        "transactions": generate_finance_transactions,
    },
    "hr": {
        "employees": generate_hr_employees,
        "performance": generate_hr_performance,
        "benefits": generate_hr_benefits,
    },
    "sales": {
        "leads": generate_sales_leads,
        "deals": generate_sales_deals,
        "accounts": generate_sales_accounts,
    },
    "inventory": {
        "products": generate_inventory_products,
        "warehouse": generate_inventory_warehouse,
    },
    "support": {
        "tickets": generate_support_tickets,
    },
    "engineering": {
        "projects": generate_eng_projects,
        "bugs": generate_eng_bugs,
    },
}


def generate(domain: str, subdomain: str, n: int = 20) -> list[dict]:
    """Generate synthetic data for a given domain/subdomain."""
    gen = GENERATORS.get(domain, {}).get(subdomain)
    if not gen:
        raise ValueError(f"No generator for {domain}/{subdomain}")
    return gen(n)


def generate_all(domains: list[str] = None, n: int = 20) -> dict:
    """Generate synthetic data for all domains. Returns {domain: {subdomain: [rows]}}."""
    result = {}
    target = domains or list(GENERATORS.keys())
    for domain in target:
        result[domain] = {}
        for subdomain in GENERATORS[domain]:
            result[domain][subdomain] = GENERATORS[domain][subdomain](n)
    return result


def save_all_to_csvs(output_dir: str = "data", n: int = 20):
    """Generate all synthetic data and save as CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    for domain, subdomains in GENERATORS.items():
        for subdomain, gen_fn in subdomains.items():
            rows = gen_fn(n)
            if not rows:
                continue
            filename = f"{domain}_{subdomain}.csv"
            path = os.path.join(output_dir, filename)
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            print(f"  Generated {len(rows)} rows → {path}")


def generate_with_groq(
    groq_client,
    domain: str,
    subdomain: str,
    columns: list[str],
    row_count: int = 20,
) -> list[dict]:
    """Generate synthetic data using Groq LLM for more realistic output."""
    return groq_client.generate_synthetic_data(domain, subdomain, columns, row_count)
