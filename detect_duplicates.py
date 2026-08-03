import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


INPUT_FILE = Path(
    "data/processed/churches_images.json"
)

OUTPUT_FILE = Path(
    "data/processed/churches_duplicates.json"
)

REPORT_FILE = Path(
    "data/processed/duplicate_report.json"
)


# --------------------------------------------------
# Thresholds
# --------------------------------------------------

VERY_CLOSE_METERS = 30
CLOSE_METERS = 100

HIGH_NAME_SIMILARITY = 0.90
VERY_HIGH_NAME_SIMILARITY = 0.95


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
# Text normalization
# --------------------------------------------------


STOPWORDS = {
    "chiesa",
    "church",
    "basilica",
    "cattedrale",
    "cathedral",
    "cappella",
    "chapel",
    "pieve",

    "san",
    "santa",
    "santo",
    "santi",

    "di",
    "del",
    "della",
    "delle",
    "dei",
    "degli",
    "da",
    "in",
    "a",
    "al",
    "alla",
    "alle",
    "the",
    "of",
}


def normalize_text(value):
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
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def meaningful_tokens(value):
    text = normalize_text(value)

    return {
        token
        for token in text.split()
        if (
            len(token) >= 3
            and token not in STOPWORDS
        )
    }


def name_similarity(name1, name2):
    """
    Combine ordinary string similarity with
    token overlap.

    This helps with cases like:

      Rotonda del Brunelleschi
      Rotonda di Brunelleschi
    """

    a = normalize_text(name1)
    b = normalize_text(name2)

    if not a or not b:
        return 0.0

    sequence = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()

    tokens_a = meaningful_tokens(a)
    tokens_b = meaningful_tokens(b)

    if (
        tokens_a
        and tokens_b
    ):
        intersection = len(
            tokens_a & tokens_b
        )

        union = len(
            tokens_a | tokens_b
        )

        jaccard = (
            intersection / union
            if union
            else 0
        )
    else:
        jaccard = 0

    # Keep whichever signal is stronger.
    return max(
        sequence,
        jaccard,
    )


# --------------------------------------------------
# Coordinates
# --------------------------------------------------


def haversine_meters(
    lat1,
    lon1,
    lat2,
    lon2,
):
    radius = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    delta_phi = math.radians(
        lat2 - lat1
    )

    delta_lambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(delta_phi / 2) ** 2
        +
        math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return radius * c


def canonical_coordinates(church):
    resolved = church.get(
        "resolved_coordinates",
        {},
    )

    canonical = resolved.get(
        "canonical"
    )

    if not canonical:
        return None

    lat = canonical.get(
        "latitude"
    )

    lon = canonical.get(
        "longitude"
    )

    if (
        lat is None
        or lon is None
    ):
        return None

    return lat, lon


# --------------------------------------------------
# OSM identity
# --------------------------------------------------


def osm_keys(church):
    result = set()

    for match in church.get(
        "osm_matches",
        [],
    ):
        osm_type = match.get(
            "osm_type"
        )

        osm_id = match.get(
            "osm_id"
        )

        if (
            osm_type
            and osm_id is not None
        ):
            result.add(
                f"{osm_type}/{osm_id}"
            )

    return result


# --------------------------------------------------
# Location evidence
# --------------------------------------------------


def shared_location(church1, church2):
    locations1 = set(
        church1.get(
            "location_ids",
            [],
        )
    )

    locations2 = set(
        church2.get(
            "location_ids",
            [],
        )
    )

    return bool(
        locations1 & locations2
    )


# --------------------------------------------------
# Candidate detection
# --------------------------------------------------


def compare_pair(
    church1,
    church2,
):
    name1 = church1[
        "derived"
    ].get(
        "display_name"
    )

    name2 = church2[
        "derived"
    ].get(
        "display_name"
    )

    similarity = name_similarity(
        name1,
        name2,
    )

    reasons = []

    score = 0


    # ------------------------------------------
    # Same OSM object
    # ------------------------------------------

    shared_osm = (
        osm_keys(church1)
        &
        osm_keys(church2)
    )

    if shared_osm:
        score += 100

        reasons.append(
            {
                "shared_osm_objects":
                    sorted(shared_osm)
            }
        )


    # ------------------------------------------
    # Geographic distance
    # ------------------------------------------

    coords1 = canonical_coordinates(
        church1
    )

    coords2 = canonical_coordinates(
        church2
    )

    distance = None

    if coords1 and coords2:

        distance = haversine_meters(
            coords1[0],
            coords1[1],
            coords2[0],
            coords2[1],
        )

        if distance <= VERY_CLOSE_METERS:
            score += 40

            reasons.append(
                {
                    "distance_meters":
                        round(
                            distance,
                            2,
                        )
                }
            )

        elif distance <= CLOSE_METERS:
            score += 20

            reasons.append(
                {
                    "distance_meters":
                        round(
                            distance,
                            2,
                        )
                }
            )


    # ------------------------------------------
    # Name similarity
    # ------------------------------------------

    if (
        similarity
        >= VERY_HIGH_NAME_SIMILARITY
    ):
        score += 40

        reasons.append(
            {
                "name_similarity":
                    round(
                        similarity,
                        3,
                    )
            }
        )

    elif (
        similarity
        >= HIGH_NAME_SIMILARITY
    ):
        score += 25

        reasons.append(
            {
                "name_similarity":
                    round(
                        similarity,
                        3,
                    )
            }
        )


    # ------------------------------------------
    # Same P131 administrative location
    # ------------------------------------------

    same_location = shared_location(
        church1,
        church2,
    )

    if same_location:
        score += 10

        reasons.append(
            "shared_location_id"
        )


    # ------------------------------------------
    # Decide if this is worth review
    # ------------------------------------------

    candidate = False

    # Strongest possible signal.
    if shared_osm:
        candidate = True

    # Very close + moderately strong name.
    elif (
        distance is not None
        and distance <= VERY_CLOSE_METERS
        and similarity >= 0.75
    ):
        candidate = True

    # Nearby + almost identical name.
    elif (
        distance is not None
        and distance <= CLOSE_METERS
        and similarity
        >= VERY_HIGH_NAME_SIMILARITY
    ):
        candidate = True

    # Important for records missing coordinates:
    # almost identical name + same municipality.
    elif (
        same_location
        and similarity
        >= VERY_HIGH_NAME_SIMILARITY
    ):
        candidate = True


    if not candidate:
        return None


    if score >= 80:
        confidence = "high"

    elif score >= 55:
        confidence = "medium"

    else:
        confidence = "low"


    return {
        "qid_1":
            church1[
                "wikidata_id"
            ],

        "name_1":
            name1,

        "qid_2":
            church2[
                "wikidata_id"
            ],

        "name_2":
            name2,

        "name_similarity":
            round(
                similarity,
                3,
            ),

        "distance_meters":
            (
                round(
                    distance,
                    2,
                )
                if distance
                is not None
                else None
            ),

        "shared_location":
            same_location,

        "shared_osm_objects":
            sorted(shared_osm),

        "score":
            score,

        "confidence":
            confidence,

        "reasons":
            reasons,
    }


# --------------------------------------------------
# Detection
# --------------------------------------------------


def detect_duplicates(churches):
    candidates = []

    total = len(churches)

    for i in range(total):

        church1 = churches[i]

        for j in range(
            i + 1,
            total,
        ):
            church2 = churches[j]

            result = compare_pair(
                church1,
                church2,
            )

            if result:
                candidates.append(
                    result
                )

    candidates.sort(
        key=lambda item: (
            -item["score"],
            (
                item[
                    "distance_meters"
                ]
                if item[
                    "distance_meters"
                ]
                is not None
                else float("inf")
            ),
        )
    )

    return candidates


# --------------------------------------------------
# Attach results to records
# --------------------------------------------------


def attach_candidates(
    churches,
    candidates,
):
    by_qid = {}

    for candidate in candidates:

        qid1 = candidate[
            "qid_1"
        ]

        qid2 = candidate[
            "qid_2"
        ]

        by_qid.setdefault(
            qid1,
            [],
        ).append(
            {
                "wikidata_id": qid2,
                "name":
                    candidate[
                        "name_2"
                    ],
                "score":
                    candidate[
                        "score"
                    ],
                "confidence":
                    candidate[
                        "confidence"
                    ],
            }
        )

        by_qid.setdefault(
            qid2,
            [],
        ).append(
            {
                "wikidata_id": qid1,
                "name":
                    candidate[
                        "name_1"
                    ],
                "score":
                    candidate[
                        "score"
                    ],
                "confidence":
                    candidate[
                        "confidence"
                    ],
            }
        )


    for church in churches:

        qid = church[
            "wikidata_id"
        ]

        matches = by_qid.get(
            qid,
            [],
        )

        church[
            "duplicate_candidates"
        ] = matches

        church[
            "derived"
        ][
            "possible_duplicate"
        ] = bool(matches)

        church[
            "derived"
        ][
            "duplicate_review_required"
        ] = bool(matches)


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(
    churches,
    candidates,
):
    high = [
        item
        for item in candidates
        if item[
            "confidence"
        ] == "high"
    ]

    medium = [
        item
        for item in candidates
        if item[
            "confidence"
        ] == "medium"
    ]

    low = [
        item
        for item in candidates
        if item[
            "confidence"
        ] == "low"
    ]

    affected_qids = set()

    for item in candidates:
        affected_qids.add(
            item["qid_1"]
        )

        affected_qids.add(
            item["qid_2"]
        )

    return {
        "total_entities":
            len(churches),

        "candidate_pairs":
            len(candidates),

        "entities_flagged":
            len(affected_qids),

        "high_confidence_pairs":
            len(high),

        "medium_confidence_pairs":
            len(medium),

        "low_confidence_pairs":
            len(low),

        "candidate_records":
            candidates,
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run select_images.py first."
        )

    churches = load_json(
        INPUT_FILE
    )

    candidates = detect_duplicates(
        churches
    )

    attach_candidates(
        churches,
        candidates,
    )

    save_json(
        OUTPUT_FILE,
        churches,
    )

    report = build_report(
        churches,
        candidates,
    )

    save_json(
        REPORT_FILE,
        report,
    )

    print()
    print(
        "Duplicate detection complete"
    )

    print(
        "----------------------------"
    )

    print(
        "Entities:",
        report[
            "total_entities"
        ],
    )

    print(
        "Candidate pairs:",
        report[
            "candidate_pairs"
        ],
    )

    print(
        "Entities flagged:",
        report[
            "entities_flagged"
        ],
    )

    print(
        "High confidence:",
        report[
            "high_confidence_pairs"
        ],
    )

    print(
        "Medium confidence:",
        report[
            "medium_confidence_pairs"
        ],
    )

    print(
        "Low confidence:",
        report[
            "low_confidence_pairs"
        ],
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