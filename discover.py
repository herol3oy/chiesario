import requests

from project_config import (
    QIDS_FILE,
    REGION_NAME,
    REGION_QID,
    ensure_directories,
)


ENDPOINT = "https://query.wikidata.org/sparql"


def main():
    ensure_directories()

    print(
        f"Region: {REGION_NAME} "
        f"({REGION_QID})"
    )

    query = f"""
SELECT DISTINCT ?church ?inception
WHERE {{
  wd:Q16970 ^wdt:P279*/^wdt:P31 ?church .
  ?church wdt:P131+ wd:{REGION_QID} .
  ?church wdt:P571 ?inception .

  FILTER(
    ?inception <
    "1800-01-01T00:00:00Z"^^xsd:dateTime
  )
}}
"""

    response = requests.get(
        ENDPOINT,
        params={
            "query": query,
            "format": "json",
        },
        headers={
            "User-Agent": "ItalianChurchDirectory/0.1"
        },
        timeout=60,
    )

    response.raise_for_status()
    data = response.json()

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
