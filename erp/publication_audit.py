"""Bounded audit of the Git index; private values are checked but never printed."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

FORBIDDEN = ("erp/private/", "erp/protected/", "erp/runtime/", "erp/vendor/", "erp/runs/",
             "_sources/", ".runtime/", "node_modules/", "datasets/restricted/", "tmp/", "output/qa/",
             "artifacts/private/")
FORBIDDEN += (".qarinah/", ".local/", ".venv/", "output/pdf/")
PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,200}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,200}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{15,2048}\.[A-Za-z0-9_-]{15,2048}\.[A-Za-z0-9_-]{15,2048}"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worktree", action="store_true",
                        help="Read clean tracked worktree files directly; reject differing staged/working contents")
    parser.add_argument("--since",
                        help="Audit only tracked files changed from this reviewed Git base to HEAD")
    args = parser.parse_args()
    repo = args.repo.resolve()
    files = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"]).decode().split("\0")
    files = [name for name in files if name]
    if args.since:
        changed = set(subprocess.check_output(["git", "-C", str(repo), "diff", "--name-only",
                                               "--diff-filter=ACMR", args.since, "HEAD"]).decode().splitlines())
        files = [name for name in files if name in changed]
    if args.worktree:
        differences = subprocess.check_output(["git", "-C", str(repo), "diff", "--name-only"]).decode().strip()
        if differences:
            raise RuntimeError("Worktree audit requires tracked files to match the index")
    private_env = Path(__file__).resolve().parent / "private" / "experiment.env"
    private_values = [line.split("=", 1)[1].encode() for line in private_env.read_text().splitlines()] if private_env.exists() else []
    whole_private = repo / "artifacts/private/wholeapp-v1"
    if (whole_private / "private-runtime.json").exists():
        runtime = json.loads((whole_private / "private-runtime.json").read_text(encoding="utf-8"))
        private_values += [runtime[key].encode() for key in ("root_password", "app_password", "login_password")
                           if runtime.get(key)]
    if (whole_private / "api-credentials.json").exists():
        credentials = json.loads((whole_private / "api-credentials.json").read_text(encoding="utf-8"))
        private_values += [record[key].encode() for record in credentials.values()
                           for key in ("api_key", "api_secret") if record.get(key)]
    issues = []
    manifest = {}
    for index, name in enumerate(files):
        if index and index % 500 == 0:
            print(f"Audited {index}/{len(files)} tracked files.", flush=True)
        if any(name.startswith(prefix) for prefix in FORBIDDEN) or name.endswith((".env", ".sql", ".sql.gz")):
            issues.append({"path": name, "issue": "private/generated path tracked"})
        body = (repo / name).read_bytes() if args.worktree else subprocess.check_output(["git", "-C", str(repo), "show", ":" + name])
        if len(body) > 8_000_000:
            issues.append({"path": name, "issue": "large file needs explicit review"})
        # Exact private values are checked in every file. Text token patterns
        # need not scan binary media and cannot use unbounded regex backtracking.
        text_body = body if b"\0" not in body[:4096] else b""
        if any(pattern.search(text_body) for pattern in PATTERNS) or any(value and value in body for value in private_values):
            issues.append({"path": name, "issue": "possible credential/private value"})
        manifest[name] = hashlib.sha256(body).hexdigest()
    result = {"passed": not issues, "tracked_files": len(files), "reviewed_base": args.since,
              "issues": issues,
              "scope": "Git-index paths, common token/private-key patterns and exact original/disposable ERP passwords/API credentials; not an exhaustive secret detector",
              "values_disclosed": False, "file_hashes": manifest}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "file_hashes"}, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
