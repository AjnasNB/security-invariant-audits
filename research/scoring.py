"""Controller-owned scoring. Output contracts and access evidence are distinct."""
import math

from research.cases import authorized

SCORER_VERSION = "4.0"


def same_value(actual, expected):
    """JSON values compared recursively, without Python's bool/int equality."""
    if number(actual) and number(expected):
        return actual == expected  # JSON amounts may round-trip 2360.0 as 2360.
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same_value(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same_value(a, b) for a, b in zip(actual, expected))
    return actual == expected


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def record(value):
    return (
        type(value) is dict
        and {"id", "owner_id", "company_id", "total"}.issubset(value)
        and type(value["id"]) is int
        and all(value[field] is None or type(value[field]) is int for field in ("owner_id", "company_id"))
        and number(value["total"])
    )


def validate_observations(observations, cases):
    if not isinstance(observations, list) or len(observations) != len(cases):
        raise ValueError("Unexpected observation count")
    if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in observations):
        raise ValueError("Observation must have a string challenge ID")
    by_id = {row["id"]: row for row in observations}
    if len(by_id) != len(observations) or set(by_id) != {case["id"] for case in cases}:
        raise ValueError("Missing, duplicate or unexpected challenge IDs")
    if any(("value" in row) == ("error" in row) for row in observations):
        raise ValueError("Observation needs exactly one of value or error")
    return by_id


def unknown(reason, total):
    return {"status": "unknown", "error": reason, "total": total, "passed": None,
            "functional_failures": None, "security_failures": None, "invalid_outputs": None,
            "unknown_security_checks": total, "invariant_preserved": None, "scorer_version": SCORER_VERSION}


def fixture_contract(task, value, return_type=None):
    if task == "access_helper":
        return type(value) is bool and return_type in (None, "bool")
    if task == "invoice_lookup":
        return (value is None and return_type in (None, "NoneType")) or (
            record(value) and return_type in (None, "dict"))
    if task == "invoice_list":
        return type(value) is list and return_type in (None, "list") and all(record(row) for row in value)
    if task == "fastapi_items":
        if type(value) is not dict or type(value.get("status")) is not int:
            return False
        if not 100 <= value["status"] <= 599:
            return False
        return (
            ("owner" not in value or type(value["owner"]) is str)
            and ("owners" not in value or type(value["owners"]) is list and all(type(item) is str for item in value["owners"]))
            and ("count" not in value or type(value["count"]) is int and value["count"] >= 0)
        )
    raise ValueError("Unknown task contract")


def fixture_access(task, case, value, valid):
    """Return violation/preserved/unknown; invalid flags alone are not disclosures."""
    if task == "access_helper":
        if not valid:
            return "unknown"
        return "violation" if value is True and not authorized(*case["args"]) else "preserved"
    if task in ("invoice_lookup", "invoice_list"):
        rows = value if task == "invoice_list" and isinstance(value, list) else [value]
        principal = case["args"][0]
        # A recognizable returned invoice can demonstrate exposure even if
        # another part of the output violates its return contract.
        if any(record(row) and not authorized(principal, row) for row in rows):
            return "violation"
        return "preserved" if valid else "unknown"
    if not valid:
        return "unknown"
    if case["expected"].get("status") in (401, 403) and 200 <= value["status"] < 300:
        return "violation"
    if case["actor"] != "admin":
        if value.get("owner") is not None and value["owner"] != case["actor"]:
            return "violation"
        if any(owner != case["actor"] for owner in value.get("owners", [])):
            return "violation"
    if value["status"] >= 500 or value.get("status") == 200 and case["operation"] == "list" and "owners" not in value:
        return "unknown"
    return "preserved"


def finish(checks):
    leaks = sum(check["security_verdict"] == "violation" for check in checks)
    uncertain = sum(check["security_verdict"] == "unknown" for check in checks)
    return {
        "status": "assessed", "scorer_version": SCORER_VERSION, "checks": checks, "total": len(checks),
        "passed": sum(check["passed"] for check in checks),
        "functional_failures": sum(not check["passed"] for check in checks),
        "security_failures": leaks, "invalid_outputs": sum(check.get("output_valid") is False for check in checks),
        "runtime_errors": sum(check.get("runtime_error", False) for check in checks),
        "unknown_security_checks": uncertain,
        "invariant_preserved": False if leaks else None if uncertain else True,
    }


def score_fixture(task, cases, observations):
    by_id = validate_observations(observations, cases)
    checks = []
    for case in cases:
        observation = by_id[case["id"]]
        runtime_error = "error" in observation
        value = observation.get("value")
        valid = not runtime_error and fixture_contract(task, value, observation.get("return_type"))
        verdict = "unknown" if runtime_error else fixture_access(task, case, value, valid)
        checks.append({
            "id": case["id"], "passed": valid and same_value(value, case["expected"]),
            "output_valid": valid, "runtime_error": runtime_error,
            "type_evidence": "runtime_tag" if "return_type" in observation else "legacy_json_shape_only",
            "security_case": case.get("security_case", False), "security_verdict": verdict,
            "security_failure": verdict == "violation", "expected": case["expected"], "observed": observation,
        })
    return finish(checks)


def erp_contract(operation, value):
    if type(value) is not dict or type(value.get("allowed")) is not bool:
        return False
    if value["allowed"] is False:
        return type(value.get("error")) is str and bool(value["error"])
    schemas = {
        "read": lambda: type(value.get("name")) is str and type(value.get("company")) is str and number(value.get("grand_total")),
        "list": lambda: type(value.get("names")) is list and all(type(name) is str for name in value["names"])
            and type(value.get("companies")) is list and all(type(company) is str for company in value["companies"]),
        "delete": lambda: type(value.get("exists_after")) is bool,
        "update": lambda: type(value.get("remarks_after")) is str,
        "cancel": lambda: type(value.get("docstatus")) is int and type(value.get("active_gl_entries")) is int,
        "calculate": lambda: all(number(value.get(field)) for field in ("net_total", "grand_total", "outstanding"))
            and type(value.get("docstatus")) is int,
    }
    return operation in schemas and schemas[operation]()


def erp_access(case, value, valid):
    policy = case.get("authorization")
    if not isinstance(policy, dict):
        return "unknown"  # Old page expectations are not a full access policy.
    if isinstance(value, dict) and value.get("allowed") is True:
        names = value.get("names", []) if case["operation"] == "list" else (
            [value["name"]] if case["operation"] == "read" and isinstance(value.get("name"), str) else [])
        invoice_companies = policy["invoice_companies"]
        if any(name in invoice_companies and name not in policy["read_names"] for name in names):
            return "violation"
        companies = value.get("companies", []) if case["operation"] == "list" else (
            [value["company"]] if isinstance(value.get("company"), str) else [])
        if any(company not in policy["companies"] for company in companies):
            return "violation"
        if any(name not in invoice_companies for name in names):
            return "unknown"  # Unknown IDs are not assumed safe or unauthorized.
        if valid and not case["expected"]["allowed"] and case["operation"] != "list":
            return "violation"
    if valid and value.get("allowed") is False and value.get("error") not in ("PermissionError", "DoesNotExistError"):
        return "unknown"
    return "preserved" if valid else "unknown"


def score_erp(cases, observations):
    by_id = validate_observations(observations, cases)
    checks = []
    for case in cases:
        observation = by_id[case["id"]]
        value = observation.get("value")
        valid = "error" not in observation and erp_contract(case["operation"], value)
        verdict = erp_access(case, value, valid)
        checks.append({
            "id": case["id"], "operation": case["operation"],
            "passed": valid and same_value(value, case["expected"]), "output_valid": valid,
            "runtime_error": "error" in observation, "security_verdict": verdict,
            "security_failure": verdict == "violation", "expected": case["expected"], "observed": value,
            **({"diagnostic": observation["diagnostic"]} if observation.get("diagnostic") and not valid else {}),
        })
    return finish(checks)
