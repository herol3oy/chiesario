# Chat Handoff — Historic Churches of Italy

I am building a provenance-first, mostly automated directory of historic churches in Italy.

I am a programmer and the project is a Python ETL/data-quality pipeline plus a Vite + TypeScript + MapLibre frontend.

## Current architecture

Italy is processed by its 20 official regions.

Configuration:

```text
config/regions.json
```

Regional data:

```text
data/regions/<region>/
├── raw/
├── processed/
├── reviews/
└── catalog/
```

Shared caches:

```text
data/cache/
```

Region environment variable:

```text
CHURCHES_REGION
```

Main pipeline runner:

```bash
uv run pipeline.py --region <region>
```

Pipeline:

```text
discover.py
↓
fetch_entities.py
↓
normalize.py
↓
classify_types.py
↓
enrich_osm.py
↓
resolve_coordinates.py
↓
resolve_dates.py
↓
resolve_historic_scope.py
↓
enrich_commons.py
↓
select_images.py
↓
detect_duplicates.py
↓
apply_overrides.py
↓
build_catalog.py
↓
qa.py
↓
build_geojson.py
```

## Important project rules

Never edit generated files directly.

Human/editorial corrections go in:

```text
data/regions/<region>/reviews/overrides.json
```

Generated data under `processed/`, `catalog/`, and frontend GeoJSON is rebuilt from the pipeline.

Prefer unresolved data over guessed data.

QA must pass before publication.

---

# Tuscany

Tuscany is the validated reference region.

Regression baseline:

```text
Total:                    194
Ready:                    174
Out of scope:              19
Duplicate:                  1
Review:                     0

Ready with hero image:    164
Ready without hero image:  10
GeoJSON features:         174

QA passed.
```

Tuscany must remain unchanged when generic pipeline logic is refactored unless there is a clearly explained reason.

Tuscany QA work is complete.

---

# Major discovery issue found with Molise

Original discovery required:

```text
P571 < 1800
```

This returned only:

```text
15 Molise churches
```

But removing the P571 requirement returned:

```text
610 candidates
```

Therefore discovery was incorrectly depending on Wikidata already having an inception date.

Discovery was refactored to be date-independent.

Historic scope is now resolved later by:

```text
resolve_historic_scope.py
```

with:

```text
historic = canonical start year < 1800
modern   = canonical start year >= 1800
unknown  = no usable date
```

Cutoff:

```text
1800
```

---

# Molise current state

Molise Wikidata region:

```text
Q1443
```

After date-independent discovery:

```text
Candidates discovered:             610
Entities fetched:                  610
Normalized records:                610

With inception claims:              22
Without inception claims:          588
```

This proved that Wikidata P571 is extremely sparse for Molise.

The larger Wikidata fetch initially hit HTTP 429 rate limiting, so generic retries, API-error handling, and batch checkpoints were added to `fetch_entities.py`.

---

# Molise measurement run

Pipeline was run through:

```text
classify_types.py
enrich_osm.py
resolve_coordinates.py
resolve_dates.py
resolve_historic_scope.py
```

No Molise overrides have been added.

No Commons/image/publication stages should be considered final yet.

## Type classification

```text
Total:              610

church:             577
chapel:              23
cathedral:             7
basilica:              2
abbey:                 1

Publishable by type: 586
Out of scope:         24
Type review:           1
```

Compatible hierarchical type candidates now auto-resolve by priority.

Examples:

```text
cathedral + basilica + church → cathedral
basilica + church             → basilica
baptistery + chapel + church  → baptistery
sacristy + chapel + church    → sacristy
```

Molise Q2942828 and Q3045554 now automatically resolve as cathedrals.

## OSM

```text
Exact OSM matches:      196
Single:                 194
Multiple:                 2
No match:               414

OSM start_date:          15
```

OSM start_date formats found:

```text
YYYY
~YYYY
C<n> BC
C<n>..C<n>
```

`resolve_dates.py` does NOT currently use OSM `start_date`.

## Dates

```text
Resolved:              22
Unresolved:           588

From Wikidata:         22
From OSM:               0
```

## Historic scope

```text
Historic:              15
Modern:                 7
Unknown:              588
```

---

# Important historical-data finding

Wikidata P571 is not just sparse; it can also represent the wrong historical concept.

Example:

```text
Q3670761 — San Leonardo, Campobasso
```

It has no P571 but appears clearly pre-1800 from historical sources.

Other manually noticed likely pre-1800 candidates lacking useful P571 include:

```text
Q113625314
Q63457618
Q116031345
Q72397889
Q113574286
Q3670761
```

Also:

```text
Q3673469 — Santa Maria Maggiore
```

has a Wikidata P571 around 1911, but historical information indicates the church existed centuries earlier.

Therefore:

```text
P571 != necessarily historic origin date
```

The project should distinguish a canonical historical/origin date from raw Wikidata inception claims.

Do not blindly trust P571 as proof that a church is modern.

---

# Current next task

We decided NOT to manually research the 588 unknown Molise records yet.

The next task is measurement of alternative historical-source coverage.

The last prompt prepared for the IDE agent was:

* analyze only the 588 historic-scope-unknown Molise records
* do not change algorithms yet
* do not add overrides
* do not run publication stages

Measure:

1. Italian Wikipedia coverage
2. any Wikipedia coverage
3. Commons category/P18 coverage
4. existing external IDs in Wikidata, especially:

   * BeWeb church ID
   * Wiki Loves Monuments ID
   * GCatholic church ID
   * Italian cultural heritage/catalog IDs
5. OSM `start_date` specifically among the 588 unknowns
6. architectural style / heritage designation / architect / useful historical claims already in Wikidata
7. audit the 7 currently “modern” P571 records against Italian Wikipedia to see whether the churches have older origins
8. recommend the most promising next enrichment source based on measured coverage

Current hypothesis:

```text
Wikidata P571
↓
BeWeb / authoritative church source
↓
Italian Wikipedia
↓
OSM start_date as supplemental evidence
```

But this has NOT yet been confirmed by the coverage measurement.

The next assistant should continue from this exact point and avoid restarting Tuscany QA or suggesting manual review of hundreds of Molise records.
