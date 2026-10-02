import unittest
from service import run

class ScreenTests(unittest.TestCase):
    def test_request_0(self):
        self.assertEqual(run(*[[{'owner_id': 11, 'company_id': 101, 'roles': ['staff']}, {'owner_id': 11, 'company_id': 202, 'roles': ['staff']}, {'owner_id': 77, 'company_id': 101, 'roles': ['finance']}, {'owner_id': 88, 'company_id': 101, 'roles': ['admin']}, {'owner_id': None, 'company_id': 101, 'roles': ['admin']}, {'owner_id': 11, 'roles': ['staff']}, None, {'owner_id': 11, 'company_id': 101, 'roles': ['staff']}], [{'id': 2011, 'owner_id': 11, 'company_id': 101, 'total': 30}, {'id': 2012, 'owner_id': 11, 'company_id': 101, 'total': 10}], [{'actor': 0, 'operation': 'list', 'start': 0, 'limit': 20, 'descending': False}]]), [{'records': [{'id': 2012, 'owner_id': 11, 'company_id': 101, 'total': 10}, {'id': 2011, 'owner_id': 11, 'company_id': 101, 'total': 30}], 'count': 2, 'total': 40}])

if __name__ == '__main__':
    unittest.main()
