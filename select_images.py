import json
import re
import unicodedata
from pathlib import Path


INPUT_FILE = Path(
    "data/processed/churches_commons.json"
)

OUTPUT_FILE = Path(
    "data/processed/churches_images.json"
)

REPORT_FILE = Path(
    "data/processed/image_report.json"
)


# --------------------------------------------------
# Policy
# --------------------------------------------------

AUTO_LICENSES = {
    "CC BY-SA 4.0",
    "CC BY-SA 3.0",
    "CC BY 4.0",
    "CC BY 3.0",
    "CC BY 2.5",
    "CC BY 2.0",
    "Public domain",
}


POSITIVE_TERMS = {
    "facade": 5,
    "facciata": 5,
    "exterior": 5,
    "esterno": 5,

    "church": 2,
    "chiesa": 2,
    "basilica": 2,
    "cathedral": 2,
    "cattedrale": 2,
    "pieve": 2,

    "interior": 1,
    "interno": 1,
}


NEGATIVE_TERMS = {
    "painting": -10,
    "dipinto": -10,

    "altarpiece": -10,
    "pala": -8,

    "portrait": -10,
    "ritratto": -10,

    "manuscript": -10,
    "manoscritto": -10,

    "floor plan": -10,
    "planimetria": -10,
    "pianta": -8,

    "drawing": -8,
    "disegno": -8,

    "map": -8,
    "mappa": -8,

    "sculpture": -7,
    "scultura": -7,
    "statue": -7,
    "statua": -7,

    "fresco": -5,
    "affresco": -5,

    "altar": -4,
    "altare": -4,
}


NAME_STOPWORDS = {
    "chiesa",
    "basilica",
    "cattedrale",
    "duomo",
    "pieve",
    "cappella",
    "santa",
    "santo",
    "san",
    "dei",
    "degli",
    "delle",
    "della",
    "del",
    "di",
    "da",
    "in",
    "a",
    "al",
    "alla",
    "the",
    "church",
    "of",
}


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
# Text
# --------------------------------------------------


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
        r"[_\-]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def church_name_tokens(church):
    name = church[
        "derived"
    ].get(
        "display_name"
    )

    text = normalize_text(name)

    tokens = {
        token
        for token in re.findall(
            r"[a-z0-9]+",
            text,
        )
        if (
            len(token) >= 4
            and token not in NAME_STOPWORDS
        )
    }

    return tokens


def image_text(image):
    commons = image.get(
        "commons"
    ) or {}

    parts = [
        image.get("filename"),
        (
            commons
            .get("description", {})
            .get("text")
        ),
    ]

    return normalize_text(
        " ".join(
            part
            for part in parts
            if part
        )
    )


# --------------------------------------------------
# Scoring
# --------------------------------------------------


def score_keywords(text):
    score = 0

    positive_matches = []
    negative_matches = []

    for term, points in (
        POSITIVE_TERMS.items()
    ):
        if term in text:
            score += points
            positive_matches.append(
                term
            )

    for term, points in (
        NEGATIVE_TERMS.items()
    ):
        if term in text:
            score += points
            negative_matches.append(
                term
            )

    return (
        score,
        positive_matches,
        negative_matches,
    )


def score_name_match(
    church,
    text,
):
    tokens = church_name_tokens(
        church
    )

    if not tokens:
        return 0, []

    matched = [
        token
        for token in tokens
        if token in text
    ]

    # Name overlap is useful evidence
    # that the image actually belongs
    # to this building.
    score = min(
        len(matched) * 2,
        6,
    )

    return score, matched


def image_orientation_bonus(
    image,
):
    """
    Tiny preference for landscape/square images.

    This is intentionally weak:
    content relevance matters much more.
    """

    commons = image.get(
        "commons"
    ) or {}

    width = commons.get(
        "width"
    )

    height = commons.get(
        "height"
    )

    if (
        not width
        or not height
    ):
        return 0

    if width >= height:
        return 1

    return 0


def license_info(image):
    commons = image.get(
        "commons"
    ) or {}

    license_data = commons.get(
        "license",
        {},
    )

    name = license_data.get(
        "name"
    )

    return {
        "name": name,
        "auto_approved":
            name in AUTO_LICENSES,
    }


def score_image(
    church,
    image,
):
    commons = image.get(
        "commons"
    )

    if (
        not commons
        or commons.get("missing")
    ):
        return {
            "score": -100,
            "confidence": "reject",
            "license_ok": False,
            "reasons": [
                "commons_file_missing"
            ],
        }

    text = image_text(
        image
    )

    (
        keyword_score,
        positive,
        negative,
    ) = score_keywords(
        text
    )

    (
        name_score,
        matched_name_tokens,
    ) = score_name_match(
        church,
        text,
    )

    orientation_score = (
        image_orientation_bonus(
            image
        )
    )

    license_data = license_info(
        image
    )

    score = (
        keyword_score
        + name_score
        + orientation_score
    )

    reasons = []

    if positive:
        reasons.append(
            {
                "positive_terms":
                    positive,
            }
        )

    if negative:
        reasons.append(
            {
                "negative_terms":
                    negative,
            }
        )

    if matched_name_tokens:
        reasons.append(
            {
                "name_tokens":
                    matched_name_tokens,
            }
        )

    if orientation_score:
        reasons.append(
            "landscape_or_square"
        )

    if not license_data[
        "auto_approved"
    ]:
        reasons.append(
            "license_requires_review"
        )

    # Negative visual-category terms
    # should make auto-selection difficult.
    if negative:
        confidence = "low"

    elif (
        score >= 6
        and license_data[
            "auto_approved"
        ]
    ):
        confidence = "high"

    elif score >= 2:
        confidence = "medium"

    else:
        confidence = "low"

    return {
        "score": score,
        "confidence": confidence,

        "license":
            license_data["name"],

        "license_ok":
            license_data[
                "auto_approved"
            ],

        "reasons": reasons,
    }


# --------------------------------------------------
# Church selection
# --------------------------------------------------


def select_for_church(
    church,
):
    images = church.get(
        "images",
        [],
    )

    scored = []

    for image in images:

        selection = score_image(
            church,
            image,
        )

        image[
            "selection"
        ] = selection

        scored.append(
            image
        )

    scored.sort(
        key=lambda image:
            image[
                "selection"
            ][
                "score"
            ],
        reverse=True,
    )

    if not scored:
        return {
            "hero_image": None,
            "review_required": True,
            "reason": "no_images",
        }

    best = scored[0]

    best_result = best[
        "selection"
    ]

    # Only automatically choose a hero
    # when confidence is genuinely high.
    if (
        best_result[
            "confidence"
        ] == "high"
        and best_result[
            "license_ok"
        ]
    ):
        return {
            "hero_image": {
                "filename":
                    best.get(
                        "filename"
                    ),

                "url":
                    best[
                        "commons"
                    ].get(
                        "url"
                    ),

                "thumbnail_url":
                    best[
                        "commons"
                    ].get(
                        "thumbnail_url"
                    ),

                "description_url":
                    best[
                        "commons"
                    ].get(
                        "description_url"
                    ),

                "license":
                    best[
                        "commons"
                    ].get(
                        "license"
                    ),

                "artist":
                    best[
                        "commons"
                    ].get(
                        "artist"
                    ),

                "score":
                    best_result[
                        "score"
                    ],
            },

            "review_required": False,
            "reason":
                "high_confidence",
        }

    return {
        "hero_image": None,

        "best_candidate": {
            "filename":
                best.get(
                    "filename"
                ),

            "score":
                best_result[
                    "score"
                ],

            "confidence":
                best_result[
                    "confidence"
                ],

            "reasons":
                best_result[
                    "reasons"
                ],
        },

        "review_required": True,

        "reason":
            "no_high_confidence_image",
    }


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(churches):
    auto_selected = []
    review = []
    no_images = []

    for church in churches:

        result = church[
            "image_selection"
        ]

        record = {
            "wikidata_id":
                church[
                    "wikidata_id"
                ],

            "name":
                church[
                    "derived"
                ][
                    "display_name"
                ],
        }

        if result[
            "hero_image"
        ]:
            record[
                "hero_image"
            ] = result[
                "hero_image"
            ][
                "filename"
            ]

            auto_selected.append(
                record
            )

        else:
            record["reason"] = (
                result["reason"]
            )

            record[
                "best_candidate"
            ] = result.get(
                "best_candidate"
            )

            review.append(
                record
            )

            if (
                result["reason"]
                == "no_images"
            ):
                no_images.append(
                    record
                )

    return {
        "total":
            len(churches),

        "hero_images_auto_selected":
            len(
                auto_selected
            ),

        "image_review_required":
            len(review),

        "no_images":
            len(no_images),

        "auto_selected_records":
            auto_selected,

        "review_records":
            review,
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run enrich_commons.py first."
        )

    churches = load_json(
        INPUT_FILE
    )

    for church in churches:

        result = select_for_church(
            church
        )

        church[
            "image_selection"
        ] = result

        derived = church[
            "derived"
        ]

        derived[
            "has_hero_image"
        ] = bool(
            result[
                "hero_image"
            ]
        )

        derived[
            "image_review_required"
        ] = result[
            "review_required"
        ]

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
        "Image selection complete"
    )

    print(
        "------------------------"
    )

    print(
        "Churches:",
        report[
            "total"
        ],
    )

    print(
        "Hero images auto-selected:",
        report[
            "hero_images_auto_selected"
        ],
    )

    print(
        "Need image review:",
        report[
            "image_review_required"
        ],
    )

    print(
        "No images:",
        report[
            "no_images"
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