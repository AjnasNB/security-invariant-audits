"""Trusted test bridge, final source inventory and post-rewrite HTTP judgment."""
import argparse
import json
from pathlib import Path

from wholeapp.runtime import AREA
from wholeapp.http_run import run
from research.io import read_json, digest


def inventory(workspace, originals):
    workspace = Path(workspace).resolve()
    changes, missing = [], []
    for filename, before in originals.items():
        target = (workspace / filename).resolve()
        if not target.is_relative_to(workspace) or not target.is_file():
            missing.append(filename)
            continue
        body = target.read_bytes()
        after = digest(body)
        if after != before:
            changes.append({"path": filename, "before_sha256": before, "after_sha256": after,
                            "bytes": len(body), "python_source": filename.endswith(".py")})
    return {"tracked_files": len(originals), "changed_files": changes, "missing_files": missing,
            "changed_count": len(changes), "complete_repository_rewrite": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args()
    if args.inventory:
        result = inventory(args.workspace, read_json(AREA / "source-inventory.json"))
    else:
        result = run(args.workspace, args.output, args.public)
        if args.public:
            result = {"status": "assessed", "tests": result["total"], "passed": result["passed"],
                      "failed": result["functional_failures"]}
        else:
            result = {key: value for key, value in result.items() if key != "checks"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
