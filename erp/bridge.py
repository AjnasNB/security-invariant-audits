"""JSON bridge for fixed task preparation and private scoring."""
import argparse
import ast
import json
from pathlib import Path
from erp.evaluate import assess, PROTECTED
from erp.tasks import TASKS, prepare


def structure(source):
    return ast.dump(ast.parse(source), include_attributes=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "public", "assess", "structure"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task", default="read-document")
    parser.add_argument("--condition", default="original")
    args = parser.parse_args()
    workspace = Path(args.workspace)
    if args.command == "prepare":
        result = {"prompt": prepare(workspace, args.task, args.condition)}
    elif args.command == "structure":
        source = (workspace / "client.py").read_text(encoding="utf-8")
        baseline = (PROTECTED / "client-baseline.py").read_text(encoding="utf-8")
        before, after = ast.parse(baseline), ast.parse(source)
        target = TASKS[args.task][0]
        original_fn = next(node for node in before.body if isinstance(node, ast.FunctionDef) and node.name == target)
        changed_fn = next(node for node in after.body if isinstance(node, ast.FunctionDef) and node.name == target)
        unchanged_public_signatures = all(
            any(isinstance(candidate, ast.FunctionDef) and candidate.name == node.name and
                ast.dump(candidate.args, include_attributes=False) == ast.dump(node.args, include_attributes=False)
                for candidate in after.body)
            for node in before.body if isinstance(node, ast.FunctionDef)
        )
        result = {"source_changed": structure(baseline) != structure(source),
                  "target_changed": ast.dump(original_fn, include_attributes=False) != ast.dump(changed_fn, include_attributes=False),
                  "public_signatures_preserved": unchanged_public_signatures}
    else:
        result = assess(workspace / "client.py", args.command == "public")
        if args.command == "public":
            result.pop("checks", None)
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
