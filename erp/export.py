"""Publishable ERP evidence: no credentials, raw model reasoning or site config."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from erp.evaluate import ROOT, PRIVATE, PROTECTED, seed, parse_record


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_lf(file, value):
    Path(file).write_text(value.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def main():
    destination = ROOT / "evidence" / "erp"
    destination.mkdir(parents=True, exist_ok=True)
    run_root = ROOT / "erp/runs/pilot-20261001"
    results = json.loads((run_root / "results.json").read_text(encoding="utf-8"))
    baseline = json.loads((PRIVATE / "baseline-assessment.json").read_text())
    controls = json.loads((PRIVATE / "judge-validation.json").read_text())
    integrated = json.loads((ROOT / "erp/runtime/integration-result.json").read_text())
    http = json.loads((PRIVATE / "http-smoke.json").read_text())
    source = json.loads((ROOT / "erp/sources.json").read_text())
    if not (results["allPassed"] and controls["passed"] and integrated["passed"] and http["passed"]):
        raise RuntimeError("Refusing to publish an unverified success summary")
    records = []
    for row in results["results"]:
        directory = next(path for path in run_root.iterdir() if path.is_dir() and
                         path.name.endswith(row["task"] + "-" + row["condition"]))
        exported = destination / directory.name
        exported.mkdir(exist_ok=True)
        candidate = directory / "candidate.py"
        text = candidate.read_text(encoding="utf-8")
        text = "# Modified by Ajnas N B's controlled AI-refactoring experiment, October 1, 2026.\n" + text
        write_lf(exported / "candidate.py", text)
        write_lf(exported / "input.py", (directory / "input.py").read_text(encoding="utf-8"))
        summary = {key: value for key, value in row.items() if key not in ("assessment", "answer")}
        summary["assessment"] = {key: value for key, value in row["assessment"].items() if key != "checks"}
        summary["published_candidate_sha256"] = digest(text.encode())
        summary["annotation_note"] = "Added a modification/copyright notice before publication; executable structure unchanged."
        write_lf(exported / "result.json", json.dumps(summary, indent=2))
        metadata = []
        for path in sorted(directory.glob("metadata-*.json")):
            raw = json.loads(path.read_text())
            metadata.append({key: value for key, value in raw.items()
                             if key in ("httpStatus", "model", "status", "usage", "responseSha256")})
        write_lf(exported / "provider-usage.json", json.dumps(metadata, indent=2))
        records.append(summary)
    combined = (ROOT / "erp/runtime/combined-client.py").read_text(encoding="utf-8")
    combined = "# Modified by Ajnas N B; combined three accepted AI refactors, October 1, 2026.\n" + combined.rstrip() + "\n"
    write_lf(destination / "combined-client.py", combined)
    write_lf(destination / "baseline-client.py", (PROTECTED / "client-baseline.py").read_text(encoding="utf-8"))
    fixture = seed()
    write_lf(destination / "synthetic-fixture.json", json.dumps(fixture, indent=2))
    baseline_checks = {key: value for key, value in baseline.items() if key != "checks"}
    integration_checks = {key: value for key, value in integrated["assessment"].items() if key != "checks"}
    report = {"recorded_at": datetime.now(timezone.utc).isoformat(), "source": source,
              "baseline": baseline_checks, "judge_controls": controls,
              "runs": records, "usage": results["usage"],
              "run_count": len(records), "meaningful_refactors": sum(row["meaningfulRefactor"] for row in records),
              "private_checks": sum(row["assessment"]["total"] for row in records),
              "private_passed": sum(row["assessment"]["passed"] for row in records),
              "security_failures": sum(row["assessment"]["security_failures"] for row in records),
              "combined_candidate": {"passed": integrated["passed"], "assessment": integration_checks,
                                      "original_candidate_sha256": integrated["candidate_sha256"],
                                      "published_candidate_sha256": digest(combined.encode())},
              "http_workflow": http,
              "publication": {"raw_traces_withheld": True, "site_credentials_excluded": True,
                  "erpnext_gpl_preserved": True, "modified_frappe_files_mit": True,
                  "redactions": ["model reasoning/transcripts", "host profile/endpoint settings", "site configuration and passwords",
                                  "HTTP session cookies", "database backups", "restricted MUCOCO/JailGuard data"],
                  "not_redacted": "Synthetic fixture, modified code, result denominators, setup failures and aggregate token use"}}
    write_lf(ROOT / "reports/erpnext-results.json", json.dumps(report, indent=2))
    manifest = {path.relative_to(destination).as_posix(): digest(path.read_bytes())
                for path in destination.rglob("*") if path.is_file() and path.name != "manifest.json"}
    write_lf(destination / "manifest.json", json.dumps({"files": manifest, "source": source}, indent=2))
    print(json.dumps({"exported_runs": len(records), "private_checks": report["private_checks"],
                      "private_passed": report["private_passed"], "http_checks": http["passed_checks"],
                      "secrets_exported": False}, indent=2))


if __name__ == "__main__":
    main()
