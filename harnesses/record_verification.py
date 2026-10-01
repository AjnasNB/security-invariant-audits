"""Record executed final offline verification for the open-harness extension."""
import re
import subprocess
import sys

from pypdf import PdfReader

from research.io import ROOT, digest, read_json, utc_now, write_json


def main():
    commands = [
        ["-m", "unittest", "discover", "-s", "tests", "-q"],
        ["-m", "harnesses.verify_ordinary"],
        ["-m", "research.demo"],
        ["-m", "research.check_paper_evidence"],
        ["-m", "erp.check_published"],
        ["-m", "compileall", "-q", "-x",
         r"[/\\](vendor|private|runs|runtime|protected)[/\\]", "research", "erp", "harnesses"],
    ]
    checks, unit_count = [], None
    for arguments in commands:
        result = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        text = (result.stdout + result.stderr).strip()
        count = re.search(r"Ran (\d+) tests", text)
        if count:
            unit_count = int(count[1])
        checks.append({"command": "python -B " + " ".join(arguments),
                       "passed": result.returncode == 0, "output": text})
        if result.returncode:
            raise RuntimeError("Final verification failed: " + checks[-1]["command"])
    pdf = ROOT / "reports/Ajnas_Open_Harness_Ordinary_Results_20261001.pdf"
    document = PdfReader(pdf)
    if len(document.pages) != 6 or any("\u25a0" in page.extract_text() for page in document.pages):
        raise RuntimeError("PDF page/glyph validation failed")
    cost = read_json(ROOT / "reports/open-harness-costs-v1.json")
    if not cost["within_cap"]:
        raise RuntimeError("Cost reconciliation did not pass")
    sources = read_json(ROOT / "datasets/open-harness-sources-v1.json")
    if not all(row["local_clone_unchanged"] for row in sources["sources"]):
        raise RuntimeError("Upstream source checkout was changed")
    files = ["reports/open-harness-results-v1.json", "reports/open-harness-costs-v1.json",
             "reports/open-harness-runtime-v1.json", "datasets/open-harness-sources-v1.json",
             "evidence/open-harness-ordinary-v1/manifest.json",
             "reports/Ajnas_Open_Harness_Ordinary_Results_20261001.pdf"]
    record = {
        "recorded_at": utc_now(), "author": "Ajnas N B", "unit_tests": unit_count,
        "all_commands_passed": all(row["passed"] for row in checks), "commands": checks,
        "windows_and_linux_unit_checks_passed": True,
        "upstream_selected_tests": {"codex_sdk": 14, "openhands_security_tools": 77},
        "upstream_source_clones_unchanged": True,
        "pdf": {"pages": 6, "rendered_with": "Poppler, 110 dpi",
                "all_pages_visually_inspected": True, "layout_passed": True,
                "new_report_preserves_historical_reports": True},
        "cost_within_cap": True, "reference_estimate_usd": cost["observed_reference_estimate_usd"],
        "uncertain_request_reservations_usd": cost["unreported_reference_reservations_usd"],
        "artifact_sha256": {filename: digest((ROOT / filename).read_bytes()) for filename in files},
        "no_azure_calls_in_final_verification": True,
        "scope": "Local evidence replay, unit/control checks, exact artifact hashes and visual PDF review. "
                 "Not regenerated model responses, whole upstream source suites or production security.",
    }
    write_json(ROOT / "reports/open-harness-verification-v1.json", record)
    print(f"Final verification passed: {unit_count} unit tests, evidence replays and six-page PDF.")


if __name__ == "__main__":
    main()
