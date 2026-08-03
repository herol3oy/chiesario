import json
import time
from pathlib import Path

import requests


API = "https://www.wikidata.org/w/api.php"
BATCH_SIZE = 50

HEADERS = {
    "User-Agent": "ItalianChurchDirectory/0.1"
}


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


with open(
    "data/raw/tuscany_qids.txt",
    encoding="utf-8",
) as f:
    qids = [
        line.strip()
        for line in f
        if line.strip()
    ]


entities = {}


for number, batch in enumerate(
    chunks(qids, BATCH_SIZE),
    start=1,
):
    print(
        f"Fetching batch {number}: "
        f"{len(batch)} entities"
    )

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

    response.raise_for_status()

    data = response.json()

    entities.update(
        data["entities"]
    )

    time.sleep(0.2)


Path("data/raw").mkdir(
    parents=True,
    exist_ok=True,
)


with open(
    "data/raw/tuscany_entities.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(
        entities,
        f,
        ensure_ascii=False,
        indent=2,
    )


print(
    f"Stored {len(entities)} full entities"
)