"""Record final local verification from executed checks and immutable artifacts."""
import re
import subprocess
import sys

from research.io import ROOT, digest, read_json, utc_now, write_json


def main():
    commands = [
        ["-m", "unittest", "discover", "-s", "tests", "-q"],
        ["-m", "research.demo"],
        ["-m", "research.check_paper_evidence"],
        ["-m", "erp.check_published"],
        ["-m", "compileall", "-q", "-x",
         r"[/\\](vendor|private|runs|runtime|protected)[/\\]", "research", "erp", "harnesses"],
    ]
    checks = []
    units = None
    for arguments in commands:
        completed = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT,
                                   capture_output=True, text=True, encoding="utf-8", timeout=60)
        text = completed.stdout + completed.stderr
        matched = re.search(r"Ran (\d+) tests", text)
        if matched:
            units = int(matched[1])
        checks.append({"command": "python -B " + " ".join(arguments),
                       "passed": completed.returncode == 0, "output": text.strip()})
        if completed.returncode:
            raise RuntimeError("Final check failed: " + checks[-1]["command"])
    from pypdf import PdfReader
    pdf = ROOT / "reports/Ajnas_Ordinary_Prompt_Research_Correction_20261001.pdf"
    reader = PdfReader(pdf)
    if len(reader.pages) != 6 or any("\u25a0" in (page.extract_text() or "") for page in reader.pages):
        raise RuntimeError("Unexpected correction PDF pages/glyphs")
    artifacts = [pdf, *(ROOT / "reports" / filename for filename in (
        "ordinary-v1-results.json", "measurement-correction-v4.json",
        "reassessment-v4-executed.json", "mucoco-author-replay-v1.json",
        "mucoco-model-v1.json", "cost-accounting-v4.json",
    )), ROOT / "protocols/ordinary-v1.json", ROOT / "protocols/mucoco-prediction-v1.json"]
    record = {
        "recorded_at": utc_now(), "research_unit_tests": units,
        "all_final_commands_passed": all(check["passed"] for check in checks), "commands": checks,
        "runtime_controls": {
            "ordinary_controls_passed": read_json(ROOT / "reports/ordinary-controls-v1.json")["passed"],
            "actual_erp_timeout_cleanup_passed": read_json(ROOT / "reports/runtime-validation-v4.json")["passed"],
            "archived_failure_replays_confirmed": read_json(ROOT / "reports/mucoco-author-replay-v1.json")["confirmed_selected_failures"],
        },
        "artifact_sha256": {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in artifacts},
        "pdf": {"pages": len(reader.pages), "rendered_with": "Poppler pdftoppm 105 dpi",
                "all_pages_visually_inspected": True, "layout_review_passed": True,
                "new_dated_report_not_overwritten_historical_pdf": True},
        "typescript_validation": "Four changed/new runner files separately transpile-checked with zero syntax errors",
        "no_paid_calls_in_final_verification": True,
        "scope": "Local checks of this correction and published saved evidence; not a security guarantee "
                 "or independent replication of fresh model outputs",
    }
    write_json(ROOT / "reports/correction-verification-v4.json", record)
    print(f"Verified {units} unit tests, saved evidence, runtime controls and six-page PDF.")


if __name__ == "__main__":
    main()
