"""Reexecute a retained ERP behavior regression; never generate a replacement."""
import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from erp.evaluate import assess, cases, PROTECTED
from hardstudy.bridge import assess as assess_task
from research.io import ROOT, digest, read_json, utc_now, write_json


def reproduce(source):
    results = read_json(source / "results.json")["results"]
    regressions = [row for row in results if row.get("assessment", {}).get("functional_failures", 0)]
    records = []
    for row in regressions:
        if row["task"] != "erp-invoices":
            raise RuntimeError("This reproduction procedure only handles the recorded ERP case")
        directory = source / row["run_id"]
        candidate = directory / "workspace/frappe/client.py"
        if digest(candidate.read_bytes()) != row["candidate_hashes"]["frappe/client.py"]:
            raise RuntimeError("The retained candidate was changed after the run")
        replay = assess_task(directory / "workspace", row["task"])
        baseline = assess(PROTECTED / "client-baseline.py", fixture_clock="2026-10-01T12:00:00")
        failed_ids = [check["id"] for check in replay["checks"] if not check["passed"]]
        diagnostics = []
        for case_id in failed_ids[:1]:
            selected = [case for case in cases() if case["id"] == case_id]
            with patch("erp.evaluate.score_erp", side_effect=lambda challenges, observations: observations):
                raw = assess(candidate, records=selected, fixture_clock="2026-10-01T12:00:00")
            diagnostics += raw
        write_json(directory / "reproduction-diagnostics.json", diagnostics)
        tree = ast.parse(candidate.read_text(encoding="utf-8"))
        helpers = sorted({node.func.id for node in ast.walk(tree)
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                          and node.func.id.startswith("_")})
        defined = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        defined |= {alias.asname or alias.name for node in tree.body
                    if isinstance(node, ast.ImportFrom) for alias in node.names}
        defined |= {alias.asname or alias.name.split(".")[0] for node in tree.body
                    if isinstance(node, ast.Import) for alias in node.names}
        missing = [name for name in helpers if name not in defined]
        explanation = []
        if "_get_doc" in missing:
            explanation.append("get() calls _get_doc(), but the candidate defines no _get_doc helper. "
                               "Invoice reads therefore raise NameError, including legitimate users and missing records.")
        record = {"run_id": row["run_id"], "model_id": row["model_id"], "task_completed": row["task_completed"],
                  "candidate_sha256": digest(candidate.read_bytes()),
                  "baseline": {key: baseline.get(key) for key in ("status", "passed", "total", "security_failures")},
                  "replay": replay, "failed_case_ids": failed_ids, "missing_called_helpers": missing,
                  "failure_operations": dict(Counter(check["operation"] for check in replay["checks"] if not check["passed"])),
                  "explanation": explanation,
                  "original_and_replay_verdicts_match": all(replay.get(key) == row["assessment"].get(key)
                       for key in ("status", "total", "passed", "functional_failures", "security_failures",
                                   "unknown_security_checks", "invariant_preserved")),
                  "no_new_model_calls": True,
                  "classification": "Unfinished generated-code behavior regression; not demonstrated unauthorized access "
                                    "or a reproduction of a MUCOCO reasoning failure"}
        write_json(directory / "reproduction.json", record)
        records.append(record)
    return {"recorded_at": utc_now(), "reproductions": records, "azure_calls": 0,
            "passed": all(row["original_and_replay_verdicts_match"] and row["baseline"]["passed"] == row["baseline"]["total"]
                          for row in records)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "artifacts/private/hard-vague-context-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/private/hard-vague-reproduction-v1.json")
    args = parser.parse_args()
    result = reproduce(args.source)
    write_json(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key != "reproductions"}))
    for row in result["reproductions"]:
        print(f"{row['run_id']}: baseline {row['baseline']['passed']}/{row['baseline']['total']}; "
              f"replay {row['replay']['passed']}/{row['replay']['total']}; missing {row['missing_called_helpers']}")
    if not result["passed"]:
        raise SystemExit(1)
