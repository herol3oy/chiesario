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

    args = parser.parse_args()

    errors = check_catalog()

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
