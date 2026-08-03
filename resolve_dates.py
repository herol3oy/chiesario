import json

from project_config import (
    DATE_REPORT_FILE,
    DATES_FILE,
    RESOLVED_FILE,
)

INPUT_FILE = RESOLVED_FILE
OUTPUT_FILE = DATES_FILE
REPORT_FILE = DATE_REPORT_FILE


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


def extract_year(time_value):
    if not time_value:
        return None

    try:
        date = time_value.split("T")[0]

        negative = date.startswith("-")

        date = date.lstrip("+-")

        year = int(
            date.split("-")[0]
        )

        return -year if negative else year

    except (ValueError, IndexError):
        return None


def ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {
            1: "st",
            2: "nd",
            3: "rd",
        }.get(
            number % 10,
            "th",
        )

    return f"{number}{suffix}"


def normalize_date_claim(claim):
    """
    Turn a Wikidata time claim into a period.

    Crucially:

    precision 9  -> exact year
    precision 8  -> decade
    precision 7  -> century
    precision 6  -> millennium
    """

    year = extract_year(
        claim.get("time")
    )

    precision = claim.get(
        "precision"
    )

    if year is None:
        return None

    # Year, month, day...
    if precision is not None and precision >= 9:
        return {
            "kind": "year",
            "start_year": year,
            "end_year": year,
            "display": str(year),
            "precision": precision,
            "statement_id":
                claim.get("statement_id"),
            "rank":
                claim.get("rank"),
        }

    # Decade
    if precision == 8:
        start = (
            year // 10
        ) * 10

        return {
            "kind": "decade",
            "start_year": start,
            "end_year": start + 9,
            "display": f"{start}s",
            "precision": precision,
            "statement_id":
                claim.get("statement_id"),
            "rank":
                claim.get("rank"),
        }

    # Century
    if precision == 7:
        start = (
            ((year - 1) // 100)
            * 100
            + 1
        )

        century = (
            ((start - 1) // 100)
            + 1
        )

        return {
            "kind": "century",
            "start_year": start,
            "end_year": start + 99,
            "display":
                f"{ordinal(century)} century",
            "precision": precision,
            "statement_id":
                claim.get("statement_id"),
            "rank":
                claim.get("rank"),
        }

    # Millennium
    if precision == 6:
        start = (
            ((year - 1) // 1000)
            * 1000
            + 1
        )

        millennium = (
            ((start - 1) // 1000)
            + 1
        )

        return {
            "kind": "millennium",
            "start_year": start,
            "end_year": start + 999,
            "display":
                f"{ordinal(millennium)} millennium",
            "precision": precision,
            "statement_id":
                claim.get("statement_id"),
            "rank":
                claim.get("rank"),
        }

    return {
        "kind": "unknown",
        "start_year": None,
        "end_year": None,
        "display": None,
        "precision": precision,
        "statement_id":
            claim.get("statement_id"),
        "rank":
            claim.get("rank"),
    }


def candidate_claims(church):
    claims = [
        claim
        for claim in church.get(
            "inception_claims",
            [],
        )
        if claim.get("rank")
        != "deprecated"
    ]

    preferred = [
        claim
        for claim in claims
        if claim.get("rank")
        == "preferred"
    ]

    if preferred:
        return preferred

    return claims


def resolve_date(church):
    raw_candidates = candidate_claims(
        church
    )

    candidates = []

    for claim in raw_candidates:
        normalized = (
            normalize_date_claim(
                claim
            )
        )

        if normalized:
            candidates.append(
                normalized
            )

    if not candidates:
        return {
            "canonical": None,
            "candidates": [],
            "review_required": True,
            "reason": "no_usable_date",
        }

    # Deduplicate equivalent periods.
    unique = {}

    for candidate in candidates:
        key = (
            candidate["kind"],
            candidate["start_year"],
            candidate["end_year"],
        )

        unique.setdefault(
            key,
            candidate,
        )

    unique_candidates = list(
        unique.values()
    )

    # Automatically resolve ONLY when all usable
    # statements mean the same period.
    if len(unique_candidates) == 1:
        return {
            "canonical":
                unique_candidates[0],

            "candidates":
                unique_candidates,

            "review_required":
                False,

            "reason":
                "unambiguous",
        }

    return {
        "canonical": None,
        "candidates":
            unique_candidates,

        "review_required":
            True,

        "reason":
            "multiple_competing_dates",
    }


def build_report(churches):
    unresolved = []
    resolved = []

    exact_year = 0
    century = 0
    decade = 0

    for church in churches:
        result = church[
            "resolved_date"
        ]

        canonical = result[
            "canonical"
        ]

        record = {
            "wikidata_id":
                church["wikidata_id"],

            "name":
                church["derived"][
                    "display_name"
                ],
        }

        if canonical:
            record["date"] = canonical

            resolved.append(record)

            if canonical["kind"] == "year":
                exact_year += 1

            elif canonical["kind"] == "century":
                century += 1

            elif canonical["kind"] == "decade":
                decade += 1

        else:
            record["reason"] = (
                result["reason"]
            )

            record["candidates"] = (
                result["candidates"]
            )

            unresolved.append(
                record
            )

    return {
        "total": len(churches),

        "resolved":
            len(resolved),

        "review_required":
            len(unresolved),

        "resolved_exact_year":
            exact_year,

        "resolved_century":
            century,

        "resolved_decade":
            decade,

        "review_records":
            unresolved,
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run resolve_coordinates.py first."
        )

    churches = load_json(
        INPUT_FILE
    )

    for church in churches:
        result = resolve_date(
            church
        )

        church[
            "resolved_date"
        ] = result

        canonical = result[
            "canonical"
        ]

        derived = church[
            "derived"
        ]

        derived[
            "date_review_required"
        ] = result[
            "review_required"
        ]

        if canonical:
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

        else:
            derived[
                "canonical_date_display"
            ] = None

            derived[
                "canonical_date_start_year"
            ] = None

            derived[
                "canonical_date_end_year"
            ] = None

            derived[
                "canonical_date_kind"
            ] = None

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
    print("Date resolution complete")
    print("------------------------")

    print(
        "Total:",
        report["total"],
    )

    print(
        "Resolved:",
        report["resolved"],
    )

    print(
        "Need review:",
        report["review_required"],
    )

    print(
        "Exact years:",
        report[
            "resolved_exact_year"
        ],
    )

    print(
        "Century dates:",
        report[
            "resolved_century"
        ],
    )

    print(
        "Decade dates:",
        report[
            "resolved_decade"
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
