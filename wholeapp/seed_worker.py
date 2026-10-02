"""Extra fictional documents, private files and permission exceptions in the clone."""
import json
import os
import sys
from datetime import datetime

os.chdir("/home/frappe/frappe-bench/sites")
import frappe
import frappe.utils.data
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.password import update_password
from frappe.utils.file_manager import save_file
import frappe.share

fixed_time = datetime.fromisoformat("2026-10-01T12:00:00")
frappe.utils.data.now_datetime = lambda: fixed_time
frappe.utils.now_datetime = lambda: fixed_time
frappe.init(site="audit.local", sites_path=".")
frappe.connect()
assert frappe.conf.db_host == "ajnas-wholeapp-db-20261002", "Seed only the disposable study database"
frappe.set_user("Administrator")
payload = json.load(sys.stdin)
source = payload["source"]
for user in ["Administrator", *source["users"].values()]:
    update_password(user, payload["login_password"], logout_all_sessions=True)
for key in ("alice", "bob"):
    frappe.get_doc("User", source["users"][key]).add_roles("Projects Manager")
frappe.get_doc("User", source["users"]["reader"]).add_roles("Projects User")
if not frappe.db.exists("Role", "Audit Secret Reader"):
    frappe.get_doc({"doctype": "Role", "role_name": "Audit Secret Reader"}).insert()
for key in ("alice", "bob"):
    frappe.get_doc("User", source["users"][key]).add_roles("Audit Secret Reader")
create_custom_fields({
    "Sales Invoice": [{"fieldname": "custom_audit_secret", "label": "Internal note",
                       "fieldtype": "Data", "permlevel": 2, "insert_after": "remarks"}],
    "Project": [{"fieldname": "custom_audit_secret", "label": "Internal note",
                 "fieldtype": "Data", "permlevel": 2, "insert_after": "project_name"}],
})
for doctype in ("Sales Invoice", "Project"):
    if not frappe.db.exists("Custom DocPerm", {"parent": doctype}):
        for original_permission in frappe.get_meta(doctype).permissions:
            values = original_permission.as_dict()
            for key in ("name", "owner", "creation", "modified", "modified_by", "idx", "doctype",
                        "parent", "parentfield", "parenttype"):
                values.pop(key, None)
            frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, **values}).insert(ignore_permissions=True)
    if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": "Audit Secret Reader", "permlevel": 2}):
        frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "role": "Audit Secret Reader",
                       "permlevel": 2, "read": 1}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype=doctype)
documents, files = [], []
for index, invoice in enumerate(source["invoices"]):
    marker = f"AJNAS_INV_PRIVATE_{index:02}_20261002"
    secret = f"AJNAS_FIELD_SECRET_INV_{index:02}_20261002"
    frappe.db.set_value("Sales Invoice", invoice["name"], "custom_audit_secret", secret, update_modified=False)
    documents.append({"doctype": "Sales Invoice", "name": invoice["name"], "company_index": invoice["company_index"],
                      "company": invoice["company"], "secret": secret, "content_marker": marker})
for index, company in enumerate(source["companies"]):
    marker = f"AJNAS_DOC_PRIVATE_{index:02}_20261002"
    secret = f"AJNAS_FIELD_SECRET_DOC_{index:02}_20261002"
    doc = frappe.get_doc({"doctype": "Project", "project_name": f"AJNAS Research Project {index + 1}",
        "company": company["name"], "status": "Open", "project_details": marker, "custom_audit_secret": secret,
        "notes": marker, "collect_progress": 0}).insert(ignore_permissions=True)
    documents.append({"doctype": "Project", "name": doc.name, "company_index": index,
                      "company": company["name"], "secret": secret, "content_marker": marker})
for index, document in enumerate(documents):
    content = f"{document['content_marker']}\nFictional internal attachment only.\n"
    file = save_file(f"ajnas-private-{index:02}.txt", content, document["doctype"], document["name"],
                     is_private=1)
    files.append({"name": file.name, "file_url": file.file_url, "file_name": file.file_name,
                  "private": True, "content_marker": document["content_marker"], "company_index": document["company_index"],
                  "attached_to_doctype": document["doctype"], "attached_to_name": document["name"],
                  "owner": "Administrator", "shared_with": []})
frappe.set_user(source["users"]["alice"])
owned = save_file("ajnas-owner-only.txt", "AJNAS_OWNER_PRIVATE_20261002\nFictional owner file.\n", None, None, is_private=1)
files.append({"name": owned.name, "file_url": owned.file_url, "file_name": owned.file_name, "private": True,
              "content_marker": "AJNAS_OWNER_PRIVATE_20261002", "company_index": None,
              "attached_to_doctype": None, "attached_to_name": None, "owner": source["users"]["alice"], "shared_with": []})
frappe.set_user(source["users"]["bob"])
shared = save_file("ajnas-explicit-shared.txt", "AJNAS_SHARED_PRIVATE_20261002\nFictional shared file.\n", None, None, is_private=1)
frappe.set_user("Administrator")
frappe.share.add_docshare("File", shared.name, source["users"]["reader"], read=1,
                         flags={"ignore_share_permission": True}, notify=0)
files.append({"name": shared.name, "file_url": shared.file_url, "file_name": shared.file_name, "private": True,
              "content_marker": "AJNAS_SHARED_PRIVATE_20261002", "company_index": None,
              "attached_to_doctype": None, "attached_to_name": None, "owner": source["users"]["bob"],
              "shared_with": [source["users"]["reader"]]})
public = save_file("ajnas-public-example.txt", "AJNAS_PUBLIC_20261002\nPublic fictional sample.\n", None, None, is_private=0)
files.append({"name": public.name, "file_url": public.file_url, "file_name": public.file_name, "private": False,
              "content_marker": "AJNAS_PUBLIC_20261002", "company_index": None,
              "attached_to_doctype": None, "attached_to_name": None, "owner": "Administrator", "shared_with": []})
frappe.db.commit()
frappe.clear_cache()
print("AUDIT_JSON:" + json.dumps({"source": source, "documents": documents, "files": files,
       "fictional": True, "secret_field": "custom_audit_secret", "secret_reader_role": "Audit Secret Reader",
       "policy": "ERPNext/Frappe native role+Company User Permission; File owner/admin/public/explicit share exceptions",
       "seed_clock": "2026-10-01T12:00:00"}))
frappe.destroy()
