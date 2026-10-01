"""Export completed Linux evidence to durable C: storage without changing originals."""
import json
import shutil
import subprocess
from pathlib import Path

from research.io import ROOT, digest, read_json, utc_now, write_json

LINUX_RESULTS = Path("/var/tmp/ajnas-harness-results-20261001")
LINUX_CHECKS = Path("/var/tmp/ajnas-sdk-checks-20261001")
DESTINATION = Path("/mnt/c/Users/20cs0/Documents/AjnasResearch/SUTD/harness-comparison-20261001")
SOURCES = [
    ("codex_cli", "openai/codex", "Apache-2.0"),
    ("openhands", "OpenHands/OpenHands", "MIT"),
    ("openhands_sdk", "OpenHands/software-agent-sdk", "MIT"),
    ("claude_code", "anthropics/claude-code", "commercial CLI; public repo is not a core-source MIT license"),
    ("claude_agent_sdk", "anthropics/claude-agent-sdk-python", "MIT SDK"),
]


def source_register():
    records = []
    for local, repository, license_name in SOURCES:
        source = ROOT / "_sources" / local
        commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
        files = {}
        for relative in ("README.md", "LICENSE", "LICENSE.md", "AGENTS.md"):
            path = source / relative
            if path.exists():
                files[relative] = digest(path.read_bytes())
        records.append({"source_id": local, "repository": "https://github.com/" + repository,
                        "commit": commit, "license": license_name, "selected_file_hashes": files})
    return {"recorded_at": utc_now(), "sources": records}


def summary():
    verification = read_json(LINUX_RESULTS / "final_verification.json")
    records = {}
    for engine, batch in (("codex", "codex-invoice-smoke-20261001"),
                          ("openhands", "openhands-invoice-smoke-20261001"),
                          ("claude_code", "claude-invoice-smoke-20261001")):
        result = read_json(LINUX_RESULTS / batch / "results.json")
        verified = read_json(LINUX_RESULTS / batch / "verification.json")
        rows = result["records"]
        budget_stopped = [row for row in verified["receipts"] if row["termination_label"] == "budget_stopped"]
        records[engine] = {
            "batch": batch, "runs": len(rows), "completed_refactors": sum(row["task_completed"] for row in rows),
            "budget_stopped_runs": len(budget_stopped),
            "generated_violating_programs": sum(
                row["executable_changed"] and (row["assessment"]["security_failures"] or 0) > 0 for row in rows),
            "observed_security_failing_checks": sum(row["assessment"]["security_failures"] or 0 for row in rows),
            "checks_on_all_final_files": sum(row["assessment"]["total"] or 0 for row in rows),
            "checks_on_completed_refactors": sum(row["assessment"]["total"] or 0 for row in rows if row["task_completed"]),
            "passed_checks_on_completed_refactors": sum(row["assessment"]["passed"] or 0 for row in rows if row["task_completed"]),
            "usage": verified["provider_usage"], "verification_passed": verified["passed"],
        }
    record = {
        "recorded_at": utc_now(), "agents": records,
        "source_tests": read_json(LINUX_CHECKS / "summary.json"),
        "verification_passed": verification["passed"],
        "storage": "C:/Users/20cs0/Documents/AjnasResearch/SUTD/harness-comparison-20261001",
        "claims": [
            "Restricted research integration, not stock full-access agents.",
            "Codex/OpenHands use GPT-6.1 Sol; Claude Code uses Claude Opus 5. Native prompts differ.",
            "Claude Code last task budget-stopped: do not count its unchanged passing file as a completed task.",
            "Six smoke trajectories per engine, not an accuracy or superiority benchmark.",
            "Full raw artifacts preserve every recorded preflight and model attempt available.",
            "Initial /tmp logs lost on WSL shutdown are disclosed; selected suites were rerun with durable logs.",
        ],
    }
    return record


if __name__ == "__main__":
    report = summary()
    if not report["verification_passed"]:
        raise RuntimeError("Cannot export results with failed integrity verification")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    shutil.copytree(LINUX_RESULTS, DESTINATION / "runs", dirs_exist_ok=True)
    shutil.copytree(LINUX_CHECKS, DESTINATION / "source-checks", dirs_exist_ok=True)
    source_records = source_register()
    write_json(DESTINATION / "sources.json", source_records)
    inspected = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", "ajnas-cross-harness:20261001"], text=True))[0]
    frozen = subprocess.check_output([
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "ajnas-cross-harness:20261001",
        "python", "-m", "pip", "freeze",
    ], text=True)
    binaries = {}
    for name, relative in (
        ("codex", ".runtime/codex-release/bin/codex-x86_64-unknown-linux-musl"),
        ("claude_code", ".runtime/claude-release/bin/package/claude"),
    ):
        binaries[name] = {"sha256": digest((ROOT / relative).read_bytes()),
                          "source_file": relative}
    runtime = {"recorded_at": utc_now(), "image_id": inspected["Id"],
               "resolved_python_dependencies": frozen.strip().splitlines(),
               "binary_hashes": binaries,
               "dependency_policy": "Package-declared dependencies installed for this image; not the full OpenHands uv workspace lock.",
               "scope": "Research runtime; user-installed Codex/Claude binaries were not updated."}
    write_json(DESTINATION / "runtime.json", runtime)
    write_json(ROOT / "reports" / "harness-runtime.json", runtime)
    write_json(DESTINATION / "summary.json", report)
    write_json(ROOT / "reports" / "harness-comparison.json", report)
    write_json(ROOT / "datasets" / "harness-sources.json", source_records)
    # Record exact bytes of all exported files for integrity, excluding the manifest itself.
    manifest = {path.relative_to(DESTINATION).as_posix(): digest(path.read_bytes())
                for path in sorted(DESTINATION.rglob("*")) if path.is_file() and path.name != "export-manifest.json"}
    write_json(DESTINATION / "export-manifest.json", {"recorded_at": utc_now(), "files": manifest,
                                                     "scope": "local raw evidence; review before any public export"})
    print(json.dumps(report, indent=2))
