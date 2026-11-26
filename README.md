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

## Kennewick collector preview (disabled by default)

This opt-in trial reads the City of Kennewick [rolling weekly Activity Report](https://www.go2kennewick.com/ArchiveCenter/ViewFile/Item/51).
Only tested detached single-family work classes enter the preview; other residential,
commercial, alterations, trades and public works are not included. The role is
the city's published Contractor column, not a verified GC or material buyer. Owner
and applicant values are not retained. The report URL rolls forward; each row
stores its report week, page, and content SHA-256 for evidence traceability.
One report is fetched per manual preview. Missing snapshots mean missing history;
the collector does not infer a backfill from the current rolling file.

For local review, in an isolated copy of the repository with Poppler's
`pdftotext` and the existing Python dependencies installed:

```sh
PYTHONPATH=src WA_ENABLE_KENNEWICK=1 python -m washington_permits.main
```

The command updates that copy's JSON and RSS files. Do not enable the environment
flag in the publishing workflow without reviewing freshness, coverage, the direct
municipal source's reliability, and sample identity/publication rules.

Spokane is not enabled. Its official map layer exposes Open Date, not Issue Date,
and no role-labelled contractor. City PDFs have issued dates and a combined
Contractor/Architect/Engineer role, but their binary endpoint denied ordinary
requests during this audit. Spokane County's separate GIS response errored, its
published XLS opened with headers only, and weekly county PDFs were historical.
None of those paths is a current Spokane issued-permit feed.
