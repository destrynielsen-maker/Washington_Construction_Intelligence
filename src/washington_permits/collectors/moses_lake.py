"""City of Moses Lake's monthly copies of issued permits."""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..classify import EXCLUDE
from ..models import Permit
from .issued_reports import ReportLink, collect_reports, latest_reports, report_anchors


INDEX = 'https://moseslakewa.gov/Archive.aspx?AMID=74'
MONTH = re.compile(r'([A-Za-z]+) (20\d{2}) PERMITS ISSUED', re.I)
PERMIT_ID = re.compile(r'\bPermit\s*#:\s*(BLD20\d{2}-\d{4,7})\b', re.I)
ISSUE = re.compile(r'^Issued:\s*(\d{1,2}/\d{1,2}/20\d{2})\s*$', re.I | re.M)
PERMIT_TYPE = re.compile(r'Permit\s*Type:\s*([^\n]+)', re.I)
DESCRIPTION = re.compile(r'^Work Description:\s*([^\n]+)', re.I | re.M)
JOB_ADDRESS = re.compile(r'^Job Address:\s*(\d+ [^\n]+?\bMoses Lake,\s*WA,?\s*\d{5})\b', re.I | re.M)
VALUATION = re.compile(r'^Valuation:\s*\$([\d,]+\.\d{2})(?=\s|$)', re.I | re.M)
EXPLICIT_NEW = re.compile(r'\bnew (?:sfd|sfr|single[- ]family (?:home|residen(?:ce|tial)|dwelling)|construction)\b', re.I)
CONFLICT = re.compile(r'\b(?:adu|accessory|manufactured|mobile|duplex|multi[- ]?family)\b', re.I)


def discover(html: str, today: date) -> list[ReportLink]:
    links = []
    for label, url, target in report_anchors(html, INDEX):
        match = MONTH.fullmatch(label)
        if not match or target.path.casefold() != '/archive.aspx' or not re.fullmatch(r'ADID=\d+', target.query, re.I):
            continue
        start = datetime.strptime(f'{match[1]} {match[2]}', '%B %Y').date()
        end = start.replace(day=monthrange(start.year, start.month)[1])
        if today - timedelta(days=120) <= end <= today:
            links.append(ReportLink(start, end, url))
    return latest_reports(links, 2)


def parse(pages: list[str], report: ReportLink, digest: str):
    permits = []
    observed = []
    skipped = 0
    for page_number, text in enumerate(pages, 1):
        lines = [' '.join(line.split()) for line in text.splitlines()]
        header = '\n'.join(lines[:35])
        identities = PERMIT_ID.findall(header)
        if not identities and re.search(r'\bPage [2-9] of \d+\b', text, re.I):
            continue
        issue_dates = ISSUE.findall(header)
        work = PERMIT_TYPE.search(header)
        if (not re.search(r'\bCity of Moses Lake\b', header, re.I) or len(identities) != 1
                or len(issue_dates) != 1 or not work):
            skipped += 1
            continue
        try:
            issued = datetime.strptime(issue_dates[0], '%m/%d/%Y').date()
        except ValueError:
            skipped += 1
            continue
        if not report.start <= issued <= report.end:
            skipped += 1
            continue
        number = identities[0].upper()
        observed.append((number, issued.isoformat()))
        if work[1].casefold() != 'residential - 1 unit':
            continue
        description = DESCRIPTION.search(header)
        if not description or not EXPLICIT_NEW.search(description[1]) or EXCLUDE.search(description[1]) or CONFLICT.search(description[1]):
            continue
        address = JOB_ADDRESS.search(header)
        if not address:
            skipped += 1
            continue
        valuation = VALUATION.search(header)
        permits.append(Permit(
            state='WA', jurisdiction='Moses Lake', permit_number=number, issued_date=issued.isoformat(),
            permit_type='Single Family / New', building_use='Single Family', project_name='New single family dwelling',
            address=address[1], units=1, valuation=float(valuation[1].replace(',', '')) if valuation else None,
            status='Issued', source_name='City of Moses Lake Building Permit Archive', source_url=report.url,
            raw={'permitclass': 'Single Family', 'permittypedesc': 'New', 'source_work_class': work[1],
                 'source_period_start': report.start.isoformat(), 'source_period_end': report.end.isoformat(),
                 'source_page': page_number, 'source_pdf_sha256': digest},
        ))
    if not observed or skipped > len(pages) / 3:
        raise ValueError('Moses Lake report does not have enough verifiable issued-permit pages')
    return permits, observed, skipped


class MosesLakeCollector:
    name = 'Moses Lake'
    source_url = INDEX
    freshness_days = 45
    max_pdf_bytes = 20_000_000
    max_pages = 125
    scope_note = 'City-issued single-family dwellings with exact text-layer type and explicit new work only. Scan-based partial coverage.'
    discover = staticmethod(discover)
    parse = staticmethod(parse)

    def collect(self, session=None):
        return collect_reports(self, session, datetime.now(ZoneInfo('America/Los_Angeles')).date())
