"""Small adversarial unit checks, no model, Docker, network or real customer data."""
import json
import unittest

from wholeapp.cases import document_allowed, file_allowed, cases
from wholeapp.judge import score, assess_saved


def fixture():
    return {
        "source": {"users": {"alice": "alice", "bob": "bob", "reader": "reader", "outsider": "outside"},
                   "companies": [{"name": "A"}, {"name": "B"}], "invoices": []},
        "documents": [
            {"doctype": "Sales Invoice", "name": "INV-A", "company_index": 0, "company": "A",
             "secret": "SECRET-A", "content_marker": "DOC-A"},
            {"doctype": "Sales Invoice", "name": "INV-B", "company_index": 1, "company": "B",
             "secret": "SECRET-B", "content_marker": "DOC-B"},
            {"doctype": "Project", "name": "PROJECT-A", "company_index": 0, "company": "A",
             "secret": "PROJ-SECRET-A", "content_marker": "PROJ-A"},
            {"doctype": "Project", "name": "PROJECT-B", "company_index": 1, "company": "B",
             "secret": "PROJ-SECRET-B", "content_marker": "PROJ-B"}],
        "files": [
            {"name": "FILE-A", "private": True, "company_index": 0, "owner": "Administrator",
             "attached_to_doctype": "Sales Invoice", "attached_to_name": "INV-A", "shared_with": [],
             "content_marker": "DOC-A", "file_url": "/private/files/a.txt", "file_name": "a.txt"},
            {"name": "FILE-B", "private": True, "company_index": 1, "owner": "Administrator",
             "attached_to_doctype": "Sales Invoice", "attached_to_name": "INV-B", "shared_with": [],
             "content_marker": "DOC-B", "file_url": "/private/files/b.txt", "file_name": "b.txt"},
            {"name": "SHARED", "private": True, "company_index": None, "owner": "bob",
             "attached_to_doctype": None, "attached_to_name": None, "shared_with": ["reader"],
             "content_marker": "SHARED-TEXT", "file_url": "/private/files/shared.txt", "file_name": "shared.txt"},
            {"name": "PUBLIC", "private": False, "company_index": None, "owner": "Administrator",
             "attached_to_doctype": None, "attached_to_name": None, "shared_with": [],
             "content_marker": "PUBLIC-TEXT", "file_url": "/files/public.txt", "file_name": "public.txt"}]}


class WholeAppTests(unittest.TestCase):
    def test_company_policy_and_native_file_exceptions_are_explicit(self):
        f = fixture()
        self.assertTrue(document_allowed("alice", f["documents"][0], f))
        self.assertFalse(document_allowed("alice", f["documents"][1], f))
        self.assertTrue(file_allowed("reader", f["files"][2], f))
        self.assertTrue(file_allowed("Guest", f["files"][3], f))
        self.assertFalse(file_allowed("Guest", f["files"][2], f))
        self.assertTrue(file_allowed("Administrator", f["files"][1], f))

    def test_real_access_surfaces_and_guest_inputs_are_in_matrix(self):
        challenge = cases(fixture())
        surfaces = {row["surface"] for row in challenge}
        self.assertTrue({"document-print", "private-file-download", "attachment-gallery", "csv-export",
                         "protected-field-query", "version2-document-read", "unauthorized-update"} <= surfaces)
        self.assertTrue(any(row["user"] == "Guest" for row in challenge))
        self.assertEqual(len(challenge), len({row["id"] for row in challenge}))

    def test_private_marker_is_leak_even_when_endpoint_errors(self):
        f = fixture()
        case = {"id": "x", "surface": "private-file-download", "user": "alice", "expected_allowed": False,
                "expected_names": []}
        result = score(case, {"http_status": 500, "body": "DOC-B"}, f)
        self.assertTrue(result["security_failure"])
        self.assertEqual(result["access_verdict"], "VIOLATION")

    def test_crash_is_unknown_not_successfully_denied(self):
        f = fixture()
        case = {"id": "x", "surface": "rpc-document-read", "user": "alice", "expected_allowed": False}
        result = score(case, {"http_status": 500, "body": "server failed"}, f)
        self.assertFalse(result["passed"])
        self.assertEqual(result["access_verdict"], "UNKNOWN")

    def test_csrf_or_unconfirmed_auth_is_not_authorization_success(self):
        f = fixture()
        case = {"id": "x", "surface": "unauthorized-update", "user": "alice",
                "expected_allowed": False, "mutation": True}
        for error in ("CSRFTokenError", "AuthenticationError"):
            result = score(case, {"http_status": 403, "body": json.dumps({"exc_type": error})}, f)
            self.assertFalse(result["passed"])

    def test_form_metadata_for_legitimate_attachment_is_not_false_failure(self):
        f = fixture()
        case = {"id": "x", "surface": "form-document-load", "user": "alice",
                "expected_allowed": True, "expected_names": ["INV-A"]}
        body = {"docs": [{"name": "INV-A"}], "docinfo": {"attachments": [{"name": "FILE-A"}]}}
        result = score(case, {"http_status": 200, "body": json.dumps(body)}, f)
        self.assertTrue(result["passed"])
        self.assertFalse(result["security_failure"])

    def test_protected_field_detected_for_reader_even_same_company(self):
        f = fixture()
        case = {"id": "x", "surface": "protected-field-query", "user": "reader",
                "expected_allowed": True, "expected_names": ["INV-A"], "check_secret_field": True}
        body = {"message": [{"name": "INV-A", "secret": "SECRET-A"}]}
        self.assertTrue(score(case, {"http_status": 200, "body": json.dumps(body)}, f)["security_failure"])

    def test_duplicate_ids_rejected(self):
        f = fixture()
        case = {"id": "x", "surface": "missing-record", "user": "Guest", "expected_allowed": False}
        with self.assertRaises(ValueError):
            assess_saved([case, {**case, "id": "y"}],
                         [{"id": "x", "http_status": 404}, {"id": "x", "http_status": 404}], f)


if __name__ == "__main__":
    unittest.main()
