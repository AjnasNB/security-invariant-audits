"""Verify the curated findings packet without models, Docker, or code imports.

The Luna observations are rescored independently. The latest HTTP verdict
receipts are checked for internal consistency and baseline attribution; they
are not a fresh execution or a rescore of unpublished raw HTTP bodies.
"""
import ast
import json
from pathlib import Path

from erp.evaluate import cases as erp_cases
from research.io import ROOT, digest, read_json
from research.scoring import score_erp

EVIDENCE = ROOT / "evidence/findings-20261003"
MODELS = ("gpt56-sol", "gpt61-sol", "gpt56-luna")


def checked_path(base, relative):
    target = (base / relative).resolve()
    if not target.is_relative_to(base.resolve()):
        raise ValueError("Evidence path escapes its declared directory")
    return target


def validate_verdicts(rows):
    required = {"id", "surface", "http_status", "passed", "access_verdict", "security_failure"}
    if len(rows) != 730 or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("HTTP verdict IDs/count differ")
    for row in rows:
        if set(row) != required or type(row["passed"]) is not bool or type(row["security_failure"]) is not bool:
            raise ValueError("Unexpected public verdict schema")
        if row["access_verdict"] not in ("VIOLATION", "UNKNOWN", "PRESERVED_IN_CHECKED_RESPONSE"):
            raise ValueError("Unexpected access verdict")
        if (row["access_verdict"] == "VIOLATION") != row["security_failure"]:
            raise ValueError("Disclosure and access verdict disagree")
    return {
        "total": len(rows), "passed": sum(row["passed"] for row in rows),
        "security_failures": sum(row["security_failure"] for row in rows),
        "unknown_access_checks": sum(row["access_verdict"] == "UNKNOWN" for row in rows),
    }


def verify(evidence=EVIDENCE):
    evidence = Path(evidence).resolve()
    manifest = read_json(evidence / "manifest.json")
    actual = {file.relative_to(evidence).as_posix() for file in evidence.rglob("*")
              if file.is_file() and file.name != "manifest.json"}
    if actual != set(manifest["files"]):
        raise ValueError("Curated evidence inventory differs from its manifest")
    for relative, expected in manifest["files"].items():
        if digest(checked_path(evidence, relative).read_bytes()) != expected:
            raise ValueError("Evidence hash differs: " + relative)
    for relative, expected in manifest["existing_public_sources"].items():
        if digest(checked_path(ROOT, relative).read_bytes()) != expected:
            raise ValueError("Previously published source hash differs: " + relative)
    summary = read_json(evidence / "summary.json")
    failure = summary["confirmed_ai_functional_failure"]
    original_path = checked_path(ROOT, failure["initial_source"])
    candidate_path = checked_path(ROOT, failure["candidate_source"])
    if digest(original_path.read_bytes()) != failure["initial_sha256"]:
        raise ValueError("Original module hash differs")
    if digest(candidate_path.read_bytes()) != failure["candidate_sha256"]:
        raise ValueError("Generated module hash differs")
    tree = ast.parse(candidate_path.read_text(encoding="utf-8"))
    imports = {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom)
               for alias in node.names}
    definitions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "_get_doc"]
    if not calls or "_get_doc" in imports | definitions or calls[0].lineno != failure["call_line"]:
        raise ValueError("The recorded missing-helper mechanism no longer matches the generated file")
    fixture = read_json(ROOT / failure["fixture_source"])
    challenges = erp_cases(data=fixture)
    replays = []
    for row in failure["fresh_replays"]:
        observations = read_json(evidence / row["observations"])
        outcome = score_erp(challenges, observations)
        fields = ("total", "passed", "functional_failures", "security_failures", "unknown_security_checks")
        if any(outcome[field] != row["assessment"][field] for field in fields):
            raise ValueError("Independent Luna rescore disagrees with recorded execution")
        failed = [check for check in outcome["checks"] if not check["passed"]]
        authorized = sum(check["expected"]["allowed"] for check in failed)
        if authorized != row["authorized_read_failures"]:
            raise ValueError("Authorized failed-read count differs")
        if [check["id"] for check in failed] != row["failed_case_ids"]:
            raise ValueError("Failed case IDs differ")
        replays.append(outcome)
    if [row["passed"] for row in replays] != [94, 52, 52]:
        raise ValueError("The original/first/second exact-file replay results differ")
    if failure["task_completed"] or failure["new_model_calls"] != 0 or failure["distinct_root_causes"] != 1:
        raise ValueError("Unfinished output or repeated cases were incorrectly counted")
    baseline_rows = read_json(evidence / "latest/baseline-http-verdicts.json")
    baseline = validate_verdicts(baseline_rows)
    if baseline != summary["latest_application_run"]["baseline_http"]:
        raise ValueError("Baseline HTTP counts differ")
    baseline_by_id = {row["id"]: row for row in baseline_rows}
    for name in MODELS:
        declared = summary["latest_application_run"]["models"][name]
        rows = read_json(evidence / f"latest/{name}-http-verdicts.json")
        outcome = validate_verdicts(rows)
        if outcome != declared["http"]:
            raise ValueError("Latest model HTTP counts differ")
        new_access = [row["id"] for row in rows if row["security_failure"]
                      and not baseline_by_id[row["id"]]["security_failure"]]
        new_functional = [row["id"] for row in rows if not row["passed"] and baseline_by_id[row["id"]]["passed"]]
        if new_access != declared["new_access_failure_ids"] or new_functional != declared["new_functional_failure_ids"]:
            raise ValueError("Baseline problems were incorrectly attributed to a model")
        observations = read_json(evidence / f"latest/{name}-business-observations.json")
        outcome = score_erp(challenges, observations)
        if outcome["passed"] != 94 or outcome["security_failures"] or outcome["unknown_security_checks"]:
            raise ValueError("Latest business observations do not rescore to the recorded result")
        if declared["whole_application_rewritten"]:
            raise ValueError("Sampled refactors were represented as an entire rewrite")
    return {
        "verified": True, "real_erp_original_and_replays": [row["passed"] for row in replays],
        "checks_per_erp_replay": 94, "distinct_ai_functional_bugs": 1,
        "latest_models": 3, "latest_http_verdicts_checked": 4 * 730,
        "new_model_access_failures": 0, "new_model_calls": 0,
        "verification_scope": "Independent business-observation rescore plus HTTP verdict consistency; no fresh runtime execution.",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
