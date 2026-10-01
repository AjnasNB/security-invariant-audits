"""Run bounded upstream component suites inside no-network containers.

No upstream source is modified. Test copies and logs use persistent Linux storage.
"""
import json
import os
import subprocess
from pathlib import Path

from research.io import ROOT, digest, utc_now, write_json

IMAGE = "ajnas-cross-harness:20261001"
OUTPUT = Path("/var/tmp/ajnas-sdk-checks-20261001")


def run_check(name, source, arguments, shell=False, timeout=150):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # The tmpfs is writable; source snapshots stay read-only.
    command = [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--memory", "1536m", "--cpus", "2",
        "--pids-limit", "100", "--tmpfs", "/tmp:rw,nosuid,size=256m",
        "--mount", f"type=bind,source={source},target=/source,readonly",
        "--workdir", "/source", "-e", "OPENHANDS_SUPPRESS_BANNER=1",
        "-e", "CODEX_EXEC_PATH=/usr/local/bin/codex", IMAGE,
    ]
    command += ["sh", "-c", arguments] if shell else arguments
    started = utc_now()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        exit_code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = 124
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr or ""
    (OUTPUT / f"{name}.stdout.txt").write_text(stdout, encoding="utf-8")
    (OUTPUT / f"{name}.stderr.txt").write_text(stderr, encoding="utf-8")
    record = {
        "name": name, "started_at": started, "completed_at": utc_now(), "exit_code": exit_code,
        "source": str(source), "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
        "summary_tail": (stdout + "\n" + stderr)[-1800:],
        "network": "none", "source_read_only": True,
        "scope": "Selected upstream component tests; not a full harness security audit.",
    }
    write_json(OUTPUT / f"{name}.json", record)
    print(json.dumps(record, indent=2), flush=True)
    return record


def main():
    if os.name == "nt":
        raise RuntimeError("Run source checks under Ubuntu/WSL.")
    checks = []
    checks.append(run_check(
        "claude-sdk-selected",
        ROOT / "_sources" / "claude_agent_sdk",
        ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--override-ini", "addopts=",
         "tests/test_message_parser.py", "tests/test_transport.py", "tests/test_tool_callbacks.py"],
    ))
    # The namespace package is added as a read-only import source; this only
    # supplies the upstream persistence models needed by five SDK secret tests.
    checks.append(run_check(
        "openhands-security-selected",
        ROOT / "_sources" / "openhands_sdk",
        "PYTHONPATH=/source/openhands-agent-server python -m pytest -q -p no:cacheprovider "
        "--override-ini addopts= tests/sdk/security/test_confirmation_policy.py "
        "tests/sdk/security/test_security_risk.py tests/sdk/tool/test_to_responses_tool_security.py "
        "tests/sdk/utils/test_pydantic_secrets.py",
        shell=True,
    ))
    checks.append(run_check(
        "codex-sdk-exec",
        ROOT / "_sources" / "codex_cli" / "sdk" / "typescript",
        "cp -a /source /tmp/sdk && ln -s /opt/codex-test-deps/node_modules /tmp/sdk/node_modules && "
        "cd /tmp/sdk && node /opt/codex-test-deps/node_modules/jest/bin/jest.js "
        "--config jest.config.cjs --runInBand --no-cache tests/exec.test.ts",
        shell=True,
    ))
    write_json(OUTPUT / "summary.json", {"recorded_at": utc_now(), "checks": checks})


if __name__ == "__main__":
    main()
