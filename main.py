import json
import requests
from pathlib import Path

ENDPOINT = "https://query.wikidata.org/sparql"

def main():
    QUERY = """
   SELECT DISTINCT
  ?church
  ?churchLabel
  ?coord
  ?inception
  ?place
  ?placeLabel
WHERE {
  ?church wdt:P31/wdt:P279* wd:Q16970 .

  # Somewhere inside Tuscany
  ?church wdt:P131* wd:Q1273 .

  # Must have a known inception/construction date
  ?church wdt:P571 ?inception .

  # Only before 1800
  FILTER(
    ?inception < "1800-01-01T00:00:00Z"^^xsd:dateTime
  )

  OPTIONAL {
    ?church wdt:P625 ?coord .
  }

  OPTIONAL {
    ?church wdt:P131 ?place .
  }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "it,en".
  }
}
ORDER BY ?inception
LIMIT 1000
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

    with open("data/raw/wikidata_tuscany_pre1800.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Downloaded {len(data['results']['bindings'])} rows")


if __name__ == "__main__":
    main()
