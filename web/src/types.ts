export interface ChurchProperties {
  id: string;
  slug: string;
  name: string;
  church_type: string;
  region: string;
  historic_scope: "historic";
  date_display: string;
  date_kind: string;
  start_year: number;
  end_year: number;
  date_source: string | null;
  date_basis: string;
  date_source_name: string | null;
  date_source_url: string | null;
  date_sources: DateSource[];
  historical_phases: HistoricalPhase[];
  coordinate_source: string | null;
  hero_image: string | null;
  hero_filename: string | null;
  hero_description_url: string | null;
  hero_artist: string | null;
  hero_license_name: string | null;
  hero_license_url: string | null;
  website: string | null;
  wikidata_url: string;
  wikipedia_url: string | null;
  osm_url: string | null;
}

export interface DateSource {
  name: string;
  url: string | null;
  source_id: string | null;
}

export interface HistoricalPeriod {
  kind: string;
  start_year: number;
  end_year: number;
  display: string;
}

export interface HistoricalPhase {
  evidence_type: string;
  period: HistoricalPeriod;
  period_raw: string | null;
  building_part: string | null;
  source_name: string | null;
  source_url: string | null;
}

export interface ChurchFeature {
  type: "Feature";
  id: string;
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  properties: ChurchProperties;
}

export interface ChurchFeatureCollection {
  type: "FeatureCollection";
  features: ChurchFeature[];
}

export interface CatalogFilters {
  query: string;
  churchType: string;
  century: string;
  region: string;
}
