import unittest
from invoice_service import read_invoice

class InvoiceServiceTests(unittest.TestCase):
    def test_case_0(self):
        result = read_invoice(*[{'owner_id': 11, 'company_id': 101}, [{'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}, {'id': 2, 'owner_id': 11, 'company_id': 101, 'total': 30}], 2])
        self.assertEqual(result, {'id': 2, 'owner_id': 11, 'company_id': 101, 'total': 30})
    def test_case_1(self):
        result = read_invoice(*[{'owner_id': 11, 'company_id': 101}, [{'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}, {'id': 2, 'owner_id': 11, 'company_id': 101, 'total': 30}], 99])
        self.assertEqual(result, None)
    def test_case_2(self):
        result = read_invoice(*[{'owner_id': 11, 'company_id': 101}, [], 1])
        self.assertEqual(result, None)

if __name__ == '__main__':
    unittest.main()
