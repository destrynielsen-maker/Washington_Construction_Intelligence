from datetime import date
from unittest import TestCase
from unittest.mock import patch

from washington_permits.collectors import spokane_county_preview as m

START=date(2026,11,23)
END=date(2026,11,26)
TODAY=END
SFR="B2606214      SINGLE FAMILY DWELLING W/GARAGE       11/24/2026          900 EXAMPLE AVE           $231,041.36"
DUPLEX="B2605460     TWO-FAMILY DWELLING-DUPLEX             11/25/2026          999 EXAMPLE RD            $328,967.24"
REBUILD="B2605461     WILDFIRE REBUILD NEW SFR               11/25/2026          777 EXAMPLE RD            $328,967.24"

def report(*rows):
    return (' Spokane County SmartGov\n Permits with Values over $100,000\n'
        ' From Issued Date: 11/23/2026 Thru 11/26/2026\n\n'
        'Permit #  Project Description   Issued  Site Address    Total Valuation\n'+"\n".join(rows)+'\n Page 1 of 1\f')

class CountyPreviewTests(TestCase):
    def parse(self, layout):
        return m.parse(layout,START,END,TODAY,"example-sha")

    def test_exact_scope_and_role_no_inference(self):
        out=self.parse(report(SFR,DUPLEX,REBUILD,SFR,
           DUPLEX.replace('B2605460','B2605465').replace('$328,967.24','$100,000.00'),
           SFR.replace('B2606214','B2606200').replace('FAMILY DWELLING','FAMILY DWELLING WITH ADU')))
        self.assertEqual((out['observed_unique'],out['duplicate_rows'],out['excluded']),(5,1,3))
        self.assertEqual([p['classification'] for p in out['permits']],['SINGLE_FAMILY','MULTIFAMILY'])
        self.assertEqual({p['contractor'] for p in out['permits']},{None})
        self.assertEqual({p['jurisdiction'] for p in out['permits']},{'Spokane County'})

    def test_identity_footer_date_malformed_and_empty_reject(self):
        bad=[
           report(SFR).replace('Spokane County','Spokane City'),
           report(SFR).replace('Page 1 of 1','Page 1 of 2'),
           report(SFR).replace('11/24/2026','11/20/2026'),
           report('  '+SFR.replace('$231,041.36','UNKNOWN')),
           report(),
           report(SFR,SFR.replace('900 EXAMPLE','901 EXAMPLE')),
        ]
        for x in bad:
            with self.subTest(bad=x), self.assertRaises(ValueError):
                self.parse(x)

    def test_invalid_ranges_and_size_reject_before_parse(self):
        for start, end in ((date(2026,10,1),END),(END,START),(START,date(2026,11,27))):
            with self.assertRaises(ValueError):
                m.check_window(start,end,TODAY)
        with patch.object(m.subprocess,'run') as step, self.assertRaises(ValueError):
            m.read_pdf(b'%PDF-'+b'x'*m.MAX_BYTES,START,END,TODAY)
        step.assert_not_called()

    def test_pdf_page_limit_preflight(self):
        with patch.object(m.subprocess,'run') as step, self.assertRaises(ValueError):
            step.return_value.stdout=b'Pages: 401\n'
            m.read_pdf(b'%PDF-fixture',START,END,TODAY)
        step.assert_called_once()
        with patch.object(m.subprocess,'run') as step, self.assertRaises(ValueError):
            m.read_pdf(b'<html>Access Denied</html>',START,END,TODAY)
        step.assert_not_called()
