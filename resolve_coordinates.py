import json
import math
from pathlib import Path


INPUT_FILE = Path(
    "data/processed/churches_osm.json"
)

OUTPUT_FILE = Path(
    "data/processed/churches_resolved.json"
)

REPORT_FILE = Path(
    "data/processed/coordinate_report.json"
)


# This is only a review heuristic.
# It does NOT mean coordinates farther apart
# than this are necessarily wrong.
REVIEW_DISTANCE_METERS = 150


# --------------------------------------------------
# JSON helpers
# --------------------------------------------------


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


# --------------------------------------------------
# Distance
# --------------------------------------------------


def haversine_meters(
    lat1,
    lon1,
    lat2,
    lon2,
):
    """
    Distance between two coordinates on Earth.
    """

    earth_radius = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(
        lat2 - lat1
    )

    delta_lambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(
            delta_phi / 2
        ) ** 2
        +
        math.cos(phi1)
        * math.cos(phi2)
        * math.sin(
            delta_lambda / 2
        ) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius * c


# --------------------------------------------------
# Wikidata coordinate selection
# --------------------------------------------------


def valid_coordinate(coord):
    if not coord:
        return False

    lat = coord.get("latitude")
    lon = coord.get("longitude")

    return (
        lat is not None
        and lon is not None
    )


def choose_wikidata_coordinate(church):
    """
    Choose one Wikidata coordinate conservatively.

    Rules:

    1. Ignore invalid coordinates.
    2. Ignore deprecated statements.
    3. Prefer preferred-rank coordinates.
    4. Otherwise use a normal-rank coordinate.

    We return metadata so we don't lose provenance.
    """

    coordinates = [
        coord
        for coord in church.get(
            "coordinates",
            [],
        )
        if (
            valid_coordinate(coord)
            and coord.get("rank")
            != "deprecated"
        )
    ]

    if not coordinates:
        return None

    preferred = [
        coord
        for coord in coordinates
        if coord.get("rank")
        == "preferred"
    ]

    if preferred:
        chosen = preferred[0]
    else:
        chosen = coordinates[0]

    return {
        "latitude":
            chosen["latitude"],

        "longitude":
            chosen["longitude"],

        "source":
            "wikidata",

        "wikidata_statement_id":
            chosen.get(
                "statement_id"
            ),

        "wikidata_rank":
            chosen.get("rank"),
    }


# --------------------------------------------------
# OSM coordinate selection
# --------------------------------------------------


def choose_osm_coordinate(church):
    """
    Only choose an OSM coordinate when there is
    exactly ONE exact Wikidata-QID match.

    Multiple matches remain unresolved.
    """

    matches = church.get(
        "osm_matches",
        [],
    )

    if len(matches) != 1:
        return None

    match = matches[0]

    coord = match.get(
        "coordinates"
    )

    if not valid_coordinate(coord):
        return None

    return {
        "latitude":
            coord["latitude"],

        "longitude":
            coord["longitude"],

        "source":
            "openstreetmap",

        "osm_type":
            match.get("osm_type"),

        "osm_id":
            match.get("osm_id"),

        "osm_url":
            match.get("osm_url"),
    }


# --------------------------------------------------
# Resolve
# --------------------------------------------------


def resolve_coordinates(church):
    wikidata = (
        choose_wikidata_coordinate(
            church
        )
    )

    osm = choose_osm_coordinate(
        church
    )

    comparison = None

    # ------------------------------------------
    # Compare sources if both exist
    # ------------------------------------------

    if wikidata and osm:

        distance = haversine_meters(
            wikidata["latitude"],
            wikidata["longitude"],
            osm["latitude"],
            osm["longitude"],
        )

        comparison = {
            "distance_meters":
                round(distance, 2),

            "review_required":
                distance
                > REVIEW_DISTANCE_METERS,
        }

    # ------------------------------------------
    # Canonical choice
    # ------------------------------------------

    if wikidata:
        canonical = {
            "latitude":
                wikidata["latitude"],

            "longitude":
                wikidata["longitude"],

            "source":
                "wikidata",
        }

    elif osm:
        canonical = {
            "latitude":
                osm["latitude"],

            "longitude":
                osm["longitude"],

            "source":
                "openstreetmap",
        }

    else:
        canonical = None

    return {
        "canonical": canonical,
        "wikidata": wikidata,
        "osm": osm,
        "comparison": comparison,
    }


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(churches):
    unresolved = []
    osm_fallback = []
    disagreements = []

    wikidata_count = 0
    osm_count = 0

    compared = 0

    distances = []

    for church in churches:

        resolved = church.get(
            "resolved_coordinates",
            {},
        )

        canonical = resolved.get(
            "canonical"
        )

        comparison = resolved.get(
            "comparison"
        )

        name = church[
            "derived"
        ][
            "display_name"
        ]

        qid = church[
            "wikidata_id"
        ]

        # --------------------------------------
        # Canonical source
        # --------------------------------------

        if not canonical:

            unresolved.append(
                {
                    "wikidata_id": qid,
                    "name": name,
                    "osm_match_status":
                        church[
                            "derived"
                        ].get(
                            "osm_match_status"
                        ),
                }
            )

        elif canonical[
            "source"
        ] == "wikidata":

            wikidata_count += 1

        elif canonical[
            "source"
        ] == "openstreetmap":

            osm_count += 1

            osm_fallback.append(
                {
                    "wikidata_id": qid,
                    "name": name,

                    "latitude":
                        canonical[
                            "latitude"
                        ],

                    "longitude":
                        canonical[
                            "longitude"
                        ],
                }
            )

        # --------------------------------------
        # Cross-source comparison
        # --------------------------------------

        if comparison:

            compared += 1

            distance = comparison[
                "distance_meters"
            ]

            distances.append(
                distance
            )

            if comparison[
                "review_required"
            ]:

                disagreements.append(
                    {
                        "wikidata_id": qid,
                        "name": name,

                        "distance_meters":
                            distance,

                        "wikidata":
                            resolved[
                                "wikidata"
                            ],

                        "osm":
                            resolved[
                                "osm"
                            ],
                    }
                )

    if distances:
        average_distance = (
            sum(distances)
            / len(distances)
        )

        max_distance = max(
            distances
        )
    else:
        average_distance = None
        max_distance = None

    return {
        "total":
            len(churches),

        "canonical_from_wikidata":
            wikidata_count,

        "canonical_from_osm":
            osm_count,

        "unresolved":
            len(unresolved),

        "sources_compared":
            compared,

        "coordinate_disagreements":
            len(disagreements),

        "review_threshold_meters":
            REVIEW_DISTANCE_METERS,

        "average_wikidata_osm_distance_meters":
            (
                round(
                    average_distance,
                    2,
                )
                if average_distance
                is not None
                else None
            ),

        "maximum_wikidata_osm_distance_meters":
            (
                round(
                    max_distance,
                    2,
                )
                if max_distance
                is not None
                else None
            ),

        "osm_fallback_records":
            osm_fallback,

        "unresolved_records":
            unresolved,

        "disagreement_records":
            sorted(
                disagreements,
                key=lambda item:
                    item[
                        "distance_meters"
                    ],
                reverse=True,
            ),
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run enrich_osm.py first."
        )

    churches = load_json(
        INPUT_FILE
    )

    for church in churches:

        resolved = resolve_coordinates(
            church
        )

        church[
            "resolved_coordinates"
        ] = resolved

        canonical = resolved[
            "canonical"
        ]

        derived = church[
            "derived"
        ]

        if canonical:

            derived[
                "has_canonical_coordinates"
            ] = True

            derived[
                "canonical_coordinate_source"
            ] = canonical[
                "source"
            ]

        else:

            derived[
                "has_canonical_coordinates"
            ] = False

            derived[
                "canonical_coordinate_source"
            ] = None

        comparison = resolved.get(
            "comparison"
        )

        derived[
            "coordinate_review_required"
        ] = bool(
            comparison
            and comparison[
                "review_required"
            ]
        )

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
        "Coordinate resolution complete"
    )

    print(
        "------------------------------"
    )

    print(
        "Total:",
        report["total"],
    )

    print(
        "Canonical from Wikidata:",
        report[
            "canonical_from_wikidata"
        ],
    )

    print(
        "Canonical from OSM:",
        report[
            "canonical_from_osm"
        ],
    )

    print(
        "Unresolved:",
        report[
            "unresolved"
        ],
    )

    print()
    print(
        "Wikidata/OSM compared:",
        report[
            "sources_compared"
        ],
    )

    print(
        "Need coordinate review:",
        report[
            "coordinate_disagreements"
        ],
    )

    print(
        "Average distance:",
        report[
            "average_wikidata_osm_distance_meters"
        ],
        "m",
    )

    print(
        "Maximum distance:",
        report[
            "maximum_wikidata_osm_distance_meters"
        ],
        "m",
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