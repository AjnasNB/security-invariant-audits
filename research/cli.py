import argparse
import json
from pathlib import Path

from research.cases import application_cases, fixture_cases
from research.io import ROOT, read_json, write_json
from research.sandbox import assess
from research.variants import instruction, prepare_workspace, load_public_cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "public", "assess"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--condition", default="original")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "prepare":
        metadata = prepare_workspace(args.workspace, args.task, args.condition)
        result = {"metadata": metadata, "instruction": instruction(args.task),
                  "available_files": sorted(path.name for path in Path(args.workspace).iterdir())}
    else:
        public = args.command == "public"
        cases = load_public_cases(Path(args.workspace) / "public_cases.json") if public else (
            application_cases() if args.task == "fastapi_items" else fixture_cases(args.task)
        )
        result = assess(args.workspace, args.task, cases)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
