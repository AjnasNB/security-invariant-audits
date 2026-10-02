"""Investigate a baseline print disclosure without changing candidate code."""
import json
import os
import sys
from datetime import datetime

os.chdir("/home/frappe/frappe-bench/sites")
import frappe
import frappe.utils.data
fixed_time = datetime.fromisoformat("2026-10-01T12:00:00")
frappe.utils.data.now_datetime = lambda: fixed_time
frappe.utils.now_datetime = lambda: fixed_time
frappe.init(site="audit.local", sites_path=".")
frappe.connect()
assert frappe.conf.db_host == "ajnas-wholeapp-db-20261002"
from frappe.www.printview import validate_print_permission

payload = json.load(sys.stdin)
rows = []
for user in payload["users"]:
    frappe.set_user(user)
    for name in payload["names"]:
        doc = frappe.get_lazy_doc("Sales Invoice", name)
        row = {"user": user, "name": name, "company": doc.company,
               "read": frappe.has_permission("Sales Invoice", "read", doc),
               "print": frappe.has_permission("Sales Invoice", "print", doc),
               "user_permission": frappe.permissions.has_user_permission(doc, user),
               "website_permission": frappe.has_website_permission(doc)}
        try:
            validate_print_permission(doc)
            row["validate_print_allowed"] = True
        except Exception as error:
            row["validate_print_allowed"] = False
            row["error"] = type(error).__name__
        rows.append(row)
print("AUDIT_JSON:" + json.dumps(rows))
frappe.db.rollback()
frappe.destroy()
