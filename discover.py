import json
import requests
from pathlib import Path

ENDPOINT = "https://query.wikidata.org/sparql"

QUERY = """
SELECT DISTINCT ?church ?inception
WHERE {
  wd:Q16970 ^wdt:P279*/^wdt:P31 ?church .

  ?church wdt:P131+ wd:Q1273 .
  ?church wdt:P571 ?inception .

  FILTER(
    ?inception < "1800-01-01T00:00:00Z"^^xsd:dateTime
  )
}
LIMIT 200
"""

response = requests.get(
    ENDPOINT,
    params={
        "query": QUERY,
        "format": "json",
    },
    headers={
        "User-Agent": "ItalianChurchDirectory/0.1"
    },
    timeout=60,
)

response.raise_for_status()
data = response.json()

Path("data/raw").mkdir(parents=True, exist_ok=True)

with open(
    "data/raw/tuscany_discovery.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

qids = []

for row in data["results"]["bindings"]:
    uri = row["church"]["value"]
    qid = uri.rsplit("/", 1)[-1]

    if qid not in qids:
        qids.append(qid)

with open(
    "data/raw/tuscany_qids.txt",
    "w",
    encoding="utf-8",
) as f:
    f.write("\n".join(qids))

print(f"Discovered {len(qids)} churches")