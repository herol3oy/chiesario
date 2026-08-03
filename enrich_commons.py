import json
import time
from html.parser import HTMLParser
from pathlib import Path

import requests


INPUT_FILE = Path(
    "data/processed/churches_dates.json"
)

CACHE_FILE = Path(
    "data/raw/commons_file_metadata.json"
)

OUTPUT_FILE = Path(
    "data/processed/churches_commons.json"
)

REPORT_FILE = Path(
    "data/processed/commons_report.json"
)


API = "https://commons.wikimedia.org/w/api.php"

HEADERS = {
    "User-Agent": (
        "ItalianChurchDirectory/0.1 "
        "(historic church research project)"
    )
}

# extmetadata is relatively expensive.
BATCH_SIZE = 10


# --------------------------------------------------
# Helpers
# --------------------------------------------------


def load_json(path, default=None):
    if not path.exists():
        return default

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


def chunks(items, size):
    for i in range(
        0,
        len(items),
        size,
    ):
        yield items[i:i + size]


def filename_key(filename):
    return (
        filename
        .replace("_", " ")
        .strip()
        .casefold()
    )


# --------------------------------------------------
# Very small HTML -> text helper
# --------------------------------------------------


class TextExtractor(HTMLParser):

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(value):
    if not value:
        return None

    parser = TextExtractor()

    try:
        parser.feed(value)

        text = " ".join(
            part.strip()
            for part in parser.parts
            if part.strip()
        )

        return text or None

    except Exception:
        return value


def extmetadata_value(
    metadata,
    key,
):
    item = metadata.get(key)

    if not item:
        return None

    return item.get("value")


# --------------------------------------------------
# Commons API
# --------------------------------------------------


def fetch_batch(
    session,
    filenames,
):
    titles = "|".join(
        f"File:{filename}"
        for filename in filenames
    )

    response = session.get(
        API,
        params={
            "action": "query",
            "format": "json",
            "formatversion": 2,

            "prop": "imageinfo",

            "titles": titles,

            "iiprop": (
                "url|size|mime|"
                "extmetadata"
            ),

            # Useful web-sized thumbnail.
            "iiurlwidth": 1600,

            "iiextmetadatalanguage":
                "en",

            # Don't request every metadata field.
            "iiextmetadatafilter": (
                "LicenseShortName|"
                "LicenseUrl|"
                "UsageTerms|"
                "Artist|"
                "Credit|"
                "ImageDescription|"
                "DateTimeOriginal|"
                "AttributionRequired|"
                "Restrictions"
            ),
        },
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    return response.json()


def parse_page(page):
    title = page.get(
        "title",
        "",
    )

    filename = title.removeprefix(
        "File:"
    )

    if page.get("missing"):
        return filename, {
            "missing": True,
        }

    imageinfo = page.get(
        "imageinfo",
        [],
    )

    if not imageinfo:
        return filename, {
            "missing": True,
        }

    info = imageinfo[0]

    metadata = info.get(
        "extmetadata",
        {},
    )

    license_name = extmetadata_value(
        metadata,
        "LicenseShortName",
    )

    license_url = extmetadata_value(
        metadata,
        "LicenseUrl",
    )

    artist_raw = extmetadata_value(
        metadata,
        "Artist",
    )

    credit_raw = extmetadata_value(
        metadata,
        "Credit",
    )

    description_raw = (
        extmetadata_value(
            metadata,
            "ImageDescription",
        )
    )

    return filename, {
        "missing": False,

        "url":
            info.get("url"),

        "description_url":
            info.get(
                "descriptionurl"
            ),

        "thumbnail_url":
            info.get("thumburl"),

        "thumbnail_width":
            info.get("thumbwidth"),

        "thumbnail_height":
            info.get("thumbheight"),

        "width":
            info.get("width"),

        "height":
            info.get("height"),

        "size_bytes":
            info.get("size"),

        "mime":
            info.get("mime"),

        "license": {
            "name":
                strip_html(
                    license_name
                ),

            "url":
                license_url,

            "usage_terms":
                strip_html(
                    extmetadata_value(
                        metadata,
                        "UsageTerms",
                    )
                ),

            "attribution_required":
                strip_html(
                    extmetadata_value(
                        metadata,
                        "AttributionRequired",
                    )
                ),

            "restrictions":
                strip_html(
                    extmetadata_value(
                        metadata,
                        "Restrictions",
                    )
                ),
        },

        # Preserve both raw + simplified text.
        "artist": {
            "raw": artist_raw,
            "text":
                strip_html(
                    artist_raw
                ),
        },

        "credit": {
            "raw": credit_raw,
            "text":
                strip_html(
                    credit_raw
                ),
        },

        "description": {
            "raw":
                description_raw,

            "text":
                strip_html(
                    description_raw
                ),
        },

        "date_original":
            strip_html(
                extmetadata_value(
                    metadata,
                    "DateTimeOriginal",
                )
            ),

        # Preserve full metadata in case
        # we need something later.
        "extmetadata": metadata,
    }


# --------------------------------------------------
# Build cache
# --------------------------------------------------


def collect_filenames(churches):
    result = {}

    for church in churches:

        for image in church.get(
            "images",
            [],
        ):
            filename = image.get(
                "filename"
            )

            if not filename:
                continue

            result[
                filename_key(filename)
            ] = filename

    return list(result.values())


def enrich_cache(
    filenames,
    cache,
):
    cached_keys = {
        filename_key(name)
        for name in cache.keys()
    }

    missing = [
        filename
        for filename in filenames
        if filename_key(filename)
        not in cached_keys
    ]

    print(
        "Unique image files:",
        len(filenames),
    )

    print(
        "Already cached:",
        len(filenames)
        - len(missing),
    )

    print(
        "Need Commons lookup:",
        len(missing),
    )

    if not missing:
        return cache

    session = requests.Session()

    batches = list(
        chunks(
            missing,
            BATCH_SIZE,
        )
    )

    for batch_number, batch in enumerate(
        batches,
        start=1,
    ):
        print(
            f"Commons batch "
            f"{batch_number}/"
            f"{len(batches)} "
            f"({len(batch)} files)"
        )

        data = fetch_batch(
            session,
            batch,
        )

        pages = (
            data
            .get("query", {})
            .get("pages", [])
        )

        returned = set()

        for page in pages:

            filename, metadata = (
                parse_page(page)
            )

            cache[filename] = metadata

            returned.add(
                filename_key(filename)
            )

        # Mark anything not returned so we
        # don't repeatedly request it.
        for filename in batch:

            if (
                filename_key(filename)
                not in returned
            ):
                cache[filename] = {
                    "missing": True,
                }

        save_json(
            CACHE_FILE,
            cache,
        )

        time.sleep(0.5)

    return cache


# --------------------------------------------------
# Attach metadata
# --------------------------------------------------


def find_cached(
    cache,
    filename,
):
    wanted = filename_key(
        filename
    )

    for cached_filename, value in (
        cache.items()
    ):
        if (
            filename_key(
                cached_filename
            )
            == wanted
        ):
            return value

    return None


def attach_commons(
    churches,
    cache,
):
    for church in churches:

        images = church.get(
            "images",
            [],
        )

        for image in images:

            filename = image.get(
                "filename"
            )

            metadata = (
                find_cached(
                    cache,
                    filename,
                )
            )

            image[
                "commons"
            ] = metadata

        usable = [
            image
            for image in images
            if (
                image.get("commons")
                and not image[
                    "commons"
                ].get(
                    "missing"
                )
            )
        ]

        licensed = [
            image
            for image in usable
            if (
                image["commons"]
                .get("license", {})
                .get("name")
            )
        ]

        derived = church[
            "derived"
        ]

        derived[
            "commons_image_count"
        ] = len(usable)

        derived[
            "commons_licensed_image_count"
        ] = len(licensed)

        # We have NOT yet determined whether
        # the images actually depict the church.
        derived[
            "image_relevance_review_required"
        ] = bool(usable)


# --------------------------------------------------
# Report
# --------------------------------------------------


def build_report(churches):

    files = {}

    churches_without_images = []

    for church in churches:

        images = church.get(
            "images",
            [],
        )

        if not images:

            churches_without_images.append(
                {
                    "wikidata_id":
                        church[
                            "wikidata_id"
                        ],

                    "name":
                        church[
                            "derived"
                        ][
                            "display_name"
                        ],
                }
            )

        for image in images:

            filename = image.get(
                "filename"
            )

            metadata = image.get(
                "commons"
            )

            if filename:
                files[
                    filename_key(
                        filename
                    )
                ] = {
                    "filename":
                        filename,

                    "metadata":
                        metadata,
                }

    missing_files = []
    missing_license = []

    license_counts = {}

    for item in files.values():

        filename = item[
            "filename"
        ]

        metadata = item[
            "metadata"
        ]

        if (
            not metadata
            or metadata.get(
                "missing"
            )
        ):
            missing_files.append(
                filename
            )

            continue

        license_name = (
            metadata
            .get("license", {})
            .get("name")
        )

        if not license_name:

            missing_license.append(
                filename
            )

        else:
            license_counts[
                license_name
            ] = (
                license_counts.get(
                    license_name,
                    0,
                )
                + 1
            )

    return {
        "total_churches":
            len(churches),

        "unique_files":
            len(files),

        "files_enriched":
            len(files)
            - len(missing_files),

        "missing_files":
            len(missing_files),

        "files_missing_license_metadata":
            len(missing_license),

        "churches_without_wikidata_images":
            len(
                churches_without_images
            ),

        "license_counts":
            dict(
                sorted(
                    license_counts.items(),
                    key=lambda item:
                        (-item[1], item[0]),
                )
            ),

        "missing_file_records":
            missing_files,

        "missing_license_records":
            missing_license,

        "churches_without_images":
            churches_without_images,
    }


# --------------------------------------------------
# Main
# --------------------------------------------------


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found.\n"
            "Run resolve_dates.py first."
        )

    churches = load_json(
        INPUT_FILE,
        [],
    )

    cache = load_json(
        CACHE_FILE,
        {},
    )

    filenames = collect_filenames(
        churches
    )

    cache = enrich_cache(
        filenames,
        cache,
    )

    attach_commons(
        churches,
        cache,
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
    print(
        "Commons enrichment complete"
    )

    print(
        "---------------------------"
    )

    print(
        "Churches:",
        report[
            "total_churches"
        ],
    )

    print(
        "Unique image files:",
        report[
            "unique_files"
        ],
    )

    print(
        "Files enriched:",
        report[
            "files_enriched"
        ],
    )

    print(
        "Missing files:",
        report[
            "missing_files"
        ],
    )

    print(
        "Files missing license metadata:",
        report[
            "files_missing_license_metadata"
        ],
    )

    print(
        "Churches without Wikidata images:",
        report[
            "churches_without_wikidata_images"
        ],
    )

    print()
    print(
        "Licenses:"
    )

    for name, count in (
        report[
            "license_counts"
        ].items()
    ):
        print(
            f"  {name}: {count}"
        )

    print()
    print(
        f"Cache:  {CACHE_FILE}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print(
        f"Report: {REPORT_FILE}"
    )


if __name__ == "__main__":
    main()