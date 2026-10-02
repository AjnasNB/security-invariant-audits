"""Seal a safe public export of existing runs. No paid calls or code execution."""
import argparse
import copy
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from erp.evaluate import cases as erp_cases, seed
from hardstudy.catalog import TASKS, VAGUE_PROMPTS, cases, parts, prepare
from hardstudy.context import upstream_manifest
from hardstudy.judge import score as score_hard
from hardstudy.paper_score import score_answer
from hardstudy.structure import inspect
from hardstudy.summarize import ASSESSMENT_FIELDS, behavior_status, context_comparisons, totals
from research.io import ROOT, digest, read_json, utc_now, write_json
from research.scoring import score_erp

PRICING_SOURCES = [
    "https://developers.openai.com/api/docs/models/gpt-5.6-sol",
    "https://developers.openai.com/api/docs/models/gpt-5.6-luna",
    "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
    "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
    "https://platform.claude.com/docs/en/about-claude/models/overview",
    "https://platform.claude.com/docs/en/about-claude/pricing",
]


def provider_metadata(directory):
    records = []
    for path in sorted(directory.glob("provider-*-metadata.json")):
        row = read_json(path)
        request = path.with_name(path.name.replace("-metadata.json", "-request.json"))
        response = path.with_name(path.name.replace("-metadata.json", "-response.sse"))
        if not request.exists() or not response.exists():
            raise RuntimeError("A retained request/response is missing")
        # request_sha256 in v1 is the exact compact transmitted JSON, not its
        # pretty-printed disk encoding.
        compact = json.dumps(read_json(request), separators=(",", ":"), ensure_ascii=False)
        if row.get("request_sha256") and digest(compact) != row["request_sha256"]:
            raise RuntimeError("The compact transmitted request hash changed")
        if row.get("response_sha256") and digest(response.read_bytes()) != row["response_sha256"]:
            raise RuntimeError("Retained provider response changed")
        records.append({**row, "request_file_sha256": digest(request.read_bytes()),
                        "raw_response_excluded": True, "raw_request_excluded": True})
    return records


def observations(row):
    assessment = row["assessment"]
    if row["task"] != "erp-invoices":
        return assessment["case_observations"]
    return [{"id": check["id"], "value": check["observed"]} for check in assessment["checks"]]


def publish_candidate(source, destination, original, erp_data):
    if "assessment" not in original:
        return copy.deepcopy(original)
    local = source / original["run_id"]
    target = destination / "coding" / original["run_id"]
    target.mkdir(parents=True, exist_ok=False)
    row = {key: value for key, value in original.items() if key != "answer"}
    initial, candidate = read_json(local / "initial-source.json"), read_json(local / "candidate-source.json")
    for kind, files in (("initial", initial), ("candidate", candidate)):
        for filename, code in files.items():
            path = target / kind / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            body = code.encode("utf-8")
            if kind == "candidate" and digest(body) != original["candidate_hashes"][filename]:
                raise RuntimeError("Generated code differs from the sealed candidate")
            if kind == "initial" and digest(body) != read_json(local / "input.json")["files"][filename]:
                raise RuntimeError("Starting code differs from the input receipt")
            path.write_bytes(body)
    receipt = read_json(local / "input.json")
    for filename, expected in receipt["files"].items():
        if filename in receipt["editable"]:
            continue
        body = (local / "workspace" / filename).read_bytes()
        if digest(body) != expected:
            raise RuntimeError("An ordinary read-only project file was changed")
        path = target / "ordinary-project" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    context = (local / "context.txt").read_bytes()
    if digest(context) != original["context_sha256"]:
        raise RuntimeError("Initial large-context bytes were changed")
    write_json(target / "input.json", receipt)
    saved = observations(original)
    recalculated = score_erp(erp_cases(data=erp_data), saved) if original["task"] == "erp-invoices" else score_hard(
        original["task"], cases(original["task"]), saved)
    if any(recalculated[key] != original["assessment"][key] for key in ASSESSMENT_FIELDS):
        raise RuntimeError("Independent saved observations do not replay to the recorded judge fields")
    row["assessment"] = {key: value for key, value in recalculated.items() if key not in ("checks", "case_observations")}
    row["behavior_status"] = behavior_status(row["assessment"])
    row["completion_status"] = "COMPLETED" if row["task_completed"] else "INCOMPLETE"
    row["access_status"] = "VIOLATION" if row["assessment"]["invariant_preserved"] is False else (
        "UNKNOWN" if row["assessment"]["invariant_preserved"] is None else "PRESERVED_IN_CHECKED_CASES")
    write_json(target / "observations.json", saved)
    write_json(target / "checks.json", recalculated["checks"])
    row["evidence_directory"] = target.relative_to(destination).as_posix()
    write_json(target / "run.json", row)
    if (local / "public-tests.json").exists():
        write_json(target / "public-tests.json", read_json(local / "public-tests.json"))
    metadata = provider_metadata(local)
    event_path = local / "events.json"
    events = read_json(event_path) if event_path.exists() else []
    tool_calls = [event["details"]["name"] for event in events
                  if event.get("text", "").startswith("Tool:") and isinstance(event.get("details"), dict)
                  and isinstance(event["details"].get("name"), str)]
    write_json(target / "provenance.json", {
        "provider_metadata": metadata, "raw_events_sha256": digest(event_path.read_bytes()) if event_path.exists() else None,
        "tool_calls": dict(Counter(tool_calls)), "initial_context_sha256": digest(context),
        "long_context_reconstruction": "Pinned upstream files and manifest plus current files; not artificial repeated padding",
        "excluded_whole_files": ["context.txt (licensed upstream source; reconstruct from pins)", "events.json",
                                "checkpoint.json", "provider requests/responses (including raw reasoning)"],
        "candidate_source_and_ordinary_project_bytes_preserved": True,
    })
    return row


def costs(stages, models):
    aggregates, all_records, stage_rows = {}, [], {}
    for name, directory in stages.items():
        raw = read_json(directory / "usage.json")
        if raw["pending_requests"]:
            raise RuntimeError("A provider request is still pending")
        metadata = [row for child in sorted(directory.iterdir()) if child.is_dir()
                    for row in provider_metadata(child)]
        if len(metadata) != raw["http_attempts"]:
            raise RuntimeError("Request attempt denominator does not reconcile")
        reported = sum(row["reference_cost_usd"] for row in metadata if row.get("usage"))
        uncertain = sum(row.get("reference_cost_usd", row.get("reference_reservation_usd", 0))
                        for row in metadata if not row.get("usage") and row.get("http_status") not in (429, 400, 403, 404))
        if abs(reported + uncertain - raw["reference_estimate_usd"]) > 1e-8:
            raise RuntimeError("Reported costs and retained uncertainty do not reconcile")
        for model in models:
            selected = [row for row in metadata if row["model_id"] == model["id"]]
            merged = aggregates.setdefault(model["id"], Counter())
            for row in selected:
                merged["attempts"] += 1
                if not row.get("usage"):
                    continue
                usage = row["usage"]
                messages = model["protocol"] == "messages"
                cache = usage.get("cache_read_input_tokens", 0) if messages else usage.get("input_tokens_details", {}).get("cached_tokens", 0)
                written = usage.get("cache_creation_input_tokens", 0) if messages else usage.get("input_tokens_details", {}).get("cache_write_tokens", 0)
                inputs = usage.get("input_tokens", 0) + (cache + written if messages else 0)
                output = usage.get("output_tokens", 0)
                if min(inputs, output, cache, written) < 0 or cache + written > inputs:
                    raise RuntimeError("Invalid reported provider usage")
                factor = 2 if inputs > 272000 and not messages else 1
                expected = ((inputs - cache - written) * model["rates"]["input"] * factor
                            + cache * model["rates"]["cached"] * factor
                            + written * model["rates"]["write"] * factor
                            + output * model["rates"]["output"] * (1.5 if factor == 2 else 1)) / 1e6
                if abs(expected - row["reference_cost_usd"]) > 1e-10:
                    raise RuntimeError("Reference rate arithmetic differs from recorded cost")
                for key, value in {"requests": 1, "input_tokens": inputs, "output_tokens": output,
                                   "cached_tokens": cache, "cache_write_tokens": written,
                                   "reported_reference_usd": expected}.items():
                    merged[key] += value
            ledger = raw["per_model"].get(model["id"], {})
            if selected and sum(bool(row.get("usage")) for row in selected) != ledger.get("requests"):
                raise RuntimeError("Per-model request count differs from its usage ledger")
        stage_rows[name] = {"http_attempts": raw["http_attempts"], "reported_reference_usd": reported,
                            "uncertain_reference_reservations_usd": uncertain,
                            "reported_plus_uncertainty_usd": reported + uncertain,
                            "reference_cap_usd": raw["total_reference_cap_usd"],
                            "within_cap": reported + uncertain <= raw["total_reference_cap_usd"] + 1e-9,
                            "usage_file_sha256": digest((directory / "usage.json").read_bytes()),
                            "provider_metadata": metadata}
        all_records += [{**row, "stage": name} for row in metadata]
    reported = sum(stage["reported_reference_usd"] for stage in stage_rows.values())
    uncertain = sum(stage["uncertain_reference_reservations_usd"] for stage in stage_rows.values())
    old = read_json(ROOT / "reports/open-harness-costs-v1.json")
    return {"recorded_at": utc_now(), "currency": "USD", "stages": stage_rows,
            "per_model": {key: dict(value) for key, value in aggregates.items()},
            "http_attempts": sum(stage["http_attempts"] for stage in stage_rows.values()),
            "reported_usage_requests": sum(bool(row.get("usage")) for row in all_records),
            "reported_reference_usd": reported, "uncertain_reference_reservations_usd": uncertain,
            "reported_plus_uncertainty_usd": reported + uncertain, "overall_reference_ceiling_usd": 15,
            "within_cap": reported + uncertain <= 15 and all(stage["within_cap"] for stage in stage_rows.values()),
            "previous_reported_study_reference_usd": old["all_studies_observed_reference_estimate_usd"],
            "previous_uncertainty_reservations_usd": old["unreported_reference_reservations_usd"],
            "all_studies_reported_reference_usd": old["all_studies_observed_reference_estimate_usd"] + reported,
            "all_studies_with_identified_uncertainty_usd": old["all_studies_observed_reference_estimate_usd"]
                   + old["unreported_reference_reservations_usd"] + reported + uncertain,
            "rates_per_million": {model["id"]: model["rates"] for model in models},
            "official_pricing_pages": PRICING_SOURCES, "verified_date": "2026-10-02",
            "unreported_requests": [{key: row.get(key) for key in ("stage", "number", "model_id", "http_status",
                  "status", "reference_cost_usd", "reference_reservation_usd", "request_sha256", "response_sha256")}
                for row in all_records if not row.get("usage")],
            "scope": "Public reference rates, not verified account-specific Azure invoices or credit. "
                     "Includes connection, failed/blocked attempts and the separate paper stage; excludes this Codex chat, "
                     "other Azure services, taxes and electricity. Historical uncertainty is not erased.",
            "local_infrastructure": "Existing local WSL/Docker ERP, no new paid cloud application resources provisioned"}


def paper(source, destination, specification):
    results = read_json(source / "results.json")["results"]
    if len(results) != len(specification["schedule"]):
        raise RuntimeError("Paper schedule incomplete")
    questions = {row["id"]: row for row in specification["questions"]}
    published = []
    for row, scheduled in zip(results, specification["schedule"]):
        if any(row[key] != value for key, value in scheduled.items()):
            raise RuntimeError("Paper schedule changed")
        local = source / row["run_id"]
        metadata = provider_metadata(local)
        statuses = [record.get("status") for record in metadata if record.get("status")]
        status = statuses[-1] if statuses else None
        question = questions[row["question_id"]]
        scored = {**row, "question": question, "provider_status": status,
                  **score_answer(row["text"], question["expected"], status, row["termination"])}
        target = destination / "paper" / row["run_id"]
        target.mkdir(parents=True, exist_ok=False)
        scored["evidence_directory"] = target.relative_to(destination).as_posix()
        write_json(target / "question-and-answer.json", scored)
        write_json(target / "provider-metadata.json", metadata)
        published.append(scored)
    grouped, comparisons = {}, []
    for model in specification["models"]:
        selected = [row for row in published if row["model_id"] == model["id"]]
        grouped[model["id"]] = {"scheduled": len(selected), "answered": sum(row["answer_status"] == "ANSWERED" for row in selected),
            "correct": sum(row["correct"] is True for row in selected), "refusals": sum(row["answer_status"] == "REFUSAL" for row in selected),
            "unknown": sum(row["answer_status"] == "UNKNOWN" for row in selected),
            "invalid": sum(row["answer_status"] == "INVALID_OUTPUT" for row in selected),
            "format_noncompliant_answered": sum(row["answer_status"] == "ANSWERED" and not row["literal_format_compliant"]
                                                for row in selected)}
        for task in sorted({question["task"] for question in questions.values()}):
            first = next(row for row in selected if row["question_id"] == task + ":original")
            second = next(row for row in selected if row["question_id"] == task + ":mutant")
            answered = first["answer_status"] == second["answer_status"] == "ANSWERED"
            comparisons.append({"model_id": model["id"], "task": task,
                "status": "ANSWERED_PAIR" if answered else "INCOMPLETE_PAIR",
                "original_status": first["answer_status"], "mutant_status": second["answer_status"],
                "paper_defined_inconsistency": first["correct"] and not second["correct"] if answered else None})
    return {"rows": published, "by_model": grouped, "comparisons": comparisons,
            "attempts": len(published), "answered": sum(row["answer_status"] == "ANSWERED" for row in published),
            "correct": sum(row["correct"] is True for row in published),
            "refusals": sum(row["answer_status"] == "REFUSAL" for row in published),
            "complete_original_mutant_pairs": sum(row["status"] == "ANSWERED_PAIR" for row in comparisons),
            "paper_defined_inconsistencies": sum(row["paper_defined_inconsistency"] is True for row in comparisons),
            "scope": "Archived known-positive selections, current model questions without expected answer; "
                     "refusals do not demonstrate incorrect reasoning or access leaks"}


def catalog(destination):
    result = []
    with tempfile.TemporaryDirectory(prefix="ajnas-hard-public-") as temporary:
        for task in TASKS:
            workspace = Path(temporary) / task
            record = prepare(workspace, task, "neutral")
            target = destination / "catalog" / task
            target.mkdir(parents=True, exist_ok=False)
            for path in workspace.rglob("*"):
                if path.is_file():
                    output = target / path.relative_to(workspace)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(path.read_bytes())
            family, variant = parts(task)
            result.append({"task": task, "family": family, "configuration": variant, "prompt": record["prompt"],
                           "independent_check_count": sum(len(row["args"][2]) for row in cases(task)),
                           "ordinary_check_count": sum(len(row["args"][2]) for row in cases(task, True)),
                           "evidence_directory": target.relative_to(destination).as_posix(),
                           "synthetic": True, "configurations_are_not_24_independent_applications": True})
    return result


def export(source, paper_source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    specification = read_json(source / "protocol.json")
    records = read_json(source / "results.json")["results"]
    if len(records) != len(specification["schedule"]):
        raise RuntimeError("Coding schedule has not finished")
    for row, expected in zip(records, specification["schedule"]):
        if any(row[key] != value for key, value in expected.items()):
            raise RuntimeError("Registered coding schedule differs from retained record")
    erp_data = seed()
    write_json(destination / "erp-fixture.json", erp_data)
    rows = [publish_candidate(source, destination, row, erp_data) for row in records]
    paper_spec = read_json(paper_source / "protocol.json")
    paper_results = paper(paper_source, destination, paper_spec)
    sources = upstream_manifest()
    for name, value in sources.items():
        value["version_or_tag"] = "v16.36.0" if name == "frappe" else "v16.37.0"
        dirty = subprocess.check_output(["git", "-C", str(ROOT / "_sources" / ("large-" + name)),
                                        "status", "--porcelain"], text=True).strip()
        value["clone_unchanged"] = not dirty
        if dirty:
            raise RuntimeError("Pinned source clone changed")
    task_catalog = catalog(destination)
    cost = costs({"connection": ROOT / "artifacts/private/hard-vague-connection-v1-fixed",
                  "coding": source, "paper": paper_source}, specification["models"])
    reproduction = read_json(ROOT / "artifacts/private/hard-vague-reproduction-v1.json")
    write_json(destination / "reproduction.json", reproduction)
    write_json(destination / "preflight-date-before.json",
               read_json(ROOT / "artifacts/private/hard-preflight-v1/assessment.json"))
    write_json(destination / "preflight-clock-fixed.json",
               read_json(ROOT / "artifacts/private/hard-preflight-v1/assessment-clock-fixed.json"))
    write_json(destination / "reference-controls.json", read_json(ROOT / "reports/hard-reference-controls-v1.json"))
    write_json(destination / "configuration.json", read_json(source / "configuration.json"))
    write_json(destination / "deployment-map.json", read_json(source / "deployment-map.json"))
    write_json(destination / "connection-results.json",
               read_json(ROOT / "artifacts/private/hard-vague-connection-v1-fixed/results.json"))
    for name, value in (("hard-vague-context-v1", specification), ("hard-paper-models-v1", paper_spec)):
        write_json(destination / "protocols" / (name + ".json"), value)
    result = {"recorded_at": utc_now(), "date": "2026-10-02", "author": "Ajnas N B", "agent": "Actual Delta Native",
              "totals": totals(rows), "by_model": {model["id"]: totals([row for row in rows if row["model_id"] == model["id"]])
                                                for model in specification["models"]},
              "by_task": {task: totals([row for row in rows if row["task"] == task]) for task in specification["live_pilot_tasks"]},
              "by_context": {context: totals([row for row in rows if row["context"] == context]) for context in ("short", "long")},
              "by_condition": {condition: totals([row for row in rows if row["condition"] == condition])
                               for condition in ("neutral", "stale")},
              "coding_runs": rows, "paper": paper_results, "sources": sources, "catalog": task_catalog,
              "equal_attempt_context_comparisons": context_comparisons(rows),
              "reproduction": {"count": len(reproduction["reproductions"]), "no_new_model_calls": True,
                  "baseline_passed": reproduction["passed"], "evidence": "reproduction.json"},
              "costs": {key: cost[key] for key in ("http_attempts", "reported_usage_requests", "reported_reference_usd",
                         "uncertain_reference_reservations_usd", "reported_plus_uncertainty_usd", "within_cap")},
              "protocol_deviations": [{
                  "field": "max_input_tokens_per_trajectory", "declared": 750000, "enforced_in_v1": False,
                  "observed_over_declared": [{"scheduled_index": row["scheduled_index"], "input_tokens": row["usage"]["input_tokens"]}
                                            for row in rows if row.get("usage", {}).get("input_tokens", 0) > 750000],
                  "disposition": "Retained and disclosed; future opt-in strict estimate guard is tested. Do not relabel v1.",
              }],
              "limitations": [
                  "72 planned records, not 72 completed model refactors; budgets prevented balanced completion",
                  "25 retained bundles include ten unchanged code bundles and three stopped before any provider request",
                  "24 synthetic configurations are six templates, not 24 independent applications; only two templates received paid coding runs",
                  "Full 8,925-file upstream project was acquired; long initial input used selected complete files, not the entire repository",
                  "Full project is read-only reference; only four fixture modules or one Frappe module were editable",
                  "One unfinished generated ERP behavior regression is reproducible; its 42 failures are not 42 independent vulnerabilities",
                  "No observed unauthorized access, with 42 security-unknown checks; not evidence of general safety",
                  "All nine completed refactors passed their checks; stopped/malformed/crashing files are not completed successes",
                  "Native generic permission instructions and restricted tools remain; this is not unrestricted stock-agent behavior",
                  "Opus 4.6 had no deployed route; Opus 5's coding trial stopped before edits and paper refusals are not wrong answers",
                  "No demonstrated mutation advantage or fresh MUCOCO original-correct/mutant-wrong answered pair",
                  "Pricing is a reference estimate and identified reserves, not invoice, remaining Azure credit or a hard billing guarantee",
                  "The per-trajectory input-token ceiling was declared but not enforced in v1; one run exceeded it",
                  "Container/rollback restrictions are not a proof against hostile candidate introspection or every side effect",
              ]}
    for filename, value in (("summary.json", result), ("costs.json", cost), ("sources.json", sources)):
        write_json(destination / filename, value)
    write_json(ROOT / "reports/hard-vague-results-v1.json", result)
    write_json(ROOT / "reports/hard-vague-costs-v1.json", cost)
    write_json(ROOT / "datasets/hard-task-catalog-v1.json", task_catalog)
    write_json(ROOT / "datasets/large-erp-sources-v1.json", sources)
    write_json(destination / "manifest.json", {
        "recorded_at": utc_now(), "files": {path.relative_to(destination).as_posix(): digest(path.read_bytes())
              for path in sorted(destination.rglob("*")) if path.is_file() and path.name != "manifest.json"},
        "unchanged_private_raw_runs": True,
        "export_scope": "Exact initial/candidate code, ordinary files, inputs, independent observations, checks, "
                        "all planned row outcomes, reported usage and hashes. No credentials/raw model reasoning.",
        "upstream_terms": "Frappe candidate/input modules retain MIT notices; ERPNext GPL context is reconstructed "
                          "from pinned official sources and hashes, not relicensed or bundled as Ajnas original work",
    })
    print(json.dumps({"totals": result["totals"], "paper": {key: paper_results[key] for key in
          ("attempts", "answered", "correct", "refusals", "paper_defined_inconsistencies")}, "costs": result["costs"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "artifacts/private/hard-vague-context-v1")
    parser.add_argument("--paper-source", type=Path, default=ROOT / "artifacts/private/hard-paper-models-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/hard-vague-context-v1")
    args = parser.parse_args()
    export(args.source, args.paper_source, args.output)
