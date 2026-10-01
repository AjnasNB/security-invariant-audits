"""Fresh ordinary/paper-known-positive trials; use from WSL, never host agent access."""
import argparse
import ast
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from harnesses.ordinary_broker import OrdinaryBroker, TOOLS
from harnesses.ordinary_launch import HOST_IP, IMAGE, launch
from harnesses.ordinary_protocol import protocol, VERSION, PRIMARY
from harnesses.ordinary_provider import Provider, BudgetStop
from harnesses.response_text import response_text
from research.io import ROOT, digest, read_json, utc_now, write_json
from research.natural_bridge import natural_assess
from research.natural_tasks import prepare, summarize_structure


class Controller:
    def __init__(self, directory, limits):
        self.provider = Provider(directory, limits)
        self.capability = ""
        self.broker = None
        self.mode = None
        self.sealed = False

    def rpc(self, body):
        if self.mode == "prediction":
            raise PermissionError("No project tools in an output-prediction question")
        if body.get("method") == "tools/list":
            return {"result": {"tools": TOOLS}}
        if body.get("method") == "tools/call":
            params = body.get("params", {})
            try:
                result = self.broker.execute(params["name"], params.get("arguments", {}))
                return {"result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
            except Exception as error:
                return {"result": {"content": [{"type": "text", "text": json.dumps({
                    "error": type(error).__name__ + ": " + str(error)})}], "isError": True}}
        raise PermissionError("Method not supported")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        controller = self.server.controller
        if (urlsplit(self.path).path == "/v1/models" and
                self.headers.get("Authorization", "").removeprefix("Bearer ") == controller.capability):
            raw = json.dumps({"object": "list", "data": [{"id": "maqam-orchestrator-sol-6-1",
                "object": "model", "owned_by": "azure", "meta": {"n_ctx": 28000}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        controller = self.server.controller
        if self.headers.get("Authorization", "").removeprefix("Bearer ") != controller.capability:
            self.send_response(403)
            self.end_headers()
            return
        try:
            if controller.sealed:
                raise PermissionError("Task has finished")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 300000:
                raise ValueError("Request size limit")
            body = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == "/project/rpc":
                status, content_type, raw = 200, "application/json", json.dumps(controller.rpc(body)).encode()
            else:
                # Actual CLI/SDK instructions are unchanged. Native tools denied
                # by configuration are not presented as authorized model tools.
                if controller.mode == "coding" and isinstance(body.get("tools"), list):
                    filtered = []
                    allowed = {tool["name"] for tool in TOOLS}
                    for tool in body["tools"]:
                        if tool.get("type") == "namespace":
                            members = [item for item in tool.get("tools", [])
                                       if item.get("type") == "function" and item.get("name") in allowed]
                            if members:
                                filtered.append({**tool, "tools": members})
                        elif tool.get("type") == "function" and (
                                any(name in tool.get("name", "") for name in allowed)
                                or tool.get("name") == "finish"):
                            filtered.append(tool)
                    write_json(controller.provider.current / f"advertised-tools-{controller.provider.run_requests+1}.json",
                               {"original": body["tools"], "forwarded": filtered})
                    body["tools"] = filtered
                if controller.mode == "prediction":
                    # FinishTool is OpenHands' completion signal, not an execution tool.
                    body["tools"] = [tool for tool in body.get("tools", []) if tool.get("name") == "finish"]
                status, content_type, raw = controller.provider.model(path, body)
        except Exception as error:
            status, content_type, raw = 400, "application/json", json.dumps({
                "error": {"message": type(error).__name__ + ": " + str(error), "type": "experiment_limit"}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass


def questions():
    source = read_json(ROOT / "reports/mucoco-author-replay-v1.json")
    rows = []
    for case in source["selected"]:
        for condition, filename in (("original", "original.py"), ("mutant", "mutant.py")):
            code = (ROOT / "evidence/mucoco-author-replay-v1" / case["task_id"] / filename).read_text()
            call = case["function"] + "(" + ", ".join(repr(item) for item in case["input"]) + ")"
            prompt = (f"What does this Python call return? Reply with only the Python value.\n\n"
                      f"{code}\nCall: {call}")
            rows.append({"id": case["task_id"] + ":" + condition, "task": case["task_id"],
                         "condition": condition, "prompt": prompt, "expected": case["expected"],
                         "program_sha256": digest(code), "known_positive_source": True})
    return rows


def model_text(records, directory):
    for item in reversed(records):
        text = response_text((directory / f"provider-{item['number']}-response.sse").read_text(encoding="utf-8"))
        if text is not None:
            return text
    return None


def run(engine, mode, output, single=False, select_task="access_helper", condition="original",
        start_index=0, post_transport=False, remaining_questions=False):
    if os.name == "nt":
        raise RuntimeError("Run in Ubuntu/WSL for the isolated network relay")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    specification = protocol()
    write_json(output / "protocol.json", specification)
    write_json(ROOT / "protocols" / (VERSION + ".json"), specification)
    limits = specification[mode + "_limits_per_primary_agent"]
    if post_transport:
        followup = read_json(ROOT / "protocols/open-harness-post-transport-v1.json")
        if engine != "codex":
            raise ValueError("This follow-up allocation only permits Codex continuation")
        limits = {**limits, "reference_cap_usd": followup["codex_" + mode + "_cap_usd"]}
    if remaining_questions:
        if mode != "prediction" or engine not in ("opencode", "openhands") or post_transport:
            raise ValueError("Only registered missing prediction questions can use this allocation")
        followup = read_json(ROOT / "protocols/remaining-paper-questions-v1.json")
        limits = {**limits, "reference_cap_usd": followup[engine + "_reference_cap_usd"]}
    controller = Controller(output, limits)
    controller.provider.authenticate()
    controller.mode = mode
    schedule = ([{"task": select_task, "condition": condition, "arm": "preflight", "repetition": 0}]
                if single else specification["schedule"]) if mode == "coding" else questions()
    if start_index:
        if mode != "coding" or not post_transport or start_index != 8:
            raise ValueError("Only the registered unattempted Codex continuation can skip rows")
        schedule = schedule[start_index:]
    if remaining_questions:
        schedule = [row for row in schedule if row["id"] in followup["selection"][engine]]
    write_json(output / "schedule.json", schedule)
    write_json(output / "configuration.json", {
        "started_at": utc_now(), "engine": engine, "mode": mode, "image": IMAGE, "limits": limits,
        "azure_credentials_in_agent": False, "native_system_prompt_unchanged": True,
        "tool_adaptation": "Same four ordinary extension tools; native unavailable tools filtered "
                           "in the relay as explicitly recorded per request",
        "scope": "Restricted agent release/SDK loop; not source-built whole-core test or ranking",
        "post_transport_followup": post_transport, "schedule_start_index": start_index,
        "remaining_questions_followup": remaining_questions,
    })
    server = ThreadingHTTPServer((HOST_IP, 0), Handler)
    server.controller = controller
    threading.Thread(target=server.serve_forever, daemon=True).start()
    rows = []
    try:
        for index, item in enumerate(schedule):
            directory = output / f"{index+1:03}-{item['task'].replace('/', '-')}-{item['condition']}"
            directory.mkdir()
            workspace = directory / "workspace"
            if mode == "coding":
                prepared = prepare(workspace, item["task"], item["condition"])
                prompt = prepared["prompt"] + "\n\nProject files:\n" + "\n".join(sorted(path.name for path in workspace.iterdir()))
                before = (workspace / "invoice_service.py").read_text()
                (directory / "input.py").write_bytes((workspace / "invoice_service.py").read_bytes())
                controller.broker = OrdinaryBroker(workspace, item["task"], directory)
                write_json(directory / "input.json", {**prepared, "agent_prompt": prompt})
            else:
                workspace.mkdir()
                prompt = item["prompt"]
                write_json(directory / "input.json", item)
            controller.provider.select(directory)
            controller.capability = secrets.token_hex(24)
            controller.sealed = False
            usage_before, reference_before = controller.provider.usage.copy(), controller.provider.reference
            metadata_before = len(controller.provider.records)
            print(f"{engine}/{mode} {index+1}/{len(schedule)} {item['task']}/{item['condition']}", flush=True)
            launched = launch(engine, mode, workspace, directory, prompt, controller.capability,
                              server.server_port, limits["wall_seconds"])
            controller.sealed = True
            if controller.broker:
                controller.broker.sealed = True
            (directory / "stdout.jsonl").write_text(launched.pop("stdout"), encoding="utf-8", newline="\n")
            stderr = launched.pop("stderr")
            (directory / "stderr.txt").write_text(stderr, encoding="utf-8", newline="\n")
            termination = ("budget_stopped" if controller.provider.budget_stop else
                           "timed_out" if launched["timeout"] else "completed" if launched["exit_code"] == 0 else "failed")
            row = {**item, "engine": engine, "mode": mode, "run_id": directory.name, **launched,
                   "termination": termination, "budget_stop": controller.provider.budget_stop,
                   "stderr_excerpt": stderr[-1000:],
                   "usage": {key: controller.provider.usage[key] - usage_before[key] for key in usage_before},
                   "reference_estimate_usd": controller.provider.reference - reference_before}
            if mode == "coding":
                after = (workspace / "invoice_service.py").read_text()
                (directory / "candidate.py").write_bytes((workspace / "invoice_service.py").read_bytes())
                try:
                    structure = summarize_structure(before, after, item["task"])
                except (SyntaxError, StopIteration):
                    structure = {"source_changed": False, "api_preserved": False}
                assessment = natural_assess(workspace, item["task"])
                public = any(event["phase"] == "completed" and event["tool"] == "run_tests"
                             and event["result"].get("status") == "assessed"
                             and event["result"].get("failed") == 0 for event in controller.broker.events)
                note_read = any(event["phase"] == "completed" and event["tool"] == "inspect_file"
                                and event["result"].get("path") == "project_notes.md" for event in controller.broker.events)
                row.update({"structure": structure, "assessment": assessment, "tests_run": public,
                            "note_read": note_read, "source_sha256": digest(before), "candidate_sha256": digest(after),
                            "task_completed": termination == "completed" and structure["source_changed"]
                                and structure["api_preserved"] and public})
                print(f"  completed={row['task_completed']}; checks={assessment['passed']}/{assessment['total']}; "
                      f"leaks={assessment['security_failures']}; termination={termination}", flush=True)
            else:
                text = model_text(controller.provider.records[metadata_before:], directory)
                try:
                    value = ast.literal_eval(text.strip()) if text else None
                    valid = type(value) is type(item["expected"])
                except (SyntaxError, ValueError):
                    value, valid = None, False
                row.update({"text": text, "observed": value, "output_valid": valid,
                            "correct": termination == "completed" and valid and value == item["expected"]})
                print(f"  answer={text!r}; correct={row['correct']}; termination={termination}", flush=True)
            write_json(directory / "run.json", row)
            rows.append(row)
            write_json(output / "results.json", {"engine": engine, "mode": mode, "results": rows,
                                                "reference_estimate_usd": controller.provider.reference})
            if controller.provider.budget_stop and controller.provider.budget_stop != "Per-run request cap reached":
                print("Frozen batch cap reached; no replacement generation.", flush=True)
                break
        write_json(output / "results.json", {"engine": engine, "mode": mode, "completed_at": utc_now(),
            "scheduled": len(schedule), "results": rows, "reference_estimate_usd": controller.provider.reference})
    finally:
        controller.provider.save()
        server.shutdown()
        server.server_close()
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=PRIMARY)
    parser.add_argument("--mode", choices=("coding", "prediction"), default="coding")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--task", default="access_helper")
    parser.add_argument("--condition", default="original")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--post-transport", action="store_true")
    parser.add_argument("--remaining-questions", action="store_true")
    args = parser.parse_args()
    run(args.engine, args.mode, args.output, args.single, args.task, args.condition,
        args.start_index, args.post_transport, args.remaining_questions)
