"""City of Kennewick's rolling weekly issued-permit report."""
from __future__ import annotations

import hashlib
import re
import subprocess
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .base import CollectionResult, new_session
from ..models import Permit

REPORT_URL = "https://www.go2kennewick.com/ArchiveCenter/ViewFile/Item/51"
INDEX_URL = "https://www.go2kennewick.com/Archive/37"
HEADER = re.compile(r"^Issue Date\s+Number\s+Type / Work Class\s+Address\s+Owner\s+Contractor\s+Valuation\s*$")
DAY = r"\d{1,2}/\d{1,2}/\d{4}"
PERIOD = re.compile(rf"^\s*({DAY})\s+-\s+({DAY})\s*$", re.M)
START = re.compile(rf"^\s*({DAY})\s+([A-Z]+-\d{{4}}-\d+)\s")
FOOTER = re.compile(r"^\s*\d+ of \d+\s*$")
MAX_PDF_BYTES = 5_000_000

# Known codes only. Generic residential new construction lacks enough
# information to distinguish single-family from multi-family.
CLASSES = {
    ("BLDR", "residential / express detached single family dwelling"): "Single Family",
    ("BLDR", "residential / detached single family dwelling"): "Single Family",
}


def report_date(value: str) -> date:
    return datetime.strptime(value, "%m/%d/%Y").date()


def parse_report(layout: str, *, today: date, digest: str) -> CollectionResult:
    pages = [page for page in layout.split("\f") if page.strip()]
    if not pages:
        raise ValueError("empty Kennewick PDF")
    records = {}
    period = None
    report_dates = []
    for i, page in enumerate(pages, 1):
        matched = PERIOD.search(page)
        if not matched or "Permit Activity Report" not in page:
            raise ValueError("unexpected Kennewick report title or period")
        week = tuple(report_date(value) for value in matched.groups())
        if week[1] > today or (week[1] - week[0]).days not in (6, 7):
            raise ValueError("unexpected Kennewick report dates")
        if period and period != week:
            raise ValueError("inconsistent Kennewick report period")
        period = week
        lines = page.splitlines()
        headers = [(j, s) for j, line in enumerate(lines) if HEADER.fullmatch(s := line.lstrip())]
        if len(headers) != 1:
            raise ValueError("unexpected Kennewick column header")
        footer = [s.split() for s in lines if FOOTER.fullmatch(s)]
        if footer != [[str(i), "of", str(len(pages))]]:
            raise ValueError("incomplete Kennewick page sequence")
        j, header = headers[0]
        bounds = [lines[j].index(name) for name in ("Issue Date", "Number", "Type / Work Class", "Address", "Owner", "Contractor", "Valuation")]
        current = None
        rows = []

        def row_cells(line):
            return [line[a:b].strip() for a, b in zip(bounds, bounds[1:] + [None])]

        for line in lines[j+1:]:
            if not line.strip() or FOOTER.fullmatch(line):
                continue
            cells = row_cells(line)
            start = START.match(line)
            if start:
                if cells[:2] != list(start.groups()):
                    raise ValueError("Kennewick row does not align with declared columns")
                current = cells
                rows.append(current)
            elif current and not any(cells[:2]):
                for col in (2, 3, 4, 5, 6):  # Owner is discarded after role comparison.
                    if cells[col]:
                        current[col] = " ".join(filter(None, (current[col], cells[col])))
            else:
                raise ValueError("unrecognized line in Kennewick permit table")

        for issue, number, work, address, owner, contractor, valuation in rows:
            issued = report_date(issue)
            report_dates.append(issued.isoformat())
            if not week[0] <= issued <= week[1]:
                raise ValueError("Kennewick issue outside stated report period")
            work = " ".join(work.split())
            category = CLASSES.get((number.split("-")[0], work.casefold()))
            if not category:
                continue
            if not address or (valuation and not re.fullmatch(r"\$[\d,]+\.\d{2}", valuation)):
                raise ValueError("invalid address/valuation on Kennewick building row")
            # Unnamed, owner-builder and obvious placeholder values are not builder leads.
            if not re.search(r"[A-Za-z]", contractor) or contractor.casefold() == owner.casefold() or contractor.casefold() in {
                "n/a", "none", "owner", "owner builder", "owner-builder",
                "owner performing the work", "permitting department", "unknown",
            }:
                contractor = None
            permit = Permit(
                state="WA", jurisdiction="Kennewick", permit_number=number, issued_date=issued.isoformat(),
                permit_type=f"{category} / New", building_use=category, project_name=work, address=address,
                units=1 if category == "Single Family" else None,
                valuation=float(valuation.replace("$", "").replace(",", "")) if valuation else None,
                contractor=contractor, status="Issued", source_name="City of Kennewick Permit Activity Report",
                source_url=REPORT_URL,
                raw={"description": "", "permitclass": category, "permittypedesc": "New",
                     "source_work_class": work, "source_role": "Contractor" if contractor else None,
                     "source_period_start": week[0].isoformat(), "source_period_end": week[1].isoformat(),
                     "source_pdf_sha256": digest, "source_page": i},
            )
            old = records.get(permit.key)
            if old:
                if {k: v for k, v in old.to_dict().items() if k != "raw"} != {
                    k: v for k, v in permit.to_dict().items() if k != "raw"
                }:
                    raise ValueError("conflicting duplicate Kennewick permit")
                continue
            records[permit.key] = permit
    if not report_dates:
        raise ValueError("Kennewick PDF parsed zero report rows; source review required")
    start, end = period
    return CollectionResult("Kennewick", list(records.values()), INDEX_URL,
        f"Official rolling report {start} to {end}; inspected {len(report_dates)} report rows; opt-in; "
        "exact allowlisted work classes only; reported contractor not independently verified.",
        observed_count=len(report_dates), observed_dates=report_dates)


class KennewickCollector:
    name = "Kennewick"
    freshness_days = 14
    source_url = INDEX_URL

    def collect(self, session=None):
        session = session or new_session()
        with session.get(REPORT_URL, timeout=35, stream=True) as response:
            response.raise_for_status()
            pdf = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                pdf.extend(chunk)
                if len(pdf) > MAX_PDF_BYTES:
                    raise ValueError("Kennewick report exceeds size limit")
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("Kennewick source did not return a PDF")
        # Pass PDF on stdin so public owner columns never enter persistent files.
        parsed = subprocess.run(
            ["pdftotext", "-layout", "-", "-"], input=pdf, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True, timeout=20,
        )
        return parse_report(parsed.stdout.decode("utf-8"), today=datetime.now(ZoneInfo("America/Los_Angeles")).date(),
                            digest=hashlib.sha256(pdf).hexdigest())
