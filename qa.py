import json
import sys
from pathlib import Path


CATALOG_FILE = Path(
    "data/catalog/churches.json"
)


def load_json(path):
    with path.open(
        encoding="utf-8",
    ) as f:
        return json.load(f)


def main():
    if not CATALOG_FILE.exists():
        print(
            f"QA failed: "
            f"{CATALOG_FILE} does not exist."
        )

        print(
            "Run build_catalog.py first."
        )

        return 1

    records = load_json(
        CATALOG_FILE
    )

    review_records = [
        record
        for record in records
        if record.get("status") == "review"
    ]

    print()
    print("Catalog QA")
    print("----------")

    print(
        "Catalog records:",
        len(records),
    )

    print(
        "Remaining review records:",
        len(review_records),
    )

    if review_records:
        print()
        print(
            "QA FAILED"
        )

        print(
            "The following records "
            "still require review:"
        )

        print()

        for record in review_records:
            qid = record.get(
                "id",
                "?",
            )

            name = record.get(
                "name",
                "?",
            )

            blocking = (
                record
                .get(
                    "review",
                    {},
                )
                .get(
                    "blocking",
                    [],
                )
            )

            reasons = (
                ", ".join(blocking)
                if blocking
                else "unspecified"
            )

            print(
                f"  {qid} | "
                f"{name} | "
                f"{reasons}"
            )

        print()
        print(
            "Resolve review records "
            "before publishing."
        )

        return 1

    print()
    print("QA passed.")

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )