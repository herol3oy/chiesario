import json
import time

import requests

from project_config import (
    CHURCHES_FILE,
    CLASSIFIED_FILE,
    TYPE_ENTITIES_CACHE_FILE,
    TYPE_REPORT_FILE,
)

INPUT_FILE = CHURCHES_FILE
OUTPUT_FILE = CLASSIFIED_FILE
TYPE_CACHE_FILE = TYPE_ENTITIES_CACHE_FILE
REPORT_FILE = TYPE_REPORT_FILE


API = "https://www.wikidata.org/w/api.php"

HEADERS = {
    "User-Agent": "ItalianChurchDirectory/0.1"
}

BATCH_SIZE = 50


# --------------------------------------------------
# Classification roots
# --------------------------------------------------
#
# Order matters.
#
# Example:
#
# baptistery -> chapel
# basilica   -> church building
#
# We want "baptistery", not "chapel",
# and "basilica", not generic "church".
#

TYPE_RULES = [
    ("baptistery", "Q210077"),
    ("sacristy", "Q468939"),
    ("oratory", "Q580499"),
    ("chapel", "Q108325"),
    ("cathedral", "Q2977"),
    ("basilica", "Q163687"),
    ("former_church", "Q19899465"),
    ("abbey", "Q160742"),
    ("monastery", "Q44613"),
    ("church", "Q16970"),
]


# What we currently want in the directory.
#
# This is policy, NOT source data.
#
# You can change this later without
# downloading Wikidata again.

PUBLISH_POLICY = {
    "church": True,
    "cathedral": True,
    "basilica": True,
    "former_church": True,

    "chapel": False,
    "oratory": False,
    "baptistery": False,
    "sacristy": False,
    "abbey": False,
    "monastery": False,

    "other": False,
}


# A selected specific type may coexist with these
# less-specific or compatible categories without
# creating genuine ambiguity. TYPE_RULES still
# determines which category wins.
COMPATIBLE_TYPE_CANDIDATES = {
    "baptistery": {
        "chapel",
        "church",
    },
    "sacristy": {
        "chapel",
        "church",
    },
    "oratory": {
        "chapel",
        "church",
    },
    "chapel": {
        "church",
    },
    "cathedral": {
        "basilica",
        "church",
    },
    "basilica": {
        "church",
    },
    "former_church": {
        "church",
    },
    "abbey": {
        "monastery",
        "church",
    },
    "monastery": {
        "church",
    },
    "church": set(),
}


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def entity_id_from_claim(claim):
    try:
        value = (
            claim["mainsnak"]
            ["datavalue"]
            ["value"]
        )

        if isinstance(value, dict):
            return value.get("id")

    except (KeyError, TypeError):
        pass

    return None


def get_parent_types(entity):
    """
    Return P279 ('subclass of') IDs.
    """

    parents = []

    claims = (
        entity
        .get("claims", {})
        .get("P279", [])
    )

    for claim in claims:
        qid = entity_id_from_claim(claim)

        if qid and qid not in parents:
            parents.append(qid)

    return parents


def get_label(entity):
    labels = entity.get("labels", {})

    # Prefer English for developer/debug output.
    for language in ("en", "it"):
        item = labels.get(language)

        if item and item.get("value"):
            return item["value"]

    return None


def load_cache():
    if not TYPE_CACHE_FILE.exists():
        return {}

    with TYPE_CACHE_FILE.open(
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_cache(cache):
    TYPE_CACHE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with TYPE_CACHE_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2,
        )


def fetch_entities(qids, cache):
    """
    Fetch Wikidata entities that aren't
    already in our local cache.
    """

    missing = [
        qid
        for qid in qids
        if qid not in cache
    ]

    if not missing:
        return

    for batch_number, batch in enumerate(
        chunks(missing, BATCH_SIZE),
        start=1,
    ):
        print(
            f"Fetching type batch "
            f"{batch_number}: "
            f"{len(batch)} entities"
        )

        response = requests.get(
            API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|claims",
                "languages": "en|it",
                "format": "json",
                "formatversion": 2,
            },
            headers=HEADERS,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        for qid, entity in (
            data.get("entities", {}).items()
        ):
            cache[qid] = entity

        save_cache(cache)

        time.sleep(0.2)


def collect_type_hierarchy(
    initial_qids,
    cache,
    max_depth=10,
):
    """
    Recursively fetch P279 parents.

    Example:

        minor basilica
             ↓
          basilica
             ↓
       church building

    We limit recursion just as a safety guard.
    """

    current = set(initial_qids)
    seen = set()

    depth = 0

    while current and depth < max_depth:
        depth += 1

        print(
            f"Hierarchy depth {depth}: "
            f"{len(current)} types"
        )

        fetch_entities(
            sorted(current),
            cache,
        )

        next_level = set()

        for qid in current:
            if qid in seen:
                continue

            seen.add(qid)

            entity = cache.get(qid, {})

            parents = get_parent_types(
                entity
            )

            for parent in parents:
                if parent not in seen:
                    next_level.add(parent)

        current = next_level

    return seen


def ancestor_closure(
    qid,
    cache,
    memo,
    visiting=None,
):
    """
    Return:
        qid + every class reachable through P279.
    """

    if qid in memo:
        return memo[qid]

    if visiting is None:
        visiting = set()

    # Guard against broken/cyclic ontology data.
    if qid in visiting:
        return {qid}

    visiting = set(visiting)
    visiting.add(qid)

    result = {qid}

    entity = cache.get(qid, {})

    for parent in get_parent_types(entity):
        result.update(
            ancestor_closure(
                parent,
                cache,
                memo,
                visiting,
            )
        )

    memo[qid] = result

    return result


def classify_types(
    type_qids,
    cache,
    memo,
):
    """
    Classify one church from its P31 values.

    Returns:
        directory_type
        all matched categories
    """

    all_ancestors = set()

    for type_qid in type_qids:
        all_ancestors.update(
            ancestor_closure(
                type_qid,
                cache,
                memo,
            )
        )

    matches = []

    for category, root_qid in TYPE_RULES:
        if root_qid in all_ancestors:
            matches.append(category)

    if not matches:
        return "other", []

    # TYPE_RULES is already ordered by priority.
    return matches[0], matches


def type_review_required(
    selected_type,
    candidates,
):
    if (
        selected_type == "other"
        or not candidates
    ):
        return True

    compatible = {
        selected_type,
        *COMPATIBLE_TYPE_CANDIDATES.get(
            selected_type,
            set(),
        ),
    }

    return any(
        candidate not in compatible
        for candidate in candidates
    )


def describe_types(
    type_qids,
    cache,
):
    result = []

    for qid in type_qids:
        entity = cache.get(qid, {})

        result.append(
            {
                "qid": qid,
                "label": get_label(entity),
            }
        )

    return result


def build_report(churches):
    counts = {}

    needs_review = []

    for church in churches:
        derived = church["derived"]

        category = (
            derived["directory_type"]
        )

        counts[category] = (
            counts.get(category, 0) + 1
        )

        if derived["type_review_required"]:
            needs_review.append(
                {
                    "wikidata_id":
                        church["wikidata_id"],

                    "name":
                        derived["display_name"],

                    "wikidata_types":
                        church[
                            "wikidata_type_details"
                        ],

                    "type_candidates":
                        derived[
                            "type_candidates"
                        ],

                    "selected_type":
                        category,
                }
            )

    return {
        "total": len(churches),
        "counts": dict(
            sorted(
                counts.items(),
                key=lambda x: (
                    -x[1],
                    x[0],
                ),
            )
        ),
        "type_review_required":
            len(needs_review),
        "review_records":
            needs_review,
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run normalize.py first."
        )

    with INPUT_FILE.open(
        encoding="utf-8"
    ) as f:
        churches = json.load(f)

    # ------------------------------------------
    # Gather every P31 type found in churches
    # ------------------------------------------

    initial_type_qids = set()

    for church in churches:
        for qid in church.get(
            "wikidata_types",
            [],
        ):
            initial_type_qids.add(qid)

    print(
        f"Found {len(initial_type_qids)} "
        f"unique P31 types"
    )

    # ------------------------------------------
    # Load / populate Wikidata type cache
    # ------------------------------------------

    cache = load_cache()

    collect_type_hierarchy(
        initial_type_qids,
        cache,
    )

    save_cache(cache)

    # ------------------------------------------
    # Classify
    # ------------------------------------------

    memo = {}

    for church in churches:
        type_qids = church.get(
            "wikidata_types",
            [],
        )

        category, candidates = (
            classify_types(
                type_qids,
                cache,
                memo,
            )
        )

        church[
            "wikidata_type_details"
        ] = describe_types(
            type_qids,
            cache,
        )

        church["derived"][
            "directory_type"
        ] = category

        church["derived"][
            "type_candidates"
        ] = candidates

        church["derived"][
            "type_review_required"
        ] = type_review_required(
            category,
            candidates,
        )

        church["derived"][
            "publishable_by_type"
        ] = PUBLISH_POLICY.get(
            category,
            False,
        )

        # Do NOT declare the whole record publishable
        # yet. Date/duplicate/etc. checks still exist.
        church["derived"][
            "publishable"
        ] = False

    # ------------------------------------------
    # Save classified dataset
    # ------------------------------------------

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

    report = build_report(
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
    print("Type classification complete")
    print("----------------------------")

    for category, count in (
        report["counts"].items()
    ):
        print(
            f"{category:20} {count}"
        )

    print()
    print(
        "Needs type review:",
        report["type_review_required"],
    )

    print()
    print(
        f"Written: {OUTPUT_FILE}"
    )
    print(
        f"Written: {REPORT_FILE}"
    )
    print(
        f"Cache:   {TYPE_CACHE_FILE}"
    )


if __name__ == "__main__":
    main()
