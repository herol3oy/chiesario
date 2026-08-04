import json

from project_config import (
    DUPLICATES_FILE,
    OVERRIDES_FILE,
    REVIEWED_FILE,
    REVIEW_REPORT_FILE,
)
from resolve_historic_scope import (
    apply_historic_scope,
)

INPUT_FILE = DUPLICATES_FILE
OUTPUT_FILE = REVIEWED_FILE
REPORT_FILE = REVIEW_REPORT_FILE


VALID_TYPES = {
    "church",
    "cathedral",
    "basilica",
    "former_church",
    "chapel",
    "oratory",
    "baptistery",
    "sacristy",
    "abbey",
    "monastery",
    "other",
}


VALID_DUPLICATE_STATUSES = {
    "same_entity",
    "related",
    "false_positive",
    "needs_review",
}


# --------------------------------------------------
# IO
# --------------------------------------------------


def load_json(path, default=None):
    if not path.exists():
        return default

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
# Helpers
# --------------------------------------------------


def index_churches(churches):
    return {
        church["wikidata_id"]: church
        for church in churches
    }


def ensure_manual_section(church):
    church.setdefault(
        "manual_overrides",
        {
            "applied": [],
            "notes": [],
        },
    )

    return church["manual_overrides"]


def record_override(
    church,
    field,
    old_value,
    new_value,
):
    manual = ensure_manual_section(
        church
    )

    manual["applied"].append(
        {
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
        }
    )


# --------------------------------------------------
# Record overrides
# --------------------------------------------------


def override_name(
    church,
    value,
):
    old = (
        church["derived"]
        .get("display_name")
    )

    church["derived"][
        "display_name"
    ] = value

    church["derived"][
        "canonical_name_source"
    ] = "manual"

    record_override(
        church,
        "display_name",
        old,
        value,
    )


def override_type(
    church,
    value,
):
    if value not in VALID_TYPES:
        raise ValueError(
            f"Invalid directory_type: {value}"
        )

    old = (
        church["derived"]
        .get("directory_type")
    )

    church["derived"][
        "directory_type"
    ] = value

    church["derived"][
        "type_review_required"
    ] = False

    church["derived"][
        "directory_type_source"
    ] = "manual"

    record_override(
        church,
        "directory_type",
        old,
        value,
    )


def override_date(
    church,
    value,
):
    required = {
        "kind",
        "start_year",
        "end_year",
        "display",
    }

    missing = (
        required - set(value)
    )

    if missing:
        raise ValueError(
            "canonical_date missing fields: "
            + ", ".join(
                sorted(missing)
            )
        )

    old = (
        church.get(
            "resolved_date",
            {},
        ).get(
            "canonical"
        )
    )

    source_name = value.get(
        "source_name"
    )
    source_url = value.get(
        "source_url"
    )
    sources = value.get("sources") or []
    if not sources and (source_name or source_url):
        sources = [
            {
                "name": source_name or "Manual research",
                "url": source_url,
                "source_id": None,
            }
        ]

    canonical = {
        "kind":
            value["kind"],

        "start_year":
            value["start_year"],

        "end_year":
            value["end_year"],

        "display":
            value["display"],

        "source":
            "manual",

        "basis":
            value.get(
                "basis",
                "origin",
            ),

        "source_name":
            source_name,

        "source_url":
            source_url,

        "sources": sources,

        "evidence_refs":
            value.get(
                "evidence_refs",
                [],
            ),

        "note":
            value.get(
                "note"
            ),
    }

    church.setdefault(
        "resolved_date",
        {},
    )

    church[
        "resolved_date"
    ][
        "canonical"
    ] = canonical

    church[
        "resolved_date"
    ][
        "review_required"
    ] = False

    church[
        "resolved_date"
    ][
        "reason"
    ] = "manual_override"

    derived = church[
        "derived"
    ]

    derived[
        "date_review_required"
    ] = False

    derived[
        "canonical_date_display"
    ] = canonical[
        "display"
    ]

    derived[
        "canonical_date_start_year"
    ] = canonical[
        "start_year"
    ]

    derived[
        "canonical_date_end_year"
    ] = canonical[
        "end_year"
    ]

    derived[
        "canonical_date_kind"
    ] = canonical[
        "kind"
    ]

    derived[
        "canonical_date_source"
    ] = "manual"

    derived[
        "canonical_date_basis"
    ] = canonical[
        "basis"
    ]

    record_override(
        church,
        "canonical_date",
        old,
        canonical,
    )


def override_coordinates(
    church,
    value,
):
    latitude = value.get(
        "latitude"
    )

    longitude = value.get(
        "longitude"
    )

    if (
        latitude is None
        or longitude is None
    ):
        raise ValueError(
            "canonical_coordinates requires "
            "latitude and longitude"
        )

    if not (-90 <= latitude <= 90):
        raise ValueError(
            f"Invalid latitude: {latitude}"
        )

    if not (-180 <= longitude <= 180):
        raise ValueError(
            f"Invalid longitude: {longitude}"
        )

    old = (
        church.get(
            "resolved_coordinates",
            {},
        ).get(
            "canonical"
        )
    )

    canonical = {
        "latitude": latitude,
        "longitude": longitude,
        "source": "manual",
        "note": value.get("note"),
    }

    church.setdefault(
        "resolved_coordinates",
        {},
    )

    church[
        "resolved_coordinates"
    ][
        "canonical"
    ] = canonical

    derived = church[
        "derived"
    ]

    derived[
        "has_canonical_coordinates"
    ] = True

    derived[
        "canonical_coordinate_source"
    ] = "manual"

    derived[
        "coordinate_review_required"
    ] = False

    record_override(
        church,
        "canonical_coordinates",
        old,
        canonical,
    )


def override_hero_image(
    church,
    filename,
):
    image = next(
        (
            item
            for item in church.get(
                "images",
                [],
            )
            if item.get(
                "filename"
            ) == filename
        ),
        None,
    )

    if image is None:
        raise ValueError(
            f"Image not found on "
            f"{church['wikidata_id']}: "
            f"{filename}"
        )

    commons = image.get(
        "commons"
    ) or {}

    if commons.get("missing"):
        raise ValueError(
            f"Commons image missing: "
            f"{filename}"
        )

    old = (
        church.get(
            "image_selection",
            {},
        ).get(
            "hero_image"
        )
    )

    hero = {
        "filename": filename,

        "url":
            commons.get("url"),

        "thumbnail_url":
            commons.get(
                "thumbnail_url"
            ),

        "description_url":
            commons.get(
                "description_url"
            ),

        "license":
            commons.get(
                "license"
            ),

        "artist":
            commons.get(
                "artist"
            ),

        "source":
            "manual",
    }

    church.setdefault(
        "image_selection",
        {},
    )

    church[
        "image_selection"
    ][
        "hero_image"
    ] = hero

    church[
        "image_selection"
    ][
        "review_required"
    ] = False

    church[
        "image_selection"
    ][
        "reason"
    ] = "manual_override"

    derived = church[
        "derived"
    ]

    derived[
        "has_hero_image"
    ] = True

    derived[
        "image_review_required"
    ] = False

    derived[
        "hero_image_source"
    ] = "manual"

    record_override(
        church,
        "hero_image",
        old,
        hero,
    )


def apply_record_override(
    church,
    override,
):
    # A record cannot simultaneously specify
    # a manual hero and explicitly have no hero.
    has_manual_hero = (
        "hero_image_filename"
        in override
    )

    has_no_hero = (
        override.get(
            "no_hero_image"
        )
        is True
    )

    if (
        has_manual_hero
        and has_no_hero
    ):
        raise ValueError(
            f"{church['wikidata_id']} cannot have both "
            "hero_image_filename and no_hero_image"
        )


    if "canonical_name" in override:
        override_name(
            church,
            override[
                "canonical_name"
            ],
        )


    if "directory_type" in override:
        override_type(
            church,
            override[
                "directory_type"
            ],
        )


    if "canonical_date" in override:
        override_date(
            church,
            override[
                "canonical_date"
            ],
        )


    if "canonical_coordinates" in override:
        override_coordinates(
            church,
            override[
                "canonical_coordinates"
            ],
        )


    # ------------------------------------------
    # Image overrides
    # ------------------------------------------

    if has_manual_hero:

        override_hero_image(
            church,
            override[
                "hero_image_filename"
            ],
        )

    elif has_no_hero:

        old = (
            church.get(
                "image_selection",
                {},
            ).get(
                "hero_image"
            )
        )

        church.setdefault(
            "image_selection",
            {},
        )

        church[
            "image_selection"
        ][
            "hero_image"
        ] = None

        church[
            "image_selection"
        ][
            "review_required"
        ] = False

        church[
            "image_selection"
        ][
            "reason"
        ] = "manual_no_suitable_image"

        church[
            "derived"
        ][
            "has_hero_image"
        ] = False

        church[
            "derived"
        ][
            "image_review_required"
        ] = False

        church[
            "derived"
        ][
            "hero_image_source"
        ] = "manual_review"

        record_override(
            church,
            "hero_image",
            old,
            None,
        )


    # ------------------------------------------
    # Exclusion
    # ------------------------------------------

    if "exclude" in override:

        old = (
            church[
                "derived"
            ].get(
                "manually_excluded"
            )
        )

        excluded = bool(
            override[
                "exclude"
            ]
        )

        church[
            "derived"
        ][
            "manually_excluded"
        ] = excluded

        church[
            "derived"
        ][
            "exclusion_reason"
        ] = override.get(
            "exclusion_reason"
        )

        record_override(
            church,
            "manually_excluded",
            old,
            excluded,
        )


    # ------------------------------------------
    # Note
    # ------------------------------------------

    note = override.get(
        "note"
    )

    if note:
        manual = (
            ensure_manual_section(
                church
            )
        )

        manual[
            "notes"
        ].append(
            note
        )

# --------------------------------------------------
# Duplicate resolutions
# --------------------------------------------------


def apply_duplicate_pair(
    pair,
    church_by_qid,
):
    qid1 = pair[
        "qid_1"
    ]

    qid2 = pair[
        "qid_2"
    ]

    status = pair[
        "status"
    ]

    if status not in (
        VALID_DUPLICATE_STATUSES
    ):
        raise ValueError(
            f"Invalid duplicate status: "
            f"{status}"
        )

    if qid1 not in church_by_qid:
        raise ValueError(
            f"Unknown QID: {qid1}"
        )

    if qid2 not in church_by_qid:
        raise ValueError(
            f"Unknown QID: {qid2}"
        )

    church1 = church_by_qid[qid1]
    church2 = church_by_qid[qid2]

    resolution = {
        "qid_1": qid1,
        "qid_2": qid2,
        "status": status,
        "note": pair.get("note"),
    }

    if status == "same_entity":

        canonical_qid = pair.get(
            "canonical_qid"
        )

        if canonical_qid not in {
            qid1,
            qid2,
        }:
            raise ValueError(
                "same_entity requires "
                "canonical_qid equal to "
                "qid_1 or qid_2"
            )

        duplicate_qid = (
            qid2
            if canonical_qid == qid1
            else qid1
        )

        canonical_church = (
            church_by_qid[
                canonical_qid
            ]
        )

        duplicate_church = (
            church_by_qid[
                duplicate_qid
            ]
        )

        canonical_church[
            "derived"
        ][
            "duplicate_review_required"
        ] = False

        canonical_church[
            "derived"
        ][
            "possible_duplicate"
        ] = False

        canonical_church[
            "derived"
        ][
            "duplicate_role"
        ] = "canonical"

        duplicate_church[
            "derived"
        ][
            "duplicate_review_required"
        ] = False

        duplicate_church[
            "derived"
        ][
            "possible_duplicate"
        ] = False

        duplicate_church[
            "derived"
        ][
            "duplicate_role"
        ] = "duplicate"

        duplicate_church[
            "derived"
        ][
            "duplicate_of"
        ] = canonical_qid

        duplicate_church[
            "derived"
        ][
            "suppressed_as_duplicate"
        ] = True

        resolution[
            "canonical_qid"
        ] = canonical_qid

    else:

        for church in (
            church1,
            church2,
        ):

            church[
                "derived"
            ][
                "duplicate_review_required"
            ] = (
                status
                == "needs_review"
            )

            if status in {
                "related",
                "false_positive",
            }:
                church[
                    "derived"
                ][
                    "possible_duplicate"
                ] = False

    for church in (
        church1,
        church2,
    ):
        church.setdefault(
            "duplicate_resolutions",
            [],
        ).append(
            resolution
        )


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(churches):
    overridden = []

    suppressed = []

    excluded = []
    withheld = []

    remaining_reviews = {
        "dates": [],
        "historic_scope": [],
        "coordinates": [],
        "types": [],
        "images": [],
        "duplicates": [],
    }

    for church in churches:

        qid = church[
            "wikidata_id"
        ]

        name = church[
            "derived"
        ].get(
            "display_name"
        )

        manual = church.get(
            "manual_overrides"
        )

        if (
            manual
            and manual.get(
                "applied"
            )
        ):
            overridden.append(
                {
                    "wikidata_id": qid,
                    "name": name,
                    "changes":
                        manual[
                            "applied"
                        ],
                }
            )

        derived = church[
            "derived"
        ]

        if derived.get(
            "suppressed_as_duplicate"
        ):
            suppressed.append(
                {
                    "wikidata_id": qid,
                    "name": name,
                    "duplicate_of":
                        derived.get(
                            "duplicate_of"
                        ),
                }
            )

        if derived.get(
            "manually_excluded"
        ):
            excluded.append(
                {
                    "wikidata_id": qid,
                    "name": name,
                    "reason":
                        derived.get(
                            "exclusion_reason"
                        ),
                }
            )

        historic_scope = derived.get("historic_scope")
        if historic_scope == "unknown":
            withheld.append(
                {
                    "wikidata_id": qid,
                    "name": name,
                    "reason": "unknown_historic_scope",
                }
            )
            continue

        if (
            historic_scope != "historic"
            or derived.get("manually_excluded")
            or derived.get("suppressed_as_duplicate")
        ):
            continue

        checks = {
            "dates":
                "date_review_required",

            "coordinates":
                "coordinate_review_required",

            "types":
                "type_review_required",

            "images":
                "image_review_required",

            "duplicates":
                "duplicate_review_required",
        }

        for category, field in (
            checks.items()
        ):
            if derived.get(field):
                remaining_reviews[
                    category
                ].append(
                    {
                        "wikidata_id":
                            qid,

                        "name":
                            name,
                    }
                )

    return {
        "total_entities":
            len(churches),

        "records_with_manual_overrides":
            len(overridden),

        "suppressed_duplicates":
            len(suppressed),

        "manually_excluded":
            len(excluded),

        "withheld_unknown_scope":
            len(withheld),

        "remaining_review_counts": {
            key: len(value)
            for key, value in (
                remaining_reviews
                .items()
            )
        },

        "overridden_records":
            overridden,

        "suppressed_duplicate_records":
            suppressed,

        "excluded_records":
            excluded,

        "withheld_records":
            withheld,

        "remaining_reviews":
            remaining_reviews,
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run detect_duplicates.py first."
        )

    churches = load_json(
        INPUT_FILE,
        [],
    )

    overrides = load_json(
        OVERRIDES_FILE,
        {
            "records": {},
            "duplicate_pairs": [],
        },
    )

    church_by_qid = (
        index_churches(
            churches
        )
    )

    # ------------------------------------------
    # Individual record overrides
    # ------------------------------------------

    for qid, override in (
        overrides.get(
            "records",
            {},
        ).items()
    ):

        church = church_by_qid.get(
            qid
        )

        if church is None:
            raise ValueError(
                f"Override references "
                f"unknown QID: {qid}"
            )

        apply_record_override(
            church,
            override,
        )

    # ------------------------------------------
    # Duplicate decisions
    # ------------------------------------------

    for pair in overrides.get(
        "duplicate_pairs",
        [],
    ):
        apply_duplicate_pair(
            pair,
            church_by_qid,
        )

    # Date overrides are applied after the automatic
    # historic-scope stage. Recompute the derived scope
    # so reviewed canonical dates remain authoritative.
    for church in churches:
        apply_historic_scope(
            church
        )

    # ------------------------------------------
    # Save
    # ------------------------------------------

    save_json(
        OUTPUT_FILE,
        churches,
    )

    report = build_report(
        churches
    )

    save_json(
        REPORT_FILE,
        report,
    )

    print()
    print(
        "Manual review layer applied"
    )

    print(
        "---------------------------"
    )

    print(
        "Entities:",
        report[
            "total_entities"
        ],
    )

    print(
        "Records overridden:",
        report[
            "records_with_manual_overrides"
        ],
    )

    print(
        "Suppressed duplicates:",
        report[
            "suppressed_duplicates"
        ],
    )

    print(
        "Manually excluded:",
        report[
            "manually_excluded"
        ],
    )

    print(
        "Withheld (unknown historic scope):",
        report[
            "withheld_unknown_scope"
        ],
    )

    print()
    print(
        "Remaining reviews:"
    )

    for category, count in (
        report[
            "remaining_review_counts"
        ].items()
    ):
        print(
            f"  {category:12} {count}"
        )

    print()
    print(
        f"Output: {OUTPUT_FILE}"
    )

    print(
        f"Report: {REPORT_FILE}"
    )


if __name__ == "__main__":
    main()
