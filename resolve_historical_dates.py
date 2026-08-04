import argparse
import copy
import json
import re

from enrich_beweb import classify_evidence
from project_config import (
    DATES_FILE,
    HISTORICAL_DATE_REPORT_FILE,
    HISTORICAL_DATES_FILE,
    HISTORICAL_EVIDENCE_FILE,
)


INPUT_FILE = DATES_FILE
EVIDENCE_FILE = HISTORICAL_EVIDENCE_FILE
OUTPUT_FILE = HISTORICAL_DATES_FILE
REPORT_FILE = HISTORICAL_DATE_REPORT_FILE

ORIGIN_TYPES = {
    "origin",
    "foundation",
    "construction",
}
ATTESTATION_TYPES = {
    "documentary_attestation",
    "predecessor",
}

COMPONENT_TERMS = {
    "abside",
    "campanile",
    "cappella",
    "copertura",
    "cripta",
    "facciata",
    "interno",
    "navata",
    "pavimento",
    "portale",
    "portico",
    "presbiterio",
    "pronao",
    "sacrestia",
    "tetto",
}

ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}
ROMAN_NUMERALS = (
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
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


def ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {
            1: "st",
            2: "nd",
            3: "rd",
        }.get(number % 10, "th")
    return f"{number}{suffix}"


def roman_to_int(value):
    value = value.upper()
    if not value or any(char not in ROMAN_VALUES for char in value):
        return None

    total = 0
    previous = 0
    for char in reversed(value):
        current = ROMAN_VALUES[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current

    if total < 1 or total > 21:
        return None
    remaining = total
    canonical = ""
    for amount, numeral in ROMAN_NUMERALS:
        while remaining >= amount:
            canonical += numeral
            remaining -= amount
    if canonical != value:
        return None
    return total


def normalized_period(
    kind,
    start_year,
    end_year,
    display,
):
    return {
        "kind": kind,
        "start_year": start_year,
        "end_year": end_year,
        "display": display,
    }


def normalize_period(value):
    if not isinstance(value, str):
        return None

    text = re.sub(r"\s+", " ", value).strip(" .;,:()")
    if not text:
        return None

    lowered = text.casefold()
    approximate = bool(
        re.search(r"\b(?:ca\.?|circa)\b", lowered)
    )
    without_approximation = re.sub(
        r"\b(?:ca\.?|circa)\b",
        "",
        lowered,
    ).strip(" .,-")

    decade_match = re.fullmatch(
        r"(?:anni\s+)?(\d{3})0",
        without_approximation,
    )
    if decade_match and lowered.startswith("anni"):
        start = int(decade_match.group(1)) * 10
        return normalized_period(
            "decade",
            start,
            start + 9,
            f"{start}s",
        )

    range_match = re.fullmatch(
        r"(\d{3,4})\s*[-‐–—/]\s*(\d{3,4})",
        without_approximation,
    )
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        if 1 <= start <= end <= 2100:
            if start % 10 == 0 and end == start + 9:
                kind = "decade"
                display = f"{start}s"
            else:
                kind = "year_range"
                display = f"{start}–{end}"
            return normalized_period(
                kind,
                start,
                end,
                display,
            )

    year_match = re.fullmatch(
        r"(\d{3,4})",
        without_approximation,
    )
    if year_match:
        year = int(year_match.group(1))
        if 1 <= year <= 2100:
            return normalized_period(
                "circa_year" if approximate else "year",
                year,
                year,
                f"circa {year}" if approximate else str(year),
            )

    mixed_match = re.fullmatch(
        r"([IVXLCDM]+)\s*[-‐–—/]\s*(\d{3,4})",
        text,
        flags=re.IGNORECASE,
    )
    if mixed_match:
        century = roman_to_int(mixed_match.group(1))
        end = int(mixed_match.group(2))
        if century:
            start = (century - 1) * 100 + 1
            if start <= end <= 2100:
                return normalized_period(
                    "mixed_range",
                    start,
                    end,
                    f"{ordinal(century)} century–{end}",
                )

    century_text = re.sub(
        r"^(?:sec(?:olo)?\.?\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    century_match = re.fullmatch(
        r"([IVXLCDM]+)(?:\s*[-‐–—/]\s*"
        r"(?:sec(?:olo)?\.?\s*)?([IVXLCDM]+))?",
        century_text,
        flags=re.IGNORECASE,
    )
    if century_match:
        first = roman_to_int(century_match.group(1))
        second = (
            roman_to_int(century_match.group(2))
            if century_match.group(2)
            else first
        )
        if first and second and first <= second:
            start = (first - 1) * 100 + 1
            end = second * 100
            if first == second:
                return normalized_period(
                    "century",
                    start,
                    end,
                    f"{ordinal(first)} century",
                )
            return normalized_period(
                "century_range",
                start,
                end,
                (
                    f"{ordinal(first)}–"
                    f"{ordinal(second)} century"
                ),
            )

    return None


def period_key(period):
    return (
        period.get("kind"),
        period.get("start_year"),
        period.get("end_year"),
    )


def periods_overlap(left, right):
    left_start = left.get("start_year")
    left_end = left.get("end_year")
    right_start = right.get("start_year")
    right_end = right.get("end_year")
    if None in {left_start, left_end, right_start, right_end}:
        return False
    return left_start <= right_end and right_start <= left_end


def primary_source(
    name,
    url,
    source_id=None,
):
    return {
        "name": name,
        "url": url,
        "source_id": source_id,
    }


def wikidata_canonical(church, canonical):
    qid = church["wikidata_id"]
    result = copy.deepcopy(canonical)
    result.setdefault("basis", "inception")
    result.setdefault("source", "wikidata")
    result.setdefault("source_name", "Wikidata")
    result.setdefault(
        "source_url",
        f"https://www.wikidata.org/wiki/{qid}",
    )
    result.setdefault(
        "sources",
        [
            primary_source(
                "Wikidata",
                result["source_url"],
                qid,
            )
        ],
    )
    statement_id = result.get("statement_id")
    result.setdefault(
        "evidence_refs",
        [statement_id] if statement_id else [],
    )
    return result


def beweb_canonical(
    period,
    evidence_type,
    beweb,
    evidence_ref,
):
    result = copy.deepcopy(period)
    result.update(
        {
            "basis": evidence_type,
            "source": "beweb",
            "source_name": "BeWeb",
            "source_url": beweb["url"],
            "sources": [
                primary_source(
                    "BeWeb",
                    beweb["url"],
                    beweb["beweb_id"],
                )
            ],
            "evidence_refs": [evidence_ref],
        }
    )
    return result


def prepared_beweb_evidence(beweb):
    if not beweb or beweb.get("status") != "structured_date":
        return [], []

    prepared = []
    phases = []
    for evidence in beweb.get("historical_evidence", []):
        item = copy.deepcopy(evidence)
        # Reclassify from the lossless raw fields when present so a
        # semantic parser improvement also applies to an existing
        # enrichment artifact, without another network fetch.
        if any(
            item.get(field)
            for field in (
                "intervention_raw",
                "context_raw",
                "short_evidence_excerpt",
            )
        ):
            item["evidence_type"] = classify_evidence(
                item.get("intervention_raw"),
                item.get("context_raw"),
                item.get("short_evidence_excerpt"),
            )
        period = normalize_period(item.get("period_raw"))
        item["normalized_period"] = period
        eligible, ineligibility_reason = canonical_eligibility(item)
        item["canonical_date_eligible"] = eligible
        item["canonical_ineligibility_reason"] = (
            ineligibility_reason
        )
        evidence_ref = (
            f"beweb:{beweb['beweb_id']}:history:"
            f"{item.get('entry_ordinal')}"
        )
        item["evidence_ref"] = evidence_ref
        prepared.append(item)
        if period:
            phases.append(
                {
                    "evidence_ref": evidence_ref,
                    "evidence_type": item.get(
                        "evidence_type",
                        "other",
                    ),
                    "period": period,
                    "period_raw": item.get("period_raw"),
                    "building_part": item.get(
                        "building_part_raw"
                    ),
                    "short_evidence_excerpt": item.get(
                        "short_evidence_excerpt"
                    ),
                    "source_name": "BeWeb",
                    "source_url": beweb["url"],
                }
            )
    return prepared, phases


def canonical_eligibility(item):
    evidence_type = item.get("evidence_type")
    if evidence_type not in ORIGIN_TYPES | ATTESTATION_TYPES:
        return False, "secondary_or_other_phase"

    building_part = (
        item.get("building_part_raw")
        or ""
    ).casefold()
    context = (
        item.get("context_raw")
        or ""
    ).casefold()
    narrative = (
        item.get("short_evidence_excerpt")
        or ""
    ).casefold()
    combined = f"{building_part} {context} {narrative}"

    if "?" in combined:
        return False, "source_marks_context_uncertain"

    uncertainty_markers = (
        "la tradizione",
        "secondo la tradizione",
        "probabil",
        "presumibil",
        "potrebbe",
        "sarebbe",
        "si può evincere",
    )
    if any(marker in narrative for marker in uncertainty_markers):
        return False, "source_language_is_uncertain"

    component = next(
        (
            term
            for term in sorted(COMPONENT_TERMS)
            if term in building_part
        ),
        None,
    )
    if component:
        return False, f"building_component:{component}"

    if "caratteri ascrivibili" in narrative:
        return False, "architectural_style_assessment_only"

    period = item.get("normalized_period") or {}
    start_year = period.get("start_year")
    end_year = period.get("end_year")
    duration = (
        end_year - start_year
        if isinstance(start_year, int)
        and isinstance(end_year, int)
        else 0
    )
    distinct_phase_markers = (
        "chiesa attuale",
        "costruzione attuale",
        "struttura attuale",
        "sui resti",
        "preesistente",
        "antica cappella",
        "cripta databile",
    )
    if (
        duration > 20
        and any(marker in narrative for marker in distinct_phase_markers)
    ):
        return False, "combined_distinct_historical_phases"

    if (
        item.get("evidence_type") == "construction"
        and "potrebbe" in narrative
        and any(
            marker in narrative
            for marker in ("restauro", "rifacimento")
        )
    ):
        return False, "construction_or_restoration_unclear"

    return True, None


def unique_evidence(items):
    unique = {}
    for item in items:
        unique.setdefault(
            period_key(item["normalized_period"]),
            item,
        )
    return list(unique.values())


def resolve_record(church, beweb):
    existing = church.get("resolved_date", {})
    existing_canonical = existing.get("canonical")
    wikidata = (
        wikidata_canonical(church, existing_canonical)
        if existing_canonical
        else None
    )
    prepared, phases = prepared_beweb_evidence(beweb)
    if beweb:
        beweb["historical_evidence"] = prepared

    origin = unique_evidence(
        [
            item
            for item in prepared
            if item.get("normalized_period")
            and item.get("evidence_type") in ORIGIN_TYPES
            and item.get("canonical_date_eligible")
        ]
    )
    attestations = [
        item
        for item in prepared
        if item.get("normalized_period")
        and item.get("evidence_type") in ATTESTATION_TYPES
        and item.get("canonical_date_eligible")
    ]

    candidates = copy.deepcopy(existing.get("candidates", []))
    for item in origin + attestations:
        candidates.append(
            {
                **item["normalized_period"],
                "basis": item.get("evidence_type"),
                "source": "beweb",
                "evidence_ref": item["evidence_ref"],
            }
        )

    if len(origin) > 1:
        return {
            "canonical": None,
            "candidates": candidates,
            "historical_phases": phases,
            "review_required": True,
            "reason": "multiple_beweb_origin_periods",
        }

    if len(origin) == 1:
        item = origin[0]
        candidate = beweb_canonical(
            item["normalized_period"],
            item["evidence_type"],
            beweb,
            item["evidence_ref"],
        )
        if wikidata and not periods_overlap(wikidata, candidate):
            secondary_match = any(
                phase["evidence_type"] in {
                    "reconstruction",
                    "restoration",
                    "consecration",
                }
                and periods_overlap(wikidata, phase["period"])
                for phase in phases
            )
            if not secondary_match:
                return {
                    "canonical": None,
                    "candidates": candidates,
                    "historical_phases": phases,
                    "review_required": True,
                    "reason": "wikidata_beweb_origin_conflict",
                }
        reason = (
            "beweb_disambiguates_wikidata_phase"
            if wikidata and not periods_overlap(wikidata, candidate)
            else "unambiguous_beweb_origin"
        )
        return {
            "canonical": candidate,
            "candidates": candidates,
            "historical_phases": phases,
            "review_required": False,
            "reason": reason,
        }

    if attestations:
        item = min(
            attestations,
            key=lambda value: (
                value["normalized_period"]["end_year"],
                value["normalized_period"]["start_year"],
            ),
        )
        candidate = beweb_canonical(
            item["normalized_period"],
            "documentary_attestation",
            beweb,
            item["evidence_ref"],
        )
        if wikidata and wikidata.get("end_year") is not None:
            if wikidata["end_year"] <= candidate["end_year"]:
                return {
                    "canonical": wikidata,
                    "candidates": candidates,
                    "historical_phases": phases,
                    "review_required": False,
                    "reason": "wikidata_precedes_attestation",
                }
        return {
            "canonical": candidate,
            "candidates": candidates,
            "historical_phases": phases,
            "review_required": False,
            "reason": "earliest_documentary_attestation",
        }

    if wikidata:
        return {
            "canonical": wikidata,
            "candidates": candidates,
            "historical_phases": phases,
            "review_required": False,
            "reason": existing.get("reason", "wikidata_only"),
        }

    return {
        "canonical": None,
        "candidates": candidates,
        "historical_phases": phases,
        "review_required": True,
        "reason": (
            "beweb_has_no_eligible_date"
            if beweb
            else existing.get("reason", "no_usable_date")
        ),
    }


def apply_result(church, result):
    church["resolved_date"] = result
    canonical = result["canonical"]
    derived = church.setdefault("derived", {})
    derived["date_review_required"] = result["review_required"]
    derived["canonical_date_display"] = (
        canonical.get("display") if canonical else None
    )
    derived["canonical_date_start_year"] = (
        canonical.get("start_year") if canonical else None
    )
    derived["canonical_date_end_year"] = (
        canonical.get("end_year") if canonical else None
    )
    derived["canonical_date_kind"] = (
        canonical.get("kind") if canonical else None
    )
    derived["canonical_date_basis"] = (
        canonical.get("basis") if canonical else None
    )
    derived["canonical_date_source"] = (
        canonical.get("source") if canonical else None
    )


def build_report(churches):
    report = {
        "total": len(churches),
        "resolved": 0,
        "unresolved": 0,
        "by_source": {},
        "by_basis": {},
        "unresolved_reasons": {},
        "review_records": [],
    }
    for church in churches:
        result = church["resolved_date"]
        canonical = result["canonical"]
        if canonical:
            report["resolved"] += 1
            source = canonical.get("source", "unknown")
            basis = canonical.get("basis", "unknown")
            report["by_source"][source] = (
                report["by_source"].get(source, 0) + 1
            )
            report["by_basis"][basis] = (
                report["by_basis"].get(basis, 0) + 1
            )
        else:
            report["unresolved"] += 1
            reason = result.get("reason", "unknown")
            report["unresolved_reasons"][reason] = (
                report["unresolved_reasons"].get(reason, 0) + 1
            )
            report["review_records"].append(
                {
                    "wikidata_id": church["wikidata_id"],
                    "name": church.get("derived", {}).get(
                        "display_name"
                    ),
                    "reason": reason,
                }
            )
    return report


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resolve conservative historical dates from Wikidata "
            "and optional BeWeb evidence."
        )
    )
    parser.add_argument(
        "--use-beweb",
        action="store_true",
        help="Use previously collected BeWeb evidence.",
    )
    args = parser.parse_args()

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run resolve_dates.py first."
        )
    churches = load_json(INPUT_FILE)
    evidence_by_qid = {}
    if args.use_beweb:
        if not EVIDENCE_FILE.exists():
            raise FileNotFoundError(
                f"{EVIDENCE_FILE} not found. Run enrich_beweb.py first."
            )
        evidence_by_qid = {
            church["wikidata_id"]: church.get(
                "source_evidence", {}
            ).get("beweb")
            for church in load_json(EVIDENCE_FILE)
        }

    for church in churches:
        beweb = copy.deepcopy(
            evidence_by_qid.get(church["wikidata_id"])
        )
        if beweb:
            church.setdefault("source_evidence", {})["beweb"] = beweb
        apply_result(
            church,
            resolve_record(church, beweb),
        )

    save_json(OUTPUT_FILE, churches)
    report = build_report(churches)
    save_json(REPORT_FILE, report)

    print()
    print("Historical date resolution complete")
    print("-----------------------------------")
    print("Total:", report["total"])
    print("Resolved:", report["resolved"])
    print("Unresolved:", report["unresolved"])
    print("By source:", json.dumps(report["by_source"], sort_keys=True))
    print("By basis:", json.dumps(report["by_basis"], sort_keys=True))
    print(f"Output: {OUTPUT_FILE}")
    print(f"Report: {REPORT_FILE}")


if __name__ == "__main__":
    main()
