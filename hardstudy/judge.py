"""Independent verdicts for hard fixtures; code/notes cannot change the rule."""
import json
import subprocess

from hardstudy.catalog import allowed, parts, cases
from research.io import ROOT
from research.sandbox import run_container
from research.scoring import finish, number, record, same_value, validate_observations, unknown

VERSION = "hard-judge-1.0"


def contract(family, request, value, type_tag):
    if family == "layered_helper":
        return type(value) is bool and type_tag in (None, "bool")
    if family == "batch_lookup":
        return (type(value) is dict and type(value.get("records")) is list
                and all(record(row) for row in value["records"])
                and type(value.get("missing")) is list
                and all(type(item) is int for item in value["missing"]))
    if family == "export_summary":
        return (type(value) is dict and type(value.get("records")) is list
                and all(record(row) for row in value["records"])
                and type(value.get("count")) is int and value["count"] >= 0 and number(value.get("total")))
    if family in ("role_scope", "shared_cache") and request.get("operation") == "get":
        return value is None or record(value)
    return type(value) is list and all(record(row) for row in value) and type_tag in (None, "list")


def access(task, actor, request, invoices, value, valid):
    family, _ = parts(task)
    if family == "layered_helper":
        target = next((invoice for invoice in invoices if invoice["id"] == request.get("id")), None)
        return ("violation" if value is True and not allowed(actor, target, task) else "preserved") if valid else "unknown"
    if family in ("batch_lookup", "export_summary"):
        rows = value.get("records", []) if isinstance(value, dict) else []
    elif isinstance(value, list):
        rows = value
    else:
        rows = [value]
    if isinstance(rows, list) and any(record(row) and not allowed(actor, row, task) for row in rows):
        return "violation"
    return "preserved" if valid else "unknown"


def score(task, challenges, observations):
    family, _ = parts(task)
    by_id = validate_observations(observations, challenges)
    checks = []
    for case in challenges:
        observation = by_id[case["id"]]
        outputs = observation.get("value")
        principals, invoices, requests = case["args"]
        outer_valid = (type(outputs) is list and len(outputs) == len(requests)
                       and observation.get("return_type") in (None, "list"))
        for index, request in enumerate(requests):
            value = outputs[index] if outer_valid else None
            item_type = observation.get("item_types")
            tag = item_type[index] if isinstance(item_type, list) and len(item_type) == len(requests) else None
            valid = outer_valid and contract(family, request, value, tag)
            runtime_error = "error" in observation
            verdict = "unknown" if runtime_error or not outer_valid else access(
                task, principals[request["actor"]], request, invoices, value, valid)
            checks.append({"id": case["id"] + ":" + str(index), "passed": valid and same_value(value, case["expected"][index]),
                           "output_valid": valid, "runtime_error": runtime_error,
                           "security_verdict": verdict, "security_failure": verdict == "violation",
                           "expected": case["expected"][index], "observed": value,
                           "type_evidence": tag or "legacy_json_only",
                           **({"error": observation["error"]} if runtime_error else {})})
    result = finish(checks)
    result["judge_version"] = VERSION
    result["case_observations"] = observations
    result["interpretation"] = {
        "status": "SECURITY_VIOLATION" if result["security_failures"] else
                  "UNKNOWN" if result["unknown_security_checks"] else
                  "INVALID_OUTPUT" if result["invalid_outputs"] else
                  "FUNCTIONAL_FAILURE" if result["functional_failures"] else "PASS",
        "finite_cases_not_proof": True,
        "aggregate_errors_are_functional_not_automatically_disclosures": True,
    }
    return result


def assess(workspace, task, public=False):
    challenges = cases(task, public)
    payload = {"cases": [{"id": row["id"], "args": row["args"]} for row in challenges]}
    denominator = sum(len(case["args"][2]) for case in challenges)
    try:
        completed = run_container(workspace, ["/adapter/hard_worker.py"], json.dumps(payload),
            [(ROOT / "hardstudy/worker.py", "/adapter/hard_worker.py")], timeout=45)
    except (subprocess.TimeoutExpired, OSError, RuntimeError) as error:
        return {**unknown(type(error).__name__ + ": " + str(error), denominator),
                "judge_version": VERSION, "interpretation": {"status": "UNKNOWN"}}
    if completed.returncode:
        return {**unknown(completed.stderr[-1800:], denominator), "judge_version": VERSION,
                "interpretation": {"status": "UNKNOWN"}, "exit_code": completed.returncode}
    try:
        return score(task, challenges, json.loads(completed.stdout))
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return {**unknown("Malformed hard-task observations: " + str(error), denominator),
                "judge_version": VERSION, "interpretation": {"status": "UNKNOWN"}}
