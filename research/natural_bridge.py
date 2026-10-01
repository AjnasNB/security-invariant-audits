"""Controller bridge. Public test feedback contains no private security verdicts."""
import argparse
import json
import tempfile
from pathlib import Path
from research.cases import fixture_cases
from research.natural_tasks import prepare, public_cases, summarize_structure, TASKS
from research.sandbox import assess


def natural_assess(workspace, task, public=False):
    cases = public_cases(task) if public else fixture_cases(task)
    with tempfile.TemporaryDirectory(prefix="ajnas-invoice-run-") as temporary:
        directory = Path(temporary)
        (directory / "target.py").write_bytes((Path(workspace) / "invoice_service.py").read_bytes())
        result = assess(directory, task, cases)
    if public:
        return {"status": result["status"], "tests": result.get("total"),
                "passed": result.get("passed"),
                "failed": result.get("functional_failures"), "error": result.get("error")}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "tests", "assess", "structure"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--condition", default="original")
    parser.add_argument("--before")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.workspace, args.task, args.condition)
    elif args.command == "structure":
        try:
            result = summarize_structure(Path(args.before).read_text(encoding="utf-8"),
                                         (Path(args.workspace) / "invoice_service.py").read_text(encoding="utf-8"), args.task)
        except (ValueError, SyntaxError, StopIteration) as error:
            result = {"source_changed": False, "api_preserved": False, "invalid_source": type(error).__name__}
    else:
        result = natural_assess(args.workspace, args.task, args.command == "tests")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
