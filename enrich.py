import json
import requests
from pathlib import Path

ENDPOINT = "https://query.wikidata.org/sparql"

BATCH_SIZE = 50

with open(
    "data/raw/tuscany_qids.txt",
    encoding="utf-8",
) as f:
    qids = [
        line.strip()
        for line in f
        if line.strip()
    ]


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_batch(batch):
    values = " ".join(
        f"wd:{qid}"
        for qid in batch
    )

    query = f"""
    SELECT
      ?church
      ?churchLabel
      ?coord
      ?inception
      ?place
      ?placeLabel
      ?image
      ?website
    WHERE {{

      VALUES ?church {{
        {values}
      }}

      OPTIONAL {{
        ?church wdt:P625 ?coord .
      }}

      OPTIONAL {{
        ?church wdt:P571 ?inception .
      }}

      OPTIONAL {{
        ?church wdt:P131 ?place .
      }}

      OPTIONAL {{
        ?church wdt:P18 ?image .
      }}

      OPTIONAL {{
        ?church wdt:P856 ?website .
      }}

      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "it,en".
      }}
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

    return response.json()["results"]["bindings"]


all_rows = []

for number, batch in enumerate(
    chunks(qids, BATCH_SIZE),
    start=1,
):
    print(
        f"Fetching batch {number} "
        f"({len(batch)} churches)"
    )

    rows = fetch_batch(batch)
    all_rows.extend(rows)


Path("data/raw").mkdir(
    parents=True,
    exist_ok=True,
)

with open(
    "data/raw/tuscany_enriched.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(
        all_rows,
        f,
        ensure_ascii=False,
        indent=2,
    )

print(f"Got {len(all_rows)} rows")