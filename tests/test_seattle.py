import unittest
from washington_permits.collectors.seattle import SeattleCollector

class SeattleTests(unittest.TestCase):
    def test_identity_accepts_seattle(self):
        SeattleCollector._validate_source_identity([{"originalstate":"WA","originalcity":"SEATTLE","link":{"url":"https://services.seattle.gov/portal/customize/LinkToRecord.aspx?altId=1"}}])
    def test_identity_rejects_foreign_state(self):
        with self.assertRaises(RuntimeError):
            SeattleCollector._validate_source_identity([{"originalstate":"OR","originalcity":"PORTLAND"}])
    def test_date(self):
        self.assertEqual(SeattleCollector._date("2026-08-21T00:00:00.000"),"2026-08-21")

if __name__=="__main__": unittest.main()
