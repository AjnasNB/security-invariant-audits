import unittest
from invoice_service import can_read

class InvoiceServiceTests(unittest.TestCase):
    def test_case_0(self):
        result = can_read(*[{'owner_id': 11, 'company_id': 101}, {'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}])
        self.assertEqual(result, True)
    def test_case_1(self):
        result = can_read(*[None, {'id': 1, 'owner_id': 11, 'company_id': 101, 'total': 20}])
        self.assertEqual(result, False)
    def test_case_2(self):
        result = can_read(*[{'owner_id': 11, 'company_id': 101}, None])
        self.assertEqual(result, False)

if __name__ == '__main__':
    unittest.main()
