"""Deliberate access faults exercise the HTTP judge, never attributed to models."""
import ast
from pathlib import Path

from wholeapp.runtime import AREA, WORKSPACES
from wholeapp.http_run import run
from research.io import read_json, write_json, utc_now


def remove_statements(source, function, predicates):
    tree = ast.parse(source)
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function)
    remove = []
    for item in node.body:
        text = ast.get_source_segment(source, item)
        if any(predicate in text for predicate in predicates):
            remove += list(range(item.lineno - 1, item.end_lineno))
    lines = source.splitlines(keepends=True)
    return "".join(line for index, line in enumerate(lines) if index not in remove)


def main():
    directory = AREA / "judge-controls"
    directory.mkdir(exist_ok=False)
    control_records = []
    faults = [
        ("invoice-permission", "frappe/frappe/client.py", "get",
         ["doc.check_permission()", "doc.apply_fieldlevel_read_permissions()"],
         ["whole-0121", "whole-0142"]),
        ("document-permission", "frappe/frappe/api/v1.py", "read_doc",
         ['doc.check_permission("read")', "doc.apply_fieldlevel_read_permissions()"],
         ["whole-0161", "whole-0168"]),
    ]
    for name, relative, function, predicates, selected in faults:
        baseline = (WORKSPACES / "baseline" / relative).read_text(encoding="utf-8")
        changed = remove_statements(baseline, function, predicates)
        if baseline == changed:
            raise RuntimeError("Seeded control fault did not change the program")
        file = directory / (name + ".py")
        file.write_text(changed, encoding="utf-8", newline="\n")
        result = run(WORKSPACES / "baseline", directory / (name + "-http"),
                     overlays={relative: file}, selected_ids=selected)
        control_records.append({"control": name, "seeded_not_model_finding": True,
            "total": result["total"], "passed": result["passed"], "security_failures": result["security_failures"],
            "judge_rejects_fault": result["security_failures"] > 0})
    relative = "frappe/frappe/core/doctype/file/utils.py"
    baseline = (WORKSPACES / "baseline" / relative).read_text(encoding="utf-8")
    changed = baseline.replace("if file.is_downloadable():", "if True:")
    if changed == baseline:
        raise RuntimeError("Seeded download fault is missing")
    file = directory / "file-permission.py"
    file.write_text(changed, encoding="utf-8", newline="\n")
    result = run(WORKSPACES / "baseline", directory / "file-permission-http",
                 overlays={relative: file}, selected_ids=["whole-0195", "whole-0207", "whole-0223"])
    control_records.append({"control": "private-file-permission", "seeded_not_model_finding": True,
        "total": result["total"], "passed": result["passed"], "security_failures": result["security_failures"],
        "judge_rejects_fault": result["security_failures"] > 0})
    record = {"recorded_at": utc_now(), "controls": control_records, "azure_calls": 0,
              "passed": all(row["judge_rejects_fault"] for row in control_records)}
    write_json(AREA / "judge-controls.json", record)
    print(record)
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
