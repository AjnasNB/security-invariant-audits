import unittest
from service import run

class ScreenTests(unittest.TestCase):
    def test_request_0(self):
        self.assertEqual(run(*[[{'owner_id': 11, 'company_id': 101, 'roles': ['staff']}, {'owner_id': 11, 'company_id': 202, 'roles': ['staff']}, {'owner_id': 77, 'company_id': 101, 'roles': ['manager']}, {'owner_id': 88, 'company_id': 101, 'roles': ['admin']}, {'owner_id': None, 'company_id': 101, 'roles': ['admin']}, {'owner_id': 11, 'roles': ['staff']}, None, {'owner_id': 11, 'company_id': 101, 'roles': ['staff']}], [{'id': 1011, 'owner_id': 11, 'company_id': 101, 'total': 30}, {'id': 1012, 'owner_id': 11, 'company_id': 101, 'total': 10}], [{'actor': 0, 'id': 1011}, {'actor': 0, 'id': -1}]]), [True, False])

if __name__ == '__main__':
    unittest.main()
