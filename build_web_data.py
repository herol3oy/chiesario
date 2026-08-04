import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REGIONS_FILE = ROOT / "config" / "regions.json"
DATA_DIR = ROOT / "data" / "regions"
OUTPUT_DIR = ROOT / "web" / "public" / "data"
OUTPUT_GEOJSON = OUTPUT_DIR / "churches.geojson"
OUTPUT_MANIFEST = OUTPUT_DIR / "catalog_manifest.json"


def load_json(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def published_region_slugs(regions):
    result = []
    for slug, region in regions.items():
        publish = region.get("publish", False)
        if not isinstance(publish, bool):
            raise ValueError(
                f"Region {slug!r} has non-boolean publish value"
            )
        if publish:
            result.append(slug)
    return result


def load_region_geojson(slug, region):
    path = DATA_DIR / slug / "catalog" / "churches.geojson"
    if not path.exists():
        raise FileNotFoundError(
            f"Published region GeoJSON not found: {path}"
        )

    geojson = load_json(path)
    if geojson.get("type") != "FeatureCollection":
        raise ValueError(
            f"{path} is not a GeoJSON FeatureCollection"
        )

    features = geojson.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{path} has no features array")

    expected_name = region["name"]
    required_properties = {
        "id",
        "name",
        "church_type",
        "region",
        "historic_scope",
        "date_display",
        "start_year",
        "date_source",
        "date_basis",
        "wikidata_url",
    }
    for feature in features:
        properties = feature.get("properties", {})
        missing = [
            field
            for field in sorted(required_properties)
            if properties.get(field) is None
        ]
        if missing:
            raise ValueError(
                f"{properties.get('id')} is missing required "
                f"web fields: {', '.join(missing)}"
            )
        if properties.get("region") != expected_name:
            raise ValueError(
                f"{properties.get('id')} has region "
                f"{properties.get('region')!r}; expected "
                f"{expected_name!r}"
            )
        if properties.get("historic_scope") != "historic":
            raise ValueError(
                f"{properties.get('id')} is not confirmed historic"
            )
        if properties.get("date_source") == "beweb":
            sources = properties.get("date_sources") or []
            if (
                not properties.get("date_source_url")
                or not any(
                    source.get("source_id")
                    and source.get("url")
                    for source in sources
                )
            ):
                raise ValueError(
                    f"{properties.get('id')} has a BeWeb date "
                    "without stable provenance"
                )
        if properties.get("hero_image"):
            image_missing = [
                field
                for field in (
                    "hero_description_url",
                    "hero_license_name",
                )
                if not properties.get(field)
            ]
            if image_missing:
                raise ValueError(
                    f"{properties.get('id')} has an image without "
                    "required Commons provenance: "
                    f"{', '.join(image_missing)}"
                )

    return features


def merge_geojson(regions, selected_slugs):
    seen_ids = set()
    features = []
    manifest_regions = []

    for slug in selected_slugs:
        if slug not in regions:
            raise ValueError(f"Unknown region: {slug}")
        region_features = load_region_geojson(
            slug,
            regions[slug],
        )
        for feature in region_features:
            qid = feature.get("properties", {}).get("id")
            if not qid:
                raise ValueError(
                    f"Feature in {slug} has no properties.id"
                )
            if qid in seen_ids:
                raise ValueError(
                    f"Duplicate QID across published regions: {qid}"
                )
            seen_ids.add(qid)
            features.append(feature)

        manifest_regions.append(
            {
                "slug": slug,
                "name": regions[slug]["name"],
                "feature_count": len(region_features),
            }
        )

    features.sort(
        key=lambda feature: feature["properties"]["id"]
    )
    return (
        {
            "type": "FeatureCollection",
            "features": features,
        },
        {
            "schema_version": 1,
            "total_features": len(features),
            "regions": manifest_regions,
        },
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic frontend data from "
            "QA-approved regional GeoJSON files."
        )
    )
    parser.add_argument(
        "--regions",
        nargs="+",
        help=(
            "Region slugs to publish. Defaults to regions "
            "with publish=true in config/regions.json."
        ),
    )
    args = parser.parse_args()

    regions = load_json(REGIONS_FILE)
    selected = (
        args.regions
        if args.regions
        else published_region_slugs(regions)
    )
    if not selected:
        raise RuntimeError("No regions are configured for publication")

    geojson, manifest = merge_geojson(
        regions,
        selected,
    )
    save_json(OUTPUT_GEOJSON, geojson)
    save_json(OUTPUT_MANIFEST, manifest)

    print()
    print("Web publication data built")
    print("--------------------------")
    print("Regions:", ", ".join(selected))
    print("Features:", manifest["total_features"])
    print(f"GeoJSON: {OUTPUT_GEOJSON}")
    print(f"Manifest: {OUTPUT_MANIFEST}")


if __name__ == "__main__":
    main()
