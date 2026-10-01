import ast
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from erp.tasks import TASKS, CONDITIONS


class ERPContractTests(unittest.TestCase):
    def test_tasks_are_actual_distinct_request_functions(self):
        self.assertEqual(set(TASKS), {"read-document", "list-documents", "delete-document"})
        self.assertEqual({name for names in TASKS.values() for name in names}, {"get", "get_list", "delete_doc"})

    def test_notes_and_semantic_variants_are_separate_conditions(self):
        self.assertEqual(CONDITIONS, ["original", "rename", "formatting", "neutral", "misleading"])

    def test_public_code_parses_without_local_vendor(self):
        for source in (Path(__file__).resolve().parents[1] / "erp").glob("*.py"):
            ast.parse(source.read_text(encoding="utf-8"))

    def test_ordinary_erp_profile_has_no_experiment_security_coaching(self):
        from erp.tasks import prepare
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "client-baseline.py").write_text(
                "def get():\n    return None\n", encoding="utf-8")
            with patch("erp.tasks.PROTECTED", root):
                prompt = prepare(root / "task", "read-document", "misleading", "ordinary-v1")
            for phrase in ("security", "company", "private", "hidden", "synthetic", "untrusted"):
                self.assertNotIn(phrase, prompt.lower())
            context = (root / "task" / "APP_CONTEXT.md").read_text(encoding="utf-8")
            self.assertNotIn("permission", context)
            self.assertNotIn("synthetic", context)
            self.assertIn("skip", (root / "task" / "PROJECT_NOTE.md").read_text())

    def test_erp_formatting_preserves_historical_profile_and_pure_new_profile(self):
        from erp.tasks import prepare
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = "def get():\n    return None\n"
            (root / "client-baseline.py").write_text(baseline, encoding="utf-8")
            with patch("erp.tasks.PROTECTED", root):
                prepare(root / "old", "read-document", "formatting", "defended-v1")
                prepare(root / "new", "read-document", "formatting", "ordinary-v1")
            self.assertTrue((root / "old" / "client.py").read_text().startswith("# Formatting-only"))
            self.assertEqual("".join((root / "new" / "client.py").read_text().split()),
                             "".join(baseline.split()))


if __name__ == "__main__":
    unittest.main()
