"""Evidence integrity checks. Hashes support provenance, not semantic correctness."""
import argparse
import ast
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from research.io import ROOT, digest, read_json, utc_now, write_json


def source_hashes():
    selected = {
        "mucoco": ["code_mutation/ast_mutation.py", "datasets/open_ended_format/humaneval_test_modified_open.csv"],
        "jailguard": ["JailGuard/main_txt.py", "JailGuard/utils/utils.py", "JailGuard/utils/similarity.py",
                     "JailGuard/utils/augmentations.py", "JailGuard/utils/mask_utils.py",
                     "dataset/text/dataset.pkl", "dataset/text/dataset-key.pkl"],
        "humaneval": ["data/HumanEval.jsonl.gz", "human_eval/execution.py", "LICENSE"],
        "django_multitenant": ["django_multitenant/views.py", "django_multitenant/mixins.py",
                              "django_multitenant/tests/test_viewsets.py", "LICENSE"],
        "agentdojo": ["src/agentdojo/default_suites/v1/banking/user_tasks.py",
                     "src/agentdojo/default_suites/v1/banking/injection_tasks.py", "LICENSE"],
        "fastapi_app": ["backend/app/api/routes/items.py", "backend/app/models.py",
                       "backend/tests/api/routes/test_items.py", "backend/pyproject.toml", "LICENSE"],
        "erpnext": ["erpnext/accounts/doctype/sales_invoice/sales_invoice.py",
                   "erpnext/accounts/doctype/sales_invoice/test_sales_invoice.py", "license.txt"],
    }
    result = {}
    for source, paths in selected.items():
        result[source] = {
            path: digest((ROOT / "_sources" / source / path).read_bytes())
            for path in paths if (ROOT / "_sources" / source / path).is_file()
        }
    write_json(ROOT / "datasets" / "source_file_hashes.json", result)
    return result


def metadata_usage(batch):
    totals = Counter()
    for path in batch.rglob("provider-*-metadata.json"):
        metadata = read_json(path)
        if metadata.get("usage"):
            usage = metadata["usage"]
            totals["requests"] += 1
            totals["input_tokens"] += usage.get("input_tokens", 0)
            totals["output_tokens"] += usage.get("output_tokens", 0)
            totals["cached_tokens"] += usage.get("input_tokens_details", {}).get("cached_tokens", 0)
            totals["cache_write_tokens"] += usage.get("input_tokens_details", {}).get("cache_write_tokens", 0)
    return dict(totals)


def audit_batch(batch_name):
    batch = ROOT / "artifacts" / "agent_runs" / batch_name
    result = read_json(batch / "results.json")
    issues = []
    trajectories = []
    schedule = read_json(batch / "schedule.json") if (batch / "schedule.json").exists() else []
    if result.get("mode") in ("pilot", "smoke", "single", "application"):
        for row in result["results"]:
            directory = batch / row["run_id"]
            receipt = read_json(directory / "run.json")
            candidate = (directory / "candidate.py").read_bytes()
            if digest(candidate) != receipt["candidate_sha256"]:
                issues.append(f"{row['run_id']}: candidate integrity mismatch")
            assessment = read_json(directory / "assessment.json")
            checks = assessment.get("checks", [])
            if assessment.get("status") == "assessed":
                if len(checks) != assessment["total"]:
                    issues.append(f"{row['run_id']}: assessment denominator mismatch")
                if sum(check["passed"] for check in checks) != assessment["passed"]:
                    issues.append(f"{row['run_id']}: assessment pass count mismatch")
            events = [json.loads(line) for line in (directory / "tool_events.jsonl").open(encoding="utf-8")]
            tools = [event["details"]["name"] for event in events if event["text"].startswith("Tool:")]
            if any(tool not in ("study_read_file", "study_write_file", "study_run_public_tests") for tool in tools):
                issues.append(f"{row['run_id']}: unapproved tool")
            for event in events:
                if event["text"] == "Tool: study_write_file" and event["details"]["arguments"].get("path") != "target.py":
                    issues.append(f"{row['run_id']}: outside-target write")
            input_record = read_json(directory / "input.json")
            source = (directory / "workspace" / "target.py").read_bytes()
            candidate_structure = ast.dump(ast.parse(candidate.decode("utf-8")), include_attributes=False)
            from research.variants import source_code, historical_mutate
            starting_code = historical_mutate(source_code(row["task"]), row["task"], row["condition"])
            structure_changed = candidate_structure != ast.dump(ast.parse(starting_code), include_attributes=False)
            trajectories.append({
                "run_id": row["run_id"], "task": row["task"], "condition": row["condition"],
                "changed_executable_structure": structure_changed,
                "public_tests_run": "study_run_public_tests" in tools,
                "note_read": receipt.get("note_read"), "record_matches": row == receipt,
            })
            if row != receipt:
                issues.append(f"{row['run_id']}: batch and trajectory receipt differ")
    totals = metadata_usage(batch)
    if not result.get("error") and result.get("completed_at"):
        for key in ("requests", "input_tokens", "output_tokens", "cached_tokens"):
            if totals.get(key, 0) != result["total"].get(key, 0):
                issues.append(f"Provider usage does not reconcile: {key}")
        if schedule and len(schedule) != len(result["results"]):
            issues.append("Schedule/run count mismatch")
    record = {"audited_at": utc_now(), "batch": batch_name, "passed": not issues,
              "issues": issues, "provider_usage": totals, "trajectories": trajectories,
              "limitation": "Byte integrity and counted tool observations, not a proof of complete OS action surveillance."}
    write_json(batch / "integrity_audit.json", record)
    return record


def environment():
    from research.sandbox import APP_IMAGE, IMAGE, docker_prefix
    records = {}
    for label, image in (("fixtures", IMAGE), ("application", APP_IMAGE), ("tenant", "ajnas-security-tenant:20261001")):
        inspect = subprocess.run(docker_prefix() + ["image", "inspect", image], capture_output=True, text=True, check=True)
        metadata = json.loads(inspect.stdout)[0]
        frozen = subprocess.run(docker_prefix() + [
            "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            image, "python", "-m", "pip", "freeze",
        ], capture_output=True, text=True, check=True)
        records[label] = {
            "image": image, "image_id": metadata["Id"], "created": metadata["Created"],
            "dependencies": frozen.stdout.strip().splitlines(),
        }
        requirements = ROOT / "sandbox" / f"requirements-{label}-lock.txt"
        requirements.write_text(frozen.stdout, encoding="utf-8")
    record = {"recorded_at": utc_now(), "runtimes": records,
              "note": "Exact image IDs and resolved dependency locks; provider deployments may remain mutable."}
    write_json(ROOT / "artifacts" / "environment.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch")
    args = parser.parse_args()
    source_hashes()
    if args.batch:
        print(json.dumps(audit_batch(args.batch), indent=2))
    else:
        print(json.dumps(environment(), indent=2))
