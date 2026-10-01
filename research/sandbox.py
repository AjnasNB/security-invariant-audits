import json
import os
import subprocess
import uuid
from pathlib import Path

from research.io import ROOT, digest, utc_now, write_json
from research.scoring import score_fixture, unknown

IMAGE = "ajnas-security-study:20261001"
APP_IMAGE = "ajnas-security-app:20261001"


def linux_path(path):
    path = Path(path).resolve()
    if os.name == "nt":
        return "/mnt/" + path.drive[0].lower() + "/" + path.as_posix()[3:]
    return str(path)


def docker_prefix():
    return ["wsl", "-d", "Ubuntu", "--", "docker"] if os.name == "nt" else ["docker"]


def run_container(workspace, python_args, stdin="", extra_mounts=(), timeout=45,
                  image=IMAGE, output_limit=2_000_000):
    name = "ajnas-" + uuid.uuid4().hex[:12]
    arguments = docker_prefix() + [
        "run", "--rm", "-i", "--name", name, "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "--memory", "768m", "--cpus", "1", "--pids-limit", "64",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m",
        "--mount", f"type=bind,source={linux_path(workspace)},target=/task,readonly",
        "--workdir", "/task",
    ]
    for host_path, destination in extra_mounts:
        arguments += ["--mount", f"type=bind,source={linux_path(host_path)},target={destination},readonly"]
    arguments += [image, "python", "-B", *python_args]
    try:
        result = subprocess.run(arguments, input=stdin, text=True, capture_output=True,
                                encoding="utf-8", timeout=timeout)
        if len(result.stdout) > output_limit or len(result.stderr) > 200_000:
            raise RuntimeError("Candidate output exceeds research limit")
        return result
    except subprocess.TimeoutExpired:
        subprocess.run(docker_prefix() + ["rm", "-f", name], capture_output=True, timeout=20)
        raise


def assess(workspace, task_id, cases):
    payload = {"task_id": task_id, "cases": [
        {key: value for key, value in case.items() if key not in ("expected", "security_case")}
        for case in cases
    ]}
    try:
        result = run_container(workspace, ["/adapter/worker.py"], json.dumps(payload), [
            (ROOT / "research" / "worker.py", "/adapter/worker.py"),
            (ROOT / "research" / "app_worker.py", "/adapter/app_worker.py"),
        ], image=APP_IMAGE if task_id == "fastapi_items" else IMAGE)
    except subprocess.TimeoutExpired:
        return unknown("Candidate execution timed out; named container cleanup requested", len(cases))
    if result.returncode:
        return {**unknown(result.stderr[-2000:], len(cases)), "exit_code": result.returncode}
    try:
        observations = json.loads(result.stdout)
        score = score_fixture(task_id, cases, observations)
    except (ValueError, TypeError, KeyError) as error:
        return {**unknown(str(error), len(cases)), "stdout": result.stdout[-1000:]}
    return {**score, "stderr": result.stderr[-1000:]}


def probe(image=IMAGE):
    code = r'''
import json, os, socket
checks = {}
checks["non_root"] = os.getuid() != 0
checks["no_provider_credentials"] = not any("TOKEN" in key or "API_KEY" in key or key.startswith("AZURE") for key in os.environ)
checks["no_developer_home"] = not os.path.exists("/mnt/c/Users") and not os.path.exists("/root/.azure")
checks["no_docker_socket"] = not os.path.exists("/var/run/docker.sock")
try:
    open("/task/should-not-write", "w").close()
    checks["task_read_only"] = False
except OSError:
    checks["task_read_only"] = True
try:
    open("/etc/should-not-write", "w").close()
    checks["root_read_only"] = False
except OSError:
    checks["root_read_only"] = True
try:
    socket.create_connection(("1.1.1.1", 443), timeout=1).close()
    checks["outbound_blocked"] = False
except OSError:
    checks["outbound_blocked"] = True
status = open("/proc/self/status").read()
checks["capabilities_dropped"] = "CapEff:\t0000000000000000" in status
checks["no_new_privileges"] = "NoNewPrivs:\t1" in status
print(json.dumps(checks))
'''
    result = run_container(ROOT / "tasks" / "access_helper", ["-c", code], timeout=25, image=image)
    if result.returncode:
        raise RuntimeError(result.stderr)
    checks = json.loads(result.stdout)
    record = {"tested_at": utc_now(), "image": image, "checks": checks, "passed": all(checks.values()),
              "probe_sha256": digest(code),
              "limitation": "Configured container restrictions; not a proof of containment against kernel exploits."}
    filename = "sandbox_probe_app.json" if image == APP_IMAGE else "sandbox_probe.json"
    write_json(ROOT / "artifacts" / filename, record)
    if not record["passed"]:
        raise RuntimeError("Sandbox probe failed")
    return record


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
