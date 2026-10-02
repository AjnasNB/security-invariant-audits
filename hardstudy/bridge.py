"""Host-owned assessment bridge; no private security verdict in agent test feedback."""
import argparse
import json
from pathlib import Path

from hardstudy.judge import assess as fixture_assess
from erp.evaluate import assess as erp_assess, cases as erp_cases
from hardstudy.structure import inspect


def assess(workspace, task, public=False):
    workspace = Path(workspace)
    if task == "erp-invoices":
        records = erp_cases()
        if public:
            records = [record for record in records if record["user"] == "Administrator"
                       and record["operation"] in ("read", "list")]
        result = erp_assess(workspace / "frappe/client.py", records=records,
                            fixture_clock="2026-10-01T12:00:00")
    else:
        result = fixture_assess(workspace, task, public)
    if public:
        return {"status": result["status"], "tests": result.get("total"), "passed": result.get("passed"),
                "failed": result.get("functional_failures"), "error": result.get("error")}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--structure-before", type=Path)
    parser.add_argument("--structure-after", type=Path)
    args = parser.parse_args()
    if args.structure_before and args.structure_after:
        print(json.dumps(inspect(json.loads(args.structure_before.read_text(encoding="utf-8")),
                                 json.loads(args.structure_after.read_text(encoding="utf-8")))))
    else:
        print(json.dumps(assess(args.workspace, args.task, args.public)))
