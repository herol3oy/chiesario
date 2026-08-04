import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REGIONS_FILE = ROOT / "config" / "regions.json"


def load_regions():
    with REGIONS_FILE.open(encoding="utf-8") as f:
        regions = json.load(f)
    if not isinstance(regions, dict):
        raise ValueError("config/regions.json must contain an object")
    return regions


def published_regions(regions):
    result = []
    for slug, region in regions.items():
        publish = region.get("publish", False)
        if not isinstance(publish, bool):
            raise ValueError(
                f"Region {slug!r} has a non-boolean publish value"
            )
        if publish:
            result.append(slug)
    if not result:
        raise RuntimeError("No regions are configured for publication")
    return result


def run_region_qa(slug):
    env = os.environ.copy()
    env["CHURCHES_REGION"] = slug
    subprocess.run(
        [
            sys.executable,
            "qa.py",
            "--geojson",
            "--strict-publication",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )


def main():
    regions = load_regions()
    selected = published_regions(regions)

    print("Published-region QA")
    print("-------------------")
    for slug in selected:
        print(f"Checking {regions[slug]['name']} ({slug})")
        run_region_qa(slug)

    subprocess.run(
        [
            sys.executable,
            "build_web_data.py",
            "--regions",
            *selected,
        ],
        cwd=ROOT,
        check=True,
    )

    print()
    print("Publication data is ready")
    print("Regions:", ", ".join(selected))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print()
        print("Publication stopped because a region failed QA.")
        raise SystemExit(exc.returncode or 1)
