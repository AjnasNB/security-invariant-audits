"""Stage exactly the intended files; never send research logs/secrets as build context."""
import shutil
import subprocess
from pathlib import Path

from research.io import ROOT


def stage(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files = [
        ".runtime/codex-release/bin/codex-x86_64-unknown-linux-musl",
        ".runtime/claude-release/bin/package/claude",
        "harnesses/Dockerfile", "harnesses/mcp_proxy.py", "harnesses/openhands_worker.py",
    ]
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for relative in ("_sources/openhands_sdk/openhands-sdk", "_sources/claude_agent_sdk"):
        shutil.copytree(ROOT / relative, destination / relative, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "node_modules"))
    return destination


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    print(stage(args.destination), flush=True)
