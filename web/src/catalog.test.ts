import { describe, expect, it } from "vitest";

import {
  centuryForYear,
  filterChurches,
  formatChurchDate,
  formatPeriod,
  sortChurches,
} from "./catalog";
import type { ChurchFeature } from "./types";


function church(
  id: string,
  name: string,
  year: number,
  type = "church",
): ChurchFeature {
  return {
    type: "Feature",
    id,
    geometry: {
      type: "Point",
      coordinates: [11, 43],
    },
    properties: {
      id,
      slug: id.toLocaleLowerCase(),
      name,
      church_type: type,
      region: "Tuscany",
      historic_scope: "historic",
      date_display: String(year),
      date_kind: "year",
      start_year: year,
      end_year: year,
      date_source: "wikidata",
      date_basis: "inception",
      date_source_name: null,
      date_source_url: null,
      date_sources: [],
      historical_phases: [],
      coordinate_source: "wikidata",
      hero_image: null,
      hero_filename: null,
      hero_description_url: null,
      hero_artist: null,
      hero_license_name: null,
      hero_license_url: null,
      website: null,
      wikidata_url: `https://www.wikidata.org/wiki/${id}`,
      wikipedia_url: null,
      osm_url: null,
    },
  };
}


describe("catalog filtering", () => {
  const records = [
    church("Q1", "Chiesa di Sant'Agata", 1200),
    church("Q2", "Basilica di San Luca", 1700, "basilica"),
    church("Q3", "Cattedrale di Firenze", 1400, "cathedral"),
  ];

  it("matches Italian names without requiring accents", () => {
    const result = filterChurches(records, {
      query: "sant agata",
      churchType: "",
      century: "",
      region: "",
    });
    expect(result.map((item) => item.id)).toEqual(["Q1"]);
  });

  it("combines type and century filters", () => {
    const result = filterChurches(records, {
      query: "",
      churchType: "basilica",
      century: "17",
      region: "Tuscany",
    });
    expect(result.map((item) => item.id)).toEqual(["Q2"]);
  });

  it("sorts oldest first and then by Italian name", () => {
    const result = sortChurches([
      church("Q2", "Zeta", 1500),
      church("Q1", "Alfa", 1500),
      church("Q3", "Medio", 1200),
    ]);
    expect(result.map((item) => item.id)).toEqual([
      "Q3",
      "Q1",
      "Q2",
    ]);
  });
});


describe("century calculation", () => {
  it("uses historical century boundaries", () => {
    expect(centuryForYear(1200)).toBe(12);
    expect(centuryForYear(1201)).toBe(13);
    expect(centuryForYear(1800)).toBe(18);
  });

  it("formats structured historical periods in Italian", () => {
    expect(formatPeriod({
      kind: "century",
      start_year: 1201,
      end_year: 1300,
      display: "13th century",
    })).toBe("XIII secolo");
    expect(formatPeriod({
      kind: "year_range",
      start_year: 1690,
      end_year: 1702,
      display: "1690–1702",
    })).toBe("1690–1702");
    expect(formatPeriod({
      kind: "mixed_range",
      start_year: 1701,
      end_year: 1872,
      display: "18th century–1872",
    })).toBe("XVIII secolo–1872");
  });

  it("labels documentary evidence without calling it construction", () => {
    const record = church("Q4", "Chiesa documentata", 1354);
    record.properties.date_basis = "documentary_attestation";
    expect(formatChurchDate(record.properties)).toBe(
      "Documentata entro il 1354",
    );
  });
});
