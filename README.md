# Italian Historic Churches Dataset

A provenance-first data pipeline for building a structured directory of historic churches in Italy from public datasets.

The project currently focuses on **Tuscany** as a development dataset. It discovers church-related entities from Wikidata, preserves their source claims, enriches them with OpenStreetMap and Wikimedia Commons data, resolves safe canonical fields, and flags ambiguous records for review rather than guessing.

## Current Status

Current Tuscany dataset:

* 194 candidate entities
* 191 have Wikidata coordinates
* 1 additional record receives coordinates from an exact OpenStreetMap match
* 2 records remain without canonical coordinates
* 187 dates resolve automatically
* 7 dates require review
* 205 Wikimedia Commons images enriched with licensing metadata
* 90 hero images selected automatically
* 104 records require image review
* 3 records have no Wikidata image
* 1 possible duplicate/entity-overlap pair detected

The pipeline is intentionally conservative. Ambiguous records remain unresolved instead of being silently modified.

---

## Design Principles

### Preserve source data

Wikidata, OpenStreetMap, and Wikimedia Commons data are stored separately.

Source values are not overwritten when another source disagrees.

For example:

```text
Wikidata coordinates
        +
OpenStreetMap coordinates
        ↓
coordinate resolver
        ↓
canonical coordinates + provenance
```

The canonical result records which source was selected.

### Claims are evidence, not final values

Wikidata statements are preserved with information such as:

* statement ID
* rank
* precision
* qualifiers
* references

This is especially important for dates.

For example, Wikidata may encode:

```text
+1401-01-01...
precision = century
```

This means:

```text
15th century
```

not:

```text
built in 1401
```

The pipeline preserves that distinction.

### Prefer unresolved over incorrect

If several plausible values exist, the pipeline generally produces:

```json
{
  "canonical": null,
  "review_required": true
}
```

rather than choosing one arbitrarily.

### Editorial policy is separate from source data

A chapel can remain correctly classified as a chapel even if the current directory policy excludes chapels.

For example:

```json
{
  "directory_type": "chapel",
  "publishable_by_type": false
}
```

Changing directory scope should not require downloading or modifying the original source data again.

---

# Pipeline

```text
Wikidata Query Service
        │
        ▼
discover.py
        │
        │ QIDs
        ▼
fetch_entities.py
        │
        │ full Wikidata entities
        ▼
normalize.py
        │
        ▼
classify_types.py
        │
        ▼
OpenStreetMap
        │
        ▼
enrich_osm.py
        │
        ▼
resolve_coordinates.py
        │
        ▼
resolve_dates.py
        │
        ▼
Wikimedia Commons
        │
        ▼
enrich_commons.py
        │
        ▼
select_images.py
        │
        ▼
detect_duplicates.py
        │
        ▼
review / publication layer
```

---

# Running the Pipeline

The scripts are currently executed with `uv`.

Run them in order:

```bash
uv run discover.py

uv run fetch_entities.py

uv run normalize.py

uv run classify_types.py

uv run enrich_osm.py

uv run resolve_coordinates.py

uv run resolve_dates.py

uv run enrich_commons.py

uv run select_images.py

uv run detect_duplicates.py
```

Each stage consumes the output of the previous stage.

External API responses are cached where appropriate so repeated runs do not unnecessarily query public services.

---

# Pipeline Stages

## 1. Discovery

```text
discover.py
```

Uses the Wikidata Query Service to discover candidate church-related entities.

Discovery intentionally retrieves identifiers rather than attempting to construct complete records in one large SPARQL query.

Output:

```text
data/raw/tuscany_qids.txt
```

Example:

```text
Q123456
Q987654
Q112233
```

The Wikidata QID is the primary external identifier used throughout the pipeline.

---

## 2. Wikidata Entity Fetch

```text
fetch_entities.py
```

Retrieves complete Wikidata entity JSON for the discovered QIDs.

This avoids flattening important information such as:

* multiple statements
* date precision
* ranks
* qualifiers
* references
* aliases
* multilingual labels

Output:

```text
data/raw/tuscany_entities.json
```

---

## 3. Wikidata Normalization

```text
normalize.py
```

Converts raw Wikidata entities into a consistent internal structure while preserving source claims.

Important normalized fields include:

```text
wikidata_id

names
descriptions

wikidata_types
location_ids

coordinates[]

inception_claims[]

images[]

websites[]

derived
```

The normalization stage does not attempt to resolve every ambiguity.

Output:

```text
data/processed/churches.json
data/processed/quality_report.json
```

---

## 4. Type Classification

```text
classify_types.py
```

Classifies Wikidata `instance of` (`P31`) values using the Wikidata subclass hierarchy.

Current categories include:

```text
church
basilica
cathedral
former_church
chapel
oratory
baptistery
sacristy
abbey
monastery
other
```

The classification hierarchy prefers more specific types.

For example:

```text
baptistery
    ↓
chapel
    ↓
church building
```

is classified as:

```text
baptistery
```

rather than simply:

```text
church
```

Current publication policy includes:

```text
church
basilica
cathedral
former_church
```

Other types remain in the dataset but are currently marked as excluded by policy.

Output:

```text
data/processed/churches_classified.json
data/processed/type_report.json
```

---

## 5. OpenStreetMap Enrichment

```text
enrich_osm.py
```

Searches OpenStreetMap for objects containing an exact:

```text
wikidata=Q...
```

tag.

This provides deterministic joins without relying on fuzzy name matching.

Possible enrichment includes:

* OSM object ID
* coordinates
* address
* website
* denomination
* religion
* building type
* start date
* phone
* Wikipedia tag
* Wikimedia Commons tag
* complete OSM tags

The script caches completed QID lookups so interrupted runs can resume.

Current exact-match results:

```text
161 single matches
2 multiple matches
31 no exact match
```

Output:

```text
data/raw/osm_by_qid.json

data/processed/churches_osm.json
data/processed/osm_report.json
```

---

## 6. Coordinate Resolution

```text
resolve_coordinates.py
```

Produces canonical coordinates while keeping source provenance.

Current preference:

```text
Wikidata coordinate
        ↓
single exact OpenStreetMap match
        ↓
unresolved
```

When both Wikidata and OSM coordinates exist, their geographic distance is calculated.

Large disagreements are flagged for review.

Current results:

```text
Total: 194

Canonical from Wikidata: 191
Canonical from OSM: 1
Unresolved: 2

Wikidata/OSM compared: 160
Coordinate review required: 2
Average difference: 16.39 m
Maximum difference: 495.5 m
```

Output:

```text
data/processed/churches_resolved.json
data/processed/coordinate_report.json
```

---

## 7. Date Resolution

```text
resolve_dates.py
```

Converts Wikidata time claims into safe canonical periods.

Date precision is preserved.

Examples:

```text
precision 9
→ 1458
→ exact year

precision 8
→ 1450s
→ decade

precision 7
→ 15th century
→ century
```

Multiple incompatible dates are not automatically resolved.

Current results:

```text
Total: 194
Resolved: 187
Review required: 7

Exact years: 154
Century dates: 29
Decade dates: 4
```

Output:

```text
data/processed/churches_dates.json
data/processed/date_report.json
```

---

## 8. Wikimedia Commons Enrichment

```text
enrich_commons.py
```

Retrieves metadata for Wikidata image claims using the Wikimedia Commons API.

Stored metadata includes:

* original file URL
* thumbnail URL
* dimensions
* MIME type
* author
* credit
* description
* original date
* license
* license URL
* attribution requirements
* raw Commons extended metadata

Current results:

```text
Churches: 194
Unique files: 205
Files enriched: 205
Missing files: 0
Files missing license metadata: 0
Churches without Wikidata images: 3
```

The Commons response cache is stored at:

```text
data/raw/commons_file_metadata.json
```

Output:

```text
data/processed/churches_commons.json
data/processed/commons_report.json
```

---

## 9. Hero Image Selection

```text
select_images.py
```

Scores Wikidata-provided Commons images for use as directory hero images.

Positive signals include terms such as:

```text
facade
facciata
exterior
church
chiesa
basilica
cathedral
interior
```

Negative signals include:

```text
painting
altarpiece
portrait
floor plan
drawing
map
sculpture
fresco
altar
```

The selector is deliberately conservative.

Only high-confidence candidates with automatically accepted licensing are selected.

Current results:

```text
Churches: 194
Hero images auto-selected: 90
Image review required: 104
No images: 3
```

Output:

```text
data/processed/churches_images.json
data/processed/image_report.json
```

---

## 10. Duplicate Detection

```text
detect_duplicates.py
```

Detects possible duplicate or overlapping Wikidata entities.

Signals currently include:

* normalized name similarity
* geographic distance
* shared administrative location
* shared OpenStreetMap objects

Duplicates are never merged automatically.

Current result:

```text
Candidate pairs: 1
Entities flagged: 2
```

The currently detected pair is:

```text
Q110944216
Rotonda del Brunelleschi

Q19947673
Rotonda di Brunelleschi
```

The normalized names match exactly and the records share an administrative location, but there is not yet enough independent evidence for an automatic merge.

Output:

```text
data/processed/churches_duplicates.json
data/processed/duplicate_report.json
```

---

# Data Layout

```text
data/
├── raw/
│   ├── tuscany_qids.txt
│   ├── tuscany_entities.json
│   ├── wikidata_type_entities.json
│   ├── osm_by_qid.json
│   └── commons_file_metadata.json
│
└── processed/
    ├── churches.json
    ├── churches_classified.json
    ├── churches_osm.json
    ├── churches_resolved.json
    ├── churches_dates.json
    ├── churches_commons.json
    ├── churches_images.json
    ├── churches_duplicates.json
    │
    ├── quality_report.json
    ├── type_report.json
    ├── osm_report.json
    ├── coordinate_report.json
    ├── date_report.json
    ├── commons_report.json
    ├── image_report.json
    └── duplicate_report.json
```

`raw/` contains source responses and caches.

`processed/` contains progressively enriched and resolved records.

Generated processed files should generally be reproducible from the raw source data and pipeline code.

---

# Data Sources

## Wikidata

Used for:

* entity discovery
* names
* entity types
* inception dates
* coordinates
* administrative locations
* images
* websites
* source claims and references

Wikidata QIDs are retained as persistent external identifiers.

## OpenStreetMap

Used for additional:

* coordinates
* addresses
* websites
* denomination
* religion
* building metadata
* geographic cross-checking

Exact `wikidata=*` joins are preferred over fuzzy matching.

OSM-derived data must retain appropriate OpenStreetMap attribution and be handled in accordance with the OpenStreetMap data license.

## Wikimedia Commons

Used for:

* photographs and other media
* thumbnails
* photographer/creator metadata
* license metadata
* attribution information

Each Commons file is treated individually because licensing and attribution requirements can differ between files.

---

# Provenance

A central rule of this project is that a canonical field should not erase its sources.

For example:

```json
{
  "resolved_coordinates": {
    "canonical": {
      "latitude": 43.76845,
      "longitude": 11.26274,
      "source": "wikidata"
    },

    "wikidata": {
      "...": "..."
    },

    "osm": {
      "...": "..."
    },

    "comparison": {
      "distance_meters": 6.8,
      "review_required": false
    }
  }
}
```

The same principle should eventually apply to:

* canonical names
* dates
* church types
* addresses
* websites
* descriptions

---

# Review Philosophy

Automated review flags are expected.

They are not necessarily errors.

Examples include:

```text
date_review_required
type_review_required
coordinate_review_required
image_review_required
duplicate_review_required
```

The pipeline intentionally optimizes for:

```text
high-confidence automation
+
small explicit review queues
```

rather than maximum automatic coverage.

---

# Known Limitations

## Wikidata coverage

Wikidata is incomplete.

A historic church may have:

* no inception date
* no image
* incomplete type information
* missing coordinates
* multiple competing statements

Future sources will be needed to improve coverage.

## OpenStreetMap joins

Not every OSM church has a `wikidata=*` tag.

Records without an exact QID match are currently left unmatched rather than automatically fuzzy-matched.

## Dates

`inception` does not always mean one simple construction year.

Churches may have separate dates for:

* initial foundation
* present building
* façade
* reconstruction
* restoration
* museum or institutional creation

Ambiguous entities remain in the review queue.

## Images

Wikidata `P18` does not guarantee that an image is a useful photograph of the building.

It may point to:

* paintings
* altarpieces
* plans
* artworks
* interiors
* architectural details

The current image selector therefore favors precision over coverage.

## Duplicate entities

Two Wikidata entities with similar names may represent:

* the same building
* different parts of a complex
* a church and its institution
* a church and a museum
* related but distinct structures

Duplicate candidates must therefore be reviewed before merging.

---

# Planned Work

Possible next stages include:

1. persistent manual review/override files
2. canonical name resolution
3. richer Commons image discovery
4. enrichment from Italian cultural-heritage datasets
5. enrichment from ecclesiastical heritage datasets
6. controlled fuzzy matching for unmatched OSM objects
7. database import into PostgreSQL/PostGIS
8. publication-quality record generation
9. regional expansion beyond Tuscany
10. web API and map-based frontend

---

# Goal

The eventual goal is not merely to produce a list of churches.

The project aims to build a provenance-aware, machine-maintainable dataset that can power a searchable directory of historic Italian churches by:

* location
* century
* architectural period
* church type
* region
* historical significance
* map position

while keeping enough source information to explain where each published fact came from.

## Correcting Data

### Never edit generated files directly

Files under directories such as:

```text
data/processed/
data/catalog/
web/public/data/
```

are generated artifacts.

For example:

```text
data/catalog/churches.geojson
```

is produced from upstream source data and pipeline scripts.

If something looks wrong on the website, **do not edit the GeoJSON, catalog JSON, or other generated output directly**.

Any direct edit will be lost the next time the pipeline runs.

### Correct workflow

When visual inspection reveals a problem:

```text
Website / map
      ↓
find incorrect record
      ↓
identify its Wikidata QID
      ↓
determine whether the problem is:
  - source-data problem
  - resolver problem
  - automatic-selection problem
  - genuine human editorial decision
      ↓
record human decisions in:
data/reviews/overrides.json
      ↓
regenerate downstream files
```

For example, if a church has a valid Wikimedia Commons image but the automatic hero-image selector did not choose it, add a manual override:

```json
{
  "records": {
    "Q123456": {
      "hero_image_filename": "Example church.jpg",
      "note": "Image visually verified as a suitable photograph of the church."
    }
  }
}
```

Then rebuild the downstream dataset:

```bash
uv run apply_overrides.py
uv run build_catalog.py
uv run build_geojson.py
```

If the frontend uses a copied GeoJSON file, update that file as well:

```bash
cp data/catalog/churches.geojson \
   web/public/data/churches.geojson
```

### Source of truth

Human/editorial corrections belong in:

```text
data/reviews/overrides.json
```

Algorithmic corrections belong in the relevant pipeline script.

For example:

```text
wrong date-resolution logic
→ fix resolve_dates.py

bad automatic image scoring
→ fix select_images.py

one manually verified hero image
→ overrides.json

one verified duplicate relationship
→ overrides.json
```

This keeps the entire project reproducible:

```text
raw data
   +
pipeline code
   +
manual overrides
   ↓
same generated catalog
```

Generated files should therefore be treated as **build artifacts, not source files**.
