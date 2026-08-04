import json

from project_config import (
    HISTORICAL_DATES_FILE,
    HISTORIC_SCOPE_FILE,
    HISTORIC_SCOPE_REPORT_FILE,
)


INPUT_FILE = HISTORICAL_DATES_FILE
OUTPUT_FILE = HISTORIC_SCOPE_FILE
REPORT_FILE = HISTORIC_SCOPE_REPORT_FILE

HISTORIC_CUTOFF_YEAR = 1800

VALID_HISTORIC_SCOPES = {
    "historic",
    "modern",
    "unknown",
}


def load_json(path):
    with path.open(encoding="utf-8") as f:
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


def canonical_start_year(church):
    canonical = (
        church.get(
            "resolved_date",
            {},
        ).get(
            "canonical"
        )
    )

    if not isinstance(canonical, dict):
        return None

    start_year = canonical.get(
        "start_year"
    )

    if (
        not isinstance(start_year, int)
        or isinstance(start_year, bool)
    ):
        return None

    return start_year


def resolve_historic_scope(church):
    start_year = canonical_start_year(
        church
    )

    if start_year is None:
        return "unknown"

    canonical = church.get(
        "resolved_date",
        {},
    ).get("canonical") or {}
    basis = canonical.get("basis")

    if basis in {
        "documentary_attestation",
        "predecessor",
    }:
        end_year = canonical.get("end_year")
        if (
            isinstance(end_year, int)
            and not isinstance(end_year, bool)
            and end_year < HISTORIC_CUTOFF_YEAR
        ):
            return "historic"
        return "unknown"

    if start_year < HISTORIC_CUTOFF_YEAR:
        return "historic"

    return "modern"


def apply_historic_scope(church):
    scope = resolve_historic_scope(
        church
    )

    derived = church.setdefault(
        "derived",
        {},
    )

    derived[
        "historic_scope"
    ] = scope

    derived[
        "historic_scope_review_required"
    ] = scope == "unknown"

    return scope


def build_report(churches):
    counts = {
        scope: 0
        for scope in sorted(
            VALID_HISTORIC_SCOPES
        )
    }

    for church in churches:
        scope = (
            church.get(
                "derived",
                {},
            ).get(
                "historic_scope"
            )
        )

        if scope not in counts:
            scope = "unknown"

        counts[scope] += 1

    return {
        "total": len(churches),
        "historic": counts["historic"],
        "modern": counts["modern"],
        "unknown": counts["unknown"],
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run resolve_historical_dates.py first."
        )

    churches = load_json(
        INPUT_FILE
    )

    for church in churches:
        apply_historic_scope(
            church
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
    print("Historic-scope resolution complete")
    print("------------------------------------")
    print("Total:", report["total"])
    print("Historic:", report["historic"])
    print("Modern:", report["modern"])
    print("Unknown:", report["unknown"])
    print()
    print(f"Output: {OUTPUT_FILE}")
    print(f"Report: {REPORT_FILE}")


if __name__ == "__main__":
    main()
