"""Curated public findings and pedagogical demo; no network/model execution."""
import ast
import copy
import importlib.util
import unittest

from research.io import ROOT, read_json
from research.verify_findings import validate_verdicts, verify


class FindingsTests(unittest.TestCase):
    def test_packet_replays_actual_business_observations(self):
        result = verify()
        self.assertEqual(result["real_erp_original_and_replays"], [94, 52, 52])
        self.assertEqual(result["distinct_ai_functional_bugs"], 1)
        self.assertEqual(result["new_model_calls"], 0)
        self.assertEqual(result["new_model_access_failures"], 0)

    def test_incomplete_luna_output_not_counted_as_finished_refactor(self):
        summary = read_json(ROOT / "evidence/findings-20261003/summary.json")
        failure = summary["confirmed_ai_functional_failure"]
        self.assertFalse(failure["task_completed"])
        self.assertEqual(failure["original_stop"], "8-step limit")
        for replay in failure["fresh_replays"][1:]:
            self.assertEqual(replay["assessment"]["unknown_security_checks"], 42)
            self.assertEqual(replay["authorized_read_failures"], 15)

    def test_http_verdict_duplicate_is_rejected(self):
        rows = read_json(ROOT / "evidence/findings-20261003/latest/baseline-http-verdicts.json")
        rows[-1] = copy.deepcopy(rows[0])
        with self.assertRaises(ValueError):
            validate_verdicts(rows)

    def test_demo_illustrates_one_error_without_claiming_real_erp_replay(self):
        spec = importlib.util.spec_from_file_location("missing_helper_demo", ROOT / "examples/missing_helper_demo.py")
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            invoices = {"INV-A": module.Invoice("INV-A", "A")}
            self.assertEqual(module.original_get(invoices, "INV-A", "A").name, "INV-A")
            with self.assertRaises(PermissionError):
                module.original_get(invoices, "INV-A", "B")
            with self.assertRaises(NameError):
                module.refactored_get(invoices, "INV-A", "A")
        finally:
            sys.modules.pop(spec.name, None)

    def test_public_findings_has_no_raw_private_trace_files(self):
        evidence = ROOT / "evidence/findings-20261003"
        forbidden = (".sse", ".env", ".sql", ".gz")
        for file in evidence.rglob("*"):
            if file.is_file():
                self.assertNotIn(file.suffix, forbidden)
                self.assertNotIn("checkpoint", file.name)
                self.assertNotIn("credentials", file.name)
                self.assertNotIn("site_config", file.name)

    def test_specimen_preserves_real_candidate_hash_and_call(self):
        summary = read_json(ROOT / "evidence/findings-20261003/summary.json")
        failure = summary["confirmed_ai_functional_failure"]
        candidate = ROOT / failure["candidate_source"]
        tree = ast.parse(candidate.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "_get_doc"]
        self.assertEqual([node.lineno for node in calls], [109])


if __name__ == "__main__":
    unittest.main()
