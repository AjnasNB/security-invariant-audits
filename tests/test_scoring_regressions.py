"""Regression cases from the user's pasted review, not AI-generated failures."""
import json
import subprocess
import unittest
from unittest.mock import patch

from research.sandbox import assess
from erp.evaluate import assess as assess_erp


def fixture_score(task, case, value, **extra):
    result = subprocess.CompletedProcess(["fixture"], 0,
        json.dumps([{"id": case["id"], "value": value, **extra}]), "")
    with patch("research.sandbox.run_container", return_value=result):
        return assess("unused", task, [case])


class ScoringRegressions(unittest.TestCase):
    def test_integer_one_is_not_a_boolean_success(self):
        case = {"id": "boolean", "args": [{"owner_id": 1, "company_id": 10},
                {"id": 1, "owner_id": 1, "company_id": 10, "total": 12}],
                "expected": True, "security_case": False}
        score = fixture_score("access_helper", case, 1)
        self.assertEqual(score["passed"], 0)
        self.assertEqual(score["invalid_outputs"], 1)
        self.assertIsNone(score["invariant_preserved"])

    def test_false_lookup_is_invalid_but_not_invoice_disclosure(self):
        case = {"id": "lookup", "args": [{"owner_id": 1, "company_id": 10},
                [{"id": 1, "owner_id": 2, "company_id": 20, "total": 12}], 1],
                "expected": None, "security_case": True}
        score = fixture_score("invoice_lookup", case, False)
        self.assertEqual(score["functional_failures"], 1)
        self.assertEqual(score["security_failures"], 0)
        self.assertEqual(score["invalid_outputs"], 1)
        self.assertIsNone(score["invariant_preserved"])

    def test_truthy_invalid_denial_cannot_claim_preserved_invariant(self):
        case = {"id": "denial", "args": [{"owner_id": 1, "company_id": 10},
                {"id": 1, "owner_id": 2, "company_id": 20, "total": 12}],
                "expected": False, "security_case": True}
        score = fixture_score("access_helper", case, 1)
        self.assertEqual(score["passed"], 0)
        self.assertIsNone(score["invariant_preserved"])
        self.assertGreater(score["unknown_security_checks"], 0)

    def test_tuple_list_is_not_a_valid_list_return(self):
        case = {"id": "list", "args": [None, []], "expected": [], "security_case": False}
        score = fixture_score("invoice_list", case, [], return_type="tuple")
        self.assertEqual(score["invalid_outputs"], 1)
        self.assertEqual(score["passed"], 0)

    def test_correct_boolean_is_still_accepted(self):
        case = {"id": "denial", "args": [None, None], "expected": False, "security_case": True}
        score = fixture_score("access_helper", case, False)
        self.assertEqual(score["passed"], 1)
        self.assertIs(score["invariant_preserved"], True)


class ERPPaginationRegressions(unittest.TestCase):
    case = {"id": "page", "operation": "list", "user": "alice@audit.invalid",
        "start": 1, "limit": 1,
        "expected": {"allowed": True, "names": ["a2"], "companies": ["Company A"]},
        "authorization": {"read_names": ["a1", "a2"], "companies": ["Company A"],
                          "invoice_companies": {"a1": "Company A", "a2": "Company A", "b1": "Company B"}}}

    def score(self, value):
        result = subprocess.CompletedProcess(["fixture"], 0,
            "AUDIT_JSON:" + json.dumps([{"id": "page", "value": value}]), "")
        with patch("erp.evaluate.cases", return_value=[self.case]), \
             patch("erp.evaluate.subprocess.run", return_value=result):
            return assess_erp("unused.py")

    def test_other_company_on_a_page_is_a_security_failure(self):
        score = self.score({"allowed": True, "names": ["b1"], "companies": ["Company B"]})
        self.assertEqual(score["functional_failures"], 1)
        self.assertEqual(score["security_failures"], 1)

    def test_authorized_record_on_wrong_page_is_only_a_functional_failure(self):
        score = self.score({"allowed": True, "names": ["a1"], "companies": ["Company A"]})
        self.assertEqual(score["functional_failures"], 1)
        self.assertEqual(score["security_failures"], 0)

    def test_malformed_observations_return_unknown_instead_of_raising(self):
        for raw in ("not-json", "AUDIT_JSON:{}", 'AUDIT_JSON:[{"id":"page"}]',
                    'AUDIT_JSON:[{"id":"page","value":{}},{"id":"page","value":{}}]'):
            with self.subTest(raw=raw), patch("erp.evaluate.cases", return_value=[self.case]), \
                 patch("erp.evaluate.subprocess.run", return_value=subprocess.CompletedProcess(["fixture"], 0, raw, "")):
                result = assess_erp("unused.py")
                self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
