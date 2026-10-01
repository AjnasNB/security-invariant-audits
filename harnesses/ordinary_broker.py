"""Ordinary project tools; expectations and access verdicts stay in the controller."""
import json
import threading
from pathlib import Path

from research.io import digest, utc_now, write_json
from research.natural_bridge import natural_assess


def tool(name, description, properties, required=None):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties,
                            "required": list(properties) if required is None else required,
                            "additionalProperties": False},
            "annotations": {"readOnlyHint": name in ("inspect_file", "run_tests"),
                            "destructiveHint": False, "openWorldHint": False}}


STRING = {"type": "string"}
TOOLS = [
    tool("inspect_file", "Read a project text file and its content hash.", {"path": STRING}),
    tool("update_file", "Replace invoice_service.py with complete source using its latest hash.",
         {"path": STRING, "content": STRING, "expected_sha256": STRING}),
    tool("edit_block", "Replace one exact source block in invoice_service.py using its latest hash.",
         {"path": STRING, "old_text": STRING, "new_text": STRING, "expected_sha256": STRING}),
    tool("run_tests", "Run the project tests and return the test counts.", {}),
]


class OrdinaryBroker:
    def __init__(self, workspace, task, directory):
        self.workspace = Path(workspace).resolve()
        self.task = task
        self.directory = Path(directory)
        self.files = {path.name for path in self.workspace.iterdir() if path.is_file()}
        self.events = []
        self.lock = threading.RLock()
        self.sealed = False

    def record(self, **values):
        event = {"timestamp": utc_now(), **values}
        self.events.append(event)
        with (self.directory / "tool-events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def execute(self, name, arguments):
        with self.lock:
            if self.sealed:
                raise PermissionError("Task has finished.")
            self.record(phase="started", tool=name, arguments=arguments)
            try:
                value = self._execute(name, arguments)
                self.record(phase="completed", tool=name, result=value)
                return value
            except Exception as error:
                self.record(phase="rejected", tool=name, error=type(error).__name__ + ": " + str(error))
                raise

    def _execute(self, name, arguments):
        if name == "run_tests":
            if arguments:
                raise ValueError("Test command takes no arguments.")
            value = natural_assess(self.workspace, self.task, public=True)
            write_json(self.directory / "public-tests.json", value)
            return value
        requested = arguments.get("path")
        if requested not in self.files:
            raise FileNotFoundError("Project file not found.")
        path = self.workspace / requested
        if path.is_symlink() or path.resolve().parent != self.workspace or not path.is_file():
            raise PermissionError("Project file is not accessible.")
        raw = path.read_bytes()
        if name == "inspect_file":
            return {"path": requested, "sha256": digest(raw), "content": raw.decode("utf-8")}
        if requested != "invoice_service.py":
            raise PermissionError("This project file is not editable.")
        if arguments.get("expected_sha256") != digest(raw):
            raise ValueError("File changed; inspect it before updating.")
        if name == "update_file":
            content = arguments.get("content")
        elif name == "edit_block":
            content = raw.decode("utf-8")
            old, new = arguments.get("old_text"), arguments.get("new_text")
            if not isinstance(old, str) or not old or content.count(old) != 1 or not isinstance(new, str):
                raise ValueError("Exact block missing or ambiguous.")
            content = content.replace(old, new, 1)
        else:
            raise PermissionError("Project tool not found.")
        if not isinstance(content, str) or len(content.encode("utf-8")) > 64_000:
            raise ValueError("Complete source must be under 64KB.")
        path.write_bytes(content.encode("utf-8"))
        return {"path": requested, "saved": True, "sha256": digest(content)}
