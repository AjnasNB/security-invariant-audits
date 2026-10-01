import ast
import tempfile
import unittest
from pathlib import Path

from research.natural_tasks import PROMPTS, README, NOTES, TASKS, prepare, public_test_source, schedule


class OrdinaryPromptTests(unittest.TestCase):
    def test_no_test_specific_security_coaching_in_agent_requests(self):
        for text in [*PROMPTS.values(), README, NOTES["neutral"]]:
            for cue in ("hidden", "private tests", "security requirement", "untrusted",
                        "owner_id", "company_id", "synthetic", "not included", "not available"):
                self.assertNotIn(cue, text.lower())

    def test_notes_are_project_content_not_added_to_user_prompt(self):
        for text in PROMPTS.values():
            self.assertNotIn("note", text.lower())
        self.assertIn("owner_id only", NOTES["misleading"])

    def test_matched_runs_are_separate_fresh_rows(self):
        rows = schedule()
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows, schedule())
        for task in TASKS:
            selected = [row for row in rows if row["task"] == task]
            self.assertEqual(sum(row["arm"] == "benign-variation" for row in selected), 3)
            self.assertEqual(sum(row["arm"] == "unchanged-control" for row in selected), 3)
            self.assertEqual(sum(row["arm"] == "project-note" for row in selected), 2)

    def test_prepared_files_have_no_checker_or_private_expected_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "service"
            record = prepare(directory, "invoice_lookup", "misleading")
            self.assertEqual({path.name for path in directory.iterdir()},
                             {"invoice_service.py", "test_invoice_service.py", "README.md", "project_notes.md"})
            self.assertEqual(record["prompt"], PROMPTS["invoice_lookup"])
            self.assertNotIn("public_cases", "\n".join(path.name for path in directory.iterdir()))
            ast.parse(public_test_source("invoice_lookup"))


if __name__ == "__main__":
    unittest.main()
