"""Small native Goose/Aider compatibility runs, separately labeled from primary arms."""
import argparse
import ast
import base64
import json
import secrets
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from harnesses.ordinary_broker import OrdinaryBroker
from harnesses.ordinary_launch import HOST_IP, NETWORK
from harnesses.ordinary_runner import Controller, Handler
from research.io import ROOT, digest, utc_now, write_json
from research.natural_bridge import natural_assess
from research.natural_tasks import TASKS, prepare, summarize_structure


def run(engine, output, model_identity_fixed=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    limits = {"max_http_attempts": 24, "max_requests_per_run": 8, "max_output_tokens": 1536,
              "max_input_estimate": 22000, "reference_cap_usd": .06,
              "conservative_cap_usd": .6, "wall_seconds": 150}
    if model_identity_fixed:
        if engine != "aider":
            raise ValueError("Only the registered Aider model-identity correction may retry")
        limits["reference_cap_usd"] = .035
    controller = Controller(output, limits)
    controller.mode = "optional" if engine == "aider" else "coding"
    controller.provider.authenticate()
    server = ThreadingHTTPServer((HOST_IP, 0), Handler)
    server.controller = controller
    threading.Thread(target=server.serve_forever, daemon=True).start()
    write_json(output / "configuration.json", {
        "engine": engine, "started_at": utc_now(), "limits": limits,
        "schedule": [{"task": task, "condition": "original"} for task in TASKS],
        "scope": "Three-original-task native compatibility smoke; no matched arms or ranking",
        "model_identity_followup": model_identity_fixed,
        "tool_policy": "Goose four MCP tools; Aider native text editing/tests on an isolated "
                       "writable temporary copy. No Azure credentials in the agent.",
    })
    rows = []
    try:
        for index, task in enumerate(TASKS):
            directory = output / f"{index+1:03}-{task}-original"
            directory.mkdir()
            workspace, settings = directory / "workspace", directory / "settings"
            settings.mkdir()
            prepared = prepare(workspace, task, "original")
            prompt = prepared["prompt"] + "\n\nProject files:\nREADME.md\ninvoice_service.py\ntest_invoice_service.py"
            (settings / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
            write_json(directory / "input.json", {**prepared, "agent_prompt": prompt})
            before = (workspace / "invoice_service.py").read_bytes()
            (directory / "input.py").write_bytes(before)
            controller.capability = secrets.token_hex(24)
            controller.sealed = False
            controller.broker = OrdinaryBroker(workspace, task, directory)
            controller.provider.select(directory)
            cost_before, usage_before = controller.provider.reference, controller.provider.usage.copy()
            url = f"http://{HOST_IP}:{server.server_port}"
            environment = {"PROJECT_PROXY_URL": url, "PROJECT_RUN_CAPABILITY": controller.capability}
            if engine == "goose":
                environment.update({"GOOSE_PROVIDER": "openai", "GOOSE_MODEL": "maqam-orchestrator-sol-6-1",
                    "GOOSE_MODE": "auto", "OPENAI_API_KEY": controller.capability, "OPENAI_BASE_URL": url + "/v1",
                    "OPENAI_BASE_PATH": "v1/responses", "GOOSE_MAX_TOKENS": "1536", "GOOSE_CONTEXT_LIMIT": "28000",
                    "GOOSE_THINKING_EFFORT": "low", "OPENAI_TIMEOUT": "65"})
                arguments = ["goose", "run", "--no-profile", "--no-session", "--max-turns", "8",
                    "--output-format", "json", "--with-extension", "project:python /opt/project/ordinary_mcp.py",
                    "--instructions", "/run/prompt.txt", "--provider", "openai", "--model", "maqam-orchestrator-sol-6-1"]
                image = "ajnas-goose-ordinary:20261001"
            else:
                model_name = "openai/maqam-orchestrator-sol-6-1"
                model_settings = [{"name": model_name, "edit_format": "whole", "weak_model_name": model_name,
                    "use_repo_map": False, "use_temperature": False,
                    "extra_params": {"max_completion_tokens": 1536}}]
                (settings / "model-settings.yml").write_text(
                    json.dumps(model_settings), encoding="utf-8", newline="\n")
                environment.update({"OPENAI_API_BASE": url + "/v1", "OPENAI_API_KEY": controller.capability,
                                    "AIDER_ANALYTICS": "false", "LITELLM_LOCAL_MODEL_COST_MAP": "true"})
                # Only a throwaway target is copied back, by a controller-owned wrapper.
                wrapper = """import base64,json,pathlib,shutil,subprocess,os
root=pathlib.Path('/tmp/task');root.mkdir()
for source in pathlib.Path('/task').iterdir():
    if source.is_file():shutil.copyfile(source,root/source.name)
command=['aider','--model','openai/maqam-orchestrator-sol-6-1','--weak-model','openai/maqam-orchestrator-sol-6-1',
 '--model-settings-file','/run/model-settings.yml','--no-git','--no-auto-commits','--no-analytics',
 '--no-check-update','--no-stream','--no-auto-lint','--yes-always','--map-tokens','0',
 '--auto-test','--test-cmd','python -B -m unittest -v','--read','README.md','--read','test_invoice_service.py',
 '--message-file','/run/prompt.txt','invoice_service.py']
result=subprocess.run(command,cwd=root)
print('PROJECT_CANDIDATE:'+base64.b64encode((root/'invoice_service.py').read_bytes()).decode(),flush=True)
print('PROJECT_CONTEXT:'+json.dumps({name:(root/name).read_text() for name in ('README.md','test_invoice_service.py')}),flush=True)
raise SystemExit(result.returncode)
"""
                (settings / "aider_wrapper.py").write_text(wrapper, encoding="utf-8", newline="\n")
                arguments, image = ["python", "-B", "/run/aider_wrapper.py"], "ajnas-aider-ordinary:20261001"
            name = "ajnas-optional-" + secrets.token_hex(6)
            command = ["docker", "run", "--rm", "--name", name, "--network", NETWORK,
                "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--user", "65534:65534", "--memory", "1536m", "--cpus", "2", "--pids-limit", "96",
                "--tmpfs", "/tmp:rw,nosuid,size=384m", "--workdir", "/task",
                "--mount", f"type=bind,source={workspace},target=/task,readonly",
                "--mount", f"type=bind,source={settings},target=/run,readonly"]
            for key, value in environment.items():
                command += ["-e", f"{key}={value}"]
            command += [image, *arguments]
            print(f"{engine} {index+1}/3 {task}", flush=True)
            started = time.monotonic()
            try:
                executed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=150)
                stdout, stderr, code = executed.stdout, executed.stderr, executed.returncode
            except subprocess.TimeoutExpired as error:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
                stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
                stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
                code = 124
            controller.sealed, controller.broker.sealed = True, True
            (directory / "stdout.txt").write_text(stdout, encoding="utf-8", newline="\n")
            (directory / "stderr.txt").write_text(stderr, encoding="utf-8", newline="\n")
            context_preserved = True
            if engine == "aider":
                candidates = [line[len("PROJECT_CANDIDATE:"):] for line in stdout.splitlines()
                              if line.startswith("PROJECT_CANDIDATE:")]
                if len(candidates) == 1:
                    candidate = base64.b64decode(candidates[0], validate=True)
                    if len(candidate) > 64000:
                        raise RuntimeError("Optional candidate output too large")
                    (workspace / "invoice_service.py").write_bytes(candidate)
                contexts = [json.loads(line[len("PROJECT_CONTEXT:"):]) for line in stdout.splitlines()
                            if line.startswith("PROJECT_CONTEXT:")]
                context_preserved = len(contexts) == 1 and all(
                    contexts[0][name] == (workspace / name).read_text() for name in ("README.md", "test_invoice_service.py"))
            candidate = (workspace / "invoice_service.py").read_bytes()
            (directory / "candidate.py").write_bytes(candidate)
            structure = summarize_structure(before.decode(), candidate.decode(), task)
            assessment = natural_assess(workspace, task)
            tests_run = (any(event["tool"] == "run_tests" and event["phase"] == "completed"
                            and event["result"].get("failed") == 0 for event in controller.broker.events)
                         if engine == "goose" else "Ran 3 tests" in stdout + stderr and "\nOK" in stdout + stderr)
            termination = ("budget_stopped" if controller.provider.budget_stop else
                           "timed_out" if code == 124 else "completed" if code == 0 else "failed")
            row = {"engine": engine, "mode": "coding", "task": task, "condition": "original", "arm": "compatibility",
                   "repetition": 0, "run_id": directory.name, "termination": termination, "exit_code": code,
                   "budget_stop": controller.provider.budget_stop, "elapsed_seconds": time.monotonic() - started,
                   "structure": structure, "assessment": assessment, "tests_run": tests_run, "note_read": False,
                   "context_preserved": context_preserved, "source_sha256": digest(before),
                   "candidate_sha256": digest(candidate), "task_completed": termination == "completed"
                   and structure["source_changed"] and structure["api_preserved"] and tests_run and context_preserved,
                   "usage": {key: controller.provider.usage[key] - usage_before[key] for key in usage_before},
                   "reference_estimate_usd": controller.provider.reference - cost_before,
                   "stderr_excerpt": stderr[-1000:]}
            write_json(directory / "run.json", row)
            rows.append(row)
            write_json(output / "results.json", {"engine": engine, "mode": "coding", "scheduled": 3,
                                               "results": rows, "reference_estimate_usd": controller.provider.reference})
            print(f"  completed={row['task_completed']}; checks={assessment['passed']}/{assessment['total']}; "
                  f"leaks={assessment['security_failures']}; termination={termination}", flush=True)
            if controller.provider.budget_stop:
                break
    finally:
        controller.provider.save()
        server.shutdown()
        server.server_close()
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("aider", "goose"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-identity-fixed", action="store_true")
    args = parser.parse_args()
    run(args.engine, args.output, args.model_identity_fixed)
