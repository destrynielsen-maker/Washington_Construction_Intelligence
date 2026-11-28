"""Grant County's official weekly issued building permit register."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..classify import EXCLUDE
from ..models import Permit
from .issued_reports import ReportLink, collect_reports, latest_reports, report_anchors


INDEX = 'https://www.grantcountywa.gov/863/Permit-Reports'
DAY = r'\d{1,2}/\d{1,2}/20\d{2}'
RANGE = re.compile(rf'Report Dates: ({DAY})\s*-\s*({DAY})', re.I)
FOOTER = re.compile(r'Permits Issued:\s*(\d+)', re.I)
ROW = re.compile(rf'^({DAY})\s+([A-Z]{{1,8}} \d{{2}}-\d{{3,7}})\s*$', re.I | re.M)
SCOPES = (
    ('Single Family', re.compile(r'^(?:new )?(?:one family|single[- ]family) dwelling\b', re.I)),
    ('Multifamily', re.compile(r'^new (?:duplex|triplex|fourplex|apartments?|multi[- ]?family building|townhomes?)\b', re.I)),
    ('Commercial', re.compile(r'^new (?:commercial building|warehouse|retail building|office building|industrial building)\b', re.I)),
)
NON_PRIMARY = re.compile(r'\b(?:accessory|adu|existing dwelling|manufactured|mobile|replacement|relocat\w*)\b', re.I)


def discover(html: str, today: date) -> list[ReportLink]:
    links = []
    for label, url, target in report_anchors(html, INDEX):
        if not re.fullmatch(r'[A-Za-z]+ \d{1,2}, 20\d{2}', label):
            continue
        if not re.fullmatch(r'/DocumentCenter/View/\d+(?:/[A-Za-z0-9-]+)?', target.path, re.I) or target.query not in ('', 'bidId='):
            continue
        try:
            end = datetime.strptime(label, '%B %d, %Y').date()
        except ValueError:
            continue
        if today - timedelta(days=50) <= end <= today:
            links.append(ReportLink(end - timedelta(days=6), end, url))
    return latest_reports(links, 2)


def parse(pages: list[str], report: ReportLink, digest: str):
    permits = []
    observed = []
    skipped = 0
    expected_count = None
    header = ' '.join(pages[0].split())
    if ('Grant County Building Department Issued Permit Report' not in header
            or 'Issued Permit # Applicant Primary Contractor Site Address Parcel Project Description Valuation' not in header):
        raise ValueError('unrecognized Grant County building report schema')
    period = RANGE.search(header)
    if not period or tuple(datetime.strptime(value, '%m/%d/%Y').date() for value in period.groups()) != (report.start, report.end):
        raise ValueError('Grant County report does not match the linked week')

    for number, page in enumerate(pages, 1):
        text = '\n'.join(' '.join(value.split()) for value in page.splitlines() if value.strip())
        footer = FOOTER.search(text)
        if footer:
            if expected_count is not None:
                raise ValueError('Grant County report has multiple issued permit totals')
            expected_count = int(footer[1])
            text = text.split('Total Valuation:', 1)[0]
        rows = list(ROW.finditer(text))
        for index, row in enumerate(rows):
            issued = datetime.strptime(row[1], '%m/%d/%Y').date()
            if not report.start <= issued <= report.end:
                raise ValueError('Grant County issue date falls outside the linked week')
            permit_number = row[2].upper()
            observed.append((permit_number, issued.isoformat()))
            next_row = rows[index + 1].start() if index + 1 < len(rows) else len(text)
            block = text[row.end():next_row]
            fields = block.strip().splitlines()
            parcels = [i for i, value in enumerate(fields) if re.fullmatch(r'\d{8,10}', value)]
            if len(parcels) != 1 or parcels[0] < 2:
                skipped += 1
                continue
            parcel = parcels[0]
            address = ' '.join(fields[parcel - 2:parcel])
            details = fields[parcel + 1:]
            valuation = float(details.pop().replace(',', '')) if details and re.fullmatch(r'[\d,]+\.\d{2}', details[-1]) else None
            scope = ' '.join(details)
            categories = [category for category, matcher in SCOPES if matcher.search(scope)]
            if len(categories) != 1 or EXCLUDE.search(scope) or NON_PRIMARY.search(scope):
                continue
            if not re.match(r'^\d+\s+\S', address):
                skipped += 1
                continue
            category = categories[0]
            permits.append(Permit(
                state='WA', jurisdiction='Grant County', permit_number=permit_number, issued_date=issued.isoformat(),
                permit_type=f'{category} / New', building_use=category, project_name=f'New {category.lower()} building',
                address=address, units=1 if category == 'Single Family' else None, valuation=valuation, status='Issued',
                source_name='Grant County Weekly Issued Building Permits', source_url=report.url,
                raw={'permitclass': category, 'permittypedesc': 'New', 'source_period_start': report.start.isoformat(),
                     'source_period_end': report.end.isoformat(), 'source_page': number, 'source_pdf_sha256': digest},
            ))
    if expected_count != len(observed) or len(set(observed)) != len(observed):
        raise ValueError('Grant County issued permit total does not match distinct parsed rows')
    return permits, observed, skipped


class GrantCountyCollector:
    name = 'Grant County'
    source_url = INDEX
    freshness_days = 14
    max_pdf_bytes = 5_000_000
    max_pages = 25
    scope_note = 'County building issuances with explicitly recognized primary building work. City-issued permits and Fire Marshal reports remain separate.'
    discover = staticmethod(discover)
    parse = staticmethod(parse)

    def collect(self, session=None):
        return collect_reports(self, session, datetime.now(ZoneInfo('America/Los_Angeles')).date())
