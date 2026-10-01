import ast
import json
import shutil
import uuid
from pathlib import Path

from research.cases import application_cases, fixture_cases
from research.io import ROOT, digest, utc_now, write_json
from research.sandbox import assess, probe
from research.variants import CONDITIONS, TASK_IDS, prepare_workspace, source_code


class RemoveCompanyGuard(ast.NodeTransformer):
    def visit_If(self, node):
        # Only a comparison guard (not the missing-identity check).
        if isinstance(node.test, ast.Compare) and "company_id" in ast.unparse(node.test):
            return None
        return self.generic_visit(node)


def alternative(task_id):
    if task_id == "fastapi_items":
        # Readability-only valid alternative preserves exact executable structure.
        return "# Valid equivalent implementation used to self-test the judge.\n" + source_code(task_id)
    common = (
        "def allowed(principal, invoice):\n"
        "    if principal is None or invoice is None:\n"
        "        return False\n"
        "    return all(principal.get(field) is not None and invoice.get(field) is not None "
        "and principal[field] == invoice[field] for field in ('owner_id', 'company_id'))\n\n"
    )
    if task_id == "access_helper":
        return common + "def can_read(principal, invoice):\n    return allowed(principal, invoice)\n"
    if task_id == "invoice_lookup":
        return common + (
            "def read_invoice(principal, invoices, invoice_id):\n"
            "    invoice = next((row for row in invoices if row['id'] == invoice_id), None)\n"
            "    return invoice if allowed(principal, invoice) else None\n"
        )
    return common + "def list_invoices(principal, invoices):\n    return [row for row in invoices if allowed(principal, row)]\n"


def faults(task_id):
    source = source_code(task_id)
    if task_id == "fastapi_items":
        bad_guard = source.replace(
            "if not current_user.is_superuser and (item.owner_id != current_user.id):",
            "if False:",
        )
        bad_list = source.replace(".where(Item.owner_id == current_user.id)", "")
        return {"removed_item_guard": bad_guard, "unfiltered_item_list": bad_list}
    tree = RemoveCompanyGuard().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    removed_company = ast.unparse(tree) + "\n"
    correct_alternative = alternative(task_id)
    or_fault = correct_alternative.replace(
        "all(principal.get(field) is not None and invoice.get(field) is not None "
        "and principal[field] == invoice[field] for field in ('owner_id', 'company_id'))",
        "any(principal.get(field) is not None and invoice.get(field) is not None "
        "and principal[field] == invoice[field] for field in ('owner_id', 'company_id'))",
    )
    return {"removed_company_guard": removed_company, "AND_weakened_to_OR": or_fault}


def validate():
    probe_record = probe()
    session = ROOT / "artifacts" / "validation" / uuid.uuid4().hex[:10]
    records = []
    for task_id in TASK_IDS:
        cases = application_cases() if task_id == "fastapi_items" else fixture_cases(task_id)
        for condition in CONDITIONS:
            workspace = session / task_id / condition
            metadata = prepare_workspace(workspace, task_id, condition)
            result = assess(workspace, task_id, cases)
            record = {"task_id": task_id, "kind": "reference_variant", "condition": condition,
                      "metadata": metadata, "assessment": result}
            records.append(record)
            if result.get("status") != "assessed" or result.get("functional_failures"):
                write_json(ROOT / "artifacts" / "validation.json", {"passed": False, "records": records})
                raise RuntimeError(f"Reference {task_id}/{condition} failed: {json.dumps(result)[:1500]}")
            print(f"{task_id}/{condition}: {result['passed']}/{result['total']} reference checks")
        for name, code in {"valid_alternative": alternative(task_id), **faults(task_id)}.items():
            workspace = session / task_id / name
            prepare_workspace(workspace, task_id, "original")
            (workspace / "target.py").write_text(code, encoding="utf-8")
            result = assess(workspace, task_id, cases)
            expected_accept = name == "valid_alternative"
            passed = (
                result.get("status") == "assessed"
                and ((result["functional_failures"] == 0) if expected_accept else result["security_failures"] > 0)
            )
            records.append({"task_id": task_id, "kind": "evaluator_selftest", "seeded_case": name,
                            "expected_accept": expected_accept, "passed": passed, "assessment": result,
                            "not_an_agent_failure": True})
            if not passed:
                write_json(ROOT / "artifacts" / "validation.json", {"passed": False, "records": records})
                raise RuntimeError(f"Evaluator self-test {task_id}/{name} failed")
            print(f"{task_id}/{name}: evaluator {'accepts' if expected_accept else 'rejects'} as expected")
    record = {"tested_at": utc_now(), "passed": True, "sandbox": probe_record,
              "records": records, "scope": "correct variants and seeded evaluator fixtures, no live AI inference"}
    write_json(ROOT / "artifacts" / "validation.json", record)
    return record


if __name__ == "__main__":
    validate()
