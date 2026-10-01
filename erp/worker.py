"""Execution-only adapter; expected results and scoring are never sent here."""
import json
import os
import sys
import traceback
from decimal import Decimal

os.chdir("/home/frappe/frappe-bench/sites")
import frappe
import frappe.client

frappe.init(site="audit.local", sites_path=".")
frappe.connect()
payload = json.load(sys.stdin)
assert frappe.local.site == "audit.local"
observations = []
for case in payload["cases"]:
    frappe.set_user("Administrator")
    frappe.db.savepoint("audit_case")
    try:
        frappe.set_user(case["user"])
        operation = case["operation"]
        if operation == "read":
            doc = frappe.client.get("Sales Invoice", case["name"])
            value = {"allowed": True, "name": doc["name"], "company": doc.get("company"),
                     "grand_total": doc.get("grand_total")}
        elif operation == "list":
            docs = frappe.client.get_list("Sales Invoice", fields=["name", "company"],
                filters={"remarks": ["like", "AUDIT-SEED-%"]}, order_by="name",
                limit_start=case.get("start", 0), limit_page_length=case.get("limit", 100))
            value = {"allowed": True, "names": [doc.name for doc in docs],
                     "companies": sorted({doc.company for doc in docs})}
        elif operation == "delete":
            frappe.client.delete_doc("Sales Invoice", case["name"])
            value = {"allowed": True, "exists_after": bool(frappe.db.exists("Sales Invoice", case["name"]))}
        elif operation == "update":
            frappe.client.set_value("Sales Invoice", case["name"], "remarks", "AUDIT-TEMP-EDIT")
            value = {"allowed": True, "remarks_after": frappe.db.get_value("Sales Invoice", case["name"], "remarks")}
        elif operation == "calculate":
            doc = frappe.get_doc("Sales Invoice", case["name"])
            doc.check_permission()
            value = {"allowed": True, "net_total": doc.net_total, "grand_total": doc.grand_total,
                     "docstatus": doc.docstatus, "outstanding": doc.outstanding_amount}
        elif operation == "cancel":
            doc = frappe.get_doc("Sales Invoice", case["name"])
            doc.cancel()
            value = {"allowed": True, "docstatus": doc.docstatus,
                "active_gl_entries": frappe.db.count("GL Entry", {"voucher_no": doc.name, "is_cancelled": 0})}
        else:
            raise ValueError("Unknown fixed operation")
        observations.append({"id": case["id"], "value": value})
    except Exception as error:
        observations.append({"id": case["id"], "value": {"allowed": False, "error": type(error).__name__},
                             "diagnostic": traceback.format_exc()[-2400:]})
    finally:
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="audit_case")
        frappe.clear_last_message()
print("AUDIT_JSON:" + json.dumps(observations, default=str))
frappe.db.rollback()
frappe.destroy()
