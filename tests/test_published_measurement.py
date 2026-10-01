import ast
import unittest
from pathlib import Path

from research.io import ROOT, read_json
from research.scoring import same_value, score_fixture
from research.cases import fixture_cases


class PublishedMeasurementTests(unittest.TestCase):
    def test_ordinary_export_keeps_incomplete_task_and_actual_denominators(self):
        path = ROOT / "evidence/ordinary-v1/summary.json"
        if not path.exists():
            self.skipTest("No published ordinary evidence in this checkout")
        summary = read_json(path)
        runs = summary["runs"]
        self.assertEqual(len(runs), 24)
        self.assertEqual(sum(run["task_completed"] for run in runs), 23)
        self.assertEqual(sum(run["termination"] == "budget_stopped" for run in runs), 1)
        self.assertEqual(summary["total"]["checks_completed_refactors"], 2465)
        self.assertEqual(summary["total"]["checks_all_saved_files"], 2608)

    def test_export_has_no_private_trace_files(self):
        evidence = ROOT / "evidence/ordinary-v1"
        if not evidence.exists():
            self.skipTest("No published ordinary evidence in this checkout")
        for path in evidence.rglob("*"):
            if path.is_file():
                self.assertNotIn(path.suffix, (".sse", ".env", ".sql"))
                self.assertNotIn("checkpoint", path.name)
                self.assertNotIn("request", path.name)

    def test_saved_helper_integer_cannot_pass_replay(self):
        case = fixture_cases("access_helper")[0]
        self.assertTrue(case["expected"])
        result = score_fixture("access_helper", [case], [
            {"id": case["id"], "value": 1, "return_type": "int"},
        ])
        self.assertEqual(result["passed"], 0)
        self.assertEqual(result["invalid_outputs"], 1)
        self.assertIsNone(result["invariant_preserved"])

    def test_archived_failure_examples_remain_separate_from_fresh_sample(self):
        historical = ROOT / "reports/mucoco-author-replay-v1.json"
        fresh = ROOT / "reports/mucoco-model-v1.json"
        if not historical.exists() or not fresh.exists():
            self.skipTest("No paper result evidence in this checkout")
        old, new = read_json(historical), read_json(fresh)
        self.assertEqual(old["confirmed_selected_failures"], 3)
        self.assertFalse(old["new_model_generation"])
        self.assertEqual(old["azure_calls"], 0)
        self.assertEqual(new["attempted_queries"], 11)
        self.assertEqual(new["inconsistencies"], 0)
        for item in old["selected"]:
            self.assertTrue(same_value(item["original_runtime_output"], item["mutant_runtime_output"]))
            self.assertFalse(same_value(item["mutant_saved_answer"], item["expected"]))

    def test_archived_programs_parse_without_being_executed(self):
        evidence = ROOT / "evidence/mucoco-author-replay-v1"
        for path in evidence.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
