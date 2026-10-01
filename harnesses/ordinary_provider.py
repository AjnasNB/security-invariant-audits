"""Azure Responses relay with per-batch caps and no credential persistence."""
import json
import threading
import time
import urllib.error
import urllib.request

from harnesses.runner import azure_cli, token, terminal_response
from research.io import digest, utc_now, write_json


class BudgetStop(RuntimeError):
    pass


class Provider:
    def __init__(self, directory, limits, transport=None):
        self.directory = directory
        self.limits = limits
        self.lock = threading.RLock()
        self.transport = transport or urllib.request.urlopen
        self.bearer = None
        self.records = []
        self.current = directory
        self.run_requests = 0
        self.attempts = 0
        self.reference = 0.
        self.conservative = 0.
        self.unknown_usage = 0
        self.budget_stop = None
        self.pending = {}
        self.usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0,
                      "cached_tokens": 0, "cache_write_tokens": 0}

    def authenticate(self):
        metadata = azure_cli("cognitiveservices", "account", "deployment", "show",
            "-g", "rg-erpseeker-demo", "-n", "erpseeker-ai-9340a6",
            "--deployment-name", "maqam-orchestrator-sol-6-1",
            "--query", "{deployment:name,state:properties.provisioningState,model:properties.model}", "-o", "json")
        if (metadata["state"] != "Succeeded" or metadata["model"]["name"] != "gpt-6.1-sol"
                or metadata["model"]["version"] != "2026-09-29"):
            raise RuntimeError("Requested Azure model mapping did not verify")
        self.bearer = token("https://cognitiveservices.azure.com/")
        write_json(self.directory / "deployment.json", metadata)

    def select(self, directory):
        with self.lock:
            if self.pending:
                raise RuntimeError("Previous provider request still in flight; stop before starting another run")
            self.current = directory
            self.run_requests = 0
            self.budget_stop = None

    def save(self):
        write_json(self.directory / "usage.json", {
            **self.usage, "http_attempts": self.attempts, "reference_estimate_usd": self.reference,
            "conservative_debit_usd": self.conservative, "unknown_usage_attempts": self.unknown_usage,
            "limits": self.limits, "rates_per_million": {"input": 2, "cached": .1, "output": 10, "cache_write": 2.5},
            "assumption": "Cache-write tokens replace uncached input at 1.25x; no double charge.",
            "pricing": "Public Standard reference, not reconciled Azure invoice",
            "pending_requests": self.pending,
        })

    def model(self, path, body):
        with self.lock:
            chat = path.endswith("/chat/completions")
            if not path.endswith("/responses") and not chat:
                raise PermissionError("Configured provider requires the Responses endpoint")
            if chat and body.get("tools"):
                raise PermissionError("Sol Chat Completions supports this text-only compatibility test, not tools")
            if body.get("model") not in ("maqam-orchestrator-sol-6-1", "openai/maqam-orchestrator-sol-6-1"):
                raise PermissionError("Model is fixed; no alternative or small-model route")
            body["model"] = "maqam-orchestrator-sol-6-1"
            if chat:
                body["reasoning_effort"] = "low"
                body.pop("temperature", None)
                body["stream"] = False
                requested_maximum = body.pop("max_tokens", None) or body.get("max_completion_tokens")
                output_key = "max_completion_tokens"
            else:
                body["reasoning"] = {**body.get("reasoning", {}), "effort": "low"}
                requested_maximum = body.get("max_output_tokens")
                output_key = "max_output_tokens"
            body[output_key] = min(requested_maximum or self.limits["max_output_tokens"],
                                   self.limits["max_output_tokens"])
            if "store" in body:
                body["store"] = False
            raw_request = json.dumps(body).encode()
            input_estimate = (len(raw_request) + 1) // 2
            if input_estimate > self.limits["max_input_estimate"]:
                raise ValueError("Input planning limit reached")
            reference_reserve = (input_estimate * 2.5 + body[output_key] * 10) / 1e6
            conservative_reserve = (input_estimate * 4 + body[output_key] * 20) / 1e6
            reason = None
            if self.run_requests >= self.limits["max_requests_per_run"]:
                reason = "Per-run request cap reached"
            elif self.attempts >= self.limits["max_http_attempts"]:
                reason = "Frozen batch request cap reached"
            elif self.reference + reference_reserve > self.limits["reference_cap_usd"]:
                reason = "Frozen reference-cost cap reached"
            elif self.conservative + conservative_reserve > self.limits["conservative_cap_usd"]:
                reason = "Frozen conservative-cost cap reached"
            if reason:
                self.budget_stop = reason
                raise BudgetStop(reason)
            self.attempts += 1
            self.run_requests += 1
            number = self.attempts
            directory = self.current
            write_json(directory / f"provider-{number}-request.json", body)
            self.reference += reference_reserve
            self.conservative += conservative_reserve
            self.pending[number] = {"reference_reservation_usd": reference_reserve,
                                    "conservative_reservation_usd": conservative_reserve,
                                    "directory": directory.name}
            self.save()  # Interruptions retain reservations before a network request.
            request = urllib.request.Request(
                "https://erpseeker-ai-9340a6.openai.azure.com/openai/v1/" +
                    ("chat/completions" if chat else "responses"),
                data=raw_request, headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + self.bearer}, method="POST")
            started = utc_now()
            try:
                response = self.transport(request, timeout=60)
                status, headers = response.status, response.headers
                try:
                    raw = read_bounded(response)
                finally:
                    response.close()
            except urllib.error.HTTPError as error:
                status, headers, raw = error.code, error.headers, error.read(3_000_001)
            except Exception:
                self.pending.pop(number, None)
                self.unknown_usage += 1
                write_json(directory / f"provider-{number}-metadata.json", {
                    "number": number, "started_at": started, "completed_at": utc_now(),
                    "usage": None, "unknown_usage": True, "request_sha256": digest(raw_request),
                    "reference_cost_usd": reference_reserve, "failure": "Transport/total-read failure",
                })
                self.save()
                raise
            (directory / f"provider-{number}-response.sse").write_bytes(raw)
            parsed = terminal_response(raw.decode("utf-8", errors="replace"))
            usage = parsed.get("usage")
            if chat and usage:
                usage = {"input_tokens": usage.get("prompt_tokens", 0),
                         "output_tokens": usage.get("completion_tokens", 0),
                         "input_tokens_details": usage.get("prompt_tokens_details", {})}
            estimate = None
            if usage:
                inputs, outputs = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                details = usage.get("input_tokens_details") or {}
                cached = min(inputs, details.get("cached_tokens", 0))
                written = min(inputs - cached, details.get("cache_write_tokens", 0))
                estimate = ((inputs - cached - written) * 2 + cached * .1 + written * 2.5 + outputs * 10) / 1e6
                self.reference += estimate - reference_reserve
                self.conservative += (inputs * 4 + outputs * 20) / 1e6 - conservative_reserve
                for key, value in {"requests": 1, "input_tokens": inputs, "output_tokens": outputs,
                                   "cached_tokens": cached, "cache_write_tokens": written}.items():
                    self.usage[key] += value
            elif status != 429:
                self.unknown_usage += 1
            else:
                self.reference -= reference_reserve
                self.conservative -= conservative_reserve
            self.pending.pop(number, None)
            record = {"number": number, "started_at": started, "completed_at": utc_now(),
                      "http_status": status, "served_model": parsed.get("model"), "usage": usage,
                      "status": parsed.get("status"), "response_id": parsed.get("id"),
                      "reference_cost_usd": estimate, "request_sha256": digest(raw_request),
                      "response_sha256": digest(raw), "unknown_usage": not usage}
            self.records.append(record)
            write_json(directory / f"provider-{number}-metadata.json", record)
            self.save()
            if parsed.get("model") not in (None, "gpt-6.1-sol", "gpt-6.1-sol-2026-09-29",
                                           "maqam-orchestrator-sol-6-1"):
                raise RuntimeError("Unexpected served model identity")
            return status, headers.get("content-type", "text/event-stream"), raw


def read_bounded(response, seconds=60, limit=3_000_000):
    """Stop at the final SSE response rather than waiting indefinitely for EOF."""
    deadline = time.monotonic() + seconds
    chunks = bytearray()
    content_type = response.headers.get("content-type", "")
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("Total provider response deadline reached")
        chunk = response.read1(min(16384, limit + 1 - len(chunks)))
        if not chunk:
            return bytes(chunks)
        chunks.extend(chunk)
        if len(chunks) > limit:
            raise RuntimeError("Provider response exceeded the observation limit")
        if "event-stream" in content_type and chunks.endswith((b"\n\n", b"\r\n\r\n")):
            terminal = terminal_response(chunks.decode("utf-8", errors="replace"))
            if terminal.get("status") in ("completed", "incomplete"):
                return bytes(chunks)
