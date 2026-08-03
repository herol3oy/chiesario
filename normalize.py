import json
from pathlib import Path
from urllib.parse import quote


INPUT_FILE = Path("data/raw/tuscany_entities.json")
OUTPUT_FILE = Path("data/processed/churches.json")
REPORT_FILE = Path("data/processed/quality_report.json")


PRECISION_NAMES = {
    0: "billion_years",
    1: "hundred_million_years",
    2: "ten_million_years",
    3: "million_years",
    4: "hundred_thousand_years",
    5: "ten_thousand_years",
    6: "millennium",
    7: "century",
    8: "decade",
    9: "year",
    10: "month",
    11: "day",
    12: "hour",
    13: "minute",
    14: "second",
}


def get_label(entity, language):
    labels = entity.get("labels", {})
    item = labels.get(language)

    if not item:
        return None

    return item.get("value")


def get_aliases(entity, language):
    aliases = entity.get("aliases", {}).get(language, [])

    return [
        item["value"]
        for item in aliases
        if item.get("value")
    ]


def get_description(entity, language):
    descriptions = entity.get("descriptions", {})
    item = descriptions.get(language)

    if not item:
        return None

    return item.get("value")


def get_claims(entity, property_id):
    return entity.get("claims", {}).get(property_id, [])


def entity_id_from_claim(claim):
    try:
        value = claim["mainsnak"]["datavalue"]["value"]

        if isinstance(value, dict):
            return value.get("id")

    except (KeyError, TypeError):
        pass

    return None


def string_from_claim(claim):
    try:
        value = claim["mainsnak"]["datavalue"]["value"]

        if isinstance(value, str):
            return value

    except (KeyError, TypeError):
        pass

    return None


def parse_entity_ids(entity, property_id):
    result = []

    for claim in get_claims(entity, property_id):
        value = entity_id_from_claim(claim)

        if value and value not in result:
            result.append(value)

    return result


def parse_strings(entity, property_id):
    result = []

    for claim in get_claims(entity, property_id):
        value = string_from_claim(claim)

        if value and value not in result:
            result.append(value)

    return result


def parse_coordinates(entity):
    result = []

    for claim in get_claims(entity, "P625"):
        try:
            value = claim["mainsnak"]["datavalue"]["value"]

            coordinate = {
                "latitude": value.get("latitude"),
                "longitude": value.get("longitude"),
                "precision": value.get("precision"),
                "globe": value.get("globe"),
                "rank": claim.get("rank"),
                "statement_id": claim.get("id"),
            }

            if (
                coordinate["latitude"] is not None
                and coordinate["longitude"] is not None
            ):
                result.append(coordinate)

        except (KeyError, TypeError):
            continue

    return result


def parse_time_claim(claim):
    try:
        value = claim["mainsnak"]["datavalue"]["value"]

        if not isinstance(value, dict):
            return None

        precision = value.get("precision")

        return {
            "statement_id": claim.get("id"),
            "time": value.get("time"),
            "precision": precision,
            "precision_name": PRECISION_NAMES.get(
                precision,
                "unknown",
            ),
            "before": value.get("before"),
            "after": value.get("after"),
            "timezone": value.get("timezone"),
            "calendar_model": value.get("calendarmodel"),
            "rank": claim.get("rank"),
            "qualifiers": claim.get("qualifiers", {}),
            "references": claim.get("references", []),
        }

    except (KeyError, TypeError):
        return None


def parse_inception_claims(entity):
    result = []

    for claim in get_claims(entity, "P571"):
        parsed = parse_time_claim(claim)

        if parsed:
            result.append(parsed)

    return result


def year_from_wikidata_time(time_value):
    """
    Examples:

    +1458-01-01T00:00:00Z -> 1458
    +1401-01-01T00:00:00Z -> 1401

    This only extracts the numeric value.
    It DOES NOT mean that 1401 is necessarily
    an exact year. Precision must be checked separately.
    """

    if not time_value:
        return None

    try:
        date_part = time_value.split("T")[0]

        if date_part.startswith("+"):
            date_part = date_part[1:]

        if date_part.startswith("-"):
            # BCE dates are irrelevant for our current
            # church dataset, but avoid crashing.
            year_part = date_part[1:].split("-")[0]
            return -int(year_part)

        year_part = date_part.split("-")[0]

        return int(year_part)

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
        }.get(number % 10, "th")

    return f"{number}{suffix}"


def format_time_claim(claim):
    """
    Convert a Wikidata time claim into something
    safe for display without inventing precision.
    """

    year = year_from_wikidata_time(
        claim.get("time")
    )

    precision = claim.get("precision")

    if year is None:
        return None

    # Exact year or more precise
    if precision is not None and precision >= 9:
        return str(year)

    # Decade
    if precision == 8:
        decade = (year // 10) * 10
        return f"{decade}s"

    # Century
    if precision == 7:
        century = ((year - 1) // 100) + 1
        return f"{ordinal(century)} century"

    # Millennium
    if precision == 6:
        millennium = ((year - 1) // 1000) + 1
        return f"{ordinal(millennium)} millennium"

    return None


def choose_display_date(inception_claims):
    """
    IMPORTANT:

    We only automatically choose a display date
    when Wikidata gives us an unambiguous result.

    Multiple different dates => manual/enrichment review.
    """

    usable = [
        claim
        for claim in inception_claims
        if claim.get("rank") != "deprecated"
    ]

    if not usable:
        return None, True

    # Prefer Wikidata preferred-rank statements
    preferred = [
        claim
        for claim in usable
        if claim.get("rank") == "preferred"
    ]

    if preferred:
        usable = preferred

    formatted = [
        format_time_claim(claim)
        for claim in usable
    ]

    formatted = [
        value
        for value in formatted
        if value is not None
    ]

    unique_values = list(dict.fromkeys(formatted))

    # One unambiguous interpretation
    if len(unique_values) == 1:
        return unique_values[0], False

    # Multiple competing dates
    return None, True


def commons_url(filename):
    if not filename:
        return None

    filename = filename.replace(" ", "_")

    return (
        "https://commons.wikimedia.org/wiki/"
        "Special:FilePath/"
        + quote(filename, safe="")
    )


def parse_images(entity):
    result = []

    for claim in get_claims(entity, "P18"):
        filename = string_from_claim(claim)

        if not filename:
            continue

        result.append(
            {
                "filename": filename,
                "url": commons_url(filename),
                "rank": claim.get("rank"),
                "statement_id": claim.get("id"),
                "relevance": "unknown",
            }
        )

    return result


def normalize_entity(qid, entity):
    inception_claims = parse_inception_claims(
        entity
    )

    display_date, date_review_required = (
        choose_display_date(inception_claims)
    )

    coordinates = parse_coordinates(entity)

    images = parse_images(entity)

    p31_types = parse_entity_ids(
        entity,
        "P31",
    )

    locations = parse_entity_ids(
        entity,
        "P131",
    )

    websites = parse_strings(
        entity,
        "P856",
    )

    label_it = get_label(
        entity,
        "it",
    )

    label_en = get_label(
        entity,
        "en",
    )

    display_name = (
        label_it
        or label_en
        or qid
    )

    imprecise_dates = [
        claim
        for claim in inception_claims
        if (
            claim.get("precision") is not None
            and claim["precision"] < 9
        )
    ]

    non_deprecated_dates = [
        claim
        for claim in inception_claims
        if claim.get("rank") != "deprecated"
    ]

    return {
        "wikidata_id": qid,

        "names": {
            "it": label_it,
            "en": label_en,
            "aliases_it": get_aliases(
                entity,
                "it",
            ),
            "aliases_en": get_aliases(
                entity,
                "en",
            ),
        },

        "descriptions": {
            "it": get_description(
                entity,
                "it",
            ),
            "en": get_description(
                entity,
                "en",
            ),
        },

        # Raw Wikidata entity-type IDs.
        # Do NOT classify them yet.
        "wikidata_types": p31_types,

        # Raw administrative-location IDs.
        "location_ids": locations,

        "coordinates": coordinates,

        # Keep ALL inception statements.
        "inception_claims": inception_claims,

        "images": images,

        "websites": websites,

        "derived": {
            "display_name": display_name,

            # Only populated when date is
            # sufficiently unambiguous.
            "display_date": display_date,

            "date_review_required":
                date_review_required,

            "has_coordinates":
                len(coordinates) > 0,

            "has_images":
                len(images) > 0,

            "multiple_inception_claims":
                len(non_deprecated_dates) > 1,

            "has_imprecise_date":
                len(imprecise_dates) > 0,

            # We classify church/chapel/etc later.
            "directory_type": None,

            "type_review_required": True,

            "possible_duplicate": False,

            "publishable": False,
        },
    }


def build_quality_report(churches):
    total = len(churches)

    return {
        "total_entities": total,

        "missing_coordinates": sum(
            1
            for church in churches
            if not church["derived"][
                "has_coordinates"
            ]
        ),

        "missing_images": sum(
            1
            for church in churches
            if not church["derived"][
                "has_images"
            ]
        ),

        "multiple_inception_claims": sum(
            1
            for church in churches
            if church["derived"][
                "multiple_inception_claims"
            ]
        ),

        "imprecise_dates": sum(
            1
            for church in churches
            if church["derived"][
                "has_imprecise_date"
            ]
        ),

        "date_review_required": sum(
            1
            for church in churches
            if church["derived"][
                "date_review_required"
            ]
        ),

        "missing_italian_name": sum(
            1
            for church in churches
            if not church["names"]["it"]
        ),

        "missing_inception": sum(
            1
            for church in churches
            if not church[
                "inception_claims"
            ]
        ),

        "multiple_types": sum(
            1
            for church in churches
            if len(
                church["wikidata_types"]
            ) > 1
        ),
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} does not exist.\n"
            "Run fetch_entities.py first."
        )

    with INPUT_FILE.open(
        encoding="utf-8"
    ) as f:
        entities = json.load(f)

    churches = []

    for qid, entity in entities.items():

        if entity.get("missing"):
            continue

        church = normalize_entity(
            qid,
            entity,
        )

        churches.append(church)

    churches.sort(
        key=lambda church: (
            church["derived"]["display_name"]
            or ""
        ).lower()
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            churches,
            f,
            ensure_ascii=False,
            indent=2,
        )

    report = build_quality_report(
        churches
    )

    with REPORT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("Normalization complete")
    print("----------------------")
    print(
        f"Entities: {report['total_entities']}"
    )
    print(
        "Missing coordinates:",
        report["missing_coordinates"],
    )
    print(
        "Missing images:",
        report["missing_images"],
    )
    print(
        "Multiple inception claims:",
        report["multiple_inception_claims"],
    )
    print(
        "Imprecise dates:",
        report["imprecise_dates"],
    )
    print(
        "Date review required:",
        report["date_review_required"],
    )
    print(
        "Missing Italian names:",
        report["missing_italian_name"],
    )
    print()
    print(f"Written: {OUTPUT_FILE}")
    print(f"Written: {REPORT_FILE}")


if __name__ == "__main__":
    main()