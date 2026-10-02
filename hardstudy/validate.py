"""Validate frozen references and deliberate faults without model calls."""
import argparse
import tempfile
from pathlib import Path

from hardstudy.catalog import TASKS, prepare
from hardstudy.judge import assess
from research.io import ROOT, write_json, utc_now


def validate():
    rows = []
    with tempfile.TemporaryDirectory(prefix="ajnas-hard-controls-") as temporary:
        parent = Path(temporary)
        parent.chmod(0o755)
        for task in TASKS:
            for condition in ("neutral", "stale"):
                directory = parent / (task + "-" + condition)
                metadata = prepare(directory, task, condition)
                result = assess(directory, task)
                passed = result["status"] == "assessed" and result["functional_failures"] == 0 and result["invariant_preserved"] is True
                rows.append({"task": task, "condition": condition, "kind": "reference",
                             "passed": passed, "metadata": metadata,
                             "judge": {key: result.get(key) for key in
                                       ("status", "total", "passed", "security_failures", "functional_failures",
                                        "invalid_outputs", "unknown_security_checks", "invariant_preserved")}})
                print(f"{task}/{condition}: {result.get('passed')}/{result['total']} reference", flush=True)
                if not passed:
                    return {"passed": False, "rows": rows, "azure_calls": 0}
            fault = parent / (task + "-seeded")
            prepare(fault, task, "neutral")
            policy = (fault / "policy.py").read_text(encoding="utf-8")
            # Deliberate company bypass validates sensitivity. Never model evidence.
            policy = policy.replace('if fields[1] != invoice["company_id"]:', "if False:")
            (fault / "policy.py").write_text(policy, encoding="utf-8", newline="\n")
            public, result = assess(fault, task, True), assess(fault, task)
            passed = public["functional_failures"] == 0 and result["security_failures"] > 0
            rows.append({"task": task, "kind": "seeded_company_bypass", "passed": passed,
                         "not_an_agent_failure": True, "public_passed": public.get("passed"),
                         "public_total": public["total"], "security_failures": result.get("security_failures")})
            print(f"{task}/seeded: visible {public.get('passed')}/{public['total']}; "
                  f"independent violations {result.get('security_failures')}", flush=True)
            if not passed:
                return {"passed": False, "rows": rows, "azure_calls": 0}
    return {"recorded_at": utc_now(), "passed": True, "rows": rows,
            "task_catalog": len(TASKS), "reference_variants": 2 * len(TASKS),
            "seeded_faults_rejected": len(TASKS), "azure_calls": 0,
            "scope": "Reference and deliberate checker controls; not model discoveries"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports/hard-reference-controls-v1.json")
    record = validate()
    write_json(parser.parse_args().output, record)
    if not record["passed"]:
        raise SystemExit(1)
