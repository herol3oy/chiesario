import type {
  CatalogFilters,
  ChurchFeature,
} from "./types";


export const TYPE_LABELS: Record<string, string> = {
  church: "Chiesa",
  cathedral: "Cattedrale",
  basilica: "Basilica",
  former_church: "Ex chiesa",
};


function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("it")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}


export function centuryForYear(year: number): number {
  return Math.floor((year - 1) / 100) + 1;
}


export function romanNumeral(value: number): string {
  const numerals: Array<[number, string]> = [
    [1000, "M"],
    [900, "CM"],
    [500, "D"],
    [400, "CD"],
    [100, "C"],
    [90, "XC"],
    [50, "L"],
    [40, "XL"],
    [10, "X"],
    [9, "IX"],
    [5, "V"],
    [4, "IV"],
    [1, "I"],
  ];
  let remaining = value;
  let result = "";
  for (const [amount, numeral] of numerals) {
    while (remaining >= amount) {
      result += numeral;
      remaining -= amount;
    }
  }
  return result;
}


export function centuryLabel(century: number): string {
  return `${romanNumeral(century)} secolo`;
}


export function filterChurches(
  features: ChurchFeature[],
  filters: CatalogFilters,
): ChurchFeature[] {
  const query = normalize(filters.query.trim());

  return features.filter((feature) => {
    const properties = feature.properties;
    if (
      query
      && !normalize(properties.name).includes(query)
    ) {
      return false;
    }
    if (
      filters.churchType
      && properties.church_type !== filters.churchType
    ) {
      return false;
    }
    if (
      filters.region
      && properties.region !== filters.region
    ) {
      return false;
    }
    if (
      filters.century
      && centuryForYear(properties.start_year)
        !== Number(filters.century)
    ) {
      return false;
    }
    return true;
  });
}


export function sortChurches(
  features: ChurchFeature[],
): ChurchFeature[] {
  return [...features].sort((left, right) => {
    const yearDifference = (
      left.properties.start_year
      - right.properties.start_year
    );
    if (yearDifference !== 0) {
      return yearDifference;
    }
    return left.properties.name.localeCompare(
      right.properties.name,
      "it",
    );
  });
}


export function uniqueValues(
  features: ChurchFeature[],
  field: "church_type" | "region",
): string[] {
  return Array.from(
    new Set(features.map((item) => item.properties[field])),
  ).sort((left, right) => left.localeCompare(right, "it"));
}


export function availableCenturies(
  features: ChurchFeature[],
): number[] {
  return Array.from(
    new Set(
      features.map((item) => (
        centuryForYear(item.properties.start_year)
      )),
    ),
  ).sort((left, right) => left - right);
}
