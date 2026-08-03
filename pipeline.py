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

    args = parser.parse_args()

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

    stages = STAGES

    if args.start_at:
        start_index = stages.index(
            args.start_at
        )

        stages = stages[
            start_index:
        ]

    for script in stages:
        run_stage(
            script,
            env,
        )

    # ------------------------------------------
    # Publication QA gate
    # ------------------------------------------

    run_command(
        [
            sys.executable,
            "qa.py",
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