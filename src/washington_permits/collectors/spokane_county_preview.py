"""One-shot, non-publishing preview for Spokane County's valuation-limited report."""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

HOST = "https://co-spokane-wa.smartgovcommunity.com"
REPORT_ID = "84f77d9d-4faa-40b1-b449-9ffe00b519bb"
FORM = f"{HOST}/Public/Report?Id={REPORT_ID}"
MAX_BYTES = 4_000_000
MAX_PAGES = 40
MAX_DAYS = 31
DAY = r"\d{1,2}/\d{1,2}/\d{4}"
PERIOD = re.compile(rf"^\s*From Issued Date:\s*({DAY})\s+Thru\s+({DAY})\s*$", re.M)
HEADER = re.compile(r"^Permit #\s+Project Description\s+Issued\s+Site Address\s+Total Valuation\s*$")
FOOTER = re.compile(r"Page (\d+) of (\d+)\s*$")
ROW = re.compile(rf"^\s*([A-Z]+(?:-[A-Z]+)?\d{{5,}})\s+(.+?)\s+({DAY})\s+(.+?)\s+\$([\d,]+\.\d{{2}})\s*$")
PRIMARY_ID = re.compile(r"^(?:E-)?B\d{7}$")
LEADING = r"(?:(?:MUPS?|MUP\d+)(?:\s+PLAN[- :]+|[- :]+)\s*)?(?:(?:CONSTRUCT )?NEW\s+)?"
SINGLE = re.compile(LEADING + r"(?:SINGLE\s*[- ]\s*FAMILY\s+(?:DWELLING|RESIDENCE)|NEW SFR|SFR W[/ ]|SFR WITH)\b")
DUPLEX = re.compile(LEADING + r"(?:TWO\s*[- ]\s*FAMILY\s+DWELLING|DUPLEX)\b")
EXCLUDED = re.compile(r"\b(?:ADU|ACCESSORY DWELLING|MANUFACTURED|MOBILE HOME|REMODEL|ALTERATION|REPLACEMENT|PLAN REVISION|FIRE STATION|PUBLIC WORKS|WILDFIRE|REBUILD)\b")


def check_window(start, end, today):
    if start > end or end > today or (end-start).days >= MAX_DAYS:
        raise ValueError("Require an ordered, non-future range of at most 31 calendar days.")


def parse(layout, start, end, today, digest):
    check_window(start, end, today)
    pages = [p for p in layout.split("\f") if p.strip()]
    if not 0 < len(pages) <= MAX_PAGES:
        raise ValueError("Unexpected county report page count.")
    records = {}
    duplicates = 0
    observed = set()
    excluded = 0
    for i, p in enumerate(pages, 1):
        ds = PERIOD.findall(p)
        if (not re.search(r"^\s*Spokane County SmartGov\s*$",p,re.M)
            or not re.search(r"^\s*Permits with Values over \$100,000\s*$",p,re.M)
            or len(ds) != 1 or tuple(datetime.strptime(v,"%m/%d/%Y").date() for v in ds[0]) != (start,end)):
            raise ValueError("Unverified county identity or report period.")
        lines = p.splitlines()
        headers = [j for j,l in enumerate(lines) if HEADER.fullmatch(l)]
        footers = [m.groups() for l in lines if (m := FOOTER.search(l))]
        if len(headers) != 1 or footers != [(str(i),str(len(pages)))]:
            raise ValueError("Unrecognized or incomplete county report page layout.")
        pending = []
        for line in lines[headers[0]+1:]:
            m = ROW.fullmatch(line)
            if m:
                pending.append((m.groups(),[]))
            elif (re.match(r"^\s*[A-Z]+(?:-[A-Z]+)?\d{5,}\b", line) or
                  (line and line[0].isalnum())) and not FOOTER.search(line):
                raise ValueError("Unrecognized county permit row.")
            elif pending and line.strip() and not line.lstrip().startswith("Units:") and not FOOTER.search(line):
                pending[-1][1].append(line.strip())
        for (number, description, issued, address, valuation), continuing in pending:
            day = datetime.strptime(issued,"%m/%d/%Y").date()
            if not start <= day <= end:
                raise ValueError("Issued date outside verified report period.")
            val = Decimal(valuation.replace(",",""))
            context = " ".join((description,*continuing)).upper()
            category = "MULTIFAMILY" if DUPLEX.match(context) else "SINGLE_FAMILY" if SINGLE.match(context) else None
            identity = (day, description, address, val)
            key = f"WA|spokane county|{number.lower()}"
            if key in records:
                if records[key][0] != identity:
                    raise ValueError("Conflicting duplicate county permit ID.")
                duplicates += 1
                continue
            observed.add(day)
            if val <= 100_000 or not PRIMARY_ID.fullmatch(number) or not category or EXCLUDED.search(context):
                excluded += 1
                records[key] = (identity,None)
                continue
            records[key] = (identity,dict(key=key,state="WA",jurisdiction="Spokane County",permit_number=number,
                issued_date=day.isoformat(),status="Issued",classification=category,project_description=context,
                address=address.strip(),valuation=str(val),contractor=None,contractor_role="not provided",
                source_url=FORM,report_page=i,report_start=start.isoformat(),report_end=end.isoformat(),report_sha256=digest))
    if not records:
        raise ValueError("No verified county permit rows; not an authoritative zero.")
    return dict(mode="preview only; no stored or published writes",source_url=FORM,
        scope="Spokane County only; published valuation report subset strictly over $100,000; explicit primary SFR/duplex only",
        observed_unique=len(records),duplicate_rows=duplicates,excluded=excluded,pages=len(pages),
        latest_observed_issue=max(observed).isoformat(), permits=[row for _,row in records.values() if row])


def read_pdf(pdf, start, end, today):
    if len(pdf) > MAX_BYTES or not pdf.startswith(b"%PDF-"):
        raise ValueError("Expected a bounded County PDF, not HTML or an access-denied body.")
    info=subprocess.run(["pdfinfo","-"],input=pdf,stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,timeout=10,check=True)
    page_count=re.search(rb"^Pages:\s*(\d+)\s*$",info.stdout,re.M)
    if not page_count or not 0<int(page_count[1])<=MAX_PAGES:
        raise ValueError("County PDF page count exceeded the preview limit.")
    result=subprocess.run(["pdftotext","-layout","-","-"],input=pdf,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,timeout=15,check=True)
    if len(result.stdout)>MAX_BYTES:
        raise ValueError("County PDF text exceeded the preview limit.")
    return parse(result.stdout.decode(),start,end,today,hashlib.sha256(pdf).hexdigest())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("start",type=date.fromisoformat)
    p.add_argument("end",type=date.fromisoformat)
    p.add_argument("--pdf",required=True,type=Path,help="Official PDF exported manually with authorization")
    a=p.parse_args()
    today=datetime.now(ZoneInfo("America/Los_Angeles")).date()
    check_window(a.start,a.end,today)
    with a.pdf.open("rb") as f:
        pdf=f.read(MAX_BYTES+1)
    print(json.dumps(read_pdf(pdf,a.start,a.end,today),indent=2))

if __name__=="__main__":
    main()
