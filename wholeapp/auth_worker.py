"""Install study-only API credentials in the disposable database, never originals."""
import json
import os
import sys

os.chdir("/home/frappe/frappe-bench/sites")
import frappe
from frappe.utils.password import set_encrypted_password

frappe.init(site="audit.local", sites_path=".")
frappe.connect()
assert frappe.conf.db_host == "ajnas-wholeapp-db-20261002"
frappe.set_user("Administrator")
payload = json.load(sys.stdin)
for user, credential in payload["credentials"].items():
    frappe.db.set_value("User", user, "api_key", credential["api_key"], update_modified=False)
    set_encrypted_password("User", user, credential["api_secret"], fieldname="api_secret")
frappe.db.commit()
frappe.clear_cache()
print(json.dumps({"installed_in_disposable_database_only": True, "users": len(payload["credentials"])}))
frappe.destroy()
