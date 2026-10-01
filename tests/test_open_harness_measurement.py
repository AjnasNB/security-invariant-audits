import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harnesses.ordinary_broker import OrdinaryBroker, TOOLS
from harnesses.ordinary_protocol import protocol
from harnesses.response_text import response_text
from harnesses.ordinary_provider import read_bounded, Provider
from research.natural_tasks import prepare
from research.natural_bridge import natural_assess


class OpenHarnessMeasurementTests(unittest.TestCase):
    def test_stream_read_stops_at_terminal_event_without_waiting_for_eof(self):
        body = b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
        class Response:
            headers = {"content-type": "text/event-stream"}
            calls = 0
            def read1(self, count):
                self.calls += 1
                if self.calls > 1:
                    raise AssertionError("Reader waited for EOF after terminal event")
                return body
        response = Response()
        self.assertEqual(read_bounded(response), body)
        self.assertEqual(response.calls, 1)

    def test_provider_reservation_persists_before_transport_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            limits = {"max_requests_per_run": 1, "max_http_attempts": 1,
                      "max_output_tokens": 16, "max_input_estimate": 1000,
                      "reference_cap_usd": 1, "conservative_cap_usd": 1}
            def transport(request, **kwargs):
                recorded = json.loads((root / "usage.json").read_text())
                self.assertEqual(recorded["http_attempts"], 1)
                self.assertTrue(recorded["pending_requests"])
                raise TimeoutError("simulated")
            provider = Provider(root, limits, transport=transport)
            provider.bearer = "unit-test-not-a-real-token"
            with self.assertRaises(TimeoutError):
                provider.model("/v1/responses", {"model": "maqam-orchestrator-sol-6-1", "input": []})
            usage = json.loads((root / "usage.json").read_text())
            self.assertGreater(usage["reference_estimate_usd"], 0)
            self.assertEqual(usage["unknown_usage_attempts"], 1)
            self.assertFalse(usage["pending_requests"])

    def test_chat_versioned_model_identity_and_usage_are_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            body = {"model": "gpt-6.1-sol-2026-09-29", "choices": [
                {"message": {"content": "19"}}], "usage": {
                "prompt_tokens": 20, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 5}}}
            class Response:
                status = 200
                headers = {"content-type": "application/json"}
                remaining = json.dumps(body).encode()
                def read1(self, count):
                    result, self.remaining = self.remaining, b""
                    return result
                def close(self):
                    pass
            limits = {"max_requests_per_run": 1, "max_http_attempts": 1,
                      "max_output_tokens": 16, "max_input_estimate": 1000,
                      "reference_cap_usd": 1, "conservative_cap_usd": 1}
            provider = Provider(root, limits, transport=lambda *args, **kwargs: Response())
            provider.bearer = "unit-test-not-a-real-token"
            status, _, raw = provider.model("/v1/chat/completions",
                                            {"model": "maqam-orchestrator-sol-6-1", "messages": []})
            self.assertEqual(status, 200)
            self.assertEqual(response_text(raw.decode()), "19")
            self.assertEqual(provider.usage["input_tokens"], 20)
            self.assertEqual(provider.usage["cached_tokens"], 5)

    def test_json_and_sse_final_answers_match_without_reasoning(self):
        body = {"output": [{"type": "reasoning", "summary": [{"text": "private reasoning"}]},
                           {"type": "message", "content": [{"type": "output_text", "text": "False"}]}]}
        self.assertEqual(response_text(json.dumps(body)), "False")
        stream = "data: " + json.dumps({"type": "response.completed", "response": body}) + "\n\n"
        self.assertEqual(response_text(stream), "False")
        self.assertIsNone(response_text('{"error":{"message":"provider stopped"}}'))

    def test_finish_tool_answer_can_be_recorded_without_running_a_tool(self):
        body = {"output": [{"type": "function_call", "name": "finish",
                            "arguments": '{"message":"19"}'}]}
        self.assertEqual(response_text(json.dumps(body)), "19")

    def test_non_root_worker_copy_permissions_are_explicit_on_linux(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "source"
            prepare(workspace, "access_helper", "original")
            with patch("research.natural_bridge.assess") as assessor:
                def check(directory, task, cases):
                    self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
                    self.assertEqual((directory / "target.py").stat().st_mode & 0o777, 0o644)
                    return {"status": "assessed", "total": 3, "passed": 3, "functional_failures": 0}
                if os.name == "nt":
                    # Windows modes don't map POSIX read bits; verify the chmod calls.
                    with patch.object(Path, "chmod") as chmod:
                        assessor.return_value = {"status": "assessed", "total": 3, "passed": 3,
                                                 "functional_failures": 0}
                        natural_assess(workspace, "access_helper", True)
                        self.assertEqual([call.args[0] for call in chmod.call_args_list], [0o755, 0o644])
                else:
                    assessor.side_effect = check
                    natural_assess(workspace, "access_helper", True)

    def test_tool_descriptions_do_not_reveal_private_checker_or_security_rule(self):
        for tool in TOOLS:
            text = tool["description"].lower()
            self.assertNotIn("hidden", text)
            self.assertNotIn("security", text)
            self.assertNotIn("company", text)
            self.assertIn("annotations", tool)

    def test_uneditable_project_files_and_stale_hashes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            prepare(workspace, "access_helper", "original")
            broker = OrdinaryBroker(workspace, "access_helper", root)
            with self.assertRaises(PermissionError):
                broker.execute("update_file", {"path": "README.md", "content": "bad", "expected_sha256": ""})
            with self.assertRaises(ValueError):
                broker.execute("update_file", {"path": "invoice_service.py", "content": "bad",
                                              "expected_sha256": "stale"})

    def test_allocations_include_setup_and_stay_below_total_cap(self):
        study = protocol()
        planned = (study["setup_reference_estimate_usd"] + 3 * (
            study["coding_limits_per_primary_agent"]["reference_cap_usd"]
            + study["prediction_limits_per_primary_agent"]["reference_cap_usd"])
            + sum(row["reference_cap_usd"] for row in study["optional_agents"].values()))
        self.assertLessEqual(planned, study["total_reference_cap_usd"])


if __name__ == "__main__":
    unittest.main()
