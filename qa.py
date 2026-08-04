import argparse
import json
import sys

from project_config import (
    CATALOG_ALL_FILE,
    CATALOG_READY_FILE,
    GEOJSON_FILE,
    REGION_NAME,
    REGION_SLUG,
)


def load_json(path):
    with path.open(
        encoding="utf-8",
    ) as f:
        return json.load(f)


def duplicate_values(values):
    seen = set()
    duplicates = set()

    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)

    return sorted(duplicates)


def check_catalog():
    errors = []

    if not CATALOG_ALL_FILE.exists():
        return [
            f"{CATALOG_ALL_FILE} does not exist. "
            "Run build_catalog.py first."
        ]

    if not CATALOG_READY_FILE.exists():
        return [
            f"{CATALOG_READY_FILE} does not exist. "
            "Run build_catalog.py first."
        ]

    records = load_json(
        CATALOG_ALL_FILE
    )

    ready_records = load_json(
        CATALOG_READY_FILE
    )

    # ------------------------------------------
    # Duplicate IDs in complete catalog
    # ------------------------------------------

    all_ids = [
        record.get("id")
        for record in records
    ]

    duplicate_all_ids = (
        duplicate_values(all_ids)
    )

    for qid in duplicate_all_ids:
        errors.append(
            f"Duplicate catalog ID: {qid}"
        )

    # ------------------------------------------
    # No unresolved review records
    # ------------------------------------------

    review_records = [
        record
        for record in records
        if record.get("status") == "review"
    ]

    valid_statuses = {
        "ready",
        "review",
        "withheld",
        "out_of_scope",
        "excluded",
        "duplicate",
    }

    for record in records:
        status = record.get("status")

        if status not in valid_statuses:
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                f"has invalid status {status!r}"
            )

    for record in review_records:
        blocking = (
            record
            .get("review", {})
            .get("blocking", [])
        )

        reason = (
            ", ".join(blocking)
            if blocking
            else "unspecified"
        )

        errors.append(
            f"{record.get('id')} | "
            f"{record.get('name')} | "
            f"still requires review "
            f"({reason})"
        )

    # ------------------------------------------
    # Ready records must have coordinates
    # ------------------------------------------

    catalog_ready = [
        record
        for record in records
        if record.get("status") == "ready"
    ]

    valid_historic_scopes = {
        "historic",
        "modern",
        "unknown",
    }

    for record in records:
        historic_scope = record.get(
            "historic_scope"
        )

        if historic_scope not in valid_historic_scopes:
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "has invalid historic scope "
                f"{historic_scope!r}"
            )

    for record in catalog_ready:
        if record.get("historic_scope") != "historic":
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "ready record is not confirmed historic"
            )

        date = record.get("date") or {}
        basis = date.get("basis")
        if basis not in {
            "inception",
            "origin",
            "foundation",
            "construction",
            "documentary_attestation",
            "predecessor",
        }:
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                f"ready record has invalid date basis {basis!r}"
            )

        if not date.get("source"):
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "ready record has no date source"
            )

        if date.get("source") == "beweb":
            sources = date.get("sources") or []
            if (
                not date.get("source_url")
                or not any(
                    source.get("source_id")
                    and source.get("url")
                    for source in sources
                )
            ):
                errors.append(
                    f"{record.get('id')} | "
                    f"{record.get('name')} | "
                    "BeWeb date lacks stable provenance"
                )

        if (
            basis in {
                "documentary_attestation",
                "predecessor",
            }
            and (
                not isinstance(date.get("end_year"), int)
                or date["end_year"] >= 1800
            )
        ):
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "documentary evidence does not prove a "
                "strictly pre-1800 date"
            )

    for record in records:
        if (
            record.get("status") == "withheld"
            and record.get("historic_scope") != "unknown"
        ):
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "withheld record does not have unknown "
                "historic scope"
            )

    for record in catalog_ready:
        coordinates = (
            record.get("coordinates")
        )

        if not coordinates:
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "ready record has no coordinates"
            )
            continue

        latitude = coordinates.get(
            "latitude"
        )

        longitude = coordinates.get(
            "longitude"
        )

        if (
            latitude is None
            or longitude is None
        ):
            errors.append(
                f"{record.get('id')} | "
                f"{record.get('name')} | "
                "ready record has incomplete coordinates"
            )

    # ------------------------------------------
    # churches_ready.json integrity
    # ------------------------------------------

    ready_ids = [
        record.get("id")
        for record in ready_records
    ]

    duplicate_ready_ids = (
        duplicate_values(ready_ids)
    )

    for qid in duplicate_ready_ids:
        errors.append(
            f"Duplicate ready catalog ID: {qid}"
        )

    for record in ready_records:
        if record.get("status") != "ready":
            errors.append(
                f"{record.get('id')} appears in "
                "churches_ready.json but status is "
                f"{record.get('status')!r}"
            )

        if record.get("historic_scope") != "historic":
            errors.append(
                f"{record.get('id')} appears in "
                "churches_ready.json without confirmed "
                "historic scope"
            )

    expected_ready_ids = {
        record.get("id")
        for record in catalog_ready
    }

    actual_ready_ids = set(
        ready_ids
    )

    missing = (
        expected_ready_ids
        - actual_ready_ids
    )

    unexpected = (
        actual_ready_ids
        - expected_ready_ids
    )

    for qid in sorted(missing):
        errors.append(
            f"Ready record missing from "
            f"churches_ready.json: {qid}"
        )

    for qid in sorted(unexpected):
        errors.append(
            f"Unexpected record in "
            f"churches_ready.json: {qid}"
        )

    return errors


def check_geojson():
    errors = []

    if not CATALOG_READY_FILE.exists():
        return [
            f"{CATALOG_READY_FILE} does not exist. "
            "Run build_catalog.py first."
        ]

    if not GEOJSON_FILE.exists():
        return [
            f"{GEOJSON_FILE} does not exist. "
            "Run build_geojson.py first."
        ]

    ready_records = load_json(
        CATALOG_READY_FILE
    )

    geojson = load_json(
        GEOJSON_FILE
    )

    if (
        geojson.get("type")
        != "FeatureCollection"
    ):
        errors.append(
            "GeoJSON root is not "
            "a FeatureCollection"
        )

        return errors

    features = geojson.get(
        "features",
        [],
    )

    if len(features) != len(
        ready_records
    ):
        errors.append(
            "GeoJSON feature count does not "
            "match ready catalog count: "
            f"{len(features)} != "
            f"{len(ready_records)}"
        )

    feature_ids = [
        (
            feature
            .get("properties", {})
            .get("id")
        )
        for feature in features
    ]

    duplicate_feature_ids = (
        duplicate_values(feature_ids)
    )

    for qid in duplicate_feature_ids:
        errors.append(
            f"Duplicate GeoJSON feature ID: "
            f"{qid}"
        )

    for feature in features:
        properties = feature.get(
            "properties",
            {},
        )
        if properties.get("historic_scope") != "historic":
            errors.append(
                f"{properties.get('id')} appears in GeoJSON "
                "without confirmed historic scope"
            )

    ready_ids = {
        record.get("id")
        for record in ready_records
    }

    geojson_ids = set(
        feature_ids
    )

    missing = (
        ready_ids
        - geojson_ids
    )

    unexpected = (
        geojson_ids
        - ready_ids
    )

    for qid in sorted(missing):
        errors.append(
            f"Ready record missing from "
            f"GeoJSON: {qid}"
        )

    for qid in sorted(unexpected):
        errors.append(
            f"Unexpected GeoJSON feature: "
            f"{qid}"
        )

    return errors


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--geojson",
        action="store_true",
        help=(
            "Also validate generated "
            "GeoJSON."
        ),
    )

    parser.add_argument(
        "--strict-publication",
        action="store_true",
        help=(
            "Also reject ready records with unresolved "
            "non-blocking image review."
        ),
    )

    args = parser.parse_args()

    errors = check_catalog()

    if args.strict_publication and CATALOG_ALL_FILE.exists():
        for record in load_json(CATALOG_ALL_FILE):
            if (
                record.get("status") == "ready"
                and record.get("review", {}).get(
                    "image_review_required"
                )
            ):
                errors.append(
                    f"{record.get('id')} | "
                    f"{record.get('name')} | "
                    "ready record still requires image review"
                )

    if args.geojson:
        errors.extend(
            check_geojson()
        )

    print()
    print("Catalog QA")
    print("----------")
    print(
        "Region:",
        f"{REGION_NAME} "
        f"({REGION_SLUG})",
    )

    if errors:
        print()
        print("QA FAILED")
        print()

        for error in errors:
            print(
                f"  - {error}"
            )

        print()
        print(
            f"{len(errors)} QA error(s)"
        )

        return 1

    records = load_json(
        CATALOG_ALL_FILE
    )

    ready = load_json(
        CATALOG_READY_FILE
    )

    print(
        "Catalog records:",
        len(records),
    )

    print(
        "Ready records:",
        len(ready),
    )

    print(
        "Remaining review records:",
        0,
    )

    if args.geojson:
        geojson = load_json(
            GEOJSON_FILE
        )

        print(
            "GeoJSON features:",
            len(
                geojson.get(
                    "features",
                    [],
                )
            ),
        )

    print()
    print("QA passed.")

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
