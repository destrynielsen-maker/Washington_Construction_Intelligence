import unittest
from datetime import date
from types import SimpleNamespace
from washington_permits.pipeline import _success
from washington_permits.models import Permit

class HealthTests(unittest.TestCase):
    def test_fresh(self):
        r=SimpleNamespace(source="Seattle", permits=[Permit(state="WA",jurisdiction="Seattle",permit_number="1",issued_date="2026-08-24")], source_url="x", note="x")
        s=_success(r,1,None,"2026-08-24T00:00:00+00:00",date(2026,8,24),10)
        self.assertEqual(s["status"],"healthy")
    def test_stale(self):
        r=SimpleNamespace(source="Seattle", permits=[Permit(state="WA",jurisdiction="Seattle",permit_number="1",issued_date="2026-07-01")], source_url="x", note="x")
        s=_success(r,1,None,"2026-08-24T00:00:00+00:00",date(2026,8,24),10)
        self.assertEqual(s["status"],"stale")

if __name__=="__main__": unittest.main()
