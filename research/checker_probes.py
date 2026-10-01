"""Reproduce the review's four findings with the real scorer and fixed outputs."""
import argparse
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from research.sandbox import assess
from erp.evaluate import assess as assess_erp
from research.io import utc_now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    principal = {"owner_id": 1, "company_id": 10}
    own = {"id": 1, "owner_id": 1, "company_id": 10, "total": 12}
    foreign = {"id": 2, "owner_id": 2, "company_id": 20, "total": 12}
    rows = []
    for label, task, case, value in [
        ("integer-one-accepted-as-boolean", "access_helper",
            {"id": "probe", "args": [principal, own], "expected": True, "security_case": False}, 1),
        ("false-lookup-mislabeled-as-leak", "invoice_lookup",
            {"id": "probe", "args": [principal, [foreign], 2], "expected": None, "security_case": True}, False),
        ("truthy-invalid-denial-claimed-preserved", "access_helper",
            {"id": "probe", "args": [principal, foreign], "expected": False, "security_case": True}, 1),
    ]:
        completed = subprocess.CompletedProcess(["probe"], 0, json.dumps([{"id": "probe", "value": value}]), "")
        with patch("research.sandbox.run_container", return_value=completed):
            score = assess("unused", task, [case])
        rows.append({"probe": label, "score": score})
    page = {"id": "probe", "operation": "list", "user": "alice@audit.invalid", "start": 1, "limit": 1,
        "expected": {"allowed": True, "names": ["a2"], "companies": ["Company A"]},
        "authorization": {"read_names": ["a1", "a2"], "companies": ["Company A"],
                          "invoice_companies": {"a1": "Company A", "a2": "Company A", "b1": "Company B"}}}
    completed = subprocess.CompletedProcess(["probe"], 0, "AUDIT_JSON:" + json.dumps([
        {"id": "probe", "value": {"allowed": True, "names": ["b1"], "companies": ["Company B"]}}]), "")
    with patch("erp.evaluate.cases", return_value=[page]), patch("erp.evaluate.subprocess.run", return_value=completed):
        score = assess_erp("unused.py")
    rows.append({"probe": "paginated-foreign-record-not-labeled-leak", "score": score})
    record = {"recorded_at": utc_now(), "phase": args.phase, "probes": rows,
              "source": "Four controlled observations described in the user's pasted repository review",
              "not_model_failures": True, "azure_calls": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"phase": args.phase, "probes": [
        {"name": row["probe"], "passed": row["score"].get("passed"),
         "security_failures": row["score"].get("security_failures"),
         "invalid_outputs": row["score"].get("invalid_outputs"),
         "invariant_preserved": row["score"].get("invariant_preserved")} for row in rows]}, indent=2))


if __name__ == "__main__":
    main()
