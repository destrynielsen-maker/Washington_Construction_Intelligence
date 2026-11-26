# Washington Construction Intelligence

Washington building-permit prospecting focused on new:

- single-family residential construction
- multifamily / townhome / duplex / apartment construction
- commercial / institutional / industrial construction

## Production source

**Seattle SDCI — Issued Building Permits**

The City of Seattle public open-data feed exposes issued permit records with project description, housing units, estimated project cost, contractor, address, status, and a direct SDCI record link.

## Outputs

- sortable/filterable browser dashboard
- persistent permit history
- source-health monitoring
- builder/GC rollups
- RSS feeds for all new construction, single-family, multifamily, commercial, and top opportunities
- rep-facing source directory

## Automation

GitHub Actions runs every six hours, manually, and whenever code changes reach `main`. Bot-generated data/RSS commits are excluded from the push trigger to prevent loops.

For GitHub Pages set:

**Settings → Pages → Source → GitHub Actions**

## Spokane County valuation-report preview (offline / standalone)

This is not registered in the statewide pipeline or production schedule. In an
isolated copy with the existing Python dependencies and Poppler (`pdfinfo`,
`pdftotext`), it prints a JSON preview to stdout only:

```sh
PYTHONPATH=src python -m washington_permits.collectors.spokane_county_preview \
  2026-11-23 2026-11-26 --pdf /path/to/official-report.pdf
```

Provide an official PDF obtained through the ordinary authorized manual browser
export. The public site's [robots.txt](https://co-spokane-wa.smartgovcommunity.com/robots.txt)
disallows automated access to `/Public/Report` and `/Public/ReportsView`; this
command cannot fetch reports, perform network requests, or act as a collector.
Ranges are capped at 31 calendar days. The PDF source is a **valuation-limited
Spokane County subset**, not Spokane
city, Spokane Valley, or all County permits. The source occasionally includes
$100,000 exactly; we retain only strictly greater amounts, and only explicit
primary single-family homes or duplexes. Rebuilds, remodels, accessories/ADUs,
public works and other unverified types are not promoted. Contractor names are
not supplied by this report and are never inferred. An empty or invalid report
is not proof of zero County activity. No data retention, history writes, RSS,
dashboard output, remote workflow or publication is involved.
