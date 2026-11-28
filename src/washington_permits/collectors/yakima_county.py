"""Yakima County's weekly issued structural permits."""
from __future__ import annotations

import re
from calendar import month_abbr, month_name
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..classify import EXCLUDE
from ..models import Permit
from .issued_reports import ReportLink, collect_reports, latest_reports, report_anchors


INDEX = 'https://www.yakimacounty.us/1882/Permits-Issued---Building-and-Manufactur'
WEEK = re.compile(
    r'Building Permits Issued ([A-Za-z]+) (\d{1,2})\s*[-–]\s*(?:([A-Za-z]+) )?(\d{1,2}), (20\d{2})', re.I
)
ROW_ID = re.compile(r'(?m)^([A-Z]{2,8}20\d{2}-)\s*(\d{4,7})(?=\s)', re.I)
EVENT = re.compile(r'(?P<final>Final\s+C\s*/\s*O\s+)?Issued\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+\$(?P<value>[\d,]+\.\d{2})(?=\s)', re.I)
PARCEL = re.compile(r'^\s*(?:\d{11}|\d{7}\s+\d{4})\s*$', re.M)
ADDRESS_END = re.compile(r'\bWA\s+\d{5}(?:-\d{4})?\b', re.I)
NON_PRIMARY = re.compile(r'\b(adu|accessory|change of use|shop|temporary|agricultural|ag building)\b', re.I)
SCOPES = (
    ('Single Family', re.compile(r'\bnew (?:sfr|single[- ]family (?:residence|dwelling|home))\b', re.I)),
    ('Multifamily', re.compile(r'\bnew (?:duplex|triplex|fourplex|apartments?|multi[- ]?family (?:building|dwelling)|townhouses?|townhomes?)\b', re.I)),
    ('Commercial', re.compile(r'\bnew (?:commercial building|warehouse|retail building|office building|hotel|school|industrial building)\b', re.I)),
)
MONTH_NUMBERS = {name.casefold(): number for names in (month_name, month_abbr) for number, name in enumerate(names) if number}


def discover(html: str, today: date) -> list[ReportLink]:
    links = []
    earliest = today - timedelta(days=70)
    for label, url, target in report_anchors(html, INDEX):
        match = WEEK.fullmatch(label)
        if not match or not re.fullmatch(r'/DocumentCenter/View/\d+/Building-Permits-Issued-[A-Za-z0-9-]+', target.path, re.I) or target.query:
            continue
        month, first, final_month, last, year = match.groups()
        if not earliest.year <= int(year) <= today.year:
            continue
        try:
            first_month = MONTH_NUMBERS[month.casefold()]
            last_month = MONTH_NUMBERS[(final_month or month).casefold()]
            start = date(int(year) - int(first_month == 12 and last_month == 1), first_month, int(first))
            end = date(int(year), last_month, int(last))
        except (KeyError, ValueError):
            continue
        if 0 <= (end - start).days <= 7 and earliest <= end <= today:
            links.append(ReportLink(start, end, url))
    return latest_reports(links, 4)


def parse(pages: list[str], report: ReportLink, digest: str):
    header = ' '.join(pages[0].split())
    if not re.search(r'\bRecord ID Status Date Status Valuation Record Name Parcel Number Site Address Owner Contractor\b', header, re.I):
        raise ValueError('unrecognized Yakima County report schema')

    permits = []
    observed = []
    skipped = 0
    found = 0
    for page_number, text in enumerate(pages, 1):
        rows = list(ROW_ID.finditer(text))
        for index, row in enumerate(rows):
            found += 1
            block = text[row.end():rows[index + 1].start() if index + 1 < len(rows) else len(text)].lstrip()
            event = EVENT.match(block)
            if not event:
                skipped += 1
                continue
            if event['final']:
                continue
            issued = datetime.strptime(event['date'], '%m/%d/%Y').date()
            if not report.start <= issued <= report.end:
                raise ValueError('Yakima County issue date falls outside the linked period')
            number = ''.join(row.groups()).upper()
            observed.append((number, issued.isoformat()))
            if not number.startswith('BLD'):
                continue

            info = block[event.end():]
            parcel = PARCEL.search(info)
            if not parcel:
                skipped += 1
                continue
            title = ' '.join(info[:parcel.start()].split())
            if EXCLUDE.search(title) or NON_PRIMARY.search(title):
                continue
            categories = [category for category, scope in SCOPES if scope.search(title)]
            if len(categories) != 1:
                continue
            address_lines = info[parcel.end():].strip()
            address_end = ADDRESS_END.search(address_lines)
            if (not address_end or not re.match(r'^\d+\s+', address_lines)
                    or len(address_lines[:address_end.end()].splitlines()) > 4):
                skipped += 1
                continue
            address = ' '.join(address_lines[:address_end.end()].split())
            category = categories[0]
            permits.append(Permit(
                state='WA', jurisdiction='Yakima County', permit_number=number, issued_date=issued.isoformat(),
                permit_type=f'{category} / New', building_use=category, project_name=f'New {category.lower()} building',
                address=address, units=1 if category == 'Single Family' else None,
                valuation=float(event['value'].replace(',', '')), status='Issued',
                source_name='Yakima County Weekly Building Permits Issued', source_url=report.url,
                raw={'permitclass': category, 'permittypedesc': 'New', 'source_status': 'Issued',
                     'source_period_start': report.start.isoformat(), 'source_period_end': report.end.isoformat(),
                     'source_page': page_number, 'source_pdf_sha256': digest},
            ))
    if not found:
        raise ValueError('Yakima County report contained no recognizable permit rows')
    return permits, observed, skipped


class YakimaCountyCollector:
    name = 'Yakima County'
    source_url = INDEX
    freshness_days = 14
    max_pdf_bytes = 5_000_000
    max_pages = 25
    scope_note = 'County-issued primary buildings with explicit new work only. Final occupancy and applications are excluded.'
    discover = staticmethod(discover)
    parse = staticmethod(parse)

    def collect(self, session=None):
        return collect_reports(self, session, datetime.now(ZoneInfo('America/Los_Angeles')).date())
