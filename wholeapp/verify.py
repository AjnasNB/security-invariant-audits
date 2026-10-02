"""Offline public replay: no Docker, Azure, private site or candidate imports."""
import argparse
import ast
import os
from pathlib import Path

from research.io import ROOT, read_json, digest
from wholeapp.judge import assess_saved

FIELDS = ("total", "passed", "functional_failures", "security_failures", "unknown_access_checks", "invariant_preserved")


def verify(evidence):
    evidence = Path(evidence).resolve()
    if os.name == "nt" and not str(evidence).startswith("\\\\?\\"):
        evidence = Path("\\\\?\\" + str(evidence))
    manifest = read_json(evidence / "manifest.json")
    actual = {path.relative_to(evidence).as_posix() for path in evidence.rglob("*")
              if path.is_file() and path.name != "manifest.json"}
    if actual != set(manifest["files"]):
        raise RuntimeError("Evidence inventory changed")
    for filename, expected in manifest["files"].items():
        path = (evidence / filename).resolve()
        if not path.is_relative_to(evidence) or digest(path.read_bytes()) != expected:
            raise RuntimeError("Evidence byte hash differs: " + filename)
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"))
    fixture = read_json(evidence / "fixture.json")
    report = read_json(evidence / "summary.json")
    replayed = {}
    for response_file in evidence.rglob("responses.json"):
        directory = response_file.parent
        challenges = read_json(directory / "cases.json")
        responses = read_json(response_file)
        for row in responses:
            if digest(row["body"]) != row["public_body_sha256"]:
                raise RuntimeError("Redacted response-body hash differs")
        outcome = assess_saved(challenges, responses, fixture)
        declared = read_json(directory / "assessment.json")
        if outcome != declared:
            raise RuntimeError("Independent HTTP scoring does not replay exactly")
        replayed[directory.relative_to(evidence).as_posix()] = outcome
    baseline = replayed["baseline"]
    hardening = replayed["hardening/http"]
    if any(report["baseline"][key] != baseline[key] for key in FIELDS) or any(
            report["hardening"][key] != hardening[key] for key in FIELDS):
        raise RuntimeError("Baseline/hardening denominator differs")
    baseline_failures = {row["id"] for row in baseline["checks"] if row["security_failure"]}
    if len(baseline_failures) != report["baseline_print_conflict"]["failing_responses"]:
        raise RuntimeError("Pre-existing policy-conflict count differs")
    new_regressions = 0
    for row in report["model_runs"]:
        directory = evidence / row["evidence_directory"]
        receipt = read_json(directory / "run.json")
        if receipt != row:
            raise RuntimeError("Model receipt differs from summary")
        assessed = replayed[row["evidence_directory"] + "/http"]
        if any(assessed[key] != row["http"][key] for key in FIELDS):
            raise RuntimeError("Model retained response counts differ")
        failures = {check["id"] for check in assessed["checks"] if check["security_failure"]}
        if sorted(failures - baseline_failures) != row["new_access_failure_ids"]:
            raise RuntimeError("Pre-existing failures were incorrectly relabeled model regressions")
        new_regressions += bool(failures - baseline_failures)
        if row["whole_application_rewrite_completed"]:
            raise RuntimeError("A partial attempt is incorrectly labeled a full rewrite")
        for change in row["changed_files"]:
            source = directory / "initial" / change["path"]
            candidate = directory / "candidate" / change["path"]
            if digest(source.read_bytes()) != change["before_sha256"] or digest(candidate.read_bytes()) != change["after_sha256"]:
                raise RuntimeError("Changed source bytes differ")
    if new_regressions != report["new_model_access_regressions"]:
        raise RuntimeError("New access regression total differs")
    inventory = read_json(evidence / "starting-source-inventory.json")
    if len(inventory) != report["full_source_tracked_files"]:
        raise RuntimeError("Full starting source inventory differs")
    controls = read_json(evidence / "controls/summary.json")
    if not controls["passed"] or controls["azure_calls"] != 0:
        raise RuntimeError("Control result differs")
    for control in controls["controls"]:
        replay = replayed["controls/" + control["control"]]
        if replay["security_failures"] != control["security_failures"] or not control["seeded_not_model_finding"]:
            raise RuntimeError("Seeded judge-control findings differ")
    helpers = read_json(evidence / "changed-helper-checks.json")
    for group in helpers["results"]:
        if group["passed"] != all(row["passed"] for row in group["checks"]):
            raise RuntimeError("Changed-helper verdict differs")
        if any(row["passed"] != (row["original_sha256"] == row["candidate_sha256"]) for row in group["checks"]):
            raise RuntimeError("Changed-helper output comparison differs")
    for label, declared in report["business"].items():
        recorded = read_json(evidence / "business" / (label + ".json"))["assessment"]
        if any(recorded[key] != declared[key] for key in declared):
            raise RuntimeError("Business contract total differs")
        if len(recorded["checks"]) != recorded["total"] or sum(check["passed"] for check in recorded["checks"]) != recorded["passed"]:
            raise RuntimeError("Business check rows do not reconcile")
    cost = read_json(evidence / "costs.json")
    observed = sum(row.get("reference_cost_usd", 0) for stage in cost["stages"].values()
                   for row in stage["provider_metadata"] if row.get("usage"))
    uncertain = sum(row.get("reference_cost_usd", 0) for stage in cost["stages"].values()
                    for row in stage["provider_metadata"] if not row.get("usage") and row.get("http_status") not in (400, 403, 404, 429))
    if abs(observed - cost["reported_reference_usd"]) > 1e-9 or abs(
            uncertain - cost["uncertain_reservations_usd"]) > 1e-9 or not cost["within_cap"]:
        raise RuntimeError("Reported usage and uncertain reserves differ")
    if observed + uncertain > cost["frozen_reference_ceiling_usd"]:
        raise RuntimeError("Reported reference ceiling exceeded")
    if report["whole_application_rewrite_completed"]:
        raise RuntimeError("Whole application was not rewritten")
    total = sum(row["total"] for row in replayed.values())
    print(f"Verified {len(manifest['files'])} public hashes; {len(inventory)} starting source paths; "
          f"{len(report['model_runs'])} retained model attempts.")
    print(f"Replayed {total} HTTP checks; original {baseline['passed']}/{baseline['total']}; "
          f"hardening {hardening['passed']}/{hardening['total']}; new model access regressions {new_regressions}.")
    print("No Azure, Docker, credentials, private site or generated-code execution. Full rewrite remains incomplete.")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence/wholeapp-v1")
    verify(parser.parse_args().evidence)
