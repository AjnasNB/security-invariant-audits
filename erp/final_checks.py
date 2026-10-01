"""Read-only checks of live integrated source, retained fixtures and ledger balance."""
import ast
import hashlib
import json
from pathlib import Path
from erp.evaluate import ROOT, PRIVATE, parse_record, seed
from erp.manage import compose


def main():
    live = compose(["exec", "-T", "backend", "cat", "apps/frappe/frappe/client.py"],
                   capture_output=True, timeout=30)
    if live.returncode:
        raise RuntimeError("Integrated backend source unavailable")
    expected = (ROOT / "erp/runtime/combined-client.py").read_text(encoding="utf-8")
    assert ast.dump(ast.parse(live.stdout)) == ast.dump(ast.parse(expected))
    code = """import os
os.chdir('/home/frappe/frappe-bench/sites')
import frappe,json
frappe.init(site='audit.local',sites_path='.')
frappe.connect()
frappe.set_user('Administrator')
invoices=frappe.get_all('Sales Invoice',filters={'remarks':['like','AUDIT-SEED-%']},fields=['name','docstatus','grand_total'],order_by='name')
temporary=frappe.db.count('Sales Invoice',{'remarks':'AUDIT-HTTP-TEMP-INVOICE'})
item=bool(frappe.db.exists('Item','AUDIT-HTTP-TEMP'))
ledgers={}
for row in invoices:
    entries=frappe.get_all('GL Entry',filters={'voucher_no':row.name,'is_cancelled':0},fields=['debit','credit'])
    ledgers[row.name]={'entries':len(entries),'debit':sum(entry.debit for entry in entries),'credit':sum(entry.credit for entry in entries)}
print('AUDIT_JSON:'+json.dumps({'invoices':invoices,'temporary_invoices':temporary,'temporary_item_exists':item,'ledgers':ledgers}))
frappe.db.rollback()
frappe.destroy()
"""
    result = compose(["exec", "-T", "backend", "./env/bin/python", "-"],
                     input=code, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Read-only final database check failed")
    data = parse_record(result.stdout)
    fixture = seed()
    assert len(data["invoices"]) == len(fixture["invoices"]) == 6
    by_name = {row["name"]: row for row in data["invoices"]}
    for invoice in fixture["invoices"]:
        row = by_name[invoice["name"]]
        assert row["docstatus"] == invoice["status"]
        assert row["grand_total"] == float(invoice["grand_expected"])
        ledger = data["ledgers"][invoice["name"]]
        assert ledger["debit"] == ledger["credit"]
        assert ledger["entries"] > 0 if row["docstatus"] == 1 else ledger["entries"] == 0
    assert data["temporary_invoices"] == 0 and data["temporary_item_exists"] is False
    report = {"passed": True, "integrated_source_ast_matches": True,
              "integrated_source_normalized_sha256": hashlib.sha256(live.stdout.encode()).hexdigest(),
              "seeded_invoice_count": len(data["invoices"]), "all_seeded_states_and_amounts_preserved": True,
              "submitted_ledgers_balanced": True, "temporary_http_records_removed": True,
              "scope": "Read-only final check of this local synthetic ERP instance"}
    (ROOT / "reports/erp-final-checks.json").write_text(json.dumps(report, indent=2) + "\n",
                                                     encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
