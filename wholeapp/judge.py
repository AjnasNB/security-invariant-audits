"""Independent response/content ground truth; no crash is labeled safely denied."""
import csv
import io
import json

from wholeapp.cases import document_allowed, file_allowed, principal

DENIAL_CODES = (401, 403, 404)


def names_from_json(value, known):
    selected = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("name", "value", "label") and isinstance(item, str) and item in known:
                selected.add(item)
            selected |= names_from_json(item, known)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item in known:
                selected.add(item)
            selected |= names_from_json(item, known)
    return selected


def exposed_names(body, data, fixture):
    known = {row["name"] for row in fixture["documents"] + fixture["files"]}
    return sorted(names_from_json(data, known))


def forbidden_markers(user, fixture):
    actor = principal(user, fixture)
    forbidden = {}
    for document in fixture["documents"]:
        if not document_allowed(user, document, fixture):
            forbidden[document["content_marker"]] = "other_company_document_content"
        if not document_allowed(user, document, fixture) or not actor["secret"]:
            forbidden[document["secret"]] = "protected_field_content"
    for file in fixture["files"]:
        if not file_allowed(user, file, fixture):
            forbidden[file["content_marker"]] = "private_attachment_content"
    return forbidden


def score(case, response, fixture):
    body = response.get("body", "")
    code = response.get("http_status")
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        data = None
    markers = [{"marker": marker, "type": kind} for marker, kind in forbidden_markers(case["user"], fixture).items()
               if marker in body]
    expected_names = set(case.get("expected_names", []))
    observed_names = set(exposed_names(body, data, fixture))
    unauthorized = []
    for name in observed_names:
        document = next((row for row in fixture["documents"] if row["name"] == name), None)
        file = next((row for row in fixture["files"] if row["name"] == name), None)
        if document and not document_allowed(case["user"], document, fixture) or file and not file_allowed(
                case["user"], file, fixture):
            unauthorized.append(name)
    if case.get("csv_response"):
        known = {row["name"] for row in fixture["documents"]}
        observed_names |= {cell for row in csv.reader(io.StringIO(body)) for cell in row if cell in known}
        unauthorized += [name for name in observed_names if name not in expected_names]
    if case.get("text_response"):
        target = case.get("document", {}).get("name")
        if target and target in body:
            observed_names.add(target)
        # HTML often includes document names even in error templates. Markers
        # or a success response plus document content are stronger evidence.
        if not case["expected_allowed"] and code == 200 and observed_names:
            unauthorized += list(observed_names)
    success = isinstance(code, int) and 200 <= code < 300
    incorrect_denial = isinstance(data, dict) and data.get("exc_type") in (
        "CSRFTokenError", "AuthenticationError", "ValidationError")
    violation = bool(markers or unauthorized)
    if case.get("mutation") and success and not case["expected_allowed"]:
        violation = True
    access_verdict = "VIOLATION" if violation else (
        "UNKNOWN" if response.get("transport_error") or code is None or code >= 500 or incorrect_denial
        else "PRESERVED_IN_CHECKED_RESPONSE")
    if case.get("mutation"):
        functional = code in (401, 403) and not violation and not incorrect_denial
    elif case["expected_allowed"]:
        functional = success
        if case.get("binary_response"):
            functional &= case["expected_marker"] in body
        elif "expected_names" in case:
            if case["surface"] == "form-document-load":
                # The normal form response also includes authorized attachment
                # metadata. Keep leak analysis broad but document value
                # comparison specific to the requested business document.
                business_names = {row["name"] for row in fixture["documents"]}
                functional &= observed_names & business_names == expected_names
            else:
                functional &= observed_names == expected_names
    else:
        empty = success and not observed_names and not markers and case.get("empty_is_denial", False)
        functional = (code in DENIAL_CODES or empty) and not violation
        if incorrect_denial:
            functional = False
            if not violation:
                access_verdict = "UNKNOWN"
    if case.get("check_secret_field") and markers:
        functional = False
    return {
        "id": case["id"], "surface": case["surface"], "user": case["user"],
        "http_status": code, "passed": bool(functional), "access_verdict": access_verdict,
        "security_failure": violation, "exposed_names": sorted(observed_names),
        "unauthorized_names": sorted(set(unauthorized)), "leaked_markers": markers,
        "response_sha256": response.get("sha256"), "response_bytes": response.get("bytes"),
        **({"transport_error": response["transport_error"]} if response.get("transport_error") else {}),
    }


def assess_saved(challenges, observations, fixture):
    if len(challenges) != len(observations) or {row["id"] for row in challenges} != {row["id"] for row in observations}:
        raise ValueError("Response count/IDs do not match the frozen access matrix")
    lookup = {row["id"]: row for row in observations}
    if len(lookup) != len(observations):
        raise ValueError("Duplicate observation ID")
    checks = [score(case, lookup[case["id"]], fixture) for case in challenges]
    leaks = [row for row in checks if row["security_failure"]]
    unknown = sum(row["access_verdict"] == "UNKNOWN" for row in checks)
    return {"version": "whole-http-judge-1.0", "total": len(checks), "passed": sum(row["passed"] for row in checks),
            "functional_failures": sum(not row["passed"] for row in checks), "security_failures": len(leaks),
            "unknown_access_checks": unknown, "invariant_preserved": False if leaks else None if unknown else True,
            "checks": checks, "by_surface": {surface: {"total": len(selected),
                "passed": sum(row["passed"] for row in selected), "security_failures": sum(row["security_failure"] for row in selected),
                "unknown": sum(row["access_verdict"] == "UNKNOWN" for row in selected)}
                for surface in sorted({row["surface"] for row in checks})
                for selected in [[row for row in checks if row["surface"] == surface]]},
            "finite_response_matrix_not_proof": True}
