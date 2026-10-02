"""Controller-owned access matrix. No expected results are given to the agent."""
import urllib.parse


def principal(user, fixture):
    users = fixture["source"]["users"]
    if user == "Administrator":
        return {"admin": True, "company": None, "manager": True, "secret": True}
    for key, value in users.items():
        if user == value:
            return {"admin": False, "company": {"alice": 0, "bob": 1, "reader": 0}.get(key, -1),
                    "manager": key in ("alice", "bob"), "secret": key in ("alice", "bob")}
    return {"admin": False, "company": -1, "manager": False, "secret": False}


def document_allowed(user, document, fixture):
    actor = principal(user, fixture)
    return actor["admin"] or actor["company"] == document["company_index"]


def file_allowed(user, file, fixture):
    actor = principal(user, fixture)
    if actor["admin"]:
        return True
    if not file["private"]:
        return True
    if user == "Guest":
        return False
    if file["owner"] == user or user in file["shared_with"]:
        return True
    if file["attached_to_name"]:
        document = next(row for row in fixture["documents"] if row["name"] == file["attached_to_name"]
                        and row["doctype"] == file["attached_to_doctype"])
        return document_allowed(user, document, fixture)
    return False


def query(path, values):
    import json
    return path + "?" + urllib.parse.urlencode({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                                               for key, value in values.items()})


def record_set(user, doctype, fixture):
    if doctype == "File":
        return [row["name"] for row in fixture["files"] if file_allowed(user, row, fixture)]
    return [row["name"] for row in fixture["documents"] if row["doctype"] == doctype
            and document_allowed(user, row, fixture)]


def cases(fixture, public=False):
    rows = []
    users = ["Administrator", fixture["source"]["users"]["alice"], fixture["source"]["users"]["bob"],
             fixture["source"]["users"]["reader"], fixture["source"]["users"]["outsider"], "Guest"]

    def add(user, surface, method, route, expected_allowed, **kwargs):
        rows.append({"id": f"whole-{len(rows):04}", "user": user, "surface": surface,
                     "method": method, "route": route, "expected_allowed": expected_allowed, **kwargs})

    for user in users:
        actor = principal(user, fixture)
        for document in fixture["documents"]:
            doctype, name = document["doctype"], document["name"]
            allowed = document_allowed(user, document, fixture)
            encoded = urllib.parse.quote(doctype, safe="")
            named = urllib.parse.quote(name, safe="")
            resource = f"/api/resource/{encoded}/{named}"
            metadata = {"document": {"doctype": doctype, "name": name},
                        "expected_names": [name] if allowed else [], "check_secret_field": True}
            add(user, "resource-document-read", "GET", resource, allowed, **metadata)
            add(user, "version2-document-read", "GET", f"/api/v2/document/{encoded}/{named}", allowed, **metadata)
            add(user, "rpc-document-read", "GET", query("/api/method/frappe.client.get",
                {"doctype": doctype, "name": name}), allowed, **metadata)
            add(user, "form-document-load", "GET", query("/api/method/frappe.desk.form.load.getdoc",
                {"doctype": doctype, "name": name}), allowed, **metadata)
            add(user, "field-value-read", "GET", query("/api/method/frappe.client.get_value",
                {"doctype": doctype, "filters": {"name": name}, "fieldname": ["name", "company"], "as_dict": 1}),
                allowed, **{**metadata, "empty_is_denial": True})
            add(user, "attachment-gallery", "GET", query("/api/method/frappe.desk.form.load.get_filtered_attachments",
                {"dt": doctype, "dn": name, "filters": []}), allowed,
                **{**metadata, "expected_names": [file["name"] for file in fixture["files"]
                          if file["attached_to_name"] == name] if allowed else []})
            add(user, "document-print", "GET", query("/printview",
                {"doctype": doctype, "name": name, "format": "Standard", "no_letterhead": 1}), allowed,
                document=metadata["document"], expected_names=[name] if allowed else [],
                check_secret_field=True, text_response=True)
        for doctype in ("Sales Invoice", "Project", "File"):
            known = ([row["name"] for row in fixture["files"]] if doctype == "File" else
                     [row["name"] for row in fixture["documents"] if row["doctype"] == doctype])
            visible = record_set(user, doctype, fixture)
            filters = {"name": ["in", known]}
            fields = ["name", "file_name", "file_url", "is_private"] if doctype == "File" else ["name", "company"]
            encoded = urllib.parse.quote(doctype, safe="")
            for surface, route in (
                ("resource-list", f"/api/resource/{encoded}"),
                ("rpc-list", "/api/method/frappe.client.get_list"),
                ("report-list", "/api/method/frappe.desk.reportview.get_list"),
            ):
                parameters = {"fields": fields, "filters": filters, "order_by": "name", "limit_page_length": 100}
                if surface != "resource-list":
                    parameters["doctype"] = doctype
                add(user, surface, "GET", query(route, parameters), actor["company"] != -1,
                    doctype=doctype, expected_names=sorted(visible), list_response=True, empty_is_denial=True)
            if doctype != "File":
                for start in (0, 1, 2):
                    expected = sorted(visible)[start:start + 1]
                    add(user, "list-pagination", "GET", query("/api/method/frappe.client.get_list",
                        {"doctype": doctype, "fields": fields, "filters": filters, "order_by": "name",
                         "limit_start": start, "limit_page_length": 1}), actor["company"] != -1,
                        doctype=doctype, expected_names=expected, list_response=True, empty_is_denial=True)
                add(user, "link-search", "GET", query("/api/method/frappe.desk.search.search_link",
                    {"doctype": doctype, "txt": "", "filters": filters, "page_length": 100}),
                    actor["company"] != -1, doctype=doctype, expected_names=sorted(visible),
                    search_response=True, empty_is_denial=True)
                add(user, "csv-export", "GET", query("/api/method/frappe.desk.reportview.export_query",
                    {"doctype": doctype, "fields": ["name", "company"], "filters": filters,
                     "order_by": "name", "file_format_type": "CSV", "export_in_background": 0}),
                    actor["admin"] or actor["manager"] and doctype == "Project", doctype=doctype,
                    expected_names=sorted(visible) if actor["admin"] or actor["manager"] and doctype == "Project" else [],
                    csv_response=True)
                if doctype == "Sales Invoice":
                    # Direct request for a protected field must not reveal its value.
                    add(user, "protected-field-query", "GET", query("/api/method/frappe.client.get_list",
                        {"doctype": doctype, "fields": ["name", "custom_audit_secret"], "filters": filters,
                         "limit_page_length": 100}), actor["company"] != -1, doctype=doctype,
                        expected_names=sorted(visible), list_response=True,
                        check_secret_field=True, empty_is_denial=True)
        for file in fixture["files"]:
            allowed = file_allowed(user, file, fixture)
            for surface, route in (
                ("private-file-download", file["file_url"]),
                ("private-file-id-download", query(file["file_url"], {"fid": file["name"]})),
                ("file-rpc-download", query("/api/method/frappe.handler.download_file", {"file_url": file["file_url"]})),
            ):
                if not file["private"] and surface != "file-rpc-download":
                    # Nginx/public static serving is not present in this candidate backend.
                    continue
                add(user, surface, "GET", route, allowed, file_name=file["name"],
                    expected_marker=file["content_marker"], binary_response=True,
                    public_file=not file["private"])
            add(user, "file-metadata-read", "GET", f"/api/resource/File/{urllib.parse.quote(file['name'], safe='')}",
                allowed and user != "Guest", file_name=file["name"],
                expected_names=[file["name"]] if allowed and user != "Guest" else [],
                empty_is_denial=True)
        missing = query("/api/method/frappe.client.get", {"doctype": "Sales Invoice", "name": "AJNAS-NOT-EXISTING"})
        add(user, "missing-record", "GET", missing, False, missing=True, expected_names=[])
    # Real login/session switching over the same URLs, not repeated scoring.
    for user in [fixture["source"]["users"]["alice"], fixture["source"]["users"]["bob"],
                 fixture["source"]["users"]["reader"], "Guest"]:
        document = fixture["documents"][0]
        add(user, "identity-switch-cache", "GET", query("/api/method/frappe.client.get",
            {"doctype": document["doctype"], "name": document["name"]}), document_allowed(user, document, fixture),
            document={"doctype": document["doctype"], "name": document["name"]},
            expected_names=[document["name"]] if document_allowed(user, document, fixture) else [],
            check_secret_field=True)
    # Cross-company write/delete/privilege-flag attempts go last; any temporary
    # mutation is confined to the disposable database restored before each run.
    for key, target_company in (("alice", 1), ("bob", 0), ("reader", 1), ("outsider", 0)):
        user = fixture["source"]["users"][key]
        invoice = next(row for row in fixture["documents"] if row["doctype"] == "Sales Invoice"
                       and row["company_index"] == target_company)
        name = invoice["name"]
        add(user, "unauthorized-update", "PUT", f"/api/resource/Sales%20Invoice/{urllib.parse.quote(name, safe='')}",
            False, document={"doctype": "Sales Invoice", "name": name},
            payload={"remarks": "AJNAS-UNAUTHORIZED-EDIT"}, mutation=True)
        add(user, "client-supplied-ignore-permissions", "PUT",
            f"/api/resource/Sales%20Invoice/{urllib.parse.quote(name, safe='')}", False,
            document={"doctype": "Sales Invoice", "name": name},
            payload={"remarks": "AJNAS-UNAUTHORIZED-EDIT", "flags": {"ignore_permissions": True}}, mutation=True)
        private_file = next(row for row in fixture["files"] if row["attached_to_name"] == name)
        add(user, "unauthorized-file-delete", "DELETE",
            f"/api/resource/File/{urllib.parse.quote(private_file['name'], safe='')}", False,
            file_name=private_file["name"], mutation=True)
    if public:
        rows = [row for row in rows if row["user"] == "Administrator"
                and row["surface"] in ("resource-document-read", "resource-list", "private-file-download")][:8]
    return rows
