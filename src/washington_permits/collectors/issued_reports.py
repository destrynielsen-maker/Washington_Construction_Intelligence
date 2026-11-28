"""Bounded acquisition for Washington public issued-permit PDF reports."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import requests

from .base import CollectionResult


@dataclass(frozen=True, order=True)
class ReportLink:
    start: date
    end: date
    url: str


class _ReportAnchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.text = []

    def handle_data(self, data):
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.links.append((' '.join(''.join(self.text).split()), self.href))
            self.href = None


def report_anchors(html: str, index_url: str):
    anchors = _ReportAnchors()
    anchors.feed(html)
    host = urlsplit(index_url).netloc
    for label, href in anchors.links:
        url = urljoin(index_url, href)
        target = urlsplit(url)
        if target.scheme == 'https' and target.netloc == host and not target.fragment:
            yield label, url, target


def latest_reports(links: list[ReportLink], count: int) -> list[ReportLink]:
    reports = sorted(set(links), reverse=True)[:count]
    if not reports:
        raise ValueError('official index has no recent issued-permit report links')
    if len({(report.start, report.end) for report in reports}) != len(reports):
        raise ValueError('official index has ambiguous links for a selected period')
    return reports


def _download(session, url: str, limit: int) -> bytes:
    with session.get(url, timeout=(5, 25), stream=True, allow_redirects=False) as response:
        if response.status_code in (301, 302, 307, 308):
            origin = urlsplit(url)
            canonical_url = urljoin(url, response.headers.get('Location', ''))
            target = urlsplit(canonical_url)
            if (re.fullmatch(r'/DocumentCenter/View/\d+', origin.path, re.I)
                    and target.scheme == 'https' and target.netloc == origin.netloc and not target.fragment
                    and target.query in ('', 'bidId=')
                    and re.fullmatch(re.escape(origin.path) + r'/[A-Za-z0-9-]+', target.path, re.I)):
                return _download(session, canonical_url, limit)
        if response.status_code != 200:
            raise RuntimeError(f'official report request returned HTTP {response.status_code}')
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            content.extend(chunk)
            if len(content) > limit:
                raise ValueError('official report response exceeds size limit')
    return bytes(content)


def collect_reports(collector, session, today: date) -> CollectionResult:
    if session is None:
        with requests.Session() as owned_session:
            owned_session.headers['User-Agent'] = 'WashingtonConstructionIntelligence/0.1 (public permit reports)'
            return collect_reports(collector, owned_session, today)

    from pypdf import PdfReader

    html = _download(session, collector.source_url, 1_500_000).decode('utf-8-sig')
    reports = collector.discover(html, today)
    permits = {}
    observed = set()
    skipped = 0
    for report in reports:
        pdf = _download(session, report.url, collector.max_pdf_bytes)
        if not pdf.startswith(b'%PDF-'):
            raise ValueError('issued-permit report did not return a PDF')
        reader = PdfReader(BytesIO(pdf))
        if not 1 <= len(reader.pages) <= collector.max_pages:
            raise ValueError('issued-permit report page count outside verified limits')
        pages = [page.extract_text() or '' for page in reader.pages]
        rows, dates, unmatched = collector.parse(pages, report, hashlib.sha256(pdf).hexdigest())
        observed.update(dates)
        skipped += unmatched
        for permit in rows:
            previous = permits.get(permit.key)
            if previous and (previous.issued_date, previous.permit_type, previous.address, previous.valuation) != (
                permit.issued_date, permit.permit_type, permit.address, permit.valuation
            ):
                raise ValueError('official reports disagree on an accepted permit')
            permits.setdefault(permit.key, permit)
    if not observed:
        raise ValueError('issued-permit reports contained no verified issuance dates')
    return CollectionResult(
        collector.name, list(permits.values()), collector.source_url,
        f'{len(reports)} published reports through {reports[0].end}. Dated permit IDs: {len(observed)}. '
        f'Eligible leads: {len(permits)}. {collector.scope_note}'
        + (f' {skipped} unreadable or inconsistent entries skipped.' if skipped else ''),
        observed_count=len(observed), observed_dates=sorted({issued for _, issued in observed}),
    )
