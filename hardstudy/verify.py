"""Verify all public saved evidence without Azure, Docker, or candidate execution."""
import argparse
import ast
from pathlib import Path

from erp.evaluate import cases as erp_cases
from hardstudy.catalog import TASKS, cases
from hardstudy.judge import score as score_hard
from hardstudy.paper_score import score_answer
from hardstudy.structure import inspect
from hardstudy.summarize import ASSESSMENT_FIELDS, behavior_status, context_comparisons, totals
from research.io import ROOT, digest, read_json
from research.scoring import score_erp


def verify(evidence):
    evidence = Path(evidence).resolve()
    manifest = read_json(evidence / "manifest.json")
    actual = {path.relative_to(evidence).as_posix() for path in evidence.rglob("*")
              if path.is_file() and path.name != "manifest.json"}
    if actual != set(manifest["files"]):
        raise RuntimeError("Evidence file inventory differs from its manifest")
    for filename, expected in manifest["files"].items():
        path = (evidence / filename).resolve()
        if not path.is_relative_to(evidence) or digest(path.read_bytes()) != expected:
            raise RuntimeError("Evidence byte hash differs: " + filename)
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"))
    report = read_json(evidence / "summary.json")
    protocol = read_json(evidence / "protocols/hard-vague-context-v1.json")
    rows = report["coding_runs"]
    if len(rows) != len(protocol["schedule"]):
        raise RuntimeError("Scheduled outcomes were removed")
    erp_data = read_json(evidence / "erp-fixture.json")
    for row, scheduled in zip(rows, protocol["schedule"]):
        if any(row[key] != value for key, value in scheduled.items()):
            raise RuntimeError("Model/task/context schedule changed")
        if "assessment" not in row:
            if row["termination"] != "not_run_budget" or row["task_completed"]:
                raise RuntimeError("An unrun task was counted as a completed refactor")
            continue
        directory = evidence / row["evidence_directory"]
        if row != read_json(directory / "run.json"):
            raise RuntimeError("Summary and candidate receipt disagree")
        receipt = read_json(directory / "input.json")
        before, after = {}, {}
        for filename in receipt["editable"]:
            first, second = (directory / "initial" / filename).read_bytes(), (directory / "candidate" / filename).read_bytes()
            if digest(first) != receipt["files"][filename] or digest(second) != row["candidate_hashes"][filename]:
                raise RuntimeError("Initial/candidate source bytes differ from their receipt")
            before[filename], after[filename] = first.decode("utf-8"), second.decode("utf-8")
        structure = inspect(before, after)
        if structure != row["structure"] or (before != after) != row["changed"]:
            raise RuntimeError("Source-structure completion does not replay")
        for filename, expected in receipt["files"].items():
            if filename not in receipt["editable"] and digest(
                    (directory / "ordinary-project" / filename).read_bytes()) != expected:
                raise RuntimeError("Read-only ordinary project file differs")
        expected_complete = (row["termination"] == "completed" and structure["executable_changed"]
                             and structure["public_api_preserved"] and row["tests_run"] and row["context_unchanged"])
        if row["task_completed"] != expected_complete:
            raise RuntimeError("Incomplete/no-edit output was labeled completed")
        saved = read_json(directory / "observations.json")
        score = score_erp(erp_cases(data=erp_data), saved) if row["task"] == "erp-invoices" else score_hard(
            row["task"], cases(row["task"]), saved)
        if any(score[key] != row["assessment"][key] for key in ASSESSMENT_FIELDS):
            raise RuntimeError("Saved checks do not reproduce the declared judge outcome")
        if score["checks"] != read_json(directory / "checks.json") or behavior_status(score) != row["behavior_status"]:
            raise RuntimeError("Detailed verdict table differs from independent replay")
    if totals(rows) != report["totals"] or context_comparisons(rows) != report["equal_attempt_context_comparisons"]:
        raise RuntimeError("Completion/test/comparison denominators differ")
    for model, declared in report["by_model"].items():
        if totals([row for row in rows if row["model_id"] == model]) != declared:
            raise RuntimeError("Per-model denominators differ")
    if {row["task"] for row in report["catalog"]} != set(TASKS):
        raise RuntimeError("Task catalog is incomplete")
    paper_protocol = read_json(evidence / "protocols/hard-paper-models-v1.json")
    paper_rows = report["paper"]["rows"]
    if len(paper_rows) != len(paper_protocol["schedule"]):
        raise RuntimeError("Paper question schedule differs")
    for row, scheduled in zip(paper_rows, paper_protocol["schedule"]):
        if any(row[key] != value for key, value in scheduled.items()):
            raise RuntimeError("Paper question/model pair changed")
        saved = read_json(evidence / row["evidence_directory"] / "question-and-answer.json")
        if saved != row:
            raise RuntimeError("Paper answer and summary differ")
        expected = score_answer(row["text"], row["question"]["expected"], row["provider_status"], row["termination"])
        if any(row[key] != value for key, value in expected.items()):
            raise RuntimeError("Paper final-value/refusal classification differs")
    if (sum(row["answer_status"] == "ANSWERED" for row in paper_rows),
        sum(row["correct"] is True for row in paper_rows),
        sum(row["answer_status"] == "REFUSAL" for row in paper_rows)) != (
            report["paper"]["answered"], report["paper"]["correct"], report["paper"]["refusals"]):
        raise RuntimeError("Paper answer denominator differs")
    cost = read_json(evidence / "costs.json")
    observed = uncertain = attempts = requests = 0
    for stage in cost["stages"].values():
        metadata = stage["provider_metadata"]
        attempts += len(metadata)
        requests += sum(bool(row.get("usage")) for row in metadata)
        reported = sum(row["reference_cost_usd"] for row in metadata if row.get("usage"))
        reserved = sum(row.get("reference_cost_usd", row.get("reference_reservation_usd", 0)) for row in metadata
                       if not row.get("usage") and row.get("http_status") not in (429, 400, 403, 404))
        if abs(reported - stage["reported_reference_usd"]) > 1e-9 or abs(
                reserved - stage["uncertain_reference_reservations_usd"]) > 1e-9:
            raise RuntimeError("Reported provider costs were combined incorrectly")
        observed += reported
        uncertain += reserved
    if (attempts, requests) != (cost["http_attempts"], cost["reported_usage_requests"]) or abs(
            observed + uncertain - cost["reported_plus_uncertainty_usd"]) > 1e-9:
        raise RuntimeError("Provider cost totals do not reconcile")
    if not cost["within_cap"] or observed + uncertain > cost["overall_reference_ceiling_usd"]:
        raise RuntimeError("Cost exceeded the disclosed reference ceiling")
    reproduction = read_json(evidence / "reproduction.json")
    for recorded in reproduction["reproductions"]:
        original = next(row for row in rows if row.get("run_id") == recorded["run_id"])
        if any(original["assessment"][key] != recorded["replay"][key] for key in ASSESSMENT_FIELDS):
            raise RuntimeError("Reexecuted failure differs from original saved verdict")
        if recorded["baseline"]["passed"] != recorded["baseline"]["total"]:
            raise RuntimeError("Failure reference did not pass its baseline")
    before = read_json(evidence / "preflight-date-before.json")
    fixed = read_json(evidence / "preflight-clock-fixed.json")
    if before["total"] != fixed["total"] or fixed["passed"] != fixed["total"]:
        raise RuntimeError("Clock correction did not restore the same reference challenge set")
    controls = read_json(evidence / "reference-controls.json")
    if not controls["passed"] or controls["seeded_faults_rejected"] != 24 or controls["azure_calls"] != 0:
        raise RuntimeError("Checker controls differ")
    print(f"Verified {len(manifest['files'])} evidence hashes; {len(rows)} schedule records; "
          f"{report['totals']['retained_candidate_bundles']} saved bundles; {report['totals']['completed_refactors']} completed.")
    print(f"Replayed {report['totals']['saved_output_passed']}/{report['totals']['saved_output_checks']} checks, "
          f"{report['totals']['access_failing_checks']} access failures, {report['totals']['access_unknown_checks']} unknown access checks.")
    print(f"Paper: {report['paper']['correct']}/{report['paper']['answered']} answered correctly; "
          f"{report['paper']['refusals']} refusals. No Azure, Docker, or generated-program execution.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence/hard-vague-context-v1")
    verify(parser.parse_args().evidence)
