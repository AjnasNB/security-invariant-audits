"""Combine three non-overlapping accepted refactors; never merge blind text."""
import ast
import hashlib
import json
from pathlib import Path
from erp.evaluate import ROOT, PROTECTED, assess

SELECTION = [
    ("get", "1-read-document-original"),
    ("get_list", "3-list-documents-original"),
    ("delete_doc", "5-delete-document-original"),
]


def source_segment(source, node):
    lines = source.splitlines(keepends=True)
    start = min([node.lineno, *[decorator.lineno for decorator in getattr(node, "decorator_list", [])]])
    return "".join(lines[start - 1:node.end_lineno]), start, node.end_lineno


def main():
    baseline = (PROTECTED / "client-baseline.py").read_text(encoding="utf-8")
    original = ast.parse(baseline)
    names = {node.name for node in original.body if isinstance(node, ast.FunctionDef)}
    replacement = []
    helpers = {}
    for function, directory in SELECTION:
        location = ROOT / "erp" / "runs" / "pilot-20261001" / directory
        record = json.loads((location / "result.json").read_text())
        if not record["passed"]:
            raise RuntimeError("Cannot integrate a rejected candidate")
        candidate = (location / "candidate.py").read_text(encoding="utf-8")
        parsed = ast.parse(candidate)
        target = next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == function)
        old = next(node for node in original.body if isinstance(node, ast.FunctionDef) and node.name == function)
        if ast.dump(old.args) != ast.dump(target.args):
            raise RuntimeError("Candidate changed the public signature")
        content, _, _ = source_segment(candidate, target)
        _, start, end = source_segment(baseline, old)
        replacement.append((start, end, content))
        for node in parsed.body:
            if isinstance(node, ast.FunctionDef) and node.name not in names:
                content, _, _ = source_segment(candidate, node)
                if node.name in helpers and helpers[node.name] != content:
                    raise RuntimeError("Conflicting helper definitions")
                helpers[node.name] = content
    lines = baseline.splitlines(keepends=True)
    for start, end, content in sorted(replacement, reverse=True):
        lines[start - 1:end] = [content]
    combined = "".join(lines) + "\n\n" + "\n\n".join(helpers.values()) + "\n"
    ast.parse(combined)
    destination = ROOT / "erp" / "runtime"
    destination.mkdir(exist_ok=True)
    candidate = destination / "combined-client.py"
    candidate.write_text(combined, encoding="utf-8")
    result = assess(candidate)
    report = {"accepted_components": [item[1] for item in SELECTION],
        "public_signatures_preserved": True, "new_helpers": sorted(helpers),
        "baseline_sha256": hashlib.sha256(baseline.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(combined.encode()).hexdigest(),
        "assessment": result, "passed": result["status"] == "assessed" and result["functional_failures"] == 0}
    (destination / "integration-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "assessment"}, indent=2))
    print(f"Combined candidate: {result.get('passed')}/{result.get('total')} private checks.")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
