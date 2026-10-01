"""Publish corrected open-harness observations without overwriting raw runs."""
import argparse
import ast
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from harnesses.response_text import response_text
from research.cases import fixture_cases
from research.io import ROOT, digest, read_json, utc_now, write_json
from research.scoring import score_fixture, same_value

CODING = {
    "codex": ("codex-coding", "codex-coding-continuation"),
    "opencode": ("opencode-coding",),
    "openhands": ("openhands-coding",),
    "goose": ("goose-coding",),
    "aider": ("aider-coding", "aider-coding-identity-fixed"),
}
PREDICTION = {
    "codex": ("codex-prediction", "codex-prediction-transport"),
    "opencode": ("opencode-prediction", "opencode-prediction-remaining"),
    "openhands": ("openhands-prediction", "openhands-prediction-remaining"),
}
SOURCES = [
    ("codex", ROOT / "_sources/codex_cli", "openai/codex", "Apache-2.0", "rust-v0.159.3"),
    ("opencode", ROOT / "_sources/opencode", "anomalyco/opencode", "MIT", "v1.18.34"),
    ("openhands", Path("D:/SUTD/_sources/openhands_sdk"), "OpenHands/software-agent-sdk", "MIT", "1.50.1"),
    ("goose", ROOT / "_sources/goose", "aaif-goose/goose", "Apache-2.0", "v1.52.0"),
    ("aider", ROOT / "_sources/aider", "Aider-AI/aider", "Apache-2.0", "v0.86.0"),
]


def summary(rows):
    return {
        "retained_files": len(rows), "completed_refactors": sum(row["task_completed"] for row in rows),
        "all_file_checks": sum(row["assessment"]["total"] for row in rows),
        "all_file_passed": sum(row["assessment"]["passed"] or 0 for row in rows),
        "completed_refactor_checks": sum(row["assessment"]["total"] for row in rows if row["task_completed"]),
        "completed_refactor_passed": sum(row["assessment"]["passed"] or 0 for row in rows if row["task_completed"]),
        "access_violating_files": sum((row["assessment"]["security_failures"] or 0) > 0 for row in rows),
        "access_failing_checks": sum(row["assessment"]["security_failures"] or 0 for row in rows),
        "unknown_assessments": sum(row["assessment"]["invariant_preserved"] is None for row in rows),
        "functional_failing_files": sum((row["assessment"]["functional_failures"] or 0) > 0 for row in rows),
        "termination": dict(Counter(row["termination"] for row in rows)),
        "notes_present": sum(row["condition"] in ("neutral", "misleading") for row in rows),
        "notes_read": sum(row["note_read"] for row in rows),
        "reference_estimate_usd": sum(row["reference_estimate_usd"] for row in rows),
    }


def provider_evidence(directory):
    values = []
    for path in sorted(directory.glob("provider-*-metadata.json")):
        metadata = read_json(path)
        response = path.with_name(path.name.replace("-metadata.json", "-response.sse"))
        if response.exists() and digest(response.read_bytes()) != metadata.get("response_sha256"):
            raise RuntimeError("Saved provider-response hash mismatch")
        values.append({key: metadata.get(key) for key in (
            "number", "http_status", "served_model", "usage", "status", "response_id",
            "reference_cost_usd", "request_sha256", "response_sha256", "unknown_usage", "failure",
        )})
    return values


def export_code(source, destination, batch, row):
    local = source / batch / row["run_id"]
    target = destination / "coding" / row["engine"] / batch / row["run_id"]
    target.mkdir(parents=True, exist_ok=True)
    for name in ("input.py", "candidate.py"):
        if digest((local / name).read_bytes()) != row["source_sha256" if name == "input.py" else "candidate_sha256"]:
            raise RuntimeError("Candidate/input hashes differ from the sealed receipt")
        (target / name).write_bytes((local / name).read_bytes())
    for name in ("README.md", "test_invoice_service.py", "project_notes.md"):
        if (local / "workspace" / name).exists():
            (target / name).write_bytes((local / "workspace" / name).read_bytes())
    write_json(target / "input.json", read_json(local / "input.json"))
    write_json(target / "run.json", row)
    write_json(target / "observations.json", [check["observed"] for check in row["assessment"]["checks"]])
    if (local / "public-tests.json").exists():
        write_json(target / "public-tests.json", read_json(local / "public-tests.json"))
    provider = provider_evidence(local)
    provenance = {"provider_metadata": provider, "native_response_count": len(provider),
                  "private_trace_files_excluded": True}
    if (local / "tool-events.jsonl").exists():
        events = [json.loads(line) for line in (local / "tool-events.jsonl").read_text().splitlines()]
        provenance["tool_calls"] = dict(Counter(event["tool"] for event in events if event["phase"] == "started"))
        provenance["events_sha256"] = digest((local / "tool-events.jsonl").read_bytes())
    else:
        provenance["native_aider_wrapper"] = "Text edits and unittest invocation in an isolated throwaway copy"
    write_json(target / "provenance.json", provenance)
    return target.relative_to(destination).as_posix()


def coding(source, destination):
    collected, grouped = [], {}
    for engine, batches in CODING.items():
        rows = []
        for batch in batches:
            for original in read_json(source / batch / "results.json")["results"]:
                row = {**original, "batch": batch}
                if batch == "aider-coding":
                    row["raw_termination"] = row["termination"]
                    row["termination"] = "integration_failed"
                    row["reason"] = "Verified versioned model identity was rejected by the relay; CLI exited zero without edits"
                    row["task_completed"] = False
                row["assessment"] = score_fixture(row["task"], fixture_cases(row["task"]),
                    [check["observed"] for check in original["assessment"]["checks"]])
                row["evidence_directory"] = export_code(source, destination, batch, row)
                rows.append(row)
        group = summary(rows)
        group["scheduled_primary_tasks"] = 24 if engine in ("codex", "opencode", "openhands") else 3
        group["batches"] = list(batches)
        group["scope"] = ("Partial frozen ordinary schedule; settings/caps and uncompleted rows disclosed"
                          if engine in ("codex", "opencode", "openhands") else
                          "Three-original-task compatibility smoke; not matched benign/unchanged/note arms")
        if engine == "aider":
            group["corrected_compatibility_tasks"] = 3
            group["initial_integration_failures"] = 3
        group["arms"] = {arm: summary([row for row in rows if row["arm"] == arm])
                         for arm in sorted({row["arm"] for row in rows})}
        grouped[engine] = group
        collected += rows
    return collected, grouped


def predictions(source, destination):
    all_rows, groups = [], {}
    for engine, batches in PREDICTION.items():
        completed = {}
        rows = []
        for batch in batches:
            for original in read_json(source / batch / "results.json")["results"]:
                directory = source / batch / original["run_id"]
                texts = []
                for metadata in sorted(directory.glob("provider-*-metadata.json")):
                    value = read_json(metadata)
                    raw = metadata.with_name(metadata.name.replace("-metadata.json", "-response.sse"))
                    if raw.exists():
                        request_path = metadata.with_name(metadata.name.replace("-metadata.json", "-request.json"))
                        request = read_json(request_path)
                        instructions = request.get("instructions", "")
                        instructions += "\n".join(str(item.get("content", "")) for item in request.get("input", [])
                                                  if item.get("role") in ("system", "developer"))
                        if "You are a title generator." in instructions:
                            continue
                        text = response_text(raw.read_text(encoding="utf-8"))
                        if text is not None:
                            # Keep malformed/wrong-type answers too. Filtering
                            # by expected output would hide real model failures.
                            texts.append(text)
                text = texts[-1] if texts else None
                try:
                    observed = ast.literal_eval(text.strip()) if text else None
                except (SyntaxError, ValueError):
                    observed = None
                evaluated = original["termination"] == "completed" and text is not None
                row = {key: original.get(key) for key in (
                    "id", "task", "condition", "prompt", "expected", "program_sha256", "termination",
                    "budget_stop", "exit_code", "usage", "reference_estimate_usd", "run_id",
                )}
                row.update({"engine": engine, "batch": batch, "text": text, "observed": observed,
                            "output_valid": type(observed) is type(original["expected"]) if text else False,
                            "status": "assessed" if evaluated else "unknown",
                            "correct": same_value(observed, original["expected"]) if evaluated else None,
                            "raw_parser_text": original.get("text"),
                            "reparsed_without_new_model_calls": True})
                if evaluated:
                    if row["id"] in completed:
                        raise RuntimeError("Answered paper question unexpectedly regenerated")
                    completed[row["id"]] = row
                public = destination / "predictions" / engine / batch / row["run_id"]
                public.mkdir(parents=True, exist_ok=True)
                write_json(public / "question.json", row)
                write_json(public / "provenance.json", {"provider_metadata": provider_evidence(directory)})
                row["evidence_directory"] = public.relative_to(destination).as_posix()
                rows.append(row)
        comparisons = []
        for task in ("HumanEvalTF447", "HumanEvalTF466", "HumanEvalTF547"):
            first, second = completed.get(task + ":original"), completed.get(task + ":mutant")
            comparable = first is not None and second is not None
            comparisons.append({"task": task, "status": "assessed" if comparable else "unknown",
                "original_answer": first["text"] if first else None,
                "mutant_answer": second["text"] if second else None,
                "original_correct": first["correct"] if first else None,
                "mutant_correct": second["correct"] if second else None,
                "paper_defined_inconsistency": (first["correct"] and not second["correct"]) if comparable else None})
        groups[engine] = {"unique_answered_questions": len(completed),
            "correct_answers": sum(row["correct"] for row in completed.values()),
            "retained_stopped_question_attempts": sum(row["status"] == "unknown" for row in rows),
            "comparisons": comparisons, "inconsistencies": sum(row["paper_defined_inconsistency"] is True for row in comparisons),
            "scope": "Known-positive historical examples with ordinary output-prediction requests; not full-paper replication"}
        all_rows += rows
    return all_rows, groups


def costs(source):
    totals = Counter()
    batches, missing = {}, []
    for path in sorted(source.glob("*/usage.json")):
        raw = read_json(path)
        metadata = [read_json(item) for item in path.parent.glob("*/provider-*-metadata.json")]
        inputs = sum(item.get("usage", {}).get("input_tokens", 0) for item in metadata if item.get("usage"))
        if inputs != raw["input_tokens"]:
            raise RuntimeError("Batch/provider input tokens do not reconcile")
        batch = dict(raw)
        batch["recorded_request_files"] = len(list(path.parent.glob("*/provider-*-request.json")))
        batch["metadata_files"] = len(metadata)
        batch["reported_usage_cost_usd"] = sum(item["reference_cost_usd"] or 0 for item in metadata)
        if abs(batch["reported_usage_cost_usd"] - raw["reference_estimate_usd"]) > 1e-8:
            raise RuntimeError("Recorded model cost does not reconcile")
        batches[path.parent.name] = batch
        totals.update({key: raw[key] for key in ("requests", "input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens")})
    for path in sorted(source.glob("*/*/provider-*-request.json")):
        if path.with_name(path.name.replace("-request.json", "-metadata.json")).exists():
            continue
        body = read_json(path)
        estimate = (len(json.dumps(body).encode()) + 1) // 2
        reservation = (estimate * 2.5 + body.get("max_output_tokens", 1536) * 10) / 1e6
        missing.append({"path": path.relative_to(source).as_posix(), "request_sha256": digest(path.read_bytes()),
                        "usage_unknown": True, "reference_reservation_usd": reservation,
                        "note": "Unreported request; not confirmed billed cost. OpenCode missing request is auxiliary title traffic."})
    observed = sum(batch["reported_usage_cost_usd"] for batch in batches.values())
    reserve = sum(row["reference_reservation_usd"] for row in missing)
    old = read_json(ROOT / "reports/cost-accounting-v4.json")["all_recorded_total"]
    return {"recorded_at": utc_now(), "batches": batches, "reported_usage_totals": dict(totals),
            "request_files": sum(batch["recorded_request_files"] for batch in batches.values()),
            "reported_usage_requests": int(totals["requests"]),
            "observed_reference_estimate_usd": observed, "unreported_requests": missing,
            "unreported_reference_reservations_usd": reserve,
            "observed_plus_uncertain_reservations_usd": observed + reserve,
            "total_reference_cap_usd": 1.5, "within_cap": observed + reserve <= 1.5,
            "previous_study_reference_estimate_usd": old["cache_write_estimate_usd"],
            "all_studies_observed_reference_estimate_usd": old["cache_write_estimate_usd"] + observed,
            "all_studies_with_new_uncertain_reservations_usd": old["cache_write_estimate_usd"] + observed + reserve,
            "rates_per_million": {"input": 2, "cached": .1, "output": 10, "cache_write": 2.5},
            "scope": "Observed provider usage plus explicitly separate uncertain reservations, including setup/title calls. "
                     "Not Azure invoice, credit balance, local electricity or this Codex chat.",
            "unknown_legacy_accounting": "Codex stopped batch had an unrecorded in-flight reservation; "
                                         "reconciled from saved request file without regenerating it"}


def sources():
    rows = []
    for name, root, repository, license_name, tag in SOURCES:
        revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        files = {relative: digest((root / relative).read_bytes()) for relative in
                 ("README.md", "LICENSE", "LICENSE.txt", "NOTICE", "AGENTS.md") if (root / relative).is_file()}
        changed = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain=v1"], text=True).strip()
        rows.append({"agent": name, "repository": "https://github.com/" + repository,
                     "commit": revision, "version_or_tag": tag, "license": license_name,
                     "local_clone_unchanged": not changed, "selected_hashes": files,
                     "execution": "Official pinned release binary" if name in ("codex", "opencode", "goose")
                     else "Pinned package/source SDK runtime",
                     "full_source_build_or_full_test_suite": False})
    return {"recorded_at": utc_now(), "sources": rows, "scope": "Source clones and runtime provenance, "
            "not claims of full builds or exhaustive upstream tests"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "artifacts/private/open-harness-ordinary-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/open-harness-ordinary-v1")
    parser.add_argument("--refresh", action="store_true",
                        help="Refresh this explicitly named generated public export; raw runs remain unchanged")
    args = parser.parse_args()
    if args.output.exists() and not args.refresh:
        raise RuntimeError("Public export already exists; use an explicit refresh or new output path")
    args.output.mkdir(parents=True, exist_ok=True)
    code_rows, code_groups = coding(args.source, args.output)
    question_rows, question_groups = predictions(args.source, args.output)
    cost_record, source_record = costs(args.source), sources()
    checks = [read_json(path) for path in sorted((args.source / "source-checks").glob("*.json"))]
    result = {"recorded_at": utc_now(), "author": "Ajnas N B", "coding": code_groups,
        "coding_totals": summary(code_rows), "prediction": question_groups,
        "coding_runs": [{key: row.get(key) for key in (
            "engine", "batch", "task", "condition", "arm", "run_id", "termination", "task_completed",
            "tests_run", "note_read", "candidate_sha256", "evidence_directory")} for row in code_rows],
        "prediction_runs": question_rows, "sources": source_record, "upstream_selected_tests": checks,
        "costs": {key: cost_record[key] for key in (
            "reported_usage_requests", "request_files", "observed_reference_estimate_usd",
            "unreported_reference_reservations_usd", "observed_plus_uncertain_reservations_usd", "within_cap")},
        "limitations": [
            "Three primary 24-row schedules were budget-limited; native prompts/loop overhead differ",
            "Codex continuation is separately labeled after transport correction, and original timeouts are retained",
            "Aider/Goose are three-original-task compatibility smokes, not matched-arm benchmarks",
            "Aider had three failed integration attempts and one corrected three-task retry",
            "No access violation observed; no claim of method/harness superiority, full-codebase audit or safety",
            "Original archived MUCOCO failures remain separate from today's current-model answers",
            "Not every open-source coding harness, and Claude Code commercial CLI was not included in this new open-source batch",
            "Credentials stayed on the Azure CLI controller; agents received disposable proxy capabilities",
            "Source clones retained, official release binaries/pinned SDK used; Codex Rust/OpenCode full builds not performed",
        ]}
    write_json(args.output / "summary.json", result)
    write_json(args.output / "costs.json", cost_record)
    write_json(args.output / "sources.json", source_record)
    write_json(ROOT / "reports/open-harness-results-v1.json", result)
    write_json(ROOT / "reports/open-harness-costs-v1.json", cost_record)
    write_json(ROOT / "datasets/open-harness-sources-v1.json", source_record)
    for name in ("open-harness-ordinary-v1.json", "open-harness-post-transport-v1.json",
                 "aider-model-identity-correction-v1.json", "remaining-paper-questions-v1.json"):
        write_json(args.output / "protocols" / name, read_json(ROOT / "protocols" / name))
    write_json(args.output / "manifest.json", {
        "recorded_at": utc_now(), "files": {path.relative_to(args.output).as_posix(): digest(path.read_bytes())
            for path in sorted(args.output.rglob("*")) if path.is_file() and path.name != "manifest.json"},
        "export": "Exact synthetic code and context, observations, expected checks, prompts, answer values, "
                  "aggregate metadata and hashes. Raw requests/responses, reasoning, profiles and credentials excluded.",
        "unchanged_private_raw_runs": True, "line_endings": "Publication JSON is LF; candidate/input bytes unchanged",
    })
    print(json.dumps({"coding": code_groups, "prediction": question_groups, "costs": result["costs"]}, indent=2))


if __name__ == "__main__":
    main()
