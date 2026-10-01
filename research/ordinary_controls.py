"""Test ordinary-prompt fixtures against correct code and deliberate faults."""
import argparse
import tempfile
from pathlib import Path

from research.cases import fixture_cases
from research.io import ROOT, digest, utc_now, write_json
from research.natural_tasks import TASKS, public_cases
from research.sandbox import assess
from research.validate import alternative, faults
from research.variants import mutate, source_code


def validate_controls():
    rows = []
    with tempfile.TemporaryDirectory(prefix="ajnas-ordinary-controls-") as temporary:
        for task in TASKS:
            implementations = {
                **{condition: mutate(source_code(task), task, condition)
                   for condition in ("original", "rename", "formatting")},
                "valid_alternative": alternative(task),
                **faults(task),
            }
            for name, code in implementations.items():
                workspace = Path(temporary) / task / name
                workspace.mkdir(parents=True)
                (workspace / "target.py").write_text(code, encoding="utf-8")
                public = assess(workspace, task, public_cases(task))
                independent = assess(workspace, task, fixture_cases(task))
                is_fault = name in faults(task)
                passed = (public["status"] == independent["status"] == "assessed"
                    and public["functional_failures"] == 0
                    and (independent["security_failures"] > 0 if is_fault else
                         independent["functional_failures"] == 0
                         and independent["invariant_preserved"] is True))
                row = {"task": task, "implementation": name, "source_sha256": digest(code),
                       "is_seeded_fault": is_fault, "not_an_agent_failure": True,
                       "public": {key: public[key] for key in ("status", "total", "passed", "functional_failures")},
                       "independent": {key: independent[key] for key in
                           ("status", "total", "passed", "functional_failures", "security_failures",
                            "invalid_outputs", "unknown_security_checks", "invariant_preserved")},
                       "control_passed": passed}
                rows.append(row)
                print(f"{task}/{name}: public {public['passed']}/{public['total']}, "
                      f"independent violations {independent['security_failures']}; "
                      f"control {'passed' if passed else 'FAILED'}", flush=True)
    return {"recorded_at": utc_now(), "passed": all(row["control_passed"] for row in rows),
            "controls": rows, "azure_calls": 0, "seeded_faults": sum(row["is_seeded_fault"] for row in rows),
            "scope": "Correct/alternative code accepted; deliberate permission weakening passes "
                     "ordinary visible examples but is rejected by the independent judge"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "ordinary-controls-v1.json")
    args = parser.parse_args()
    result = validate_controls()
    write_json(args.output, result)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
