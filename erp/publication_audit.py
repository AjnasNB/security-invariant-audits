"""Bounded audit of the Git index; private values are checked but never printed."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

FORBIDDEN = ("erp/private/", "erp/protected/", "erp/runtime/", "erp/vendor/", "erp/runs/",
             "_sources/", ".runtime/", "node_modules/", "datasets/restricted/", "tmp/", "output/qa/")
PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    files = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"]).decode().split("\0")
    files = [name for name in files if name]
    private_env = Path(__file__).resolve().parent / "private" / "experiment.env"
    private_values = [line.split("=", 1)[1].encode() for line in private_env.read_text().splitlines()] if private_env.exists() else []
    issues = []
    manifest = {}
    for name in files:
        if any(name.startswith(prefix) for prefix in FORBIDDEN) or name.endswith((".env", ".sql", ".sql.gz")):
            issues.append({"path": name, "issue": "private/generated path tracked"})
        body = subprocess.check_output(["git", "-C", str(repo), "show", ":" + name])
        if len(body) > 8_000_000:
            issues.append({"path": name, "issue": "large file needs explicit review"})
        if any(pattern.search(body) for pattern in PATTERNS) or any(value and value in body for value in private_values):
            issues.append({"path": name, "issue": "possible credential/private value"})
        manifest[name] = hashlib.sha256(body).hexdigest()
    result = {"passed": not issues, "tracked_files": len(files), "issues": issues,
              "scope": "Git-index paths, common token/private-key patterns and exact local ERP passwords; not an exhaustive secret detector",
              "values_disclosed": False, "file_hashes": manifest}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "file_hashes"}, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
