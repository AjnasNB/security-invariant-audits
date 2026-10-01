"""Verify archived paper replay evidence without execution, network or dependencies."""
import ast
from pathlib import Path

from research.io import ROOT, digest, read_json
from research.scoring import same_value


def main():
    evidence = ROOT / "evidence/mucoco-author-replay-v1"
    manifest = read_json(evidence / "manifest.json")
    for filename, expected in manifest["files"].items():
        path = (evidence / filename).resolve()
        if not path.is_relative_to(evidence.resolve()) or not path.is_file():
            raise RuntimeError("Invalid paper evidence manifest target")
        if digest(path.read_bytes()) != expected:
            raise RuntimeError("Paper evidence hash mismatch: " + filename)
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"))
    report = read_json(evidence / "report.json")
    if report != read_json(ROOT / "reports/mucoco-author-replay-v1.json"):
        raise RuntimeError("Published paper replay summaries differ")
    for item in report["selected"]:
        if not item["replay_confirmed"] or not item["programs_pass_author_tests"]:
            raise RuntimeError("Expected a confirmed archived replay, not an unexecuted case")
        if not all(same_value(item[field], item["expected"]) for field in (
            "original_saved_answer", "original_runtime_output", "mutant_runtime_output",
        )):
            raise RuntimeError("Archived baseline/runtime output does not match")
        if same_value(item["mutant_saved_answer"], item["expected"]):
            raise RuntimeError("Saved mutant answer is not a reproduced error")
    print(f"Verified {len(manifest['files'])} paper evidence files and "
          f"{len(report['selected'])} archived failures. No new model or program execution.")


if __name__ == "__main__":
    main()
