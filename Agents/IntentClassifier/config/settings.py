import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL: str = "https://api.groq.com/openai/v1/chat/completions"

DATABASE_URL:  str = os.getenv("DATABASE_URL", "")
TARGET_SCHEMA: str = os.getenv("TARGET_SCHEMA", "sales")

STRUCTURED_VIEWS: list[str] = [
    # Sales
    "Sales_Booking_Business_View",                    # orders, deals, order history, pricing
    "Sales_Cancellation_Business_View",               # cancellations, refund records
    "Sales_Shipment_Business_View",                   # shipment tracking, delivery status
    "Sales_Order_Change_Business_View",               # order change history, change requests
    # Finance
    "Finance_Accounting_Business_View",               # invoices, payments, ledger, receivables, tax fields
    "Finance_Asset_Management_Business_View",         # asset register, depreciation, maintenance schedules
    # Procurement
    "Procurement_Purchase_Order_Business_View",       # PO records, goods receipt (GRN), approved budget checks
    "Procurement_Vendor_Performance_Business_View",   # vendor metrics, delivery scores, incident counts
    # Logistics
    "Logistics_Inventory_Business_View",              # stock levels, SKU records, inventory movement
    "Logistics_Warehouse_Business_View",              # warehouse adjustment logs, picking records
    # Operations
    "Operations_Returns_Business_View",               # return requests, return status, disposition
    "Operations_SLA_Monitoring_Business_View",        # support tickets, SLA timestamps, breach logs
    # HR
    "HR_Workforce_Business_View",                     # employee records, roles, performance ratings
    "HR_Payroll_Business_View",                       # payroll data, bonus records, expense claims
    # Marketing
    "Marketing_Campaign_Business_View",               # campaign metrics, CRM lead records, conversion data
    # Legal
    "Legal_Compliance_Business_View",                 # consent records, data subject status, compliance flags
    # IT  — Suggestion 2: new view added for IT/Access_Management intents
    "IT_Access_Business_View",                        # access permissions, user roles, system entitlements
]

DOMAIN_TAXONOMY: dict[str, list[str]] = {
    "Sales": [
        # Suggestion 1: Credit_Note removed — belongs to Finance only
        "Booking", "Cancellation", "Shipment", "Contract",
        "Forecasting", "Order_Change", "Pricing",
    ],
    "Finance": [
        "Invoicing", "Payment", "Accounting", "Asset_Management",
        "Budget", "Tax_Compliance", "Reconciliation", "Refund", "Credit_Note",
    ],
    "Operations": [
        "Order_Management", "Quality_Control", "SLA_Monitoring",
        "Returns", "Process_Compliance", "Customer_Support",
    ],
    "Logistics": [
        "Inventory", "Shipment_Planning", "Freight",
        "Warehouse", "Carrier_Management",
    ],
    "Procurement": [
        "Purchase_Order", "Vendor_Management", "Approval",
        "Sourcing", "Goods_Receipt", "Contract_Management",
    ],
    "Marketing": [
        "Campaign", "Lead_Management", "Customer_Analytics", "Email_Campaign",
    ],
    "HR": [
        # Suggestion 1: Access_Management removed — belongs to IT only
        "Workforce", "Contract_Renewal", "Payroll",
        "Expense_Management", "Training_Development",
    ],
    "Legal": [
        "Legal_Notice", "Data_Privacy", "Contract_Obligations", "Regulatory_Compliance",
    ],
    "IT": [
        "Access_Management", "Security_Policy", "System_Permissions",
    ],
}
