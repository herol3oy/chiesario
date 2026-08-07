import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_catalog
import build_web_data
import fetch_entities
from enrich_osm import build_query as build_osm_query
from enrich_commons import mark_pending_manual_date_records
from classify_types import type_review_required
from enrich_beweb import parse_history, parse_information
from resolve_historical_dates import (
    canonical_eligibility,
    normalize_period,
    resolve_record,
)
from resolve_historic_scope import (
    apply_historic_scope,
    resolve_historic_scope,
)


class HistoricScopeTests(unittest.TestCase):
    def church(self, start_year):
        canonical = (
            None
            if start_year is None
            else {"start_year": start_year}
        )
        return {
            "resolved_date": {"canonical": canonical},
            "derived": {},
        }

    def test_cutoff_and_unknown_values(self):
        self.assertEqual(
            resolve_historic_scope(self.church(1799)),
            "historic",
        )
        self.assertEqual(
            resolve_historic_scope(self.church(1800)),
            "modern",
        )
        self.assertEqual(
            resolve_historic_scope(self.church(None)),
            "unknown",
        )
        self.assertEqual(
            resolve_historic_scope(self.church(True)),
            "unknown",
        )

    def test_unknown_requires_review_at_evidence_stage(self):
        church = self.church(None)
        apply_historic_scope(church)
        self.assertTrue(
            church["derived"][
                "historic_scope_review_required"
            ]
        )

    def test_documentary_period_must_end_before_cutoff(self):
        church = self.church(1701)
        church["resolved_date"]["canonical"].update(
            {
                "end_year": 1800,
                "basis": "documentary_attestation",
            }
        )
        self.assertEqual(resolve_historic_scope(church), "unknown")


class TypeCompatibilityTests(unittest.TestCase):
    def test_priority_hierarchies_auto_resolve(self):
        examples = [
            ("cathedral", ["cathedral", "basilica", "church"]),
            ("basilica", ["basilica", "church"]),
            ("baptistery", ["baptistery", "chapel", "church"]),
            ("sacristy", ["sacristy", "chapel", "church"]),
            ("abbey", ["abbey", "monastery", "church"]),
        ]
        for selected, candidates in examples:
            with self.subTest(selected=selected):
                self.assertFalse(
                    type_review_required(selected, candidates)
                )

    def test_contradictory_types_still_require_review(self):
        self.assertTrue(
            type_review_required(
                "cathedral",
                ["cathedral", "monastery", "church"],
            )
        )


class CatalogStatusTests(unittest.TestCase):
    def church(self, scope):
        return {
            "derived": {
                "publishable_by_type": True,
                "historic_scope": scope,
                "historic_scope_review_required": scope == "unknown",
                "date_review_required": False,
                "coordinate_review_required": False,
                "type_review_required": False,
                "duplicate_review_required": False,
            },
            "resolved_coordinates": {
                "canonical": {
                    "latitude": 43.0,
                    "longitude": 11.0,
                    "source": "wikidata",
                }
            },
            "resolved_date": {
                "canonical": {
                    "display": "1700",
                    "kind": "year",
                    "start_year": 1700,
                    "end_year": 1700,
                    "source": "wikidata",
                }
            },
        }

    def test_unknown_is_withheld_not_review(self):
        self.assertEqual(
            build_catalog.determine_status(self.church("unknown")),
            "withheld",
        )

    def test_only_historic_can_be_ready(self):
        self.assertEqual(
            build_catalog.determine_status(self.church("historic")),
            "ready",
        )
        self.assertEqual(
            build_catalog.determine_status(self.church("modern")),
            "out_of_scope",
        )


class EntityRefreshTests(unittest.TestCase):
    def test_cache_is_used_only_in_resume_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            entities_file = Path(directory) / "entities.json"
            entities_file.write_text(
                json.dumps({"Q1": {"id": "Q1"}}),
                encoding="utf-8",
            )
            with patch.object(
                fetch_entities,
                "ENTITIES_FILE",
                entities_file,
            ):
                self.assertEqual(
                    fetch_entities.load_existing_entities(False),
                    {},
                )
                self.assertEqual(
                    fetch_entities.load_existing_entities(True),
                    {"Q1": {"id": "Q1"}},
                )


class OsmQueryTests(unittest.TestCase):
    def test_query_uses_exact_indexable_wikidata_values(self):
        query = build_osm_query(["Q1", "Q20"])
        self.assertIn('nwr["wikidata"="Q1"]', query)
        self.assertIn('nwr["wikidata"="Q20"]', query)
        self.assertNotIn('"wikidata"~', query)

    def test_query_rejects_invalid_qids(self):
        with self.assertRaises(ValueError):
            build_osm_query(["Q1)bad"])


class DeferredEnrichmentTests(unittest.TestCase):
    def test_pre1800_manual_date_keeps_late_enrichment(self):
        churches = [
            {
                "wikidata_id": "Q1",
                "derived": {"historic_scope": "unknown"},
            }
        ]
        mark_pending_manual_date_records(
            churches,
            {
                "records": {
                    "Q1": {
                        "canonical_date": {
                            "kind": "year",
                            "start_year": 1700,
                            "end_year": 1700,
                            "display": "1700",
                        }
                    }
                }
            },
        )
        self.assertTrue(
            churches[0]["derived"][
                "publication_enrichment_override_pending"
            ]
        )


class BeWebParserTests(unittest.TestCase):
    def test_structured_history_is_preserved_without_normalizing(self):
        html = """
        <ul class="datalist">
          <li><b>XI – XIII</b> (costruzione intero bene)
            <ul><li>Edificio attuale del XII secolo su resti precedenti.</li></ul>
          </li>
          <li><b>1931 – 1933</b> (restauro facciata)
            <ul><li>Restauro della facciata.</li></ul>
          </li>
        </ul>
        """
        entries = parse_history(html)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["period_raw"], "XI – XIII")
        self.assertEqual(entries[0]["intervention_raw"], "costruzione")
        self.assertEqual(entries[0]["evidence_type"], "construction")
        self.assertEqual(entries[0]["building_part_raw"], "intero bene")
        self.assertIsNone(entries[0]["normalized_period"])
        self.assertEqual(entries[1]["intervention_raw"], "restauro")
        self.assertEqual(entries[1]["evidence_type"], "restoration")

    def test_record_provenance_fields_are_extracted(self):
        html = """
        <h4>Data di creazione</h4><p>10/3/2011</p>
        <h4>Data di pubblicazione</h4><p>03/10/2024</p>
        <h4>Fonte dei dati</h4>
        <p><a href="https://example.test/source">Scheda di censimento</a></p>
        """
        result = parse_information(html)
        self.assertEqual(result["created_at_raw"], "10/3/2011")
        self.assertEqual(
            result["data_source_url"],
            "https://example.test/source",
        )

    def test_generic_history_label_uses_narrow_origin_language(self):
        html = """
        <ul class="datalist">
          <li><b>XI</b> (storia intero bene)
            <ul><li>La chiesa ha origini antiche e fu edificata in questo periodo.</li></ul>
          </li>
        </ul>
        """
        self.assertEqual(
            parse_history(html)[0]["evidence_type"],
            "origin",
        )

    def test_devotion_origin_does_not_become_building_origin(self):
        html = """
        <ul class="datalist">
          <li><b>XVIII - XIX</b> (storia intero bene)
            <ul><li>La costruzione dell'edificio risale alla metà
            dell'Ottocento. La devozione locale ha origini remote.</li></ul>
          </li>
        </ul>
        """
        self.assertEqual(
            parse_history(html)[0]["evidence_type"],
            "other",
        )

    def test_reconstruction_wording_overrides_construction_label(self):
        html = """
        <ul class="datalist">
          <li><b>XVIII - 1872</b> (costruzione intero bene)
            <ul><li>La chiesa attuale venne realizzata nel 1872
            ristrutturando una costruzione preesistente.</li></ul>
          </li>
        </ul>
        """
        self.assertEqual(
            parse_history(html)[0]["evidence_type"],
            "reconstruction",
        )

    def test_inauguration_only_is_not_construction(self):
        html = """
        <ul class="datalist">
          <li><b>1932</b> (costruzione intero bene)
            <ul><li>La chiesa fu inaugurata nel 1932.</li></ul>
          </li>
        </ul>
        """
        self.assertEqual(
            parse_history(html)[0]["evidence_type"],
            "consecration",
        )


class HistoricalDateResolverTests(unittest.TestCase):
    def church(self, year=None):
        canonical = None
        candidates = []
        if year is not None:
            canonical = {
                "kind": "year",
                "start_year": year,
                "end_year": year,
                "display": str(year),
                "statement_id": "Q1$statement",
            }
            candidates = [canonical]
        return {
            "wikidata_id": "Q1",
            "resolved_date": {
                "canonical": canonical,
                "candidates": candidates,
                "review_required": canonical is None,
                "reason": "unambiguous" if canonical else "no_usable_date",
            },
            "derived": {"display_name": "Chiesa di prova"},
        }

    def beweb(self, entries):
        return {
            "beweb_id": "12345",
            "url": (
                "https://www.beweb.chiesacattolica.it/"
                "edificidiculto/edificio/12345/"
            ),
            "status": "structured_date",
            "historical_evidence": [
                {
                    "source_section": "Notizie storiche",
                    "entry_ordinal": index,
                    "period_raw": period,
                    "evidence_type": evidence_type,
                    "building_part_raw": None,
                    "short_evidence_excerpt": None,
                    "normalized_period": None,
                }
                for index, (period, evidence_type) in enumerate(entries)
            ],
        }

    def test_period_normalization_preserves_precision(self):
        self.assertEqual(
            normalize_period("sec. XIII"),
            {
                "kind": "century",
                "start_year": 1201,
                "end_year": 1300,
                "display": "13th century",
            },
        )
        self.assertEqual(
            normalize_period("1969-1970")["kind"],
            "year_range",
        )
        self.assertEqual(
            normalize_period("circa 1420")["kind"],
            "circa_year",
        )
        self.assertEqual(
            normalize_period("XVIII ‐ 1872")["kind"],
            "mixed_range",
        )
        self.assertIsNone(normalize_period("metà del XIII secolo"))

    def test_modern_wikidata_reconstruction_does_not_hide_origin(self):
        result = resolve_record(
            self.church(1911),
            self.beweb(
                [
                    ("sec. XIV", "origin"),
                    ("1911", "reconstruction"),
                ]
            ),
        )
        self.assertEqual(result["canonical"]["source"], "beweb")
        self.assertEqual(result["canonical"]["start_year"], 1301)
        self.assertEqual(
            result["reason"],
            "beweb_disambiguates_wikidata_phase",
        )

    def test_unexplained_source_conflict_requires_review(self):
        result = resolve_record(
            self.church(1911),
            self.beweb([("sec. XIV", "origin")]),
        )
        self.assertIsNone(result["canonical"])
        self.assertTrue(result["review_required"])

    def test_documentary_mention_is_not_labeled_construction(self):
        result = resolve_record(
            self.church(),
            self.beweb([("1354", "documentary_attestation")]),
        )
        self.assertEqual(
            result["canonical"]["basis"],
            "documentary_attestation",
        )
        self.assertEqual(result["canonical"]["start_year"], 1354)

    def test_building_component_cannot_become_canonical(self):
        eligible, reason = canonical_eligibility(
            {
                "evidence_type": "construction",
                "building_part_raw": "campanile",
                "context_raw": "costruzione campanile",
            }
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, "building_component:campanile")

    def test_whole_building_construction_remains_eligible(self):
        eligible, reason = canonical_eligibility(
            {
                "evidence_type": "construction",
                "building_part_raw": "intero bene",
                "context_raw": "costruzione intero bene",
            }
        )
        self.assertTrue(eligible)
        self.assertIsNone(reason)

    def test_combined_predecessor_and_current_phase_is_ineligible(self):
        eligible, reason = canonical_eligibility(
            {
                "evidence_type": "construction",
                "building_part_raw": "intero bene",
                "context_raw": "costruzione intero bene",
                "short_evidence_excerpt": (
                    "La chiesa fu edificata nel XIX secolo sui resti "
                    "di un'antica basilica del V secolo."
                ),
                "normalized_period": {
                    "start_year": 401,
                    "end_year": 1900,
                },
            }
        )
        self.assertFalse(eligible)
        self.assertEqual(
            reason,
            "combined_distinct_historical_phases",
        )

    def test_explicitly_uncertain_origin_is_ineligible(self):
        eligible, reason = canonical_eligibility(
            {
                "evidence_type": "origin",
                "building_part_raw": "intero bene",
                "context_raw": "origine intero bene",
                "short_evidence_excerpt": (
                    "Secondo la tradizione la chiesa sarebbe stata "
                    "fondata nel XIII secolo."
                ),
                "normalized_period": {
                    "start_year": 1201,
                    "end_year": 1300,
                },
            }
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, "source_language_is_uncertain")

    def test_inferred_architectural_date_is_ineligible(self):
        eligible, reason = canonical_eligibility(
            {
                "evidence_type": "construction",
                "building_part_raw": "carattere generale",
                "context_raw": "costruzione carattere generale",
                "short_evidence_excerpt": (
                    "La chiesa è del XIV secolo, come si può "
                    "evincere dai particolari architettonici."
                ),
                "normalized_period": {
                    "start_year": 1301,
                    "end_year": 1400,
                },
            }
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, "source_language_is_uncertain")

    def test_pronaos_date_is_a_component_phase(self):
        eligible, reason = canonical_eligibility(
            {
                "evidence_type": "construction",
                "building_part_raw": "pronao",
                "context_raw": "costruzione pronao",
                "normalized_period": {
                    "start_year": 1922,
                    "end_year": 1922,
                },
            }
        )
        self.assertFalse(eligible)
        self.assertEqual(reason, "building_component:pronao")


class WebDataTests(unittest.TestCase):
    def feature(self, qid, region):
        return {
            "type": "Feature",
            "id": qid,
            "geometry": {
                "type": "Point",
                "coordinates": [11.0, 43.0],
            },
            "properties": {
                "id": qid,
                "name": f"Church {qid}",
                "church_type": "church",
                "region": region,
                "historic_scope": "historic",
                "date_display": "1700",
                "start_year": 1700,
                "date_source": "wikidata",
                "date_basis": "inception",
                "date_sources": [],
                "historical_phases": [],
                "wikidata_url": (
                    f"https://www.wikidata.org/wiki/{qid}"
                ),
                "hero_image": None,
            },
        }

    def test_regions_merge_deterministically(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            regions = {
                "tuscany": {
                    "name": "Tuscany",
                    "wikidata_id": "Q1273",
                    "publish": True,
                }
            }
            catalog = data_dir / "tuscany" / "catalog"
            catalog.mkdir(parents=True)
            (catalog / "churches.geojson").write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            self.feature("Q2", "Tuscany"),
                            self.feature("Q1", "Tuscany"),
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(build_web_data, "DATA_DIR", data_dir):
                geojson, manifest = build_web_data.merge_geojson(
                    regions,
                    ["tuscany"],
                )
            self.assertEqual(
                [item["properties"]["id"] for item in geojson["features"]],
                ["Q1", "Q2"],
            )
            self.assertEqual(manifest["total_features"], 2)


class TuscanyRegressionTests(unittest.TestCase):
    def test_reference_catalog_counts(self):
        root = Path(__file__).resolve().parents[1]
        catalog_dir = (
            root / "data" / "regions" / "tuscany" / "catalog"
        )
        report = json.loads(
            (catalog_dir / "catalog_report.json").read_text(
                encoding="utf-8"
            )
        )
        geojson = json.loads(
            (catalog_dir / "churches.geojson").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["total_records"], 194)
        self.assertEqual(
            report["status_counts"],
            {
                "ready": 174,
                "out_of_scope": 19,
                "duplicate": 1,
            },
        )
        self.assertEqual(report["ready_with_hero_image"], 164)
        self.assertEqual(report["ready_without_hero_image"], 10)
        self.assertEqual(len(geojson["features"]), 174)


if __name__ == "__main__":
    unittest.main()
