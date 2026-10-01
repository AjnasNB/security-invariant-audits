"""Deterministic fictional INR companies and invoices; run only in audit.local."""
import json
from decimal import Decimal

from frappe.utils import nowdate
from erpnext.setup.setup_wizard.operations.install_fixtures import install as install_presets

assert frappe.local.site == "audit.local", "Never seed an existing ERP site."
frappe.set_user("Administrator")
install_presets("India")
frappe.db.set_single_value("System Settings", "country", "India")
frappe.db.set_single_value("System Settings", "time_zone", "Asia/Kolkata")
frappe.db.set_single_value("System Settings", "enable_onboarding", 0)
frappe.db.set_single_value("Accounts Settings", "unlink_payment_on_cancellation_of_invoice", 1)
frappe.db.set_default("currency", "INR")
frappe.db.set_default("country", "India")
frappe.db.set_global("setup_complete", 1)
if not frappe.db.exists("Fiscal Year", "Audit FY 2026-27"):
    frappe.get_doc({"doctype": "Fiscal Year", "year": "Audit FY 2026-27",
                   "year_start_date": "2026-04-01", "year_end_date": "2027-03-31"}).insert()

companies = [
    {"name": "Audit Kerala Trading", "abbr": "AKT"},
    {"name": "Audit Tamil Nadu Supplies", "abbr": "ATS"},
]
for company in companies:
    if not frappe.db.exists("Company", company["name"]):
        frappe.get_doc({"doctype": "Company", "company_name": company["name"],
            "abbr": company["abbr"], "country": "India", "default_currency": "INR",
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": "Standard"}).insert()

if not frappe.db.exists("Customer", "Audit Synthetic Customer"):
    frappe.get_doc({"doctype": "Customer", "customer_name": "Audit Synthetic Customer",
        "customer_type": "Company", "customer_group": "Commercial", "territory": "India"}).insert()
if not frappe.db.exists("Item", "AUDIT-SERVICE"):
    frappe.get_doc({"doctype": "Item", "item_code": "AUDIT-SERVICE",
        "item_name": "Fictional research service", "item_group": "Services",
        "stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1}).insert()
if not frappe.db.exists("Price List", "Audit INR Selling"):
    frappe.get_doc({"doctype": "Price List", "price_list_name": "Audit INR Selling",
        "enabled": 1, "selling": 1, "currency": "INR"}).insert()

users = {
    "alice": ("alice@audit.invalid", "Accounts Manager", companies[0]["name"]),
    "bob": ("bob@audit.invalid", "Accounts Manager", companies[1]["name"]),
    "reader": ("reader@audit.invalid", "Accounts User", companies[0]["name"]),
    "outsider": ("outsider@audit.invalid", None, None),
}
for role, (email, erp_role, company) in users.items():
    if not frappe.db.exists("User", email):
        doc = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Audit " + role,
            "enabled": 1, "send_welcome_email": 0, "user_type": "System User"})
        if erp_role:
            doc.append("roles", {"role": erp_role})
        doc.insert()
    if erp_role == "Accounts Manager":
        frappe.get_doc("User", email).add_roles("Stock User")
    if company and not frappe.db.exists("User Permission", {"user": email, "allow": "Company", "for_value": company}):
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Company",
            "for_value": company, "apply_to_all_doctypes": 1}).insert()

invoices = []
for index, company in enumerate(companies):
    currency_company = frappe.get_doc("Company", company["name"])
    receivable = currency_company.default_receivable_account or frappe.db.get_value("Account",
        {"company": company["name"], "account_type": "Receivable", "is_group": 0}, "name")
    income = currency_company.default_income_account or frappe.db.get_value("Account",
        {"company": company["name"], "root_type": "Income", "is_group": 0}, "name")
    cost_center = currency_company.cost_center or frappe.db.get_value("Cost Center",
        {"company": company["name"], "is_group": 0}, "name")
    for number, (qty, rate) in enumerate([(2, 1000), (3, 275.50), (1, 1234.56)]):
        remark = f"AUDIT-SEED-{company['abbr']}-{number}"
        existing = frappe.db.get_value("Sales Invoice", {"remarks": remark}, "name")
        if existing:
            invoice = frappe.get_doc("Sales Invoice", existing)
        else:
            invoice = frappe.get_doc({"doctype": "Sales Invoice", "company": company["name"],
                "customer": "Audit Synthetic Customer", "currency": "INR", "conversion_rate": 1,
                "selling_price_list": "Audit INR Selling", "price_list_currency": "INR", "plc_conversion_rate": 1,
                "posting_date": nowdate(), "due_date": nowdate(), "debit_to": receivable,
                "cost_center": cost_center, "remarks": remark, "is_pos": 0, "update_stock": 0,
                "disable_rounded_total": 1,
                "items": [{"item_code": "AUDIT-SERVICE", "qty": qty, "rate": rate,
                           "income_account": income, "cost_center": cost_center}],
                "taxes": [{"charge_type": "On Net Total", "account_head": income,
                           "description": "Synthetic 18 percent test charge - NOT a GST filing", "rate": 18}]})
            invoice.insert()
            if number == 0:
                invoice.submit()
        invoices.append({"name": invoice.name, "company": company["name"], "company_index": index,
            "status": invoice.docstatus, "owner": invoice.owner, "quantity": qty, "rate": str(rate),
            "net_expected": str(Decimal(str(qty)) * Decimal(str(rate))),
            "grand_expected": str((Decimal(str(qty))*Decimal(str(rate))*Decimal("1.18")).quantize(Decimal(".01"))),
            "net_total": invoice.net_total, "grand_total": invoice.grand_total,
            "outstanding": invoice.outstanding_amount})
frappe.db.commit()
frappe.clear_cache()
print("AUDIT_JSON:" + json.dumps({"companies": companies, "users": {k: v[0] for k, v in users.items()},
    "invoices": invoices, "data_is_fictional": True,
    "policy": "ERPNext Accounts roles + configured Company User Permissions. No owner-only requirement was added.",
    "tax_note": "Arithmetic fixture only; no GST registration/e-invoice/e-waybill integration or compliance claim."}))
