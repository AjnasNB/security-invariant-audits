"""Exercise changed chart/API helpers directly, not just unrelated HTTP paths."""
import json
import os
import sys
import hashlib

os.chdir("/home/frappe/frappe-bench/sites")
import frappe
import frappe.client
from erpnext.accounts.doctype.account.chart_of_accounts import chart_of_accounts as chart
from frappe.api.v1 import get_request_form_data

frappe.init(site="audit.local", sites_path=".")
frappe.connect()
assert frappe.conf.db_host == "ajnas-wholeapp-db-20261002"
frappe.set_user("Administrator")
results = []


def add(case_id, value):
    encoded = json.dumps(value, sort_keys=True, default=str).encode()
    results.append({"id": case_id, "sha256": hashlib.sha256(encoded).hexdigest(),
                    "value": value if len(encoded) < 3000 else None})


for name in ("Standard", "Standard with Numbers"):
    add("chart-" + name, chart.get_chart(name))
for flag in (False, True):
    frappe.local.flags.allow_unverified_charts = flag
    add("country-charts-" + str(flag), chart.get_charts_for_country("India", with_standard=True))
frappe.local.flags.allow_unverified_charts = False
for company in json.load(sys.stdin)["companies"]:
    add("existing-tree-" + company, chart.get_chart(None, existing_company=company))
for case_id, document in (
    ("request-form-native", {"company": "Audit Kerala Trading", "remarks": "dummy"}),
    ("request-form-json", {"company": "Audit Tamil Nadu Supplies", "remarks": "dummy"}),
):
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request
    payload = document if case_id.endswith("native") else {"data": json.dumps(document)}
    builder = EnvironBuilder(method="POST", data=json.dumps(payload), content_type="application/json")
    frappe.local.request = Request(builder.get_environ())
    frappe.local.form_dict = frappe._dict(payload)
    add(case_id, get_request_form_data())
print("AUDIT_JSON:" + json.dumps(results))
frappe.db.rollback()
frappe.destroy()
