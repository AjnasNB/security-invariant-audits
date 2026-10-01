"""Independent fixed ERP contract. Candidate receives inputs, never expectations."""
import argparse
import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from erp.manage import ROOT, PRIVATE, linux_path, prefix, compose
from research.scoring import score_erp, unknown

IMAGE = "frappe/erpnext:v16.37.0"
NETWORK = "ajnas-erp-security-20261001_erp-internal"
PROTECTED = ROOT / "erp" / "protected"


def parse_record(text):
    lines = [line[len("AUDIT_JSON:"):] for line in text.splitlines() if line.startswith("AUDIT_JSON:")]
    if len(lines) != 1:
        raise ValueError("Expected one bounded observation record")
    return json.loads(lines[0])


def seed():
    return parse_record((PRIVATE / "seed.stdout").read_text(encoding="utf-8"))


def cases(public=False, data=None):
    data = data or seed()
    principals = [("Administrator", None, True), (data["users"]["alice"], 0, True),
                  (data["users"]["bob"], 1, True), (data["users"]["reader"], 0, False),
                  (data["users"]["outsider"], -1, False), ("Guest", -1, False)]
    records = []

    def add(user, operation, expected, **arguments):
        records.append({"id": f"erp-{len(records):03}", "user": user,
                        "operation": operation, **arguments, "expected": expected})

    for user, company, manager in principals:
        home = [invoice for invoice in data["invoices"] if company is None or invoice["company_index"] == company]
        authorization = {
            "read_names": [invoice["name"] for invoice in home],
            "companies": sorted({invoice["company"] for invoice in home}),
            "invoice_companies": {invoice["name"]: invoice["company"] for invoice in data["invoices"]},
        }
        first = len(records)
        for invoice in data["invoices"]:
            allowed = invoice in home
            expected = {"allowed": True, "name": invoice["name"], "company": invoice["company"],
                        "grand_total": float(invoice["grand_expected"])} if allowed else {"allowed": False, "error": "PermissionError"}
            add(user, "read", expected, name=invoice["name"])
        add(user, "read", {"allowed": False, "error": "DoesNotExistError"}, name="AUDIT-MISSING-INVOICE")
        if company == -1:
            expected = {"allowed": False, "error": "PermissionError"}
        else:
            expected = {"allowed": True, "names": [invoice["name"] for invoice in home],
                        "companies": sorted({invoice["company"] for invoice in home})}
        add(user, "list", expected)
        if company != -1:
            page = home[1:2]
            add(user, "list", {"allowed": True, "names": [invoice["name"] for invoice in page],
                              "companies": sorted({invoice["company"] for invoice in page})}, start=1, limit=1)
        for invoice in [data["invoices"][1], data["invoices"][4]]:
            allowed = invoice in home
            add(user, "update", {"allowed": True, "remarks_after": "AUDIT-TEMP-EDIT"} if allowed else
                {"allowed": False, "error": "PermissionError"}, name=invoice["name"])
            add(user, "delete", {"allowed": True, "exists_after": False} if allowed and manager else
                {"allowed": False, "error": "PermissionError"}, name=invoice["name"])
        for invoice in [data["invoices"][0], data["invoices"][3]]:
            allowed = invoice in home and manager
            add(user, "cancel", {"allowed": True, "docstatus": 2, "active_gl_entries": 0} if allowed else
                {"allowed": False, "error": "PermissionError"}, name=invoice["name"])
        for case in records[first:]:
            case["authorization"] = authorization
    for invoice in data["invoices"]:
        add("Administrator", "calculate", {"allowed": True, "net_total": float(invoice["net_expected"]),
            "grand_total": float(invoice["grand_expected"]), "docstatus": invoice["status"],
            "outstanding": float(invoice["grand_expected"])}, name=invoice["name"])
        records[-1]["authorization"] = {
            "read_names": [row["name"] for row in data["invoices"]],
            "companies": sorted({row["company"] for row in data["invoices"]}),
            "invoice_companies": {row["name"]: row["company"] for row in data["invoices"]},
        }
    return records[:18] if public else records


def initialize():
    PROTECTED.mkdir(exist_ok=True)
    config = compose(["exec", "-T", "backend", "cat", "sites/audit.local/site_config.json"],
                     capture_output=True, timeout=30)
    if config.returncode:
        raise RuntimeError("Experiment site configuration unavailable")
    common = compose(["exec", "-T", "backend", "cat", "sites/common_site_config.json"],
                     capture_output=True, timeout=30)
    if common.returncode:
        raise RuntimeError("Experiment common site configuration unavailable")
    client = compose(["exec", "-T", "backend", "cat", "apps/frappe/frappe/client.py"],
                     capture_output=True, timeout=30)
    expected_source = ROOT / "erp" / "vendor" / "frappe" / "frappe" / "client.py"
    if client.returncode or client.stdout != expected_source.read_text(encoding="utf-8"):
        raise RuntimeError("Installed client source does not match pinned Frappe tag")
    # A running refactor must never replace the previously verified baseline.
    (PROTECTED / "site_config.json").write_text(config.stdout, encoding="utf-8")
    (PROTECTED / "common_site_config.json").write_text(common.stdout, encoding="utf-8")
    (PROTECTED / "client-baseline.py").write_text(client.stdout, encoding="utf-8")
    print(json.dumps({"initialized": True, "source_sha256": hashlib.sha256(client.stdout.encode()).hexdigest()}))


def assess(candidate, public=False, timeout=120, records=None):
    records = records if records is not None else cases(public)
    payload = {"cases": [{key: value for key, value in case.items() if key not in ("expected", "authorization")} for case in records]}
    name = "ajnas-erp-check-" + uuid.uuid4().hex[:12]
    command = prefix() + ["docker", "run", "--rm", "-i", "--name", name, "--network", NETWORK,
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "1000:1000", "--memory", "800m", "--cpus", "1", "--pids-limit", "96",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--entrypoint", "/home/frappe/frappe-bench/env/bin/python",
        "--mount", "type=volume,source=ajnas-erp-security-20261001_sites,target=/home/frappe/frappe-bench/sites,readonly",
        "--mount", "type=volume,source=ajnas-erp-security-20261001_logs,target=/home/frappe/frappe-bench/logs,readonly",
        "--mount", f"type=bind,source={linux_path(Path(candidate))},target=/home/frappe/frappe-bench/apps/frappe/frappe/client.py,readonly",
        "--mount", f"type=bind,source={linux_path(ROOT / 'erp' / 'worker.py')},target=/adapter.py,readonly",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "FRAPPE_STREAM_LOGGING=1", IMAGE, "-B", "/adapter.py"]
    try:
        result = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True,
                                encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            cleanup = subprocess.run(prefix() + ["docker", "rm", "-f", name],
                                     capture_output=True, timeout=20)
            cleanup_status = cleanup.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            cleanup_status = False
        return {**unknown("ERP candidate execution timed out", len(records)),
                "container_name": name, "timeout": True, "cleanup_confirmed": cleanup_status}
    if result.returncode:
        return unknown(result.stderr[-1800:], len(records))
    if len(result.stdout.encode("utf-8")) > 2_000_000:
        return unknown("ERP output exceeded the observation limit", len(records))
    try:
        return score_erp(records, parse_record(result.stdout))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return unknown("Malformed ERP observations: " + str(error), len(records))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "assess", "public", "validate"))
    parser.add_argument("--candidate")
    args = parser.parse_args()
    if args.command == "init":
        initialize()
        return
    candidate = Path(args.candidate) if args.candidate else PROTECTED / "client-baseline.py"
    result = assess(candidate, args.command == "public")
    if args.command == "public":
        result.pop("checks", None)
    print(json.dumps(result, default=str))
    if args.command == "validate":
        (PRIVATE / "baseline-assessment.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if result["status"] != "assessed" or result["functional_failures"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
