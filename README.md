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
