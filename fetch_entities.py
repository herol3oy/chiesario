import argparse
import json
import random
import time

import requests

from project_config import (
    ENTITIES_FILE,
    QIDS_FILE,
    ensure_directories,
)


API = "https://www.wikidata.org/w/api.php"
BATCH_SIZE = 50
MAX_RETRIES = 6

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

HEADERS = {
    "User-Agent": "ItalianChurchDirectory/0.1"
}


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def save_entities(entities):
    with ENTITIES_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            entities,
            f,
            ensure_ascii=False,
            indent=2,
        )


def load_existing_entities(resume):
    if not resume or not ENTITIES_FILE.exists():
        return {}

    with ENTITIES_FILE.open(
        encoding="utf-8",
    ) as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        raise RuntimeError(
            f"{ENTITIES_FILE} must contain an object"
        )

    return loaded


def fetch_batch(batch):
    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            response = requests.get(
                API,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": (
                        "labels|descriptions|aliases|"
                        "claims|sitelinks"
                    ),
                    "languages": "it|en",
                    "format": "json",
                    "formatversion": 2,
                },
                headers=HEADERS,
                timeout=60,
            )

            if (
                response.status_code
                in RETRYABLE_STATUS_CODES
            ):
                if attempt == MAX_RETRIES:
                    response.raise_for_status()

                retry_after = response.headers.get(
                    "Retry-After"
                )

                if (
                    retry_after
                    and retry_after.isdigit()
                ):
                    delay = float(retry_after)
                else:
                    delay = min(
                        60,
                        2 ** attempt,
                    )
                    delay += random.uniform(
                        0,
                        1,
                    )

                print(
                    f"Wikidata API returned "
                    f"{response.status_code}. "
                    f"Retry {attempt}/"
                    f"{MAX_RETRIES} "
                    f"in {delay:.1f}s..."
                )

                time.sleep(delay)
                continue

            response.raise_for_status()

            data = response.json()
            api_error = data.get(
                "error"
            )

            if api_error:
                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        "Wikidata API error after "
                        f"{MAX_RETRIES} attempts: "
                        f"{api_error}"
                    )

                delay = min(
                    60,
                    2 ** attempt,
                )
                delay += random.uniform(
                    0,
                    1,
                )

                print(
                    "Wikidata API error "
                    f"{api_error.get('code')!r}: "
                    f"{api_error.get('info', 'unknown error')}. "
                    f"Retry {attempt}/"
                    f"{MAX_RETRIES} "
                    f"in {delay:.1f}s..."
                )

                time.sleep(delay)
                continue

            if not isinstance(
                data.get("entities"),
                dict,
            ):
                raise RuntimeError(
                    "Wikidata API response did not "
                    "contain an entities object"
                )

            return data

        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as exc:
            if attempt == MAX_RETRIES:
                raise

            delay = min(
                60,
                2 ** attempt,
            )
            delay += random.uniform(
                0,
                1,
            )

            print(
                f"Wikidata API connection error: "
                f"{exc}"
            )
            print(
                f"Retry {attempt}/"
                f"{MAX_RETRIES} "
                f"in {delay:.1f}s..."
            )

            time.sleep(delay)

    raise RuntimeError(
        "Wikidata entity fetch failed "
        "after all retries."
    )


def main():
    ensure_directories()

    parser = argparse.ArgumentParser(
        description=(
            "Fetch complete Wikidata entities for "
            "the selected region."
        )
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Reuse already fetched QIDs and fetch only "
            "missing entities. The default is a full refresh."
        ),
    )
    args = parser.parse_args()

    if not QIDS_FILE.exists():
        raise FileNotFoundError(
            f"{QIDS_FILE} not found.\n"
            "Run discover.py first."
        )

    with QIDS_FILE.open(
        encoding="utf-8",
    ) as f:
        qids = [
            line.strip()
            for line in f
            if line.strip()
        ]

    existing_entities = load_existing_entities(
        args.resume
    )

    entities = {
        qid: existing_entities[qid]
        for qid in qids
        if qid in existing_entities
    }

    pending_qids = [
        qid
        for qid in qids
        if qid not in entities
    ]

    print(
        f"Reused from cache: {len(entities)}"
    )
    print(
        f"Need Wikidata fetch: {len(pending_qids)}"
    )

    for number, batch in enumerate(
        chunks(pending_qids, BATCH_SIZE),
        start=1,
    ):
        print(
            f"Fetching batch {number}: "
            f"{len(batch)} entities"
        )

        data = fetch_batch(
            batch
        )

        entities.update(
            data["entities"]
        )

        save_entities(
            entities
        )

        time.sleep(1)

    save_entities(
        entities
    )

    print(
        f"Stored {len(entities)} full entities"
    )
    print(f"Written: {ENTITIES_FILE}")


if __name__ == "__main__":
    main()
