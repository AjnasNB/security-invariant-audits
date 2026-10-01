"""Public saved-evidence verification: no Azure, Docker or candidate execution."""
import argparse
import ast
from collections import Counter
from pathlib import Path

from research.cases import fixture_cases
from research.io import ROOT, digest, read_json
from research.scoring import score_fixture, same_value

FIELDS = ("status", "total", "passed", "functional_failures", "security_failures",
          "invalid_outputs", "unknown_security_checks", "invariant_preserved")


def verify(evidence):
    evidence = Path(evidence).resolve()
    manifest = read_json(evidence / "manifest.json")
    for filename, expected in manifest["files"].items():
        path = (evidence / filename).resolve()
        if not path.is_relative_to(evidence) or not path.is_file() or digest(path.read_bytes()) != expected:
            raise RuntimeError("Open-harness manifest mismatch: " + filename)
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"))
    report = read_json(evidence / "summary.json")
    total = Counter()
    grouped = {}
    for item in report["coding_runs"]:
        directory = evidence / item["evidence_directory"]
        row = read_json(directory / "run.json")
        for name, key in (("input.py", "source_sha256"), ("candidate.py", "candidate_sha256")):
            if digest((directory / name).read_bytes()) != row[key]:
                raise RuntimeError("Candidate/input byte hash mismatch")
        score = score_fixture(row["task"], fixture_cases(row["task"]),
                              read_json(directory / "observations.json"))
        if any(score[key] != row["assessment"][key] for key in FIELDS):
            raise RuntimeError("Saved access checks do not replay to the published verdict")
        total["files"] += 1
        total["checks"] += score["total"]
        total["passed"] += score["passed"]
        total["completed"] += row["task_completed"]
        total["completed_checks"] += score["total"] if row["task_completed"] else 0
        engine = grouped.setdefault(row["engine"], Counter())
        engine["files"] += 1
        engine["completed"] += row["task_completed"]
        engine["checks"] += score["total"]
    expected = report["coding_totals"]
    if (total["files"], total["completed"], total["checks"], total["passed"], total["completed_checks"]) != (
        expected["retained_files"], expected["completed_refactors"], expected["all_file_checks"],
        expected["all_file_passed"], expected["completed_refactor_checks"],
    ):
        raise RuntimeError("Open-harness coding denominators do not reconcile")
    for name, row in grouped.items():
        declared = report["coding"][name]
        if (row["files"], row["completed"], row["checks"]) != (
                declared["retained_files"], declared["completed_refactors"], declared["all_file_checks"]):
            raise RuntimeError("Per-agent counts do not reconcile")
    answers = {}
    for item in report["prediction_runs"]:
        row = read_json(evidence / item["evidence_directory"] / "question.json")
        if row["status"] == "assessed":
            key = (row["engine"], row["id"])
            if key in answers:
                raise RuntimeError("Answered question duplicated")
            value = ast.literal_eval(row["text"])
            if same_value(value, row["expected"]) != row["correct"]:
                raise RuntimeError("Paper prediction verdict does not replay")
            answers[key] = row["correct"]
        elif row["correct"] is not None:
            raise RuntimeError("Unanswered question must have unknown correctness")
    costs = read_json(evidence / "costs.json")
    if not costs["within_cap"] or costs["observed_plus_uncertain_reservations_usd"] > costs["total_reference_cap_usd"]:
        raise RuntimeError("Published cost exceeds the frozen total cap")
    print(f"Verified {len(manifest['files'])} files; {total['files']} saved coding outputs; "
          f"{total['completed']} completed refactors.")
    print(f"Replayed {total['passed']}/{total['checks']} checks; {len(answers)} answered paper questions "
          f"({sum(answers.values())} correct). No Azure or generated-program execution.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence/open-harness-ordinary-v1")
    verify(parser.parse_args().evidence)
