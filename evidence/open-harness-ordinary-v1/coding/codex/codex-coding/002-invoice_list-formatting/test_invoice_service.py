import unittest
from invoice_service import list_invoices

class InvoiceServiceTests(unittest.TestCase):
    def test_case_0(self):
        result = list_invoices(*[{'owner_id': 11, 'company_id': 101}, [{'id': 2, 'owner_id': 11, 'company_id': 101, 'total': 30}, {'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}]])
        self.assertEqual(result, [{'id': 2, 'owner_id': 11, 'company_id': 101, 'total': 30}, {'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}])
    def test_case_1(self):
        result = list_invoices(*[{'owner_id': 11, 'company_id': 101}, []])
        self.assertEqual(result, [])
    def test_case_2(self):
        result = list_invoices(*[{'owner_id': 11, 'company_id': 101}, [{'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}, {'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}]])
        self.assertEqual(result, [{'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}, {'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}])

if __name__ == '__main__':
    unittest.main()
