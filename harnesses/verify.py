"""Integrity, contract and fresh replay checks for recorded cross-harness runs."""
import json
from pathlib import Path

from research.cases import fixture_cases
from research.io import ROOT, digest, read_json, utc_now, write_json
from research.sandbox import assess, probe, docker_prefix
from harnesses.broker import StudyBroker
from research.variants import prepare_workspace

ARTIFACTS = Path("/var/tmp/ajnas-harness-results-20261001")


def verify_batch(batch_name):
    directory = ARTIFACTS / batch_name
    result = read_json(directory / "results.json")
    issues = []
    receipts = []
    provider_usage = {"input_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0,
                      "output_tokens": 0, "requests": 0}
    for row in result["records"]:
        run_dir = directory / row["run_id"]
        candidate = (run_dir / "candidate.py").read_bytes()
        if digest(candidate) != row["candidate_sha256"]:
            issues.append(row["run_id"] + ": candidate hash mismatch")
        events = [json.loads(line) for line in (run_dir / "broker_events.jsonl").open(encoding="utf-8")] \
            if (run_dir / "broker_events.jsonl").exists() else []
        for event in events:
            if event.get("tool") not in ("study_read_file", "study_write_file", "study_run_public_tests"):
                issues.append(row["run_id"] + ": outside tool policy")
            if event.get("phase") == "started" and event.get("tool") == "study_write_file" \
                    and event["arguments"].get("path") != "target.py":
                issues.append(row["run_id"] + ": outside-target write")
        recorded_assessment = read_json(run_dir / "assessment.json")
        if recorded_assessment.get("status") == "assessed":
            if len(recorded_assessment["checks"]) != recorded_assessment["total"]:
                issues.append(row["run_id"] + ": denominator mismatch")
            if sum(check["passed"] for check in recorded_assessment["checks"]) != recorded_assessment["passed"]:
                issues.append(row["run_id"] + ": passed-count mismatch")
        # Fresh worker execution of the preserved candidate; no further model calls.
        repeated = assess(run_dir / "workspace", row["task"], fixture_cases(row["task"]))
        same = all(recorded_assessment.get(key) == repeated.get(key) for key in
                   ("status", "total", "passed", "functional_failures", "security_failures"))
        if not same:
            issues.append(row["run_id"] + ": fresh independent replay differs")
        blocked_by_budget = False
        if row["exit_code"] != 0:
            stdout = (run_dir / "stdout.jsonl").read_text()
            blocked_by_budget = "Batch conservative planning cap reached" in stdout
        receipt = {
            "run_id": row["run_id"], "task_completed": row["task_completed"],
            "termination_label": "budget_stopped" if blocked_by_budget else row["termination"],
            "replay_matches": same, "security_failures": repeated.get("security_failures"),
            "complete_generated_program": row["executable_changed"] and row["task_completed"],
        }
        receipts.append(receipt)
        for metadata_path in sorted(run_dir.glob("provider-*-metadata.json")):
            metadata = read_json(metadata_path)
            request_path = run_dir / metadata_path.name.replace("-metadata.json", "-request.json")
            response_path = run_dir / metadata_path.name.replace("-metadata.json", "-response.sse")
            if metadata.get("request_sha256") != digest(request_path.read_bytes()):
                # JSON manifest hashing differs from pretty formatting; reconstruct original compact JSON.
                if metadata.get("request_sha256") != digest(json.dumps(read_json(request_path)).encode()):
                    issues.append(row["run_id"] + ": provider request integrity mismatch")
            if metadata.get("response_sha256") != digest(response_path.read_bytes()):
                issues.append(row["run_id"] + ": provider response integrity mismatch")
            usage = metadata.get("usage") or {}
            provider_usage["requests"] += 1
            if result["engine"] == "claude_code":
                provider_usage["input_tokens"] += usage.get("input_tokens", 0) \
                    + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                provider_usage["cached_tokens"] += usage.get("cache_read_input_tokens", 0)
                provider_usage["cache_write_tokens"] += usage.get("cache_creation_input_tokens", 0)
            else:
                provider_usage["input_tokens"] += usage.get("input_tokens", 0)
                provider_usage["cached_tokens"] += usage.get("input_tokens_details", {}).get("cached_tokens", 0)
                provider_usage["cache_write_tokens"] += usage.get("input_tokens_details", {}).get("cache_write_tokens", 0)
            provider_usage["output_tokens"] += usage.get("output_tokens", 0)
    if provider_usage["requests"] != result["model_requests"]:
        issues.append("request count mismatch")
    verification = {"verified_at": utc_now(), "batch": batch_name, "passed": not issues,
                    "issues": issues, "receipts": receipts, "provider_usage": provider_usage,
                    "scope": "Fresh candidate behavior, broker logs and file integrity; no exhaustive OS audit."}
    write_json(directory / "verification.json", verification)
    return verification


def broker_checks():
    directory = ARTIFACTS / "broker-selftests"
    directory.mkdir(exist_ok=True)
    work = directory / "workspace"
    if not work.exists():
        prepare_workspace(work, "access_helper", "original")
    broker = StudyBroker(work, "access_helper", directory)
    checks = []
    missing = broker.execute("study_read_file", {"path": "PROJECT_NOTE.md"})
    checks.append({"id": "absent-note-explicit", "passed": missing["exists"] is False})
    for name, action in (
        ("outside-read", lambda: broker.execute("study_read_file", {"path": "../assessment.json"})),
        ("outside-write", lambda: broker.execute("study_write_file", {"path": "public_cases.json", "content": "tamper", "expected_sha256": ""})),
        ("stale-source-write", lambda: broker.execute("study_write_file", {"path": "target.py", "content": "tamper", "expected_sha256": "0"*64})),
        ("unknown-tool", lambda: broker.execute("run_command", {"command": "anything"})),
    ):
        try:
            action()
            passed = False
        except (PermissionError, ValueError):
            passed = True
        checks.append({"id": name, "passed": passed})
    original = (work / "target.py").read_bytes()
    checks.append({"id": "reference-unchanged-after-rejections",
                   "passed": original == (ROOT / "tasks/access_helper/target.py").read_bytes() or
                             original.decode().replace("\r\n", "\n") ==
                             (ROOT / "tasks/access_helper/target.py").read_text()})
    broker.sealed = True
    try:
        broker.execute("study_read_file", {"path": "target.py"})
        passed = False
    except PermissionError:
        passed = True
    checks.append({"id": "post-seal-tools-rejected", "passed": passed})
    record = {"checked_at": utc_now(), "checks": checks, "passed": all(row["passed"] for row in checks)}
    write_json(directory / "verification.json", record)
    return record


if __name__ == "__main__":
    import subprocess
    results = [verify_batch(batch) for batch in (
        "codex-invoice-smoke-20261001", "openhands-invoice-smoke-20261001", "claude-invoice-smoke-20261001")]
    broker = broker_checks()
    write_json(ARTIFACTS / "final_verification.json", {
        "recorded_at": utc_now(), "batches": results, "broker": broker,
        "passed": all(row["passed"] for row in results) and broker["passed"],
    })
    print(json.dumps({"batches": [{"batch": row["batch"], "passed": row["passed"], "issues": row["issues"],
                                 "usage": row["provider_usage"]} for row in results], "broker": broker}, indent=2))
