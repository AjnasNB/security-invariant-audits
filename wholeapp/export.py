"""Publish response evidence, not private credentials/raw traces or inflated claims."""
import ast
import copy
import difflib
import json
from pathlib import Path

from wholeapp.runtime import AREA, WORKSPACES
from wholeapp.judge import assess_saved
from hardstudy.export import provider_metadata
from research.io import ROOT, read_json, write_json, digest, utc_now


def scrubbed_response(row):
    # Only benign body content is retained. Error bodies can contain internal
    # traceback/session details; retain their HTTP/error evidence and exact hash.
    text = row.get("body", "")
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = None
    error = isinstance(data, dict) and data.get("exc_type")
    if error:
        public = {"exc_type": data["exc_type"]}
        body = json.dumps(public, separators=(",", ":"), ensure_ascii=False)
    elif row.get("http_status", 500) is not None and row.get("http_status", 500) >= 400:
        body = ""
    else:
        body = text
    return {**row, "body": body, "body_error_diagnostics_removed": bool(error) or body != text,
            "original_response_sha256": row.get("sha256"), "public_body_sha256": digest(body)}


def export_http(source, target, fixture):
    challenges = read_json(source / "cases.json")
    observations = read_json(source / "observations.json")
    actual = assess_saved(challenges, observations, fixture)
    recorded = read_json(source / "assessment.json")
    fields = ("total", "passed", "functional_failures", "security_failures", "unknown_access_checks", "invariant_preserved")
    if any(actual[key] != recorded[key] for key in fields):
        raise RuntimeError("Published response judge changed the original experiment")
    public_observations = [scrubbed_response(row) for row in observations]
    public_score = assess_saved(challenges, public_observations, fixture)
    if any(actual[key] != public_score[key] for key in fields):
        raise RuntimeError("Error redaction hid relevant evidence; preserve a more specific safe observation")
    target.mkdir(parents=True, exist_ok=False)
    write_json(target / "cases.json", challenges)
    write_json(target / "responses.json", public_observations)
    write_json(target / "assessment.json", public_score)
    write_json(target / "redaction.json", {
        "source_observations_sha256": digest((source / "observations.json").read_bytes()),
        "source_checks_sha256": digest((source / "assessment.json").read_bytes()),
        "error_diagnostics_excluded": True, "credentials_and_cookies_not_exported": True,
        "success_bodies_preserved": True, "scoring_unchanged": True})
    return {key: public_score[key] for key in fields}


def costs():
    stages, all_metadata = {}, []
    for name in ("agent-runs", "agent-runs-schema-fixed"):
        source = AREA / name
        raw = read_json(source / "usage.json")
        if raw["pending_requests"]:
            raise RuntimeError("Do not publish while inference usage is pending")
        metadata = [item for directory in sorted(source.iterdir()) if directory.is_dir()
                    for item in provider_metadata(directory)]
        if len(metadata) != raw["http_attempts"]:
            raise RuntimeError("Provider attempt counts differ")
        reported = sum(row.get("reference_cost_usd", 0) for row in metadata if row.get("usage"))
        uncertain = sum(row.get("reference_cost_usd", 0) for row in metadata if not row.get("usage")
                        and row.get("http_status") not in (400, 403, 404, 429))
        if abs(reported + uncertain - raw["reference_estimate_usd"]) > 1e-9:
            raise RuntimeError("Cost and retained reservations do not reconcile")
        stages[name] = {"attempts": len(metadata), "reported_usage_requests": sum(bool(row.get("usage")) for row in metadata),
                       "reported_reference_usd": reported, "uncertain_reservations_usd": uncertain,
                       "per_model": raw["per_model"], "provider_metadata": metadata,
                       "usage_file_sha256": digest((source / "usage.json").read_bytes())}
        all_metadata += metadata
    reported = sum(stage["reported_reference_usd"] for stage in stages.values())
    uncertain = sum(stage["uncertain_reservations_usd"] for stage in stages.values())
    previous = read_json(ROOT / "reports/hard-vague-costs-v1.json")
    return {"date": "2026-10-02", "currency": "USD", "stages": stages,
            "http_attempts": len(all_metadata), "reported_usage_requests": sum(bool(row.get("usage")) for row in all_metadata),
            "reported_reference_usd": reported, "uncertain_reservations_usd": uncertain,
            "reported_plus_identified_uncertainty_usd": reported + uncertain, "frozen_reference_ceiling_usd": 5,
            "within_cap": reported + uncertain <= 5,
            "all_studies_reported_reference_usd": previous["all_studies_reported_reference_usd"] + reported,
            "all_studies_with_identified_uncertainty_usd": previous["all_studies_with_identified_uncertainty_usd"] + reported + uncertain,
            "pricing_source": "Previously fetched official model reference rates, verified October 2, 2026",
            "scope": "Reference usage including rejected attempt and recovered checkpoint; no invoice/credit "
                     "claim. Excludes this Codex chat, other Azure workloads, tax and electricity. "
                     "No new paid cloud infrastructure. Local RAM/Docker application only."}


def main():
    target = ROOT / "evidence/wholeapp-v1"
    target.mkdir(parents=True, exist_ok=False)
    fixture = read_json(AREA / "fixture.json")
    write_json(target / "fixture.json", fixture)
    inventory = read_json(AREA / "source-inventory.json")
    write_json(target / "starting-source-inventory.json", inventory)
    baseline = export_http(AREA / "baseline-http-v1-authenticated", target / "baseline", fixture)
    model_runs, changed_paths = [], set()
    for stage in ("agent-runs", "agent-runs-schema-fixed"):
        batch = read_json(AREA / stage / "results.json")
        for original in batch["results"]:
            row = {key: value for key, value in original.items() if key not in ("answer", "workspace", "assessment")}
            row["stage"] = stage
            local = AREA / stage / original["run_id"]
            directory = target / "models" / stage / original["run_id"]
            assessment = export_http(local / "final-http", directory / "http", fixture)
            row["http"] = assessment
            row["new_access_failure_ids"] = sorted(
                {check["id"] for check in read_json(local / "final-http/assessment.json")["checks"] if check["security_failure"]}
                - {check["id"] for check in read_json(AREA / "baseline-http-v1-authenticated/assessment.json")["checks"]
                   if check["security_failure"]})
            row["evidence_directory"] = directory.relative_to(target).as_posix()
            row["whole_application_rewrite_completed"] = False
            for changed in original["changed_files"]:
                relative = changed["path"]
                baseline_code = (WORKSPACES / "baseline" / relative).read_bytes()
                candidate_code = (Path(original["workspace"]) / relative).read_bytes()
                if digest(baseline_code) != changed["before_sha256"] or digest(candidate_code) != changed["after_sha256"]:
                    raise RuntimeError("Saved candidate source was altered after testing")
                for label, body in (("initial", baseline_code), ("candidate", candidate_code)):
                    output = directory / label / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(body)
                changed_paths.add(relative)
            write_json(directory / "provider-metadata.json", provider_metadata(local))
            write_json(directory / "run.json", row)
            model_runs.append(row)
    hardened = export_http(AREA / "policy-hardening/http", target / "hardening/http", fixture)
    code = (AREA / "policy-hardening/printview.py").read_bytes()
    original = (WORKSPACES / "baseline/frappe/frappe/www/printview.py").read_bytes()
    (target / "hardening/printview.py").write_bytes(code)
    (target / "hardening/original-printview.py").write_bytes(original)
    patch = "".join(difflib.unified_diff(original.decode().splitlines(True), code.decode().splitlines(True),
        fromfile="a/frappe/www/printview.py", tofile="b/frappe/www/printview.py"))
    (target / "hardening/company-boundary.patch").write_text(patch, encoding="utf-8", newline="\n")
    hardening_spec = read_json(AREA / "policy-hardening/protocol.json")
    write_json(target / "hardening/protocol.json", hardening_spec)
    write_json(target / "baseline-print-permission-probe.json", read_json(AREA / "baseline-print-permission-probe.json"))
    controls = read_json(AREA / "judge-controls.json")
    for row in controls["controls"]:
        export_http(AREA / "judge-controls" / (row["control"] + "-http" if row["control"] != "private-file-permission"
                    else "file-permission-http"), target / "controls" / row["control"], fixture)
    write_json(target / "controls/summary.json", controls)
    business = {}
    for name in ("baseline", "gpt61-sol", "gpt56-sol"):
        row = read_json(AREA / (name + "-business.json"))
        # Runtime diagnostics aren't the behavioral value; use the scored
        # expected/observed values and remove raw traceback observations.
        safe = {key: value for key, value in row.items() if key != "observations"}
        write_json(target / "business" / (name + ".json"), safe)
        business[name] = {key: row["assessment"][key] for key in ("total", "passed", "security_failures")}
    helpers = read_json(AREA / "changed-helper-checks.json")
    write_json(target / "changed-helper-checks.json", helpers)
    for name in ("wholeapp-v1", "wholeapp-schema-fixed-v1"):
        write_json(target / "protocols" / (name + ".json"), read_json(ROOT / "protocols" / (name + ".json")))
    write_json(target / "setup-receipt.json", read_json(AREA / "setup-receipt.json"))
    if (AREA / "runtime-recovery.json").exists():
        write_json(target / "runtime-recovery.json", read_json(AREA / "runtime-recovery.json"))
    accounting = costs()
    write_json(target / "costs.json", accounting)
    checks = read_json(AREA / "baseline-http-v1-authenticated/assessment.json")
    report = {
        "recorded_at": utc_now(), "author": "Ajnas N B", "date": "2026-10-02",
        "full_source_tracked_files": len(inventory), "all_source_text_available_to_agent": True,
        "whole_application_rewrite_completed": False,
        "registered_models": ["gpt61-sol", "gpt56-sol", "gpt56-luna"],
        "original_schema_rejections": 3, "corrected_model_attempts": 3, "completed_agent_refactors": 0,
        "changed_files_across_candidates": sorted(changed_paths),
        "changed_file_count_by_model": {row["model_id"]: len(row["changed_files"])
            for row in model_runs if row["stage"] == "agent-runs-schema-fixed"},
        "model_runs": model_runs, "baseline": baseline, "hardening": hardened,
        "new_model_access_regressions": sum(bool(row["new_access_failure_ids"]) for row in model_runs),
        "baseline_print_conflict": {"failing_responses": 9, "distinct_cause": "Native website/customer fallback",
            "affected_surface": "document-print", "policy": "Requested internal company isolation",
            "not_ai_generated": True, "not_nine_independent_vulnerabilities": True,
            "stock_permission_exception": "Website permission accepts invoices for a customer readable by internal staff, "
                                          "even where document Company read/print permission denies",
            "missing_safety_claim": "Not a new zero-day or a claim that every production ERP configuration is exploitable",
            "affected_case_ids": [row["id"] for row in checks["checks"] if row["security_failure"]]},
        "surfaces": checks["by_surface"], "business": business,
        "changed_helpers": {"cases_per_candidate": len(helpers["original"]), "models": 3,
                            "all_passed": all(row["passed"] for row in helpers["results"])},
        "judge_controls_passed": controls["passed"], "costs": {key: accounting[key] for key in
            ("reported_reference_usd", "uncertain_reservations_usd", "reported_plus_identified_uncertainty_usd", "within_cap")},
        "limits_and_deviations": [
            "Whole-source access, but only two files changed by each Sol and none by Luna; not a full rewrite",
            "All three corrected trajectories incomplete: two cumulative estimate stops and one rate failure",
            "Three initial schema-rejected calls retained at zero reported inference cost",
            "WSL shutdown interrupted GPT-6.1 public testing; same checkpoint resumed, spent request/estimate ledger retained",
            "500-second active invocation wall limit restarted on host recovery; not an uninterrupted trajectory wall limit",
            "Prebuilt assets retained; no full frontend asset rebuild or exhaustive upstream suite",
            "730 requests cover selected invoices/documents/files, not every possible ERP access path",
            "Baseline has nine print responses violating desired internal company isolation through a native exception",
            "Hardening patch is deliberate desired-policy fix, not model-generated code or a silent change to baseline",
            "Real HTTP error diagnostics redacted; original response hash retained and verdicts unchanged",
            "Raw provider reasoning, credentials, cookies, database dumps, private sites and full source clones excluded",
            "Generated candidates not merged into working original ERP",
            "Hardening retains website/share-key code paths but this matrix has no actual Website User/share-key execution",
        ],
    }
    write_json(target / "summary.json", report)
    write_json(ROOT / "reports/wholeapp-results-v1.json", report)
    write_json(ROOT / "reports/wholeapp-costs-v1.json", accounting)
    write_json(ROOT / "datasets/wholeapp-access-matrix-v1.json", {
        "fixture": fixture, "cases": read_json(AREA / "frozen-cases.json"),
        "synthetic": True, "not_all_possible_security_cases": True})
    write_json(target / "manifest.json", {"recorded_at": utc_now(),
        "files": {path.relative_to(target).as_posix(): digest(path.read_bytes())
                  for path in sorted(target.rglob("*")) if path.is_file() and path.name != "manifest.json"},
        "source_terms": "Frappe modules MIT; ERPNext chart module GPL-3.0 with original notices. "
                        "Original project code is not silently relicensed.",
        "private_originals_preserved": True, "response_error_redactions_do_not_change_verdicts": True})
    print({"source_files_available": len(inventory), "baseline": baseline, "hardening": hardened,
           "changed": report["changed_file_count_by_model"], "new_model_access_regressions": report["new_model_access_regressions"],
           "costs": report["costs"]})


if __name__ == "__main__":
    main()
