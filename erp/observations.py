"""Trusted baseline measurements in the actual installed ERP and database."""
import json
from decimal import Decimal
import frappe.client

assert frappe.local.site == "audit.local"
users = ["Administrator", "alice@audit.invalid", "bob@audit.invalid",
         "reader@audit.invalid", "outsider@audit.invalid", "Guest"]
frappe.set_user("Administrator")
invoices = frappe.get_all("Sales Invoice", fields=["name", "company", "net_total", "grand_total", "docstatus"],
                         filters={"remarks": ["like", "AUDIT-SEED-%"]}, order_by="name")
rows = []
for user in users:
    for invoice in invoices:
        frappe.set_user(user)
        try:
            result = frappe.client.get("Sales Invoice", invoice.name)
            rows.append({"kind": "read", "user": user, "invoice": invoice.name,
                         "company": invoice.company, "allowed": True,
                         "grand_total": result.get("grand_total")})
        except Exception as error:
            rows.append({"kind": "read", "user": user, "invoice": invoice.name,
                         "company": invoice.company, "allowed": False, "error": type(error).__name__})
    frappe.set_user(user)
    try:
        result = frappe.client.get_list("Sales Invoice", fields=["name", "company"],
                                        filters={"remarks": ["like", "AUDIT-SEED-%"]}, order_by="name",
                                        limit_page_length=100)
        rows.append({"kind": "list", "user": user, "names": [row.name for row in result],
                     "companies": sorted({row.company for row in result})})
    except Exception as error:
        rows.append({"kind": "list", "user": user, "error": type(error).__name__})
frappe.set_user("Administrator")
ledger = {}
for invoice in invoices:
    entries = frappe.get_all("GL Entry", filters={"voucher_no": invoice.name, "is_cancelled": 0},
                             fields=["debit", "credit"])
    ledger[invoice.name] = {"entries": len(entries),
        "debit": str(sum(Decimal(str(row.debit)) for row in entries)),
        "credit": str(sum(Decimal(str(row.credit)) for row in entries))}
print("AUDIT_JSON:" + json.dumps({"apps": frappe.get_installed_apps(), "invoices": invoices,
                                  "permission_observations": rows, "ledger": ledger}, default=str))
frappe.db.rollback()
