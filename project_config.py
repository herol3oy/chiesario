import json
import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_ROOT / "config" / "regions.json"


def load_regions():
    try:
        with CONFIG_FILE.open(encoding="utf-8") as f:
            regions = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Region configuration not found: {CONFIG_FILE}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in region configuration: {CONFIG_FILE}"
        ) from exc

    if not isinstance(regions, dict) or not regions:
        raise RuntimeError(
            f"Region configuration must be a non-empty object: {CONFIG_FILE}"
        )

    return regions


REGIONS = load_regions()
REGION_SLUG = (
    os.environ.get("CHURCHES_REGION", "tuscany")
    .strip()
    .lower()
)

if REGION_SLUG not in REGIONS:
    available = ", ".join(sorted(REGIONS))
    raise RuntimeError(
        f"Unknown CHURCHES_REGION {REGION_SLUG!r}. "
        f"Available regions: {available}"
    )

REGION = REGIONS[REGION_SLUG]

if not isinstance(REGION, dict):
    raise RuntimeError(
        f"Configuration for region {REGION_SLUG!r} must be an object"
    )

REGION_NAME = REGION.get("name")
REGION_QID = REGION.get("wikidata_id")

if not isinstance(REGION_NAME, str) or not REGION_NAME.strip():
    raise RuntimeError(
        f"Region {REGION_SLUG!r} must have a non-empty name"
    )

if (
    not isinstance(REGION_QID, str)
    or re.fullmatch(r"Q[1-9][0-9]*", REGION_QID) is None
):
    raise RuntimeError(
        f"Region {REGION_SLUG!r} has an invalid wikidata_id"
    )


DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
REGION_DIR = DATA_DIR / "regions" / REGION_SLUG
RAW_DIR = REGION_DIR / "raw"
PROCESSED_DIR = REGION_DIR / "processed"
REVIEWS_DIR = REGION_DIR / "reviews"
CATALOG_DIR = REGION_DIR / "catalog"

QIDS_FILE = RAW_DIR / "qids.txt"
ENTITIES_FILE = RAW_DIR / "entities.json"
BEWEB_RAW_DIR = RAW_DIR / "beweb"

CHURCHES_FILE = PROCESSED_DIR / "churches.json"
QUALITY_REPORT_FILE = PROCESSED_DIR / "quality_report.json"

CLASSIFIED_FILE = PROCESSED_DIR / "churches_classified.json"
TYPE_ENTITIES_CACHE_FILE = CACHE_DIR / "wikidata_type_entities.json"
TYPE_REPORT_FILE = PROCESSED_DIR / "type_report.json"

OSM_CACHE_FILE = CACHE_DIR / "osm_by_qid.json"
OSM_FILE = PROCESSED_DIR / "churches_osm.json"
OSM_REPORT_FILE = PROCESSED_DIR / "osm_report.json"

RESOLVED_FILE = PROCESSED_DIR / "churches_resolved.json"
COORDINATE_REPORT_FILE = PROCESSED_DIR / "coordinate_report.json"

DATES_FILE = PROCESSED_DIR / "churches_dates.json"
DATE_REPORT_FILE = PROCESSED_DIR / "date_report.json"

HISTORIC_SCOPE_FILE = PROCESSED_DIR / "churches_historic_scope.json"
HISTORIC_SCOPE_REPORT_FILE = (
    PROCESSED_DIR / "historic_scope_report.json"
)

HISTORICAL_EVIDENCE_FILE = (
    PROCESSED_DIR / "churches_historical_evidence.json"
)
HISTORICAL_EVIDENCE_REPORT_FILE = (
    PROCESSED_DIR / "historical_evidence_report.json"
)

HISTORICAL_DATES_FILE = (
    PROCESSED_DIR / "churches_historical_dates.json"
)
HISTORICAL_DATE_REPORT_FILE = (
    PROCESSED_DIR / "historical_date_report.json"
)

COMMONS_CACHE_FILE = CACHE_DIR / "commons_file_metadata.json"
COMMONS_FILE = PROCESSED_DIR / "churches_commons.json"
COMMONS_REPORT_FILE = PROCESSED_DIR / "commons_report.json"

IMAGES_FILE = PROCESSED_DIR / "churches_images.json"
IMAGE_REPORT_FILE = PROCESSED_DIR / "image_report.json"

DUPLICATES_FILE = PROCESSED_DIR / "churches_duplicates.json"
DUPLICATE_REPORT_FILE = PROCESSED_DIR / "duplicate_report.json"

OVERRIDES_FILE = REVIEWS_DIR / "overrides.json"
REVIEWED_FILE = PROCESSED_DIR / "churches_reviewed.json"
REVIEW_REPORT_FILE = PROCESSED_DIR / "review_report.json"

CATALOG_ALL_FILE = CATALOG_DIR / "churches.json"
CATALOG_READY_FILE = CATALOG_DIR / "churches_ready.json"
CATALOG_REPORT_FILE = CATALOG_DIR / "catalog_report.json"
GEOJSON_FILE = CATALOG_DIR / "churches.geojson"


def ensure_directories():
    for directory in (
        CACHE_DIR,
        RAW_DIR,
        BEWEB_RAW_DIR,
        PROCESSED_DIR,
        REVIEWS_DIR,
        CATALOG_DIR,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )
