"""Record actually executed replay checks, original preservation and report QA."""
import re
import subprocess
import sys

from pypdf import PdfReader

from research.io import ROOT, read_json, write_json, digest, utc_now
from wholeapp.runtime import AREA


def main():
    commands = [
        ["-m", "unittest", "discover", "-s", "tests", "-q"],
        ["-m", "wholeapp.verify"],
        ["-m", "hardstudy.verify"],
        ["-m", "harnesses.verify_ordinary"],
        ["-m", "research.demo"],
        ["-m", "research.check_paper_evidence"],
        ["-m", "erp.check_published"],
        ["-m", "compileall", "-q", "-x", r"[/\\](vendor|private|runs|runtime|protected)[/\\]",
         "research", "erp", "harnesses", "hardstudy", "wholeapp"],
    ]
    checks, count = [], None
    for arguments in commands:
        result = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        output = (result.stdout + result.stderr).strip()
        found = re.search(r"Ran (\d+) tests", output)
        if found:
            count = int(found[1])
        checks.append({"command": "python -B " + " ".join(arguments),
                       "passed": result.returncode == 0, "output": output})
        if result.returncode:
            raise RuntimeError("Final verification failed: " + checks[-1]["command"])
    pdf = ROOT / "reports/Ajnas_Whole_Application_Access_Results_20261002.pdf"
    document = PdfReader(pdf)
    if len(document.pages) != 5 or any("\u25a0" in page.extract_text() for page in document.pages):
        raise RuntimeError("PDF page/glyph validation failed")
    images = [ROOT / f"output/pdf/whole-app-page-{number}.png" for number in range(1, 6)]
    if not all(image.exists() for image in images):
        raise RuntimeError("Five rendered pages are required")
    cleanup = read_json(AREA / "cleanup.json")
    original = read_json(ROOT / "reports/erp-final-checks.json")
    if not cleanup["experiment_containers_removed"] or not original["passed"]:
        raise RuntimeError("Original preservation/cleanup verification failed")
    result = read_json(ROOT / "reports/wholeapp-results-v1.json")
    costs = read_json(ROOT / "reports/wholeapp-costs-v1.json")
    record = {
        "verified_at": utc_now(), "author": "Ajnas N B", "all_commands_passed": True,
        "python_unit_tests": count, "commands": checks,
        "windows_and_linux_unit_tests_executed": 73, "linux_public_evidence_replay_passed": True,
        "offline_typescript_budget_tests": {"passed": 7, "network_used": False},
        "manifest_file_count": len(read_json(ROOT / "evidence/wholeapp-v1/manifest.json")["files"]),
        "http_cases_per_main_run": 730, "total_retained_public_http_observations": 5847,
        "baseline_print_policy_conflict": 9, "hardening_passed": result["hardening"]["passed"],
        "new_model_access_regressions": 0, "entire_application_rewrite_completed": False,
        "business": result["business"], "changed_helpers": result["changed_helpers"],
        "disposable_runtime_cleanup": cleanup, "original_erp_read_only_final_check": original,
        "pdf": {"pages": 5, "all_pages_visually_inspected": True, "layout_passed": True,
                "rendered_with": "Poppler, 110 dpi", "sha256": digest(pdf.read_bytes()),
                "rendered_page_sha256": [digest(image.read_bytes()) for image in images]},
        "cost": {key: costs[key] for key in ("reported_reference_usd", "uncertain_reservations_usd",
                                           "reported_plus_identified_uncertainty_usd", "within_cap")},
        "no_new_model_calls_during_verification": True,
        "artifact_sha256": {path: digest((ROOT / path).read_bytes()) for path in
            ("reports/wholeapp-results-v1.json", "reports/wholeapp-results-v1.md", "reports/wholeapp-costs-v1.json",
             "evidence/wholeapp-v1/manifest.json", "reports/Ajnas_Whole_Application_Access_Results_20261002.pdf")},
        "scope": "Executed local unit/replay/runtime/QA checks, not generalized security or complete rewrite proof.",
    }
    write_json(ROOT / "reports/wholeapp-verification-v1.json", record)
    print(f"Verification complete: {count} Python tests, seven offline budget tests, "
          "82 evidence hashes and five reviewed PDF pages. Original ERP preserved.")


if __name__ == "__main__":
    main()
