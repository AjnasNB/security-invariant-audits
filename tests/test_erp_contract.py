import ast
import unittest
from erp.tasks import TASKS, CONDITIONS


class ERPContractTests(unittest.TestCase):
    def test_tasks_are_actual_distinct_request_functions(self):
        self.assertEqual(set(TASKS), {"read-document", "list-documents", "delete-document"})
        self.assertEqual({name for names in TASKS.values() for name in names}, {"get", "get_list", "delete_doc"})

    def test_notes_and_semantic_variants_are_separate_conditions(self):
        self.assertEqual(CONDITIONS, ["original", "rename", "formatting", "neutral", "misleading"])

    def test_public_code_parses_without_local_vendor(self):
        from pathlib import Path
        for source in (Path(__file__).resolve().parents[1] / "erp").glob("*.py"):
            ast.parse(source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
