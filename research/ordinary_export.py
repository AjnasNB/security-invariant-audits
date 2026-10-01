"""Publish selected, rights-cleared experiment evidence; never raw model traces."""
import argparse
from collections import Counter
from pathlib import Path

from research.io import ROOT, digest, read_json, utc_now, write_json
from research.scoring import SCORER_VERSION

RUN_FIELDS = (
    "task", "condition", "arm", "repetition", "run_id", "termination", "error",
    "tests_run", "note_read", "meaningful_refactor", "source_sha256", "candidate_sha256",
    "context_files_unchanged", "task_completed", "assessment", "usage", "reference_estimate_usd",
)


def group_summary(rows):
    return {
        "scheduled_trajectories": len(rows), "task_completed": sum(row["task_completed"] for row in rows),
        "budget_stopped": sum(row["termination"] == "budget_stopped" for row in rows),
        "checks_all_saved_files": sum(row["assessment"]["total"] for row in rows),
        "passed_all_saved_files": sum(row["assessment"]["passed"] or 0 for row in rows),
        "checks_completed_refactors": sum(row["assessment"]["total"] for row in rows if row["task_completed"]),
        "passed_completed_refactors": sum(row["assessment"]["passed"] or 0 for row in rows if row["task_completed"]),
        "security_violating_files": sum((row["assessment"]["security_failures"] or 0) > 0 for row in rows),
        "security_failing_checks": sum(row["assessment"]["security_failures"] or 0 for row in rows),
        "functional_failing_files": sum((row["assessment"]["functional_failures"] or 0) > 0 for row in rows),
        "unknown_files": sum(row["assessment"]["invariant_preserved"] is None for row in rows),
        "notes_present": sum(row["condition"] in ("neutral", "misleading") for row in rows),
        "notes_read": sum(row["note_read"] for row in rows),
        "reference_estimate_usd": sum(row["reference_estimate_usd"] for row in rows),
    }


def export(source, destination):
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    data = read_json(source / "results.json")
    protocol, configuration = read_json(source / "protocol.json"), read_json(source / "configuration.json")
    usage = read_json(source / "usage.json")
    rows = []
    event_counts = Counter()
    for run in data["results"]:
        local = source / run["run_id"]
        public = destination / run["run_id"]
        public.mkdir()
        row = {key: run[key] for key in RUN_FIELDS}
        if digest((local / "candidate.py").read_bytes()) != row["candidate_sha256"]:
            raise RuntimeError("Candidate does not match the sealed run receipt")
        if digest((local / "input.py").read_bytes()) != row["source_sha256"]:
            raise RuntimeError("Input does not match the sealed run receipt")
        for filename in ("candidate.py", "input.py"):
            (public / filename).write_bytes((local / filename).read_bytes())
        for filename in ("README.md", "test_invoice_service.py", "project_notes.md"):
            original = local / "workspace" / filename
            if original.exists():
                (public / filename).write_bytes(original.read_bytes())
        write_json(public / "input.json", read_json(local / "input.json"))
        if (local / "public_tests.json").exists():
            write_json(public / "public-tests.json", read_json(local / "public_tests.json"))
        observations = [check["observed"] for check in run["assessment"]["checks"]]
        write_json(public / "observations.json", observations)
        events = read_json(local / "events.json")
        tools = Counter(event["details"]["name"] for event in events if event["text"].startswith("Tool: "))
        event_counts.update(tools)
        metadata = []
        for filename in sorted(local.glob("provider-*-metadata.json")):
            item = read_json(filename)
            response = filename.with_name(filename.name.replace("-metadata.json", "-response.sse"))
            if response.exists() and digest(response.read_bytes()) != item["response_sha256"]:
                raise RuntimeError("Raw provider response does not match its retained hash")
            metadata.append({key: item.get(key) for key in (
                "request_number", "http_status", "model", "response_id", "status", "usage",
                "reference_cost_usd", "response_sha256", "usage_unknown",
            )})
        write_json(public / "provenance.json", {
            "tool_calls": dict(tools), "raw_events_sha256": digest((local / "events.json").read_bytes()),
            "provider_metadata": metadata, "excluded": ["raw provider requests/responses", "reasoning",
                "checkpoints", "assistant narrative", "profiles", "credentials"],
        })
        write_json(public / "run.json", row)
        rows.append(row)
    write_json(destination / "protocol.json", protocol)
    write_json(destination / "deployment.json", read_json(source / "deployment.json"))
    write_json(destination / "configuration.json", configuration)
    write_json(destination / "usage.json", usage)
    summary = {
        "recorded_at": utc_now(), "experiment": "Ordinary coding-prompt pilot",
        "protocol": protocol["version"], "scorer_version": SCORER_VERSION,
        "deployment": read_json(source / "deployment.json"), "total": group_summary(rows),
        "arms": {arm: group_summary([row for row in rows if row["arm"] == arm])
                 for arm in ("benign-variation", "unchanged-control", "project-note")},
        "tasks": {task: group_summary([row for row in rows if row["task"] == task])
                  for task in protocol["task_templates"]},
        "conditions": {condition: group_summary([row for row in rows if row["condition"] == condition])
                       for condition in ("original", "rename", "formatting", "neutral", "misleading")},
        "tool_calls": dict(event_counts), "usage": usage,
        "runs": [{key: row[key] for key in RUN_FIELDS if key != "assessment"} for row in rows],
        "comparison_status": "Descriptive only: benign arm has one budget-stopped run; no failures "
                             "observed, no evidence mutations outperform independent repeats",
        "limits": [
            "Three small templates, one model and one narrow Delta tool policy",
            "Original code/docstrings still contain their ordinary behavior; they were not obscured",
            "No task-specific security rule or private-test hints in user request, README or tool descriptions",
            "Unmodified Delta product instructions still enforce generic permissions and source-context boundaries",
            "Visible tests intentionally cover ordinary examples, not the complete access policy",
            "One budget stop is not a completed refactor even though its partial output passed assessment",
            "No whole-ERP ordinary-prompt rerun was added",
        ],
    }
    write_json(destination / "summary.json", summary)
    write_json(ROOT / "reports" / "ordinary-v1-results.json", summary)
    manifest = {path.relative_to(destination).as_posix(): digest(path.read_bytes())
                for path in sorted(destination.rglob("*")) if path.is_file()}
    write_json(destination / "manifest.json", {
        "recorded_at": utc_now(), "files": manifest, "author": "Ajnas N B",
        "selection": "Exact synthetic input/output code, ordinary context/tests, controller checks and "
                     "aggregate/hash evidence. No raw reasoning, credentials or restricted paper templates.",
        "redaction": "Excluded whole private trace/profile files; exported candidate/input bytes are unchanged",
    })
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "artifacts/private/ordinary-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/ordinary-v1")
    args = parser.parse_args()
    summary = export(args.source, args.output)
    print(summary["total"])


if __name__ == "__main__":
    main()
