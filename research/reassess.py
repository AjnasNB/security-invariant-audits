"""Re-score retained trajectories without model calls; optional fresh execution."""
import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from research.cases import fixture_cases, application_cases
from research.io import ROOT, digest, utc_now
from research.scoring import score_fixture, score_erp, SCORER_VERSION
from research.sandbox import assess
from erp.evaluate import cases as erp_cases, assess as erp_assess


def register(original, evidence):
    groups = []
    for label, batch in [("original-pilot", "pilot-delta-sol61-v3-20261001"),
                         ("original-fastapi", "application-fastapi-sol61-v3-20261001")]:
        directory = original / "artifacts/agent_runs" / batch
        value = json.loads((directory / "results.json").read_text())
        groups += [{"group": label, "task": row["task"], "candidate": directory / row["run_id"] / "candidate.py",
                    "assessment": directory / row["run_id"] / "assessment.json",
                    "task_completed": row.get("task_completed", False)} for row in value["results"]]
    cross = evidence / "harness-comparison-20261001/runs"
    for engine, batch in [("codex", "codex-invoice-smoke-20261001"),
                          ("openhands", "openhands-invoice-smoke-20261001"),
                          ("claude-code", "claude-invoice-smoke-20261001")]:
        directory = cross / batch
        for run in sorted(directory.iterdir()):
            if not run.is_dir() or not (run / "candidate.py").is_file():
                continue
            record = json.loads((run / "run.json").read_text())
            groups.append({"group": engine, "task": record["task"], "candidate": run / "candidate.py",
                           "assessment": run / "assessment.json", "task_completed": record.get("task_completed", False)})
    product = evidence / "delta-fixes-20261001/live-runs"
    for directory in sorted(product.iterdir()):
        if not directory.is_dir() or not (directory / "result.json").exists():
            continue
        record = json.loads((directory / "result.json").read_text())
        groups.append({"group": "delta-product", "task": record["task"], "candidate": directory / "output.py",
                       "assessment": directory / "hidden-checks.json", "task_completed": record["passed"]})
    for directory in sorted((ROOT / "erp/runs/pilot-20261001").iterdir()):
        if not directory.is_dir():
            continue
        record = json.loads((directory / "result.json").read_text())
        groups.append({"group": "erp", "task": "erp", "candidate": directory / "candidate.py",
                       "old_assessment": record["assessment"], "task_completed": record["passed"]})
    return groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    rows = register(args.original_root, args.evidence_root)
    records, cache = [], {}
    for index, row in enumerate(rows):
        old = row.get("old_assessment") or json.loads(row["assessment"].read_text())
        if row["task"] == "erp":
            cases = erp_cases()
            observations = [{"id": check["id"], "value": check["observed"]} for check in old["checks"]]
            score = score_erp(cases, observations)
        else:
            cases = application_cases() if row["task"] == "fastapi_items" else fixture_cases(row["task"])
            observations = [check["observed"] for check in old["checks"]]
            score = score_fixture(row["task"], cases, observations)
        identifier = digest(row["candidate"].read_bytes())
        fresh = None
        if args.execute:
            key = (row["task"], identifier)
            if key not in cache:
                if row["task"] == "erp":
                    cache[key] = erp_assess(row["candidate"])
                else:
                    with tempfile.TemporaryDirectory(prefix="ajnas-rescore-") as temporary:
                        directory = Path(temporary)
                        (directory / "target.py").write_bytes(row["candidate"].read_bytes())
                        if row["task"] == "fastapi_items":
                            (directory / "models.py").write_bytes((ROOT / "tasks/fastapi_items/models.py").read_bytes())
                        cache[key] = assess(directory, row["task"], cases)
            fresh = cache[key]
        fields = ("status", "total", "passed", "functional_failures", "security_failures", "invalid_outputs",
                  "unknown_security_checks", "invariant_preserved")
        assessment = {field: score.get(field) for field in fields}
        fresh_summary = {field: fresh.get(field) for field in fields} if fresh else None
        records.append({"group": row["group"], "task": row["task"], "candidate_sha256": identifier,
                        "task_completed": row["task_completed"],
                        "old": {field: old.get(field) for field in fields},
                        "replayed": assessment, "reexecuted": fresh_summary,
                        "legacy_pass_or_security_label_changed": any(old.get(field) != score.get(field)
                                                                  for field in ("passed", "security_failures")),
                        "runtime_type_evidence": "fresh execution" if fresh else "historical JSON only"})
        if index % 10 == 0:
            print(f"Reassessed {index+1}/{len(rows)} retained candidates; no model calls.", flush=True)
    grouped = defaultdict(lambda: {"candidates": 0, "checks": 0, "passed": 0, "security_failures": 0, "unknown_candidates": 0})
    for record in records:
        result = record["reexecuted"] or record["replayed"]
        group = grouped[record["group"]]
        group["candidates"] += 1
        group["checks"] += result.get("total") or 0
        group["passed"] += result.get("passed") or 0
        group["security_failures"] += result.get("security_failures") or 0
        group["unknown_candidates"] += result["status"] != "assessed" or (result.get("unknown_security_checks") or 0) > 0
    report = {"recorded_at": utc_now(), "scorer_version": SCORER_VERSION, "azure_calls": 0,
              "reexecuted": args.execute, "unique_runtime_executions": len(cache), "records": records,
              "groups": dict(grouped), "candidates": len(records),
              "changed_historical_pass_or_security_labels": sum(row["legacy_pass_or_security_label_changed"] for row in records),
              "scope": "Final saved candidate files from retained reported batches; no repeated model generations or edited historical artifacts"}
    destination = ROOT / "reports" / ("reassessment-v4-executed.json" if args.execute else "reassessment-v4-replay.json")
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"groups": report["groups"], "candidates": len(records),
                      "changed_labels": report["changed_historical_pass_or_security_labels"],
                      "runtime_executions": len(cache), "azure_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
