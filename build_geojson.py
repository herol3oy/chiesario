import json

from project_config import (
    CATALOG_READY_FILE,
    GEOJSON_FILE,
)

INPUT_FILE = CATALOG_READY_FILE
OUTPUT_FILE = GEOJSON_FILE


def load_json(path):
    with path.open(
        encoding="utf-8"
    ) as f:
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


def build_feature(church):
    coordinates = church.get(
        "coordinates"
    )

    if not coordinates:
        return None

    lat = coordinates.get(
        "latitude"
    )

    lon = coordinates.get(
        "longitude"
    )

    if lat is None or lon is None:
        return None

    date = church.get(
        "date"
    ) or {}

    hero = church.get(
        "hero_image"
    ) or {}

    website = church.get(
        "website"
    ) or {}

    return {
        "type": "Feature",

        "id": church["id"],

        "geometry": {
            "type": "Point",
            "coordinates": [
                lon,
                lat,
            ],
        },

        "properties": {
            "id":
                church["id"],

            "slug":
                church["slug"],

            "name":
                church["name"],

            "church_type":
                church["type"],

            "region":
                church["region"],

            "historic_scope":
                church.get(
                    "historic_scope"
                ),

            "date_display":
                date.get(
                    "display"
                ),

            "date_kind":
                date.get(
                    "kind"
                ),

            "start_year":
                date.get(
                    "start_year"
                ),

            "end_year":
                date.get(
                    "end_year"
                ),

            "date_source":
                date.get(
                    "source"
                ),

            "date_basis":
                date.get(
                    "basis"
                ),

            "date_source_name":
                date.get(
                    "source_name"
                ),

            "date_source_url":
                date.get(
                    "source_url"
                ),

            "date_sources":
                date.get(
                    "sources",
                    [],
                ),

            "historical_phases":
                date.get(
                    "historical_phases",
                    [],
                ),

            "coordinate_source":
                coordinates.get(
                    "source"
                ),

            "hero_image":
                hero.get(
                    "thumbnail_url"
                )
                or hero.get(
                    "url"
                ),

            "hero_filename":
                hero.get(
                    "filename"
                ),

            "hero_description_url":
                hero.get(
                    "description_url"
                ),

            "hero_artist":
                hero.get(
                    "artist"
                ),

            "hero_license_name":
                hero.get(
                    "license",
                    {},
                ).get(
                    "name"
                ),

            "hero_license_url":
                hero.get(
                    "license",
                    {},
                ).get(
                    "url"
                ),

            "website":
                website.get(
                    "url"
                ),

            "wikidata_url":
                church[
                    "wikidata"
                ][
                    "url"
                ],

            "osm_url": (
                church["osm"].get(
                    "url"
                )
                if church.get(
                    "osm"
                )
                else None
            ),
        },
    }


def main():
    churches = load_json(
        INPUT_FILE
    )

    features = []

    skipped = []

    for church in churches:

        feature = build_feature(
            church
        )

        if feature:
            features.append(
                feature
            )
        else:
            skipped.append(
                church["id"]
            )

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    save_json(
        OUTPUT_FILE,
        geojson,
    )

    print()
    print("GeoJSON build complete")
    print("----------------------")
    print(
        "Input records:",
        len(churches),
    )
    print(
        "Features:",
        len(features),
    )
    print(
        "Skipped:",
        len(skipped),
    )
    print()
    print(
        f"Output: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
