"""Complete-file, deterministic upstream context; never padding or judge values."""
import argparse
import json
import subprocess
from pathlib import Path

from hardstudy.catalog import NOTES, VAGUE_PROMPTS, prepare as fixture_prepare
from hardstudy.protocol import protocol
from research.io import ROOT, digest, write_json, utc_now

SOURCES = {"frappe": ROOT / "_sources/large-frappe", "erpnext": ROOT / "_sources/large-erpnext"}
PRIORITY = [
    ("frappe", "frappe/model/db_query.py"), ("frappe", "frappe/permissions.py"),
    ("frappe", "frappe/model/document.py"), ("frappe", "frappe/__init__.py"),
    ("erpnext", "erpnext/accounts/doctype/sales_invoice/sales_invoice.py"),
    ("erpnext", "erpnext/controllers/accounts_controller.py"),
]


def upstream_manifest():
    result = {}
    for name, root in SOURCES.items():
        tracked = subprocess.check_output(["git", "-C", str(root), "ls-files"], text=True).splitlines()
        result[name] = {
            "commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
            "tracked_files": len(tracked),
            "python_files": sum(path.endswith(".py") for path in tracked),
            "tracked_file_bytes": sum((root / path).stat().st_size for path in tracked if (root / path).is_file()),
            "license": "MIT" if name == "frappe" else "GPL-3.0",
            "repository": "https://github.com/frappe/" + name,
        }
    return result


def long_context():
    candidates = [*PRIORITY]
    candidates += [(source, path.relative_to(root).as_posix()) for source, root in SOURCES.items()
                   for path in sorted(root.rglob("*.py"))
                   if not path.name.startswith("test_") and (source, path.relative_to(root).as_posix()) not in PRIORITY]
    blocks, selected, chars = [], [], 0
    target, maximum = protocol()["context"]["long_target_characters"], protocol()["context"]["max_long_characters"]
    for source, relative in candidates:
        path = SOURCES[source] / relative
        if not path.is_file() or path.stat().st_size > 180000:
            continue
        code = path.read_text(encoding="utf-8")
        block = f"\n--- {source}/{relative} ---\n{code}\n"
        if chars + len(block) > maximum:
            continue
        blocks.append(block)
        selected.append({"source": source, "path": relative, "sha256": digest(path.read_bytes()),
                         "characters": len(code)})
        chars += len(block)
        if chars >= target:
            break
    if chars < target:
        raise RuntimeError("Complete-file source context did not reach the frozen target")
    return "".join(blocks), {"files": selected, "characters": chars, "complete_files": True}


def prepare(workspace, task, condition, context_size):
    workspace = Path(workspace)
    if task == "erp-invoices":
        workspace.mkdir(parents=True, exist_ok=False)
        (workspace / "frappe").mkdir()
        baseline = ROOT / "erp/protected/client-baseline.py"
        source = SOURCES["frappe"] / "frappe/client.py"
        if baseline.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
            raise RuntimeError("ERP reference source mismatch")
        (workspace / "frappe/client.py").write_bytes(source.read_bytes())
        (workspace / "README.md").write_text(
            "# ERP application\n\nFrappe request handlers are in frappe/client.py. "
            "The invoice screens and imports use these handlers. Related source is in the project tree. "
            "Engineering notes are in docs/query-layer.md.\n", encoding="utf-8", newline="\n")
        (workspace / "docs").mkdir()
        (workspace / "docs/query-layer.md").write_text(NOTES[condition], encoding="utf-8", newline="\n")
        metadata = {"task": task, "condition": condition, "prompt": VAGUE_PROMPTS[task]}
        editable = ["frappe/client.py"]
    else:
        metadata = fixture_prepare(workspace, task, condition)
        editable = ["service.py", "policy.py", "repository.py", "cache.py"]
    files = {path.relative_to(workspace).as_posix(): digest(path.read_bytes())
             for path in sorted(workspace.rglob("*")) if path.is_file()}
    blocks = []
    context_manifest = {"size": context_size}
    if context_size == "long":
        background, description = long_context()
        blocks.append("Project source:\n" + background)
        context_manifest.update(description)
    else:
        context_manifest.update({"files": [], "characters": 0, "complete_files": True})
    blocks.append("\nCurrent working files:\n")
    for filename in sorted(files):
        if filename.startswith("test_"):
            continue
        blocks.append(f"\n--- {filename} ---\n" + (workspace / filename).read_text(encoding="utf-8"))
    text = "\n".join(blocks)
    context_manifest.update({"sha256": digest(text), "total_characters": len(text),
                             "upstream": upstream_manifest()})
    return {**metadata, "context_size": context_size, "files": files, "editable": editable,
            "context": text, "context_manifest": context_manifest}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--condition", choices=("neutral", "stale"), required=True)
    parser.add_argument("--context", choices=("short", "long"), required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.workspace, args.task, args.condition, args.context)))
