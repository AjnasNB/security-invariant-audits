"""Read-only runtime/source provenance for the completed open-harness extension."""
import json
import os
import subprocess
from pathlib import Path

from research.io import ROOT, digest, utc_now, write_json


def docker(*arguments):
    prefix = ["wsl", "-d", "Ubuntu", "--", "docker"] if os.name == "nt" else ["docker"]
    return subprocess.check_output([*prefix, *arguments], text=True, encoding="utf-8", timeout=30).strip()


def main():
    images = {}
    for image in ("ajnas-open-harness-ordinary:20261001", "ajnas-goose-ordinary:20261001",
                  "ajnas-aider-ordinary:20261001", "ajnas-security-study:20261001"):
        value = json.loads(docker("image", "inspect", image))[0]
        images[image] = {"id": value["Id"], "created": value["Created"], "configured_user": value["Config"]["User"]}
    binaries = {}
    candidates = {
        "codex_cli": Path("D:/SUTD/.runtime/codex-release/bin/codex-x86_64-unknown-linux-musl"),
        "opencode": ROOT / ".runtime/opencode-release-v1.18.34/opencode",
        "goose": ROOT / ".runtime/goose-release-v1.52.0/goose",
    }
    for name, path in candidates.items():
        binaries[name] = {"sha256": digest(path.read_bytes()), "file_size": path.stat().st_size}
    record = {"recorded_at": utc_now(), "images": images, "binary_hashes": binaries,
              "official_archive_checksums": {
                  "opencode-linux-x64-baseline.tar.gz": "24b0d458d21ef548b2752166303defcf7f4945b049fb4876ab78dfaf86d81b27",
                  "goose-x86_64-unknown-linux-musl.tar.gz": "fdc86653285a89f7dcad6e76736af1688ab2cde44661b089328b2fc40bb79f9f",
              },
              "selected_runtime_versions": {"codex_cli": "0.159.3", "opencode": "1.18.34",
                                            "openhands_sdk": "1.50.1", "goose": "1.52.0", "aider": "0.86.0"},
              "dependency_policy": "OpenHands uses existing package-declared research image; "
                                   "Aider dependencies are pinned by its 0.86.0 package in a separate Python 3.12 image. "
                                   "Not full upstream workspace locks or source builds.",
              "model_mapping": {"deployment": "maqam-orchestrator-sol-6-1", "model": "gpt-6.1-sol",
                                "version": "2026-09-29", "state": "Succeeded"},
              "agent_config_source_hashes": {path.relative_to(ROOT).as_posix(): digest(path.read_bytes())
                  for path in (ROOT / "harnesses").glob("ordinary_*.py")},
              "scope": "Read-only runtime identities; existing desktop apps and Azure configuration unchanged"}
    write_json(ROOT / "reports/open-harness-runtime-v1.json", record)
    print("Recorded four image identities and three executable hashes.")


if __name__ == "__main__":
    main()
