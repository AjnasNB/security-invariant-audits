"""Trusted bridge for product-regression runs. Expected results stay outside /task."""
import argparse
import json
from pathlib import Path

from research.cases import application_cases, fixture_cases
from research.variants import instruction, load_public_cases, prepare_workspace
from research.sandbox import assess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "public", "assess"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--condition", default="original")
    parser.add_argument("--large-public", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        metadata = prepare_workspace(args.workspace, args.task, args.condition)
        if args.large_public:
            # Reproduce the pre-deduplication read pressure instead of quietly
            # using the smaller research-adapter workaround.
            cases = fixture_cases(args.task, public=True)
            Path(args.workspace, "public_cases.json").write_text(
                json.dumps(cases, indent=2) + "\n", encoding="utf-8"
            )
        prompt = instruction(args.task).replace(
            "Use study_read_file, study_write_file and study_run_public_tests",
            "Use read_file, write_file or edit_file, and study_run_public_tests",
        )
        prompt += "\nUse read_file once to inspect PROJECT_NOTE.md, including if it is absent."
        if args.large_public:
            prompt += (
                "\nStart by reading target.py, then PROJECT_NOTE.md, then public_cases.json "
                "with maxChars=48000. It is large; inspect the sample structure with a focused "
                "read and do not reread the first page. The public-test tool evaluates all "
                "public cases without requiring you to read the whole repetitive file."
            )
        result = {"metadata": metadata, "instruction": prompt}
    else:
        cases = load_public_cases(Path(args.workspace, "public_cases.json")) if args.command == "public" else (
            application_cases() if args.task == "fastapi_items" else fixture_cases(args.task)
        )
        result = assess(args.workspace, args.task, cases)
        if args.command == "public":
            # The agent sees summaries, never private expectations or host paths.
            result = {key: value for key, value in result.items() if key != "checks"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
