import argparse
import hashlib
import json
import random
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser

import requests

from project_config import (
    BEWEB_RAW_DIR,
    DATES_FILE,
    ENTITIES_FILE,
    HISTORICAL_EVIDENCE_FILE,
    HISTORICAL_EVIDENCE_REPORT_FILE,
    ensure_directories,
)


INPUT_FILE = DATES_FILE
OUTPUT_FILE = HISTORICAL_EVIDENCE_FILE
REPORT_FILE = HISTORICAL_EVIDENCE_REPORT_FILE

USER_AGENT = (
    "historic-churches-italy/0.1 "
    "(provenance research; public BeWeb pages)"
)
MAX_RETRIES = 3
REQUEST_DELAY_SECONDS = 1.5
TIMEOUT = (15, 45)
LICENSE_NAME = "CC BY-NC-SA 4.0"
LICENSE_URL = (
    "https://creativecommons.org/licenses/by-nc-sa/4.0/"
)
TERMS_URL = (
    "https://www.beweb.chiesacattolica.it/terminiduso/"
)

INTERVENTION_LABELS = (
    "costruzione",
    "edificazione",
    "fondazione",
    "rifacimento",
    "ricostruzione",
    "restauro",
    "ristrutturazione",
    "lavori",
    "committenza",
    "storia",
    "consacrazione",
)


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


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()


def content_sha256(content):
    return hashlib.sha256(content).hexdigest()


def short_excerpt(value, limit=280):
    value = clean_text(value)
    if len(value) <= limit:
        return value

    shortened = value[: limit + 1].rsplit(" ", 1)[0]
    return f"{shortened}…"


class HistoryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ul_depth = 0
        self.datalist_depth = None
        self.li_depth = 0
        self.in_bold = False
        self.current = None
        self.entries = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "ul":
            self.ul_depth += 1
            classes = set(
                attrs.get("class", "").split()
            )
            if (
                self.datalist_depth is None
                and "datalist" in classes
            ):
                self.datalist_depth = self.ul_depth
            return

        if self.datalist_depth is None:
            return

        if tag == "li":
            self.li_depth += 1
            if self.li_depth == 1:
                self.current = {
                    "period": [],
                    "context": [],
                    "narrative": [],
                }
            return

        if tag == "b" and self.li_depth == 1:
            self.in_bold = True

    def handle_endtag(self, tag):
        if (
            tag == "b"
            and self.datalist_depth is not None
        ):
            self.in_bold = False
            return

        if (
            tag == "li"
            and self.datalist_depth is not None
        ):
            if self.li_depth == 1 and self.current:
                self.entries.append(self.current)
                self.current = None
            self.li_depth = max(0, self.li_depth - 1)
            return

        if tag == "ul":
            if self.ul_depth == self.datalist_depth:
                self.datalist_depth = None
                self.li_depth = 0
                self.current = None
            self.ul_depth = max(0, self.ul_depth - 1)

    def handle_data(self, data):
        if not self.current or not clean_text(data):
            return

        if self.in_bold:
            self.current["period"].append(data)
        elif self.li_depth == 1:
            self.current["context"].append(data)
        elif self.li_depth >= 2:
            self.current["narrative"].append(data)


class InformationParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active_tag = None
        self.text = []
        self.current_key = None
        self.current_link = None
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag in {"h4", "p"}:
            self.active_tag = tag
            self.text = []
            if tag == "p":
                self.current_link = None
        elif tag == "a" and self.active_tag == "p":
            self.current_link = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag != self.active_tag:
            return

        value = clean_text("".join(self.text))
        if tag == "h4":
            self.current_key = value
        elif tag == "p" and self.current_key:
            self.values[self.current_key] = {
                "value": value or None,
                "url": self.current_link,
            }

        self.active_tag = None
        self.text = []

    def handle_data(self, data):
        if self.active_tag:
            self.text.append(data)


def split_context(context):
    context = clean_text(context).strip("() ")
    lowered = context.casefold()

    for label in INTERVENTION_LABELS:
        if lowered == label:
            return label, None, context
        if lowered.startswith(f"{label} "):
            return (
                label,
                clean_text(context[len(label):]),
                context,
            )

    return None, None, context or None


def parse_history(html):
    parser = HistoryParser()
    parser.feed(html)
    evidence = []

    for ordinal, raw in enumerate(parser.entries):
        period = clean_text("".join(raw["period"]))
        context = clean_text("".join(raw["context"]))
        narrative = clean_text("".join(raw["narrative"]))
        intervention, building_part, context_raw = (
            split_context(context)
        )

        evidence.append(
            {
                "source_section": "Notizie storiche",
                "entry_ordinal": ordinal,
                "period_raw": period or None,
                "intervention_raw": intervention,
                "building_part_raw": building_part,
                "context_raw": context_raw,
                "short_evidence_excerpt": (
                    short_excerpt(narrative) or None
                ),
                "entry_text_sha256": (
                    content_sha256(
                        narrative.encode("utf-8")
                    )
                    if narrative
                    else None
                ),
                "normalized_period": None,
            }
        )

    return evidence


def parse_information(html):
    parser = InformationParser()
    parser.feed(html)

    def get(label):
        return parser.values.get(
            label,
            {"value": None, "url": None},
        )

    source = get("Fonte dei dati")
    return {
        "created_at_raw": get("Data di creazione")["value"],
        "published_at_raw": get("Data di pubblicazione")["value"],
        "data_source_raw": source["value"],
        "data_source_url": source["url"],
    }


def beweb_id_for_entity(entity):
    for claim in entity.get("claims", {}).get("P5611", []):
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue

        if isinstance(value, str) and value.isdigit():
            return value

    return None


def urls_for_id(beweb_id):
    base = "https://www.beweb.chiesacattolica.it"
    return {
        "page": (
            f"{base}/edificidiculto/edificio/{beweb_id}/"
        ),
        "history": (
            f"{base}/UI/includes/fragments/scheda/"
            "CEIA/notiziestoriche.inc.jsp"
            f"?id={beweb_id}&locale=it"
        ),
        "information": (
            f"{base}/UI/includes/fragments/scheda/"
            "CEIA/informazioni.inc.jsp"
            f"?id={beweb_id}&locale=it"
        ),
    }


def fetch(session, url):
    last_error = None
    last_status = None
    last_effective_url = None
    last_content_type = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url,
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            last_status = response.status_code
            last_effective_url = response.url
            last_content_type = response.headers.get(
                "Content-Type"
            )

            if response.status_code in {
                429,
                500,
                502,
                503,
                504,
            }:
                response.raise_for_status()

            response.raise_for_status()
            return {
                "status": response.status_code,
                "effective_url": response.url,
                "content_type": response.headers.get(
                    "Content-Type"
                ),
                "content": response.content,
                "attempts": attempt,
                "error": None,
            }
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if (
                last_status is not None
                and last_status not in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }
            ):
                break
            if attempt < MAX_RETRIES:
                delay = min(30, 2 ** attempt)
                delay += random.uniform(0, 1)
                time.sleep(delay)

    return {
        "status": last_status,
        "effective_url": last_effective_url,
        "content_type": last_content_type,
        "content": b"",
        "attempts": MAX_RETRIES,
        "error": last_error,
    }


def fetch_record(session, beweb_id):
    urls = urls_for_id(beweb_id)
    record_dir = BEWEB_RAW_DIR / beweb_id
    record_dir.mkdir(parents=True, exist_ok=True)
    responses = {}

    for index, (section, url) in enumerate(urls.items()):
        result = fetch(session, url)
        content = result.pop("content")
        path = record_dir / f"{section}.html"
        path.write_bytes(content)
        responses[section] = {
            **result,
            "url": url,
            "bytes": len(content),
            "sha256": content_sha256(content),
            "cache_file": str(
                path.relative_to(BEWEB_RAW_DIR.parent)
            ),
        }
        if index < len(urls) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    metadata = {
        "beweb_id": beweb_id,
        "fetched_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "responses": responses,
    }
    save_json(record_dir / "metadata.json", metadata)
    return metadata


def load_cached_record(beweb_id):
    record_dir = BEWEB_RAW_DIR / beweb_id
    metadata_file = record_dir / "metadata.json"
    required = [
        record_dir / "page.html",
        record_dir / "history.html",
        record_dir / "information.html",
    ]

    if (
        not metadata_file.exists()
        or not all(path.exists() for path in required)
    ):
        return None

    return load_json(metadata_file)


def build_evidence(beweb_id, metadata):
    record_dir = BEWEB_RAW_DIR / beweb_id
    page = (record_dir / "page.html").read_text(
        encoding="utf-8",
        errors="replace",
    )
    history = (record_dir / "history.html").read_text(
        encoding="utf-8",
        errors="replace",
    )
    information = (
        record_dir / "information.html"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )
    responses = metadata["responses"]
    failed = any(
        item.get("status") != 200
        for item in responses.values()
    )
    entries = parse_history(history) if not failed else []

    if failed:
        status = "fetch_failed"
    elif entries:
        status = "structured_date"
    else:
        status = "no_history"

    return {
        "beweb_id": beweb_id,
        "url": urls_for_id(beweb_id)["page"],
        "fetched_at": metadata.get("fetched_at"),
        "status": status,
        "page_access": (
            "full"
            if "BEWEB_METASCHEDA" in page
            else "metadata_only"
        ),
        "license": {
            "name": LICENSE_NAME,
            "url": LICENSE_URL,
            "terms_url": TERMS_URL,
        },
        "raw_cache": {
            section: {
                "cache_file": item.get("cache_file"),
                "sha256": item.get("sha256"),
                "http_status": item.get("status"),
                "effective_url": item.get("effective_url"),
            }
            for section, item in responses.items()
        },
        "record_provenance": parse_information(
            information
        ),
        "historical_evidence": entries,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Collect raw BeWeb historical evidence without "
            "changing canonical dates."
        )
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse complete raw BeWeb cache entries.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Fetch at most this many BeWeb-linked records.",
    )
    parser.add_argument(
        "--qid",
        action="append",
        dest="qids",
        help="Restrict collection to one or more QIDs.",
    )
    args = parser.parse_args()

    ensure_directories()
    if not INPUT_FILE.exists() or not ENTITIES_FILE.exists():
        raise FileNotFoundError(
            "Run fetch_entities.py and resolve_dates.py first."
        )

    churches = load_json(INPUT_FILE)
    entities = load_json(ENTITIES_FILE)
    selected_qids = set(args.qids or [])
    linked = []

    for church in churches:
        qid = church["wikidata_id"]
        if selected_qids and qid not in selected_qids:
            continue
        beweb_id = beweb_id_for_entity(
            entities.get(qid, {})
        )
        if beweb_id:
            linked.append((church, beweb_id))

    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("--limit must be non-negative")
        linked = linked[: args.limit]

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "it-IT,it;q=0.9",
        }
    )
    counts = {
        "structured_date": 0,
        "no_history": 0,
        "fetch_failed": 0,
    }

    for index, (church, beweb_id) in enumerate(linked, 1):
        metadata = (
            load_cached_record(beweb_id)
            if args.resume
            else None
        )
        fetched = metadata is None
        if fetched:
            metadata = fetch_record(session, beweb_id)

        evidence = build_evidence(
            beweb_id,
            metadata,
        )
        church.setdefault(
            "source_evidence",
            {},
        )["beweb"] = evidence
        counts[evidence["status"]] += 1
        print(
            f"[{index}/{len(linked)}] "
            f"{church['wikidata_id']} "
            f"{evidence['status']}"
        )
        if index < len(linked) and fetched:
            time.sleep(REQUEST_DELAY_SECONDS)

    save_json(OUTPUT_FILE, churches)
    report = {
        "total_records": len(churches),
        "records_selected": len(linked),
        "structured_date": counts["structured_date"],
        "no_history": counts["no_history"],
        "fetch_failed": counts["fetch_failed"],
        "canonical_dates_changed": 0,
    }
    save_json(REPORT_FILE, report)

    print()
    print("BeWeb evidence collection complete")
    print(json.dumps(report, indent=2))
    print(f"Output: {OUTPUT_FILE}")
    print(f"Report: {REPORT_FILE}")


if __name__ == "__main__":
    main()
