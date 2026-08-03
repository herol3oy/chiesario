
# Historic Churches of Italy

A provenance-first data pipeline and web directory for historic churches in Italy.

The project currently focuses on **Tuscany** and combines data from:

* Wikidata
* OpenStreetMap
* Wikimedia Commons
* manually reviewed editorial overrides

The goal is to automate as much of the directory-building process as possible while preserving source data, uncertainty, provenance, and a controlled human-review layer.

---

## Current Status

The Tuscany catalog has completed its first full QA pass.

Current catalog:

```text
Total source records:       194

Ready:                      174
Out of scope:                19
Suppressed duplicates:        1
Remaining review:             0

Ready with hero image:      164
Ready without hero image:    10

Records with websites:       44
```

All blocking review categories are currently resolved:

```text
dates          0
coordinates    0
types          0
images         0
duplicates     0
```

The current public GeoJSON contains:

```text
174 features
```

---

# Design Principles

## Preserve source data

Raw source claims should not be flattened or overwritten prematurely.

For example, Wikidata may contain multiple inception dates with different precision or meanings.

Instead of immediately selecting one value, the pipeline preserves:

* statement IDs
* precision
* rank
* qualifiers
* references
* competing claims

Canonical values are resolved later.

---

## Prefer unresolved over incorrectly resolved

If the pipeline cannot safely determine a value, it should mark the record for review instead of guessing.

Examples include:

* conflicting construction dates
* conflicting coordinates
* ambiguous building types
* questionable hero images
* possible duplicate entities

---

## Separate source data from editorial decisions

Automated source data belongs in:

```text
data/raw/
data/processed/
```

Human editorial decisions belong in:

```text
data/reviews/overrides.json
```

Generated publication files belong in:

```text
data/catalog/
web/public/data/
```

---

# Pipeline

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

The QA step prevents publication while unresolved catalog records remain.

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
├── processed/
│   ├── churches.json
│   ├── churches_classified.json
│   ├── churches_osm.json
│   ├── churches_resolved.json
│   ├── churches_dates.json
│   ├── churches_commons.json
│   ├── churches_images.json
│   ├── churches_duplicates.json
│   ├── churches_reviewed.json
│   │
│   ├── quality_report.json
│   ├── type_report.json
│   ├── osm_report.json
│   ├── coordinate_report.json
│   ├── date_report.json
│   ├── commons_report.json
│   ├── image_report.json
│   ├── duplicate_report.json
│   └── review_report.json
│
├── reviews/
│   └── overrides.json
│
└── catalog/
    ├── churches.json
    ├── churches_ready.json
    ├── catalog_report.json
    └── churches.geojson
```

Frontend:

```text
web/
├── public/
│   └── data/
│       └── churches.geojson
├── src/
│   ├── main.ts
│   └── style.css
└── package.json
```

---

# Pipeline Stages

## 1. Discovery

```bash
uv run discover.py
```

Discovers candidate historic churches from Wikidata.

The discovery query uses Wikidata subclass traversal and Tuscany's administrative hierarchy.

The discovery stage should remain relatively broad.

Filtering and editorial decisions happen later.

---

## 2. Fetch Wikidata Entities

```bash
uv run fetch_entities.py
```

Fetches complete Wikidata entity JSON using `wbgetentities`.

This preserves richer source information than relying only on SPARQL result rows.

Stored information includes:

* labels
* descriptions
* aliases
* claims
* sitelinks
* coordinates
* inception claims
* images
* administrative locations
* entity types
* websites

---

## 3. Normalize

```bash
uv run normalize.py
```

Transforms raw Wikidata entities into a lossless normalized research schema.

Important fields include:

```text
wikidata_id
names
descriptions
wikidata_types
location_ids
coordinates
inception_claims
images
websites
derived
```

Date precision is preserved.

For example:

```text
precision 9 → year
precision 8 → decade
precision 7 → century
```

A 15th-century Wikidata statement therefore remains:

```text
15th century
```

rather than being incorrectly flattened to:

```text
1401
```

---

## 4. Type Classification

```bash
uv run classify_types.py
```

Classifies records using Wikidata `instance of` and subclass relationships.

Directory types currently include:

```text
church
cathedral
basilica
former_church
chapel
oratory
baptistery
sacristy
abbey
monastery
other
```

Current publication policy:

### Included

```text
church
cathedral
basilica
former_church
```

### Out of scope

```text
chapel
oratory
baptistery
sacristy
abbey
monastery
other
```

Ambiguous multi-type records are manually reviewed when necessary.

---

## 5. OpenStreetMap Enrichment

```bash
uv run enrich_osm.py
```

Matches records to OpenStreetMap using exact Wikidata QIDs.

The pipeline searches globally for:

```text
wikidata=Q...
```

rather than relying on expensive geographic Overpass queries.

OSM enrichment may provide:

* exact building geometry
* coordinates
* names
* addresses
* websites
* denominations
* religion
* building tags
* phone numbers
* Wikipedia links
* Wikimedia Commons tags

The raw OSM response is cached per QID.

---

## 6. Coordinate Resolution

```bash
uv run resolve_coordinates.py
```

Canonical coordinate priority:

```text
1. Wikidata coordinate
2. exact OSM match when Wikidata is missing
3. unresolved
```

When Wikidata and OSM both exist, their distance is calculated.

Large disagreements are flagged for manual review.

Human coordinate decisions are stored in:

```text
data/reviews/overrides.json
```

---

## 7. Date Resolution

```bash
uv run resolve_dates.py
```

The resolver preserves Wikidata precision and conflicting inception statements.

Automatic resolution occurs only when usable statements agree.

Supported canonical concepts include:

```text
year
circa_year
decade
century
```

Manual date research should prefer the origin or construction of the church itself rather than:

* façade construction
* fresco campaigns
* later restorations
* museum openings
* institutional foundation dates

When a manually researched date is used, provenance may include:

```text
source_name
source_url
note
```

---

## 8. Wikimedia Commons Enrichment

```bash
uv run enrich_commons.py
```

Fetches metadata for Wikidata `P18` images from Wikimedia Commons.

Stored metadata includes:

* full URL
* thumbnail URL
* Commons description URL
* dimensions
* MIME type
* license
* license URL
* attribution requirements
* artist
* credit
* description

Commons metadata is cached.

---

# Hero Image Selection

```bash
uv run select_images.py
```

Images attached directly to a Wikidata entity through `P18` are treated as strong evidence that the image represents the entity.

A licensed P18 image is normally accepted unless its metadata strongly indicates that it is unsuitable as a directory hero image.

Hard-reject signals currently include imagery such as:

```text
interior
painting
altarpiece
portrait
floor plan
map
drawing
fresco
sculpture
statue
```

The purpose is to favor photographs of the actual building while avoiding:

* paintings
* plans
* maps
* interior-only images
* artworks
* architectural details that do not represent the building

Human review can explicitly select a hero:

```json
"Q3670697": {
  "hero_image_filename": "Gorgona, san gorgonio 01.jpg",
  "note": "Visually verified as a suitable photograph."
}
```

Or explicitly record that no suitable hero exists:

```json
"Q2593098": {
  "no_hero_image": true,
  "note": "Reviewed manually; only an interior image is available."
}
```

This distinction is important.

```text
hero_image = null
```

does not necessarily mean the image review was forgotten.

It may mean:

```text
review completed
no suitable hero image exists
```

---

# Duplicate Detection

```bash
uv run detect_duplicates.py
```

Duplicate detection compares records using evidence including:

* geographic distance
* normalized name similarity
* shared OSM objects
* shared administrative location

The detector does not automatically merge entities.

Human decisions are recorded in:

```text
data/reviews/overrides.json
```

Example:

```json
"duplicate_pairs": [
  {
    "qid_1": "Q110944216",
    "qid_2": "Q19947673",
    "status": "same_entity",
    "canonical_qid": "Q19947673",
    "note": "Manually verified as the same entity."
  }
]
```

The non-canonical record is suppressed from publication but remains preserved in the research data.

---

# Manual Review Layer

```bash
uv run apply_overrides.py
```

All human decisions belong in:

```text
data/reviews/overrides.json
```

Supported editorial decisions include:

```text
canonical_name
directory_type
canonical_date
canonical_coordinates
hero_image_filename
no_hero_image
exclude
notes
duplicate decisions
```

The override layer produces:

```text
data/processed/churches_reviewed.json
data/processed/review_report.json
```

The review report tracks remaining unresolved:

```text
dates
coordinates
types
images
duplicates
```

The current Tuscany review report contains zero remaining reviews.

---

# Correcting Data

## Never edit generated files directly

Do not manually fix:

```text
data/processed/
data/catalog/
web/public/data/
```

In particular, never manually edit:

```text
data/catalog/churches.geojson
web/public/data/churches.geojson
```

These files are build artifacts.

---

## Correct workflow

When something looks wrong on the map:

```text
website/map
    ↓
identify the Wikidata QID
    ↓
determine why the value is wrong
    ↓
fix algorithm OR add editorial override
    ↓
regenerate catalog
    ↓
regenerate GeoJSON
```

If the problem affects many records, fix the relevant pipeline stage.

Examples:

```text
wrong date resolution
→ resolve_dates.py

bad automatic image classification
→ select_images.py

coordinate resolver problem
→ resolve_coordinates.py
```

If the decision is specific to one entity, use:

```text
data/reviews/overrides.json
```

Examples:

```text
manually researched date
manually verified coordinate
manual hero image
confirmed no suitable hero
type decision
duplicate decision
```

---

# Catalog Build

```bash
uv run build_catalog.py
```

Produces the publication-oriented catalog.

Possible statuses:

```text
ready
review
out_of_scope
duplicate
```

Only `ready` records are written to:

```text
data/catalog/churches_ready.json
```

---

# Automated QA

After building the catalog, run:

```bash
uv run qa.py
```

The QA command fails with a non-zero exit status if any catalog record still has:

```text
status = review
```

This prevents unresolved records from accidentally reaching the published GeoJSON.

A successful Tuscany build currently reports:

```text
QA passed
Catalog records: 194
Remaining review records: 0
```

Recommended publication sequence:

```bash
uv run apply_overrides.py
uv run build_catalog.py
uv run qa.py
uv run build_geojson.py

cp data/catalog/churches.geojson \
  web/public/data/churches.geojson
```

If QA fails, resolve the listed records before continuing.

---

# GeoJSON

```bash
uv run build_geojson.py
```

Converts:

```text
data/catalog/churches_ready.json
```

into:

```text
data/catalog/churches.geojson
```

The resulting GeoJSON is consumed by the frontend map.

Copy it to the web application with:

```bash
cp data/catalog/churches.geojson \
  web/public/data/churches.geojson
```

---

# Web QA

The frontend uses:

* Vite
* TypeScript
* MapLibre

The map is also an important visual QA tool.

Typical workflow:

```text
pipeline
  ↓
catalog
  ↓
GeoJSON
  ↓
map
  ↓
visual inspection
  ↓
problem discovered
  ↓
overrides.json or algorithm fix
  ↓
rebuild
```

This visual review process was used to identify issues including:

* unsuitable hero images
* missing hero images
* interior-only images
* paintings and plans used as P18
* conflicting dates
* inaccurate coordinates
* ambiguous types
* duplicate entities

---

# Provenance

The project distinguishes between:

```text
source claims
derived values
manual editorial decisions
publication values
```

Source information should remain recoverable whenever possible.

Manual decisions should document:

* what was changed
* why it was changed
* source or evidence when appropriate

The publication catalog is therefore a derived artifact rather than the authoritative research store.

---

# Rebuilding Tuscany

For a normal rebuild after editing `overrides.json`:

```bash
uv run apply_overrides.py
uv run build_catalog.py
uv run qa.py
uv run build_geojson.py

cp data/catalog/churches.geojson \
  web/public/data/churches.geojson
```

For a full data refresh:

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
uv run apply_overrides.py
uv run build_catalog.py
uv run qa.py
uv run build_geojson.py
```

---

# Scaling Beyond Tuscany

Tuscany now acts as the reference implementation and QA test region.

The next regions should reuse the same pipeline rather than introducing region-specific data logic whenever possible.

The main scaling loop is:

```text
discover region
    ↓
run pipeline
    ↓
inspect review reports
    ↓
improve generic rules where possible
    ↓
record genuine exceptions in overrides
    ↓
QA must reach zero
    ↓
publish
```

The objective is not zero manual work.

The objective is:

> automate repeatable decisions and preserve human review for genuine ambiguity.

---

# Project Goal

Build a reliable, traceable, mostly automated directory of historic Italian churches while preserving enough source evidence and editorial provenance to understand exactly why each published record looks the way it does.
