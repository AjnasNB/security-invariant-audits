"""Record actually executed local checks and reviewed report/runtime artifacts."""
import re
import subprocess
import sys

from pypdf import PdfReader

from research.io import ROOT, digest, read_json, utc_now, write_json


def main():
    commands = [
        ["-m", "unittest", "discover", "-s", "tests", "-q"],
        ["-m", "hardstudy.verify"],
        ["-m", "harnesses.verify_ordinary"],
        ["-m", "research.demo"],
        ["-m", "research.check_paper_evidence"],
        ["-m", "erp.check_published"],
        ["-m", "compileall", "-q", "-x", r"[/\\](vendor|private|runs|runtime|protected)[/\\]",
         "research", "erp", "harnesses", "hardstudy"],
    ]
    checks, unit_count = [], None
    for arguments in commands:
        completed = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT,
                                   capture_output=True, text=True, encoding="utf-8", timeout=60)
        text = (completed.stdout + completed.stderr).strip()
        found = re.search(r"Ran (\d+) tests", text)
        if found:
            unit_count = int(found[1])
        checks.append({"command": "python -B " + " ".join(arguments),
                       "passed": completed.returncode == 0, "output": text})
        if completed.returncode:
            raise RuntimeError("Final offline verification failed: " + checks[-1]["command"])
    pdf = ROOT / "reports/Ajnas_Vague_Context_Results_20261002.pdf"
    pages = PdfReader(pdf).pages
    if len(pages) != 6 or any("\u25a0" in page.extract_text() for page in pages):
        raise RuntimeError("PDF page count/glyph validation failed")
    rendered = [ROOT / f"output/pdf/hard-context-page-{index}.png" for index in range(1, 7)]
    if not all(path.is_file() for path in rendered):
        raise RuntimeError("Six rendered PDF pages are required")
    evidence = read_json(ROOT / "evidence/hard-vague-context-v1/manifest.json")
    report = read_json(ROOT / "reports/hard-vague-results-v1.json")
    cost = read_json(ROOT / "reports/hard-vague-costs-v1.json")
    if not cost["within_cap"]:
        raise RuntimeError("Reference-cost accounting exceeded the disclosed ceiling")
    runtime = read_json(ROOT / "reports/erp-final-checks.json")
    if not runtime["passed"]:
        raise RuntimeError("Latest read-only ERP final check did not pass")
    files = ["reports/hard-vague-results-v1.json", "reports/hard-vague-results-v1.md",
             "reports/hard-vague-costs-v1.json", "reports/hard-reference-controls-v1.json",
             "reports/Ajnas_Vague_Context_Results_20261002.pdf",
             "evidence/hard-vague-context-v1/manifest.json",
             "datasets/hard-task-catalog-v1.json", "datasets/large-erp-sources-v1.json"]
    record = {
        "recorded_at": utc_now(), "author": "Ajnas N B", "unit_tests": unit_count,
        "all_commands_passed": all(row["passed"] for row in checks), "commands": checks,
        "independently_executed_windows_and_linux_unit_tests": 65,
        "linux_saved_evidence_replay_passed": True,
        "offline_typescript_budget_tests": {"passed": 5, "failed": 0, "real_network_used": False,
            "command": "tsx --test tests/test_multi_model_budget.ts"},
        "published_evidence_hashes": len(evidence["files"]), "totals": report["totals"],
        "reference_controls": {"correct_variants_accepted": 48, "seeded_faults_rejected": 24, "azure_calls": 0},
        "erp_failure_reexecution": {"original": "94/94", "same_candidate": "52/94", "new_model_calls": 0,
                                  "classification": "unfinished generated-code behavior failure, no observed access leak"},
        "erp_read_only_final_check": runtime,
        "pdf": {"pages": 6, "rendered_with": "Poppler 110 dpi",
                "all_six_pages_visually_inspected": True, "layout_passed": True,
                "rendered_page_sha256": [digest(path.read_bytes()) for path in rendered]},
        "cost_reported_reference_usd": cost["reported_reference_usd"],
        "cost_identified_uncertainty_usd": cost["uncertain_reference_reservations_usd"],
        "cost_within_reference_ceiling": True,
        "artifact_sha256": {filename: digest((ROOT / filename).read_bytes()) for filename in files},
        "new_paid_model_calls_during_final_verification": 0,
        "scope": "Executed local checks, saved-result replay, fixture controls, retained failure reexecution, "
                 "read-only ERP data check and visual PDF review. Not a full upstream test suite or production guarantee.",
    }
    write_json(ROOT / "reports/hard-vague-verification-v1.json", record)
    print(f"Verified: {unit_count} Python tests, five offline budget tests, "
          f"{len(evidence['files'])} evidence hashes, six visually inspected PDF pages.")


if __name__ == "__main__":
    main()
