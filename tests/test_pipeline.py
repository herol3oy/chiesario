import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_catalog
import build_web_data
import fetch_entities
from classify_types import type_review_required
from enrich_beweb import parse_history, parse_information
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
        self.assertEqual(entries[0]["building_part_raw"], "intero bene")
        self.assertIsNone(entries[0]["normalized_period"])
        self.assertEqual(entries[1]["intervention_raw"], "restauro")

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
