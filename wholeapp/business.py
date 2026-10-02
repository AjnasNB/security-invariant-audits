"""Fixed business contract on full mounted application sources, no AI calls."""
import argparse
import json
from pathlib import Path

from erp.evaluate import cases, parse_record, IMAGE
from research.io import ROOT, read_json, write_json, utc_now
from research.scoring import score_erp
from wholeapp.runtime import AREA, NETWORK, WORKSPACES, reset, checked, mount_options, linux_path


def assess(workspace, output):
    records = cases(data=read_json(AREA / "fixture.json")["source"])
    payload = {"cases": [{key: value for key, value in case.items() if key not in ("expected", "authorization")}
                         for case in records]}
    reset()
    result = checked(["run", "--rm", "-i", "--network", NETWORK, "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", "1000:1000", "--memory", "800m",
        "--cpus", "1", "--pids-limit", "96", "--tmpfs", "/tmp:rw,size=67108864",
        *mount_options(workspace),
        "--mount", f"type=bind,source={linux_path(ROOT / 'erp/worker.py')},target=/business.py,readonly",
        "-e", "AJNAS_FIXTURE_CLOCK=2026-10-01T12:00:00", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "FRAPPE_STREAM_LOGGING=1", "--entrypoint", "/home/frappe/frappe-bench/env/bin/python",
        IMAGE, "-B", "/business.py"], input=json.dumps(payload).encode(), timeout=100)
    observations = parse_record(result.stdout.decode("utf-8"))
    assessment = score_erp(records, observations)
    record = {"executed_at": utc_now(), "entire_source_trees_mounted": True,
              "contract": "The unchanged independently defined 94-case invoice business/access contract",
              "observations": observations, "assessment": assessment, "azure_calls": 0}
    write_json(output, record)
    return assessment


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    r = assess(args.workspace, args.output)
    print({key: r[key] for key in ("total", "passed", "functional_failures", "security_failures")})
