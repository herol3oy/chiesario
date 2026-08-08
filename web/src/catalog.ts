import { i18n } from "./i18n";

import type {
  CatalogFilters,
  ChurchFeature,
  ChurchProperties,
  HistoricalPeriod,
} from "./types";


export function typeLabel(
  type: string,
): string {
  return (
    i18n.t(
      `types.${type}`,
      type,
    )
  );
}


export function phaseLabel(
  phase: string,
): string {
  return (
    i18n.t(
      `phases.${phase}`,
      phase,
    )
  );
}


function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase(i18n.language)
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


function ordinalSuffix(value: number): string {
  const lastDigit = value % 10;
  const lastTwoDigits = value % 100;

  if (
    lastTwoDigits >= 11
    && lastTwoDigits <= 13
  ) {
    return `${value}th`;
  }

  if (lastDigit === 1) {
    return `${value}st`;
  }

  if (lastDigit === 2) {
    return `${value}nd`;
  }

  if (lastDigit === 3) {
    return `${value}rd`;
  }

  return `${value}th`;
}


export function centuryLabel(century: number): string {
  if (i18n.language === "it") {
    return i18n.t(
      "date.century",
      {
        century: romanNumeral(century),
      },
    );
  }

  return i18n.t(
    "date.century",
    {
      century: ordinalSuffix(century),
    },
  );
}


export function formatPeriod(
  period: Pick<
    HistoricalPeriod,
    "kind" | "start_year" | "end_year" | "display"
  >,
): string {
  if (period.kind === "year") {
    return String(period.start_year);
  }

  if (period.kind === "circa_year") {
    return i18n.t(
      "date.circa",
      {
        year: period.start_year,
      },
    );
  }

  if (period.kind === "decade") {
    return i18n.t(
      "date.decade",
      {
        year: period.start_year,
      },
    );
  }

  if (period.kind === "year_range") {
    return `${period.start_year}–${period.end_year}`;
  }

  if (period.kind === "century") {
    return centuryLabel(
      centuryForYear(period.start_year),
    );
  }

  if (period.kind === "century_range") {
    const first = centuryForYear(period.start_year);
    const last = centuryForYear(period.end_year);

    if (i18n.language === "it") {
      return `${romanNumeral(first)}–${romanNumeral(last)} secolo`;
    }

    return `${ordinalSuffix(first)}–${ordinalSuffix(last)} century`;
  }

  if (period.kind === "mixed_range") {
    const first = centuryForYear(period.start_year);

    if (i18n.language === "it") {
      return `${romanNumeral(first)} secolo–${period.end_year}`;
    }

    return `${ordinalSuffix(first)} century–${period.end_year}`;
  }

  return period.display;
}


export function formatChurchDate(
  properties: ChurchProperties,
): string {
  const period = formatPeriod({
    kind: properties.date_kind,
    start_year: properties.start_year,
    end_year: properties.end_year,
    display: properties.date_display,
  });

  if (properties.date_basis === "documentary_attestation") {
    return i18n.t(
      "date.documentedBy",
      { period },
    );
  }

  if (properties.date_basis === "predecessor") {
    return i18n.t(
      "date.originsDocumentedBy",
      { period },
    );
  }

  return period;
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
      i18n.language,
    );
  });
}


export function uniqueValues(
  features: ChurchFeature[],
  field: "church_type" | "region",
): string[] {
  return Array.from(
    new Set(features.map((item) => item.properties[field])),
  ).sort((left, right) => left.localeCompare(right, i18n.language));
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
