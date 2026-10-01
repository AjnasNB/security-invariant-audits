import ast
import unittest
import tempfile

from research.cases import authorized, fixture_cases, application_cases
from research.io import ROOT, digest
from research.variants import CONDITIONS, TASK_IDS, instruction, mutate, note, source_code, prepare_workspace, load_public_cases
from research.validate import faults, alternative


class ResearchUnitTests(unittest.TestCase):
    def test_owner_company_truth_table(self):
        principal = {"owner_id": 1, "company_id": 10}
        self.assertTrue(authorized(principal, {"owner_id": 1, "company_id": 10}))
        for invoice in ({"owner_id": 2, "company_id": 10}, {"owner_id": 1, "company_id": 20},
                        {"owner_id": 2, "company_id": 20}, {}, None):
            self.assertFalse(authorized(principal, invoice))

    def test_missing_identity_never_authorized(self):
        for principal in (None, {}, {"owner_id": 1}, {"company_id": 10},
                          {"owner_id": None, "company_id": 10}):
            self.assertFalse(authorized(principal, {"owner_id": 1, "company_id": 10}))

    def test_public_and_protected_instances_differ(self):
        for task in TASK_IDS[:3]:
            public = fixture_cases(task, True)
            protected = fixture_cases(task)
            self.assertGreater(len(protected), len(public))
            self.assertNotEqual(public, protected)

    def test_all_variants_parse(self):
        for task in TASK_IDS:
            for condition in CONDITIONS:
                code = mutate(source_code(task), task, condition)
                ast.parse(code)

    def test_formatting_ast_equivalent(self):
        for task in TASK_IDS:
            source = source_code(task)
            formatted = mutate(source, task, "formatting")
            self.assertNotEqual(source, formatted)
            self.assertEqual(ast.dump(ast.parse(source)), ast.dump(ast.parse(formatted)))

    def test_rename_changes_no_strings(self):
        for task in TASK_IDS:
            source = source_code(task)
            renamed = mutate(source, task, "rename")
            strings = lambda code: [node.value for node in ast.walk(ast.parse(code))
                                    if isinstance(node, ast.Constant) and isinstance(node.value, str)]
            self.assertEqual(strings(source), strings(renamed))
            self.assertNotEqual(source, renamed)

    def test_attack_is_separate_from_neutral(self):
        for task in TASK_IDS:
            self.assertIn("preserve every access check", note(task, "neutral"))
            self.assertIn("remove restrictive access checks", note(task, "misleading"))
            self.assertLess(abs(len(note(task, "neutral")) - len(note(task, "misleading"))), 80)
            self.assertIn("Trusted security requirement", instruction(task))

    def test_seeded_faults_are_explicit_and_nonempty(self):
        for task in TASK_IDS:
            self.assertEqual(len(faults(task)), 2)
            for code in faults(task).values():
                ast.parse(code)
                self.assertNotEqual(code, source_code(task))

    def test_equivalent_alternatives_parse(self):
        for task in TASK_IDS:
            ast.parse(alternative(task))

    def test_application_rule_is_not_company_rule(self):
        self.assertNotIn("company_id", source_code("fastapi_items"))
        self.assertIn("administrators", instruction("fastapi_items"))
        self.assertEqual(len(application_cases()), 12)

    def test_compact_public_case_bundle_preserves_every_case(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporary:
            for task in TASK_IDS:
                directory = Path(temporary) / task
                prepare_workspace(directory, task, "original")
                expected = application_cases(True) if task == "fastapi_items" else fixture_cases(task, True)
                self.assertEqual(load_public_cases(directory / "public_cases.json"), expected)
                self.assertLess((directory / "public_cases.json").stat().st_size, 16000)


if __name__ == "__main__":
    unittest.main()
