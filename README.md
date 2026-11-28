# Washington Construction Intelligence

Washington building-permit prospecting focused on new:

- single-family residential construction
- multifamily / townhome / duplex / apartment construction
- commercial / institutional / industrial construction

## Configured sources

**Seattle SDCI — Issued Building Permits**

The City of Seattle public open-data feed exposes issued permit records with project description, housing units, estimated project cost, contractor, address, status, and a direct SDCI record link.

- **Kennewick** uses the city’s rolling weekly permit activity report for supported new dwelling classes.
- **Yakima County** uses the county’s four latest weekly issued-building reports for explicitly named new primary construction. The county’s archive also contains applications and occupancy events, which the collector excludes from issuance.
- **Moses Lake** uses the two latest city-issued monthly reports for single-family dwellings with legible issue dates, permit identities, and explicit new work. The image-based archive provides partial coverage.
- **Grant County** uses the two latest county building issuance reports for recognized primary building work. County coverage is separate from city-issued permits in Moses Lake and other incorporated places.

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
