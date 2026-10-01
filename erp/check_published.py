"""Offline publication check; no Docker, credentials or model calls required."""
import ast
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    evidence = root / "evidence/erp"
    if not evidence.exists():
        print("ERP evidence has not been exported yet; unit source checks only.")
        return
    manifest = json.loads((evidence / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        source = evidence / name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Published evidence integrity mismatch: " + name)
        if source.suffix == ".py":
            ast.parse(source.read_text(encoding="utf-8"))
    result = json.loads((root / "reports/erpnext-results.json").read_text())
    assert result["run_count"] == result["meaningful_refactors"] == 6
    assert result["private_checks"] == result["private_passed"] == 564
    assert result["combined_candidate"]["passed"]
    assert result["http_workflow"]["passed"] and result["http_workflow"]["temporary_records_removed"]
    print(f"Published evidence valid: {len(manifest['files'])} hashes, six refactors, 564 checks.")


if __name__ == "__main__":
    main()
