"""Full-app HTTP CRUD checks using only fictional temporary records."""
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
import time
from decimal import Decimal
from pathlib import Path
from erp.evaluate import seed
from erp.manage import PRIVATE, compose

BASE = "http://127.0.0.1:18080"


def credentials():
    values = dict(line.split("=", 1) for line in (PRIVATE / "experiment.env").read_text().splitlines())
    return values["ERP_ADMIN_PASSWORD"]


def session():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(opener, method, route, value=None):
    data = json.dumps(value).encode() if value is not None else None
    req = urllib.request.Request(BASE + route, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            value = {"non_json_error": True, "status": error.code}
        return error.code, value


def main():
    for attempt in range(30):
        try:
            with urllib.request.urlopen(BASE + "/api/method/ping", timeout=3) as response:
                if json.load(response).get("message") == "pong":
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("ERP did not become ready for HTTP checks")
    admin = session()
    status, _ = request(admin, "POST", "/api/method/login", {"usr": "Administrator", "pwd": credentials()})
    if status != 200:
        raise RuntimeError("Local ERP admin login failed")
    checks = []
    created = []
    try:
        status, apps = request(admin, "GET", "/api/method/frappe.client.get_list?" + urllib.parse.urlencode({
            "doctype": "Sales Invoice", "fields": json.dumps(["name", "company", "grand_total"]),
            "filters": json.dumps({"remarks": ["like", "AUDIT-SEED-%"]}), "limit_page_length": 100}))
        checks.append({"name": "http-seeded-invoice-list", "passed": status == 200 and len(apps.get("message", [])) == 6})
        status, item = request(admin, "POST", "/api/resource/Item", {"item_code": "AUDIT-HTTP-TEMP",
            "item_name": "Temporary synthetic CRUD service", "item_group": "Services",
            "stock_uom": "Nos", "is_stock_item": 0})
        checks.append({"name": "http-item-create", "passed": status == 200 and item.get("data", {}).get("item_code") == "AUDIT-HTTP-TEMP"})
        if status == 200:
            created.append(("Item", item["data"]["name"]))
            route = "/api/resource/Item/" + urllib.parse.quote(item["data"]["name"], safe="")
            status, updated = request(admin, "PUT", route, {"item_name": "Updated synthetic CRUD service"})
            checks.append({"name": "http-item-update", "passed": status == 200 and updated.get("data", {}).get("item_name") == "Updated synthetic CRUD service"})
            status, _ = request(admin, "DELETE", route)
            checks.append({"name": "http-item-delete", "passed": status == 202 or status == 200})
            if status in (200, 202):
                created.remove(("Item", item["data"]["name"]))
            status, _ = request(admin, "GET", route)
            checks.append({"name": "http-deleted-item-missing", "passed": status == 404})
        invoice_name = seed()["invoices"][1]["name"]
        status, existing = request(admin, "GET", "/api/resource/Sales%20Invoice/" + urllib.parse.quote(invoice_name, safe=""))
        document = existing["data"]
        fields = ["company", "customer", "currency", "conversion_rate", "selling_price_list",
                  "price_list_currency", "plc_conversion_rate", "posting_date", "due_date", "debit_to",
                  "cost_center", "disable_rounded_total", "is_pos", "update_stock"]
        new_invoice = {field: document.get(field) for field in fields}
        new_invoice["remarks"] = "AUDIT-HTTP-TEMP-INVOICE"
        new_invoice["items"] = [{key: row.get(key) for key in ("item_code", "qty", "rate", "income_account", "cost_center")}
                                for row in document["items"]]
        new_invoice["taxes"] = [{key: row.get(key) for key in ("charge_type", "account_head", "description", "rate")}
                                for row in document["taxes"]]
        status, inserted = request(admin, "POST", "/api/resource/Sales%20Invoice", new_invoice)
        checks.append({"name": "http-draft-invoice-create-and-total", "passed": status == 200 and
                       Decimal(str(inserted.get("data", {}).get("grand_total", 0))) == Decimal("975.27")})
        if status == 200:
            name = inserted["data"]["name"]
            created.append(("Sales Invoice", name))
            route = "/api/resource/Sales%20Invoice/" + urllib.parse.quote(name, safe="")
            status, _ = request(admin, "DELETE", route)
            checks.append({"name": "http-draft-invoice-delete", "passed": status in (200, 202)})
            if status in (200, 202):
                created.remove(("Sales Invoice", name))
            status, _ = request(admin, "GET", route)
            checks.append({"name": "http-deleted-invoice-missing", "passed": status == 404})
        guest = session()
        status, _ = request(guest, "GET", "/api/resource/Sales%20Invoice/" + urllib.parse.quote(invoice_name, safe=""))
        checks.append({"name": "http-guest-invoice-denied", "passed": status in (401, 403)})
    finally:
        for doctype, name in created:
            route = "/api/resource/" + urllib.parse.quote(doctype, safe="") + "/" + urllib.parse.quote(name, safe="")
            status, _ = request(admin, "DELETE", route)
            if status not in (200, 202):
                raise RuntimeError("A temporary research record could not be removed")
        created.clear()
    report = {"passed": all(check["passed"] for check in checks), "checks": checks,
              "total": len(checks), "passed_checks": sum(check["passed"] for check in checks),
              "temporary_records_removed": not created,
              "data_scope": "Only locally created fictional AUDIT-HTTP records; seeded invoice dataset retained",
              "no_real_financial_activity": True}
    (PRIVATE / "http-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
