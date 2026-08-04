import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(
    __file__
).resolve().parent


REGIONS_FILE = (
    ROOT_DIR
    / "config"
    / "regions.json"
)


STAGES = [
    "discover.py",
    "fetch_entities.py",
    "normalize.py",
    "classify_types.py",
    "enrich_osm.py",
    "resolve_coordinates.py",
    "resolve_dates.py",
    "enrich_beweb.py",
    "resolve_historical_dates.py",
    "resolve_historic_scope.py",
    "enrich_commons.py",
    "select_images.py",
    "detect_duplicates.py",
    "apply_overrides.py",
    "build_catalog.py",
]


def load_regions():
    with REGIONS_FILE.open(
        encoding="utf-8",
    ) as f:
        return json.load(f)


def run_stage(
    script,
    env,
    extra_args=None,
):
    print()
    print("=" * 60)
    print(f"Running {script}")
    print("=" * 60)
    print()

    subprocess.run(
        [
            sys.executable,
            script,
            *(extra_args or []),
        ],
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )


def run_command(
    args,
    env,
):
    print()
    print(
        "$",
        " ".join(args),
    )
    print()

    subprocess.run(
        args,
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )


def main():
    regions = load_regions()

    parser = argparse.ArgumentParser(
        description=(
            "Run the historic church "
            "pipeline for an Italian region."
        )
    )

    parser.add_argument(
        "--region",
        required=True,
        choices=sorted(regions),
        help="Region slug from config/regions.json",
    )

    parser.add_argument(
        "--start-at",
        choices=STAGES,
        help=(
            "Start from a specific stage "
            "instead of discovery."
        ),
    )

    parser.add_argument(
        "--stop-after",
        choices=STAGES,
        help=(
            "Stop after a specific stage without running "
            "publication QA or GeoJSON generation."
        ),
    )

    parser.add_argument(
        "--resume-entities",
        action="store_true",
        help=(
            "Reuse already fetched Wikidata entities "
            "instead of performing a full entity refresh."
        ),
    )

    parser.add_argument(
        "--with-beweb",
        action="store_true",
        help=(
            "Collect cached/public BeWeb history and use it "
            "in conservative historical-date resolution."
        ),
    )

    parser.add_argument(
        "--refresh-beweb",
        action="store_true",
        help=(
            "Refetch BeWeb pages instead of reusing complete "
            "raw cache entries. Requires --with-beweb."
        ),
    )

    args = parser.parse_args()

    if args.refresh_beweb and not args.with_beweb:
        parser.error("--refresh-beweb requires --with-beweb")

    if (
        args.start_at == "enrich_beweb.py"
        and not args.with_beweb
    ):
        parser.error(
            "Starting at enrich_beweb.py requires --with-beweb"
        )

    if (
        args.stop_after == "enrich_beweb.py"
        and not args.with_beweb
    ):
        parser.error(
            "Stopping after enrich_beweb.py requires --with-beweb"
        )

    region_slug = args.region
    region = regions[region_slug]

    env = os.environ.copy()

    env[
        "CHURCHES_REGION"
    ] = region_slug

    print()
    print(
        "Historic Churches of Italy"
    )
    print(
        "=========================="
    )
    print(
        "Region:",
        region["name"],
    )
    print(
        "Wikidata:",
        region["wikidata_id"],
    )

    start_index = 0
    stop_index = len(STAGES) - 1

    if args.start_at:
        start_index = STAGES.index(
            args.start_at
        )

    if args.stop_after:
        stop_index = STAGES.index(
            args.stop_after
        )

    if start_index > stop_index:
        parser.error("--start-at must not come after --stop-after")

    stages = STAGES[start_index:stop_index + 1]
    executed = []

    for script in stages:
        if script == "enrich_beweb.py" and not args.with_beweb:
            print()
            print("Skipping optional enrich_beweb.py")
            continue

        extra_args = (
            ["--resume"]
            if (
                script == "fetch_entities.py"
                and args.resume_entities
            )
            else []
        )

        if (
            script == "enrich_beweb.py"
            and args.refresh_beweb
        ):
            extra_args = ["--refresh"]

        if (
            script == "resolve_historical_dates.py"
            and args.with_beweb
        ):
            extra_args = ["--use-beweb"]

        run_stage(
            script,
            env,
            extra_args,
        )
        executed.append(script)

    if "build_catalog.py" not in executed:
        print()
        print("=" * 60)
        print("Pipeline stopped at requested research stage")
        print("=" * 60)
        print()
        print(f"Region: {region['name']}")
        print(f"Last stage: {executed[-1] if executed else 'none'}")
        return 0

    # ------------------------------------------
    # Publication QA gate
    # ------------------------------------------

    run_command(
        [
            sys.executable,
            "qa.py",
            "--strict-publication",
        ],
        env,
    )

    # Only generate publication GeoJSON
    # after catalog QA passes.

    run_stage(
        "build_geojson.py",
        env,
    )

    # Validate generated GeoJSON too.

    run_command(
        [
            sys.executable,
            "qa.py",
            "--geojson",
            "--strict-publication",
        ],
        env,
    )

    print()
    print("=" * 60)
    print("Pipeline complete")
    print("=" * 60)
    print()
    print(
        f"Region: {region['name']}"
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(
            main()
        )

    except subprocess.CalledProcessError as exc:
        print()
        print("=" * 60)
        print("Pipeline stopped")
        print("=" * 60)
        print()
        print(
            "A stage or QA check failed."
        )
        print(
            "This may be expected when "
            "a new region requires review."
        )
        print()
        print(
            f"Exit code: "
            f"{exc.returncode}"
        )

        sys.exit(
            exc.returncode
            or 1
        )
