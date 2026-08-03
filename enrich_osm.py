import json
import re
import time
from pathlib import Path

import requests


INPUT_FILE = Path(
    "data/processed/churches_classified.json"
)

CACHE_FILE = Path(
    "data/raw/osm_by_qid.json"
)

OUTPUT_FILE = Path(
    "data/processed/churches_osm.json"
)

REPORT_FILE = Path(
    "data/processed/osm_report.json"
)


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


HEADERS = {
    "User-Agent": (
        "ItalianChurchDirectory/0.1 "
        "(historic church research project)"
    )
}


BATCH_SIZE = 40

MAX_RETRIES = 6


# --------------------------------------------------
# General helpers
# --------------------------------------------------


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_json(path, default):
    if not path.exists():
        return default

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
# Overpass query
# --------------------------------------------------


def validate_qids(qids):
    for qid in qids:
        if not re.fullmatch(r"Q\d+", qid):
            raise ValueError(
                f"Invalid Wikidata QID: {qid}"
            )


def build_query(qids):
    """
    Query globally by Wikidata tag.

    We deliberately do NOT restrict by Tuscany.

    Wikidata IDs are globally unique, so the
    geographic restriction only adds unnecessary
    work for Overpass.
    """

    validate_qids(qids)

    pattern = "|".join(qids)

    return f"""
[out:json][timeout:30];

nwr["wikidata"~"^({pattern})$"];

out center tags;
"""


def request_overpass(
    session,
    endpoint,
    query,
):
    return session.post(
        endpoint,
        data={
            "data": query,
        },
        headers=HEADERS,
        timeout=60,
    )


def fetch_batch(
    session,
    qids,
):
    query = build_query(qids)

    last_error = None

    for attempt in range(MAX_RETRIES):

        endpoint = OVERPASS_ENDPOINTS[
            attempt
            % len(OVERPASS_ENDPOINTS)
        ]

        print(
            f"  endpoint: {endpoint}"
        )

        try:
            response = request_overpass(
                session,
                endpoint,
                query,
            )

            if response.status_code == 200:
                return response.json()

            if response.status_code in (
                429,
                502,
                503,
                504,
            ):
                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                if retry_after:
                    try:
                        delay = float(
                            retry_after
                        )
                    except ValueError:
                        delay = None
                else:
                    delay = None

                if delay is None:
                    delay = min(
                        5 * (2 ** attempt),
                        60,
                    )

                print(
                    f"  HTTP "
                    f"{response.status_code}; "
                    f"retrying after "
                    f"{delay:.0f}s"
                )

                last_error = (
                    requests.HTTPError(
                        f"{response.status_code} "
                        f"from {endpoint}"
                    )
                )

                time.sleep(delay)

                continue

            response.raise_for_status()

        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
        ) as exc:

            last_error = exc

            delay = min(
                5 * (2 ** attempt),
                60,
            )

            print(
                f"  request failed: {exc}"
            )

            print(
                f"  retrying after "
                f"{delay}s"
            )

            time.sleep(delay)

    raise RuntimeError(
        "All Overpass retries failed"
    ) from last_error


# --------------------------------------------------
# OSM normalization
# --------------------------------------------------


def get_coordinates(element):
    if element.get("type") == "node":

        lat = element.get("lat")
        lon = element.get("lon")

        if (
            lat is not None
            and lon is not None
        ):
            return {
                "latitude": lat,
                "longitude": lon,
                "source": "node",
            }

    center = element.get("center")

    if center:

        lat = center.get("lat")
        lon = center.get("lon")

        if (
            lat is not None
            and lon is not None
        ):
            return {
                "latitude": lat,
                "longitude": lon,
                "source": "center",
            }

    return None


def osm_url(element):
    osm_type = element.get("type")
    osm_id = element.get("id")

    if (
        not osm_type
        or osm_id is None
    ):
        return None

    return (
        "https://www.openstreetmap.org/"
        f"{osm_type}/{osm_id}"
    )


def extract_address(tags):
    mapping = {
        "street": "addr:street",
        "housenumber": "addr:housenumber",
        "postcode": "addr:postcode",
        "city": "addr:city",
        "place": "addr:place",
        "province": "addr:province",
        "country": "addr:country",
    }

    result = {}

    for output_key, osm_key in (
        mapping.items()
    ):
        value = tags.get(osm_key)

        if value:
            result[output_key] = value

    return result


def normalize_osm_element(element):
    tags = element.get(
        "tags",
        {},
    )

    return {
        "osm_type":
            element.get("type"),

        "osm_id":
            element.get("id"),

        "osm_url":
            osm_url(element),

        "wikidata_id":
            tags.get("wikidata"),

        "coordinates":
            get_coordinates(element),

        "name":
            tags.get("name"),

        "name_it":
            tags.get("name:it"),

        "building":
            tags.get("building"),

        "amenity":
            tags.get("amenity"),

        "religion":
            tags.get("religion"),

        "denomination":
            tags.get("denomination"),

        "historic":
            tags.get("historic"),

        "start_date":
            tags.get("start_date"),

        "website": (
            tags.get("website")
            or tags.get(
                "contact:website"
            )
        ),

        "phone": (
            tags.get("phone")
            or tags.get(
                "contact:phone"
            )
        ),

        "wikipedia":
            tags.get("wikipedia"),

        "wikimedia_commons":
            tags.get(
                "wikimedia_commons"
            ),

        "address":
            extract_address(tags),

        # Preserve everything.
        "tags": tags,
    }


# --------------------------------------------------
# Fetch + cache
# --------------------------------------------------


def fetch_osm(churches):
    cache = load_json(
        CACHE_FILE,
        {},
    )

    all_qids = [
        church["wikidata_id"]
        for church in churches
    ]

    # Don't request IDs already successfully
    # searched on a previous run.
    missing_qids = [
        qid
        for qid in all_qids
        if qid not in cache
    ]

    print(
        f"Total churches: "
        f"{len(all_qids)}"
    )

    print(
        f"Already cached: "
        f"{len(all_qids) - len(missing_qids)}"
    )

    print(
        f"Need OSM lookup: "
        f"{len(missing_qids)}"
    )

    if not missing_qids:
        return cache

    batches = list(
        chunks(
            missing_qids,
            BATCH_SIZE,
        )
    )

    session = requests.Session()

    for batch_number, batch in enumerate(
        batches,
        start=1,
    ):
        print()
        print(
            f"OSM batch "
            f"{batch_number}/"
            f"{len(batches)} "
            f"({len(batch)} QIDs)"
        )

        data = fetch_batch(
            session,
            batch,
        )

        # Initialize every searched QID.
        #
        # This is important:
        # [] means "we searched and found none".
        for qid in batch:
            cache[qid] = []

        elements = data.get(
            "elements",
            [],
        )

        print(
            f"  -> {len(elements)} "
            "OSM elements"
        )

        for element in elements:

            normalized = (
                normalize_osm_element(
                    element
                )
            )

            qid = normalized.get(
                "wikidata_id"
            )

            if qid in cache:
                cache[qid].append(
                    normalized
                )

        # Save immediately.
        #
        # If the script crashes later,
        # successful batches remain cached.
        save_json(
            CACHE_FILE,
            cache,
        )

        time.sleep(2)

    return cache


# --------------------------------------------------
# Attach OSM data
# --------------------------------------------------


def attach_osm(
    churches,
    cache,
):
    for church in churches:

        qid = church[
            "wikidata_id"
        ]

        matches = cache.get(
            qid,
            [],
        )

        church[
            "osm_matches"
        ] = matches

        match_count = len(
            matches
        )

        if match_count == 0:
            status = "none"

        elif match_count == 1:
            status = "single"

        else:
            status = "multiple"

        derived = church[
            "derived"
        ]

        derived[
            "osm_match_status"
        ] = status

        derived[
            "osm_match_count"
        ] = match_count

        derived[
            "osm_review_required"
        ] = match_count > 1

        derived[
            "has_osm_coordinates"
        ] = any(
            item.get(
                "coordinates"
            )
            for item in matches
        )

        derived[
            "has_osm_address"
        ] = any(
            item.get(
                "address"
            )
            for item in matches
        )

        derived[
            "has_osm_website"
        ] = any(
            item.get(
                "website"
            )
            for item in matches
        )


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(churches):
    no_match = []

    multiple_matches = []

    for church in churches:

        matches = church.get(
            "osm_matches",
            [],
        )

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

            "match_count":
                len(matches),
        }

        if len(matches) == 0:
            no_match.append(
                record
            )

        elif len(matches) > 1:

            record["matches"] = [
                {
                    "osm_type":
                        match[
                            "osm_type"
                        ],

                    "osm_id":
                        match[
                            "osm_id"
                        ],

                    "osm_url":
                        match[
                            "osm_url"
                        ],

                    "name":
                        match[
                            "name"
                        ],
                }
                for match in matches
            ]

            multiple_matches.append(
                record
            )

    return {
        "total":
            len(churches),

        "single_exact_match":
            sum(
                1
                for c in churches
                if len(
                    c.get(
                        "osm_matches",
                        [],
                    )
                ) == 1
            ),

        "multiple_exact_matches":
            len(
                multiple_matches
            ),

        "no_exact_match":
            len(no_match),

        "with_osm_coordinates":
            sum(
                1
                for c in churches
                if c[
                    "derived"
                ].get(
                    "has_osm_coordinates"
                )
            ),

        "with_osm_address":
            sum(
                1
                for c in churches
                if c[
                    "derived"
                ].get(
                    "has_osm_address"
                )
            ),

        "with_osm_website":
            sum(
                1
                for c in churches
                if c[
                    "derived"
                ].get(
                    "has_osm_website"
                )
            ),

        "no_match_records":
            no_match,

        "multiple_match_records":
            multiple_matches,
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found"
        )

    churches = load_json(
        INPUT_FILE,
        [],
    )

    cache = fetch_osm(
        churches
    )

    attach_osm(
        churches,
        cache,
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
        "OSM enrichment complete"
    )
    print(
        "-----------------------"
    )

    print(
        "Total:",
        report["total"],
    )

    print(
        "Single exact matches:",
        report[
            "single_exact_match"
        ],
    )

    print(
        "Multiple exact matches:",
        report[
            "multiple_exact_matches"
        ],
    )

    print(
        "No exact match:",
        report[
            "no_exact_match"
        ],
    )

    print(
        "With OSM coordinates:",
        report[
            "with_osm_coordinates"
        ],
    )

    print(
        "With OSM address:",
        report[
            "with_osm_address"
        ],
    )

    print(
        "With OSM website:",
        report[
            "with_osm_website"
        ],
    )

    print()
    print(
        f"Cache:  {CACHE_FILE}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print(
        f"Report: {REPORT_FILE}"
    )


if __name__ == "__main__":
    main()