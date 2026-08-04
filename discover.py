import random
import time

import requests

from project_config import (
    QIDS_FILE,
    REGION_NAME,
    REGION_QID,
    ensure_directories,
)


SPARQL_ENDPOINT = (
    "https://query.wikidata.org/sparql"
)

MAX_RETRIES = 6

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

HEADERS = {
    "User-Agent": (
        "historic-churches-italy/0.1 "
        "(research data pipeline)"
    ),
    "Accept": (
        "application/"
        "sparql-results+json"
    ),
}


def run_sparql_query(query):
    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            response = requests.get(
                SPARQL_ENDPOINT,
                params={
                    "query": query,
                    "format": "json",
                },
                headers=HEADERS,
                timeout=120,
            )

            if (
                response.status_code
                in RETRYABLE_STATUS_CODES
            ):
                if attempt == MAX_RETRIES:
                    response.raise_for_status()

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                if (
                    retry_after
                    and retry_after.isdigit()
                ):
                    delay = float(
                        retry_after
                    )
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
                    f"WDQS returned "
                    f"{response.status_code}. "
                    f"Retry {attempt}/"
                    f"{MAX_RETRIES} "
                    f"in {delay:.1f}s..."
                )

                time.sleep(delay)
                continue

            response.raise_for_status()

            return response.json()

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
                f"WDQS connection error: "
                f"{exc}"
            )

            print(
                f"Retry {attempt}/"
                f"{MAX_RETRIES} "
                f"in {delay:.1f}s..."
            )

            time.sleep(delay)

    raise RuntimeError(
        "Wikidata query failed "
        "after all retries."
    )

def main():
    ensure_directories()

    print(
        f"Region: {REGION_NAME} "
        f"({REGION_QID})"
    )

    query = f"""
SELECT DISTINCT ?church
WHERE {{
  wd:Q16970 ^wdt:P279*/^wdt:P31 ?church .
  ?church wdt:P131+ wd:{REGION_QID} .
}}
"""

    data = run_sparql_query(
        query
    )

    qids = []

    for row in data["results"]["bindings"]:
        uri = row["church"]["value"]
        qid = uri.rsplit("/", 1)[-1]

        if qid not in qids:
            qids.append(qid)

    with QIDS_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        f.write("\n".join(qids))

    print(f"Discovered {len(qids)} churches")
    print(f"Written: {QIDS_FILE}")


if __name__ == "__main__":
    main()
