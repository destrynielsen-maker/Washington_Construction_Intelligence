import tempfile, unittest, xml.etree.ElementTree as ET
from pathlib import Path
from washington_permits.models import Permit
from washington_permits.feeds import write_all_feeds

class FeedTests(unittest.TestCase):
    def test_xml(self):
        p=Permit(state="WA",jurisdiction="Seattle",permit_number="1",issued_date="2026-08-01",classification="COMMERCIAL",qualifies=True,score=40)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); write_all_feeds(out,[p],"https://example.test/")
            for f in ["new-construction.xml","single-family.xml","multifamily.xml","commercial.xml","top-opportunities.xml"]:
                ET.parse(out/f)

if __name__=="__main__": unittest.main()
