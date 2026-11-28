from datetime import date
import unittest
from unittest.mock import MagicMock

from washington_permits.classify import classify_permit
from washington_permits.collectors.grant_county import GrantCountyCollector
from washington_permits.collectors.issued_reports import ReportLink, _download, collect_reports
from washington_permits.collectors.moses_lake import MosesLakeCollector
from washington_permits.collectors.yakima_county import YakimaCountyCollector


YAKIMA_HEADER = 'Record ID Status Date Status Valuation Record Name Parcel Number Site Address Owner Contractor\n'
YAKIMA_PERIOD = ReportLink(date(2026, 11, 16), date(2026, 11, 20), 'https://www.yakimacounty.us/example')
MOSES_PERIOD = ReportLink(date(2026, 10, 1), date(2026, 10, 31), 'https://moseslakewa.gov/Archive.aspx?ADID=1')
GRANT_PERIOD = ReportLink(date(2026, 11, 14), date(2026, 11, 20), 'https://www.grantcountywa.gov/DocumentCenter/View/1')
GRANT_HEADER = ('Grant County Building Department\nIssued Permit Report\nReport Dates: 11/14/2026 - 11/20/2026\n'
                'Issued\nPermit #\nApplicant\nPrimary Contractor\nSite Address\nParcel\nProject Description\nValuation\n')


def county_row(number, status='Issued', title='TEST OWNER - New SFR', issued='11/18/2026'):
    return (f'BLD2026-\n{number} {status} {issued} $100,000.00 {title}\n'
            '1200000\n7052\n100 TEST RD,\nSELAH, WA 98942\nTEST OWNER\nTEST CONTRACTOR\n')


def moses_page(number, *, issue='Issued: 10/18/2026', work='Residential - 1 Unit', title='New SFD'):
    return (f'City of Moses Lake\nPermit #: BLD2026-{number}\n{issue}\nExpires: 5/10/2027\n'
            f'Job Address: 200 TEST RD, Moses Lake, WA, 98837\nValuation: $100,000.00 Permit Type: {work}\n'
            f'Work Description: {title}\nTEST OWNER\nTEST CONTRACTOR\nPage 1 of 1\n')


def grant_row(number, scope='One Family Dwelling, 1-story, attached garage'):
    return (f'11/19/2026\nBF 26-{number}\nTEST OWNER\nTEST CONTRACTOR\n'
            f'300 TEST RD\nMoses Lake\n142000123\n{scope}\n100,000.00\n')


class IssuedReportTests(unittest.TestCase):
    def test_yakima_selects_recent_official_issued_links_only(self):
        html = """<a href='/DocumentCenter/View/1/Building-Permits-Issued-1'>Building Permits Issued November 16-20, 2026</a>
        <a href='/DocumentCenter/View/2/Building-Permit-Applications-2'>Building Permit Applications November 23-27, 2026</a>
        <a href='/DocumentCenter/View/3/Manufactured-Homes-Issued-3'>Manufactured Homes Issued November 23-27, 2026</a>
        <a href='https://invalid.example/DocumentCenter/View/4/Building-Permits-Issued-4'>Building Permits Issued November 23-27, 2026</a>
        <a href='/DocumentCenter/View/5/Building-Permits-Issued-5'>Building Permits Issued July 31 - Aug 4, 2023</a>"""
        links = YakimaCountyCollector.discover(html, date(2026, 11, 27))
        self.assertEqual([(r.start, r.end) for r in links], [(YAKIMA_PERIOD.start, YAKIMA_PERIOD.end)])

    def test_yakima_excludes_final_occupancy_and_ambiguous_or_non_new_scopes(self):
        page = YAKIMA_HEADER + county_row('00001') + county_row('00002', 'Final C/O Issued')
        page += county_row('00003', title='New SFR Addition') + county_row('00004', title='New Shop')
        records, observed, skipped = YakimaCountyCollector.parse([page], YAKIMA_PERIOD, 'test')
        self.assertEqual(len(observed), 3)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(records), 1)
        permit = classify_permit(records[0])
        self.assertEqual(permit.classification, 'SINGLE_FAMILY')
        self.assertEqual(permit.issued_date, '2026-11-18')
        self.assertEqual(permit.raw['source_status'], 'Issued')
        self.assertNotIn('TEST OWNER', str(permit.to_dict()))
        self.assertNotIn('TEST CONTRACTOR', str(permit.to_dict()))

    def test_yakima_rejects_unrecognized_schema_and_outside_report_dates(self):
        with self.assertRaisesRegex(ValueError, 'schema'):
            YakimaCountyCollector.parse([county_row('00001')], YAKIMA_PERIOD, 'test')
        with self.assertRaisesRegex(ValueError, 'outside'):
            YakimaCountyCollector.parse([YAKIMA_HEADER + county_row('00001', issued='11/21/2026')], YAKIMA_PERIOD, 'test')

    def test_moses_archive_links_are_month_bounded(self):
        html = """<a href='Archive.aspx?ADID=1585'><span> OCTOBER 2026 PERMITS ISSUED </span></a>
        <a href='Archive.aspx?ADID=1584'>SEPTEMBER 2026 PERMITS ISSUED</a>
        <a href='Archive.aspx?ADID=1589'>NOVEMBER 2026 PERMITS ISSUED</a>
        <a href='Archive.aspx?ADID=1588'>OCTOBER 2026 PERMIT APPLICATIONS</a>"""
        links = MosesLakeCollector.discover(html, date(2026, 11, 27))
        self.assertEqual([(r.end, r.url.rsplit('=', 1)[-1]) for r in links], [
            (date(2026, 10, 31), '1585'), (date(2026, 9, 30), '1584')])

    def test_moses_requires_exact_issued_date_and_unambiguous_new_single_unit(self):
        pages = [moses_page('00001'), moses_page('00002', work='Residential - 4 Unit'),
                 moses_page('00003', issue='ISSuOd: 10/18/2026'),
                 moses_page('00004', title='Replacement windows'), 'Page 2 of 2']
        records, observed, skipped = MosesLakeCollector.parse(pages, MOSES_PERIOD, 'test')
        self.assertEqual(len(observed), 3)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(records), 1)
        permit = classify_permit(records[0])
        self.assertEqual(permit.classification, 'SINGLE_FAMILY')
        self.assertEqual(permit.raw['source_page'], 1)
        self.assertIsNone(permit.owner)
        self.assertIsNone(permit.contractor)

    def test_grant_only_dated_county_building_links_are_selected(self):
        html = """<a href='/DocumentCenter/View/1'>November 20, 2026</a>
        <a href='/DocumentCenter/View/2'>November 20, 2026 Fire Marshal</a>
        <a href='/DocumentCenter/View/3'>November 27, 2026 No Permits Issued</a>"""
        self.assertEqual(GrantCountyCollector.discover(html, date(2026, 11, 27)), [GRANT_PERIOD])

    def test_grant_reconciles_issued_totals_and_excludes_addition(self):
        page = GRANT_HEADER + grant_row('0001') + grant_row('0002', 'One Family Dwelling addition')
        page += 'Total Valuation:\n$200,000.00\nPermits Issued:\n2\n'
        records, observed, skipped = GrantCountyCollector.parse([page], GRANT_PERIOD, 'test')
        self.assertEqual(len(observed), 2)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(records), 1)
        permit = classify_permit(records[0])
        self.assertEqual(permit.jurisdiction, 'Grant County')
        self.assertEqual(permit.classification, 'SINGLE_FAMILY')
        self.assertNotIn('TEST OWNER', str(permit.to_dict()))
        with self.assertRaisesRegex(ValueError, 'total'):
            GrantCountyCollector.parse([page.replace('Permits Issued:\n2', 'Permits Issued:\n3')], GRANT_PERIOD, 'test')

    def test_restricts_report_redirect_to_its_canonical_document(self):
        session = MagicMock()
        redirect, pdf = MagicMock(), MagicMock()
        redirect.__enter__.return_value = redirect
        pdf.__enter__.return_value = pdf
        redirect.status_code = 301
        pdf.status_code = 200
        pdf.iter_content.return_value = [b'%PDF-test']
        redirect.headers = {'Location': '/DocumentCenter/View/1/Building-Permits?bidId='}
        session.get.side_effect = [redirect, pdf]
        self.assertEqual(_download(session, GRANT_PERIOD.url, 1024), b'%PDF-test')
        self.assertEqual(session.get.call_args.args[0], GRANT_PERIOD.url + '/Building-Permits?bidId=')
        redirect.headers = {'Location': 'https://other.invalid/DocumentCenter/View/1/Building-Permits'}
        session.get.reset_mock(side_effect=True)
        session.get.return_value = redirect
        with self.assertRaisesRegex(RuntimeError, 'HTTP 301'):
            _download(session, GRANT_PERIOD.url, 1024)
        session.get.assert_called_once()

    def test_http_restriction_stops_without_retry_or_a_healthy_empty_result(self):
        session = MagicMock()
        session.get.return_value.__enter__.return_value.status_code = 403
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
            collect_reports(YakimaCountyCollector(), session, date(2026, 11, 27))
        session.get.assert_called_once()

    def test_moses_archive_redirect_keeps_the_exact_document_identity(self):
        archive_url = 'https://moseslakewa.gov/Archive.aspx?ADID=1585'
        canonical = '/ArchiveCenter/ViewFile/Item/1585'
        session = MagicMock()
        redirect, pdf = MagicMock(), MagicMock()
        redirect.__enter__.return_value = redirect
        pdf.__enter__.return_value = pdf
        redirect.status_code = 302
        redirect.headers = {'Location': canonical}
        pdf.status_code = 200
        pdf.iter_content.return_value = [b'%PDF-test']
        session.get.side_effect = [redirect, pdf]
        self.assertEqual(_download(session, archive_url, 1024), b'%PDF-test')
        self.assertEqual(session.get.call_args.args[0], 'https://moseslakewa.gov' + canonical)

        for location in (
                '/ArchiveCenter/ViewFile/Item/1584',
                canonical + '?download=1',
                'https://other.invalid' + canonical,
                'http://moseslakewa.gov' + canonical,
        ):
            with self.subTest(location=location):
                redirect.headers = {'Location': location}
                session.get.reset_mock(side_effect=True)
                session.get.return_value = redirect
                with self.assertRaisesRegex(RuntimeError, 'HTTP 302'):
                    _download(session, archive_url, 1024)
                session.get.assert_called_once()
