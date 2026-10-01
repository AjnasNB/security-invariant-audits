"""Exercise ERP timeout cleanup in the actual local container, without AI calls."""
import argparse
import subprocess
import tempfile
from pathlib import Path

from erp.evaluate import assess
from erp.manage import prefix
from research.io import ROOT, utc_now, write_json


def validate_timeout(timeout=5):
    with tempfile.TemporaryDirectory(prefix="ajnas-erp-timeout-") as temporary:
        candidate = Path(temporary) / "client.py"
        # The import stalls before frappe.connect(), so this test changes no DB data.
        candidate.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        result = assess(candidate, timeout=timeout, records=[{
            "id": "timeout-probe", "user": "Guest", "operation": "read",
            "name": "AUDIT-MISSING-INVOICE",
            "expected": {"allowed": False, "error": "DoesNotExistError"},
            "authorization": {"read_names": [], "companies": [], "invoice_companies": {}},
        }])
    name = result.get("container_name")
    if not name or not name.startswith("ajnas-erp-check-"):
        raise RuntimeError("Expected the named ERP timeout path, not a normal result")
    remaining = subprocess.run(prefix() + ["docker", "ps", "-a", "--filter", "name=^/" + name + "$",
        "--format", "{{.Names}}"], capture_output=True, text=True, encoding="utf-8", timeout=20)
    passed = (result["status"] == "unknown" and result.get("timeout") is True
              and result.get("cleanup_confirmed") is True
              and result.get("invariant_preserved") is None
              and remaining.returncode == 0 and not remaining.stdout.strip())
    return {
        "recorded_at": utc_now(), "test": "Actual ERP candidate import timeout and exact-name cleanup",
        "passed": passed, "assessment": result, "container_absent_after_cleanup": not remaining.stdout.strip(),
        "cleanup_inventory_succeeded": remaining.returncode == 0, "azure_calls": 0,
        "database_changes": False, "scope": "Timeout cleanup, not a general container-escape proof",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "runtime-validation-v4.json")
    args = parser.parse_args()
    record = validate_timeout(args.timeout)
    write_json(args.output, record)
    print(record)
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
