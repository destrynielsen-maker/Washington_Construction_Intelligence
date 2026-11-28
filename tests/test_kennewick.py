from datetime import date
import unittest
from unittest.mock import MagicMock

from washington_permits.classify import classify_permit
from washington_permits.collectors.kennewick import KennewickCollector, parse_report
from washington_permits.pipeline import _success


WIDTHS = [13,16,52,27,38,43]


def columns(*cells):
    return ''.join(f'{c:<{w}}' for c,w in zip(cells,WIDTHS)) + cells[-1]


HEADER = columns('Issue Date','Number','Type / Work Class','Address','Owner','Contractor','Valuation')
FIRST = columns('11/18/2026','BLDR-2026-0001','Residential / Express Detached Single Family',
                '100 EXAMPLE AVE','FICTIONAL OWNER','FICTIONAL CONTRACTING','$352,726.00')
WRAP = columns('','','Dwelling','','','LLC','')
ROOF = columns('11/20/2026','BLDR-2026-0002','Residential / Reroof',
               '102 EXAMPLE AVE','OTHER OWNER','EXAMPLE ROOFER','$12.00')
SELF = columns('11/19/2026','BLDR-2026-0003','Residential / Detached Single Family Dwelling',
               '104 EXAMPLE AVE','SAME NAME','same name','$1.00')


def report(*rows, footer='1 of 1'):
    return '\n'.join(('Permit Activity Report','11/16/2026 - 11/22/2026',HEADER,*rows,footer))+'\f'


def parse(layout):
    return parse_report(layout,today=date(2026,11,26),digest='evidence')


class KennewickTests(unittest.TestCase):
    def test_split_work_class_roles_filtering_and_duplicate(self):
        result = parse(report(FIRST, WRAP, ROOF, FIRST, WRAP, SELF))
        self.assertEqual(result.observed_count, 4)
        self.assertEqual(len(result.permits), 2)
        found = classify_permit(result.permits[0])
        self.assertEqual(found.classification,'SINGLE_FAMILY')
        self.assertEqual(found.issued_date,'2026-11-18')
        self.assertEqual(found.contractor,'FICTIONAL CONTRACTING LLC')
        self.assertEqual(found.raw['source_role'],'Contractor')
        self.assertEqual(found.raw['source_period_end'],'2026-11-22')
        self.assertEqual(found.raw['source_pdf_sha256'],'evidence')
        self.assertIsNone(found.owner)
        self.assertNotIn('FICTIONAL OWNER',str(found.to_dict()))
        self.assertIsNone(result.permits[1].contractor)

    def test_no_eligible_projects_does_not_hide_observed_source_freshness(self):
        result = parse(report(ROOF))
        status = _success(result,0,None,'2026-11-26',date(2026,11,26),14)
        self.assertEqual(status['status'],'healthy')
        self.assertEqual(status['records_seen'],1)
        self.assertEqual(status['newest_permit_date'],'2026-11-20')
        self.assertEqual(status['qualifying_records'],0)

    def test_rejects_schema_page_drift_and_date_errors(self):
        for malformed in [report(FIRST,WRAP,footer='1 of 2'), report(FIRST,WRAP).replace('Contractor','Applicant'),
                          report(FIRST,WRAP).replace('11/18/2026','11/28/2026'), report(FIRST,WRAP).replace('11/22/2026','11/30/2026')]:
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                parse(malformed)

    def test_conflicting_duplicates_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'conflicting duplicate'):
            parse(report(FIRST,WRAP,FIRST.replace('100 EXAMPLE','102 EXAMPLE'),WRAP))

    def test_bot_wall_is_not_empty_report(self):
        session = MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.iter_content.return_value = [b'<html>Forbidden</html>']
        with self.assertRaisesRegex(ValueError,'did not return a PDF'):
            KennewickCollector().collect(session)
