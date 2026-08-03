import json
import re
import unicodedata

from project_config import (
    CATALOG_ALL_FILE,
    CATALOG_READY_FILE,
    CATALOG_REPORT_FILE,
    REGION_NAME,
    REVIEWED_FILE,
)

INPUT_FILE = REVIEWED_FILE
OUTPUT_ALL = CATALOG_ALL_FILE
OUTPUT_READY = CATALOG_READY_FILE
REPORT_FILE = CATALOG_REPORT_FILE


# --------------------------------------------------
# IO
# --------------------------------------------------


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


# --------------------------------------------------
# Slugs
# --------------------------------------------------


def slugify(value):
    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.casefold()

    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    )

    return value.strip("-")


def build_slug(church):
    name = (
        church["derived"]
        .get("display_name")
        or church["wikidata_id"]
    )

    qid = church[
        "wikidata_id"
    ].lower()

    return (
        f"{slugify(name)}-{qid}"
    )


# --------------------------------------------------
# Core fields
# --------------------------------------------------


def build_coordinates(church):
    resolved = church.get(
        "resolved_coordinates",
        {},
    )

    canonical = resolved.get(
        "canonical"
    )

    if not canonical:
        return None

    return {
        "latitude":
            canonical.get(
                "latitude"
            ),

        "longitude":
            canonical.get(
                "longitude"
            ),

        "source":
            canonical.get(
                "source"
            ),
    }


def build_date(church):
    resolved = church.get(
        "resolved_date",
        {},
    )

    canonical = resolved.get(
        "canonical"
    )

    if not canonical:
        return None

    return {
        "display":
            canonical.get(
                "display"
            ),

        "kind":
            canonical.get(
                "kind"
            ),

        "start_year":
            canonical.get(
                "start_year"
            ),

        "end_year":
            canonical.get(
                "end_year"
            ),

        "source":
            canonical.get(
                "source",
                "wikidata",
            ),

        "source_name":
            canonical.get(
                "source_name"
            ),

        "source_url":
            canonical.get(
                "source_url"
            ),
    }


def build_hero_image(church):
    selection = church.get(
        "image_selection",
        {},
    )

    hero = selection.get(
        "hero_image"
    )

    if not hero:
        return None

    license_data = hero.get(
        "license"
    ) or {}

    artist = hero.get(
        "artist"
    ) or {}

    return {
        "filename":
            hero.get(
                "filename"
            ),

        "url":
            hero.get(
                "url"
            ),

        "thumbnail_url":
            hero.get(
                "thumbnail_url"
            ),

        "description_url":
            hero.get(
                "description_url"
            ),

        "license": {
            "name":
                license_data.get(
                    "name"
                ),

            "url":
                license_data.get(
                    "url"
                ),

            "usage_terms":
                license_data.get(
                    "usage_terms"
                ),

            "attribution_required":
                license_data.get(
                    "attribution_required"
                ),
        },

        "artist":
            artist.get(
                "text"
            ),

        "source":
            hero.get(
                "source",
                "wikimedia_commons",
            ),
    }


# --------------------------------------------------
# Website
# --------------------------------------------------


def build_website(church):
    """
    Preference:

    1. Wikidata P856
    2. single exact OSM match

    Later we can create a proper website resolver.
    """

    wikidata_websites = church.get(
        "websites",
        [],
    )

    if wikidata_websites:
        return {
            "url":
                wikidata_websites[0],

            "source":
                "wikidata",
        }

    osm_matches = church.get(
        "osm_matches",
        [],
    )

    if len(osm_matches) == 1:

        website = osm_matches[0].get(
            "website"
        )

        if website:
            return {
                "url": website,
                "source":
                    "openstreetmap",
            }

    return None


# --------------------------------------------------
# OSM reference
# --------------------------------------------------


def build_osm_reference(church):
    matches = church.get(
        "osm_matches",
        [],
    )

    if len(matches) != 1:
        return None

    match = matches[0]

    return {
        "type":
            match.get(
                "osm_type"
            ),

        "id":
            match.get(
                "osm_id"
            ),

        "url":
            match.get(
                "osm_url"
            ),
    }


# --------------------------------------------------
# Review status
# --------------------------------------------------


BLOCKING_REVIEWS = {
    "date":
        "date_review_required",

    "coordinates":
        "coordinate_review_required",

    "type":
        "type_review_required",

    "duplicate":
        "duplicate_review_required",
}


def blocking_reviews(church):
    derived = church[
        "derived"
    ]

    return [
        name
        for name, field in (
            BLOCKING_REVIEWS.items()
        )
        if derived.get(field)
    ]


def determine_status(church):
    derived = church[
        "derived"
    ]

    if derived.get(
        "manually_excluded"
    ):
        return "excluded"

    if derived.get(
        "suppressed_as_duplicate"
    ):
        return "duplicate"

    if not derived.get(
        "publishable_by_type",
        False,
    ):
        return "out_of_scope"

    blockers = blocking_reviews(
        church
    )

    if blockers:
        return "review"

    if not build_coordinates(
        church
    ):
        return "review"

    if not build_date(
        church
    ):
        return "review"

    return "ready"


# --------------------------------------------------
# Catalog record
# --------------------------------------------------


def build_record(church):
    qid = church[
        "wikidata_id"
    ]

    derived = church[
        "derived"
    ]

    status = determine_status(
        church
    )

    return {
        "id": qid,

        "slug":
            build_slug(
                church
            ),

        "name":
            derived.get(
                "display_name"
            ),

        "type":
            derived.get(
                "directory_type"
            ),

        "region": REGION_NAME,

        "date":
            build_date(
                church
            ),

        "coordinates":
            build_coordinates(
                church
            ),

        "hero_image":
            build_hero_image(
                church
            ),

        "website":
            build_website(
                church
            ),

        "wikidata": {
            "id": qid,

            "url":
                f"https://www.wikidata.org/wiki/{qid}",
        },

        "osm":
            build_osm_reference(
                church
            ),

        "status":
            status,

        "review": {
            "blocking":
                blocking_reviews(
                    church
                ),

            # Image review deliberately
            # does NOT block publication.
            "image_review_required":
                derived.get(
                    "image_review_required",
                    False,
                ),
        },
    }


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(records):
    status_counts = {}

    with_images = 0
    without_images = 0

    with_websites = 0

    for record in records:

        status = record[
            "status"
        ]

        status_counts[
            status
        ] = (
            status_counts.get(
                status,
                0,
            )
            + 1
        )

        if record[
            "hero_image"
        ]:
            with_images += 1
        else:
            without_images += 1

        if record[
            "website"
        ]:
            with_websites += 1

    ready = [
        record
        for record in records
        if record[
            "status"
        ] == "ready"
    ]

    return {
        "total_records":
            len(records),

        "status_counts":
            status_counts,

        "ready_records":
            len(ready),

        "ready_with_hero_image":
            sum(
                1
                for record in ready
                if record[
                    "hero_image"
                ]
            ),

        "ready_without_hero_image":
            sum(
                1
                for record in ready
                if not record[
                    "hero_image"
                ]
            ),

        "records_with_website":
            with_websites,

        "records_with_hero_image":
            with_images,

        "records_without_hero_image":
            without_images,
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run apply_overrides.py first."
        )

    churches = load_json(
        INPUT_FILE
    )

    records = [
        build_record(
            church
        )
        for church in churches
    ]

    records.sort(
        key=lambda record: (
            record["name"]
            or ""
        ).casefold()
    )

    ready = [
        record
        for record in records
        if record[
            "status"
        ] == "ready"
    ]

    save_json(
        OUTPUT_ALL,
        records,
    )

    save_json(
        OUTPUT_READY,
        ready,
    )

    report = build_report(
        records
    )

    save_json(
        REPORT_FILE,
        report,
    )

    print()
    print(
        "Catalog build complete"
    )

    print(
        "----------------------"
    )

    print(
        "Total records:",
        report[
            "total_records"
        ],
    )

    print()
    print(
        "Statuses:"
    )

    for status, count in (
        report[
            "status_counts"
        ].items()
    ):
        print(
            f"  {status:15} {count}"
        )

    print()
    print(
        "Ready records:",
        report[
            "ready_records"
        ],
    )

    print(
        "Ready with hero image:",
        report[
            "ready_with_hero_image"
        ],
    )

    print(
        "Ready without hero image:",
        report[
            "ready_without_hero_image"
        ],
    )

    print()
    print(
        "Records with websites:",
        report[
            "records_with_website"
        ],
    )

    print()
    print(
        f"All:    {OUTPUT_ALL}"
    )

    print(
        f"Ready:  {OUTPUT_READY}"
    )

    print(
        f"Report: {REPORT_FILE}"
    )


if __name__ == "__main__":
    main()
