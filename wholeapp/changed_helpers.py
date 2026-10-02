"""Original-versus-candidate executable helper checks on the disposable ERP."""
import json

from erp.evaluate import IMAGE, parse_record
from research.io import write_json, read_json, utc_now
from wholeapp.runtime import AREA, WORKSPACES, NETWORK, checked, mount_options, reset


def execute(workspace):
    reset()
    payload = {"companies": [row["name"] for row in read_json(AREA / "fixture.json")["source"]["companies"]]}
    result = checked(["run", "--rm", "-i", "--network", NETWORK, "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "1000:1000", "--memory", "600m",
        "--cpus", "1", "--pids-limit", "96", "--tmpfs", "/tmp:rw,size=67108864",
        *mount_options(workspace), "-e", "PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint", "/home/frappe/frappe-bench/env/bin/python", IMAGE,
        "-B", "/adapter/changed_helpers_worker.py"], input=json.dumps(payload).encode(), timeout=50)
    return parse_record(result.stdout.decode("utf-8"))


def main():
    original = execute(WORKSPACES / "baseline")
    results = []
    for model in ("gpt61-sol", "gpt56-sol", "gpt56-luna"):
        observations = execute(WORKSPACES / model)
        if [row["id"] for row in original] != [row["id"] for row in observations]:
            raise RuntimeError("Changed helper cases differ")
        checks = [{"id": first["id"], "passed": first["sha256"] == second["sha256"],
                   "original_sha256": first["sha256"], "candidate_sha256": second["sha256"]}
                  for first, second in zip(original, observations)]
        results.append({"model_id": model, "checks": checks, "passed": all(row["passed"] for row in checks)})
    record = {"at": utc_now(), "original": original, "results": results, "azure_calls": 0,
              "ground_truth": "Direct unchanged-baseline helper outputs, finite cases not a general equivalence proof"}
    write_json(AREA / "changed-helper-checks.json", record)
    print({"cases_per_candidate": len(original), "candidate_groups": len(results),
           "all_passed": all(row["passed"] for row in results)})


if __name__ == "__main__":
    main()
