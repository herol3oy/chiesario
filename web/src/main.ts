import {
  GeoJSONSource,
  LngLatBounds,
  Map,
  NavigationControl,
  setWorkerUrl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  PHASE_LABELS,
  TYPE_LABELS,
  availableCenturies,
  centuryLabel,
  filterChurches,
  formatChurchDate,
  formatPeriod,
  sortChurches,
  uniqueValues,
} from "./catalog";
import "./style.css";
import type {
  CatalogFilters,
  ChurchFeature,
  ChurchFeatureCollection,
} from "./types";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";


setWorkerUrl(workerUrl);

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("Contenitore #app non trovato");
}

app.innerHTML = `
  <div class="site-shell" data-mobile-view="list">
    <header class="site-header">
      <div>
        <p class="eyebrow">Atlante storico</p>
        <h1>Chiese storiche d’Italia</h1>
        <p class="intro">
          Un catalogo verificato di chiese costruite o fondate prima del 1800,
          con fonti e attribuzioni conservate.
        </p>
      </div>
      <div class="view-switch" aria-label="Cambia vista">
        <button type="button" data-view="list" aria-pressed="true">Elenco</button>
        <button type="button" data-view="map" aria-pressed="false">Mappa</button>
      </div>
    </header>

    <main class="workspace">
      <aside class="directory" aria-label="Elenco delle chiese">
        <form class="filters" id="filters-form">
          <label class="search-field">
            <span>Cerca per nome</span>
            <input id="search" type="search" placeholder="Es. Santa Maria" autocomplete="off" />
          </label>
          <div class="filter-grid">
            <label>
              <span>Tipologia</span>
              <select id="type-filter"><option value="">Tutte</option></select>
            </label>
            <label>
              <span>Secolo</span>
              <select id="century-filter"><option value="">Tutti</option></select>
            </label>
            <label>
              <span>Regione</span>
              <select id="region-filter"><option value="">Tutte</option></select>
            </label>
          </div>
          <button class="clear-filters" id="clear-filters" type="button">Azzera filtri</button>
        </form>

        <div class="results-heading">
          <h2>Chiese verificate</h2>
          <output id="result-count" aria-live="polite">Caricamento…</output>
        </div>
        <div id="status-message" class="status-message" role="status"></div>
        <div id="church-list" class="church-list"></div>
      </aside>

      <section class="map-panel" aria-label="Mappa delle chiese">
        <div id="map"></div>
        <p class="map-credit">Mappa © OpenStreetMap · OpenFreeMap</p>
      </section>

      <aside id="detail-panel" class="detail-panel" aria-label="Dettagli della chiesa" hidden>
        <button id="close-detail" class="close-detail" type="button" aria-label="Chiudi i dettagli">×</button>
        <div id="detail-content"></div>
      </aside>
    </main>
  </div>
`;


function element<T extends Element>(selector: string): T {
  const result = document.querySelector<T>(selector);
  if (!result) {
    throw new Error(`Elemento non trovato: ${selector}`);
  }
  return result;
}


const shell = element<HTMLDivElement>(".site-shell");
const searchInput = element<HTMLInputElement>("#search");
const typeSelect = element<HTMLSelectElement>("#type-filter");
const centurySelect = element<HTMLSelectElement>("#century-filter");
const regionSelect = element<HTMLSelectElement>("#region-filter");
const clearFilters = element<HTMLButtonElement>("#clear-filters");
const resultCount = element<HTMLOutputElement>("#result-count");
const statusMessage = element<HTMLDivElement>("#status-message");
const churchList = element<HTMLDivElement>("#church-list");
const detailPanel = element<HTMLElement>("#detail-panel");
const detailContent = element<HTMLDivElement>("#detail-content");
const closeDetail = element<HTMLButtonElement>("#close-detail");
const viewButtons = Array.from(
  document.querySelectorAll<HTMLButtonElement>("[data-view]"),
);

let allFeatures: ChurchFeature[] = [];
let filteredFeatures: ChurchFeature[] = [];
let selectedId: string | null = null;
let map: Map | null = null;
let detailReturnFocus: HTMLElement | null = null;

const REGION_LABELS: Record<string, string> = {
  Tuscany: "Toscana",
  Umbria: "Umbria",
  Marche: "Marche",
  Molise: "Molise",
};

const filters: CatalogFilters = {
  query: "",
  churchType: "",
  century: "",
  region: "",
};


function option(value: string, label: string): HTMLOptionElement {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  return item;
}


function configureFilters(): void {
  for (const type of uniqueValues(allFeatures, "church_type")) {
    typeSelect.appendChild(option(type, TYPE_LABELS[type] ?? type));
  }
  for (const century of availableCenturies(allFeatures)) {
    centurySelect.appendChild(
      option(String(century), centuryLabel(century)),
    );
  }
  for (const region of uniqueValues(allFeatures, "region")) {
    regionSelect.appendChild(
      option(region, REGION_LABELS[region] ?? region),
    );
  }
  if (regionSelect.options.length === 2) {
    regionSelect.value = regionSelect.options[1]?.value ?? "";
    regionSelect.disabled = true;
    filters.region = regionSelect.value;
  }
}


function setMobileView(view: string): void {
  shell.dataset.mobileView = view;
  for (const button of viewButtons) {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.view === view),
    );
  }
  if (view === "map") {
    window.setTimeout(() => map?.resize(), 100);
  }
}


function createLink(
  label: string,
  url: string | null,
  className = "source-link",
): HTMLAnchorElement | null {
  if (!url) {
    return null;
  }
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.className = className;
  link.textContent = label;
  return link;
}


function updateSelectedLayer(): void {
  if (!map?.getLayer("selected-church")) {
    return;
  }
  map.setFilter(
    "selected-church",
    ["==", ["get", "id"], selectedId ?? ""],
  );
}


function updateUrl(id: string | null): void {
  const url = new URL(window.location.href);
  if (id) {
    url.searchParams.set("church", id);
  } else {
    url.searchParams.delete("church");
  }
  window.history.replaceState({}, "", url);
}


function showDetails(feature: ChurchFeature, moveMap = false): void {
  if (detailPanel.hidden && document.activeElement instanceof HTMLElement) {
    detailReturnFocus = document.activeElement;
  }
  selectedId = feature.properties.id;
  updateSelectedLayer();
  updateUrl(selectedId);
  detailContent.replaceChildren();

  const properties = feature.properties;
  const heading = document.createElement("p");
  heading.className = "detail-eyebrow";
  heading.textContent = [
    TYPE_LABELS[properties.church_type] ?? properties.church_type,
    REGION_LABELS[properties.region] ?? properties.region,
  ].join(" · ");
  detailContent.appendChild(heading);

  const title = document.createElement("h2");
  title.textContent = properties.name;
  detailContent.appendChild(title);

  if (properties.hero_image) {
    const figure = document.createElement("figure");
    const image = document.createElement("img");
    image.src = properties.hero_image;
    image.alt = properties.name;
    figure.appendChild(image);

    if (
      properties.hero_artist
      || properties.hero_license_name
      || properties.hero_description_url
    ) {
      const caption = document.createElement("figcaption");
      const commonsLink = createLink(
        properties.hero_artist || "Immagine su Wikimedia Commons",
        properties.hero_description_url,
      );
      if (commonsLink) {
        caption.appendChild(commonsLink);
      } else {
        caption.textContent = properties.hero_artist ?? "";
      }
      const licenseLink = createLink(
        properties.hero_license_name ?? "Licenza",
        properties.hero_license_url,
      );
      if (licenseLink && properties.hero_license_url) {
        caption.append(" · ", licenseLink);
      } else if (properties.hero_license_name) {
        caption.append(` · ${properties.hero_license_name}`);
      }
      figure.appendChild(caption);
    }
    detailContent.appendChild(figure);
  }

  const dateBlock = document.createElement("section");
  dateBlock.className = "detail-section";
  const dateTitle = document.createElement("h3");
  dateTitle.textContent = "Data storica";
  const dateValue = document.createElement("p");
  dateValue.className = "primary-date";
  dateValue.textContent = formatChurchDate(properties);
  dateBlock.append(dateTitle, dateValue);

  const dateSources = properties.date_sources.length
    ? properties.date_sources
    : [{
        name: properties.date_source_name ?? (
          properties.date_source === "manual"
            ? "Fonte verificata manualmente"
            : properties.date_source === "wikidata"
              ? "Wikidata"
              : "Fonte non specificata"
        ),
        url: properties.date_source_url ?? (
          properties.date_source === "wikidata"
            ? properties.wikidata_url
            : null
        ),
        source_id: null,
      }];
  const dateSourceList = document.createElement("div");
  dateSourceList.className = "date-sources";
  for (const source of dateSources) {
    const sourceLink = createLink(source.name, source.url);
    if (sourceLink) {
      dateSourceList.appendChild(sourceLink);
    } else {
      const sourceText = document.createElement("span");
      sourceText.className = "source-note";
      sourceText.textContent = source.name;
      dateSourceList.appendChild(sourceText);
    }
  }
  dateBlock.appendChild(dateSourceList);
  detailContent.appendChild(dateBlock);

  if (properties.historical_phases.length) {
    const phasesBlock = document.createElement("section");
    phasesBlock.className = "detail-section";
    const phasesTitle = document.createElement("h3");
    phasesTitle.textContent = "Fasi storiche documentate";
    const phasesList = document.createElement("ul");
    phasesList.className = "historical-phases";
    for (const phase of properties.historical_phases) {
      const item = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = (
        PHASE_LABELS[phase.evidence_type]
        ?? PHASE_LABELS.other
      );
      const period = document.createElement("span");
      period.textContent = formatPeriod(phase.period);
      item.append(label, period);
      if (phase.building_part) {
        const part = document.createElement("small");
        part.textContent = phase.building_part;
        item.appendChild(part);
      }
      const phaseSource = createLink(
        phase.source_name ?? "Fonte",
        phase.source_url,
      );
      if (phaseSource) {
        item.appendChild(phaseSource);
      }
      phasesList.appendChild(item);
    }
    phasesBlock.append(phasesTitle, phasesList);
    detailContent.appendChild(phasesBlock);
  }

  const sources = document.createElement("section");
  sources.className = "detail-section";
  const sourcesTitle = document.createElement("h3");
  sourcesTitle.textContent = "Fonti e collegamenti";
  const sourceLinks = document.createElement("div");
  sourceLinks.className = "source-links";
  const links = [
    createLink("Wikidata", properties.wikidata_url),
    createLink("OpenStreetMap", properties.osm_url),
    createLink("Sito ufficiale", properties.website),
  ].filter((link): link is HTMLAnchorElement => link !== null);
  sourceLinks.append(...links);
  sources.append(sourcesTitle, sourceLinks);
  detailContent.appendChild(sources);

  detailPanel.hidden = false;
  if (moveMap && map) {
    map.flyTo({
      center: feature.geometry.coordinates,
      zoom: Math.max(map.getZoom(), 13),
      essential: true,
    });
  }
}


function hideDetails(restoreFocus = false): void {
  selectedId = null;
  detailPanel.hidden = true;
  updateSelectedLayer();
  updateUrl(null);
  if (restoreFocus) {
    detailReturnFocus?.focus();
  }
}


function renderList(): void {
  churchList.replaceChildren();
  resultCount.textContent = `${filteredFeatures.length} risultati`;
  statusMessage.textContent = filteredFeatures.length
    ? ""
    : "Nessuna chiesa corrisponde ai filtri selezionati.";

  const fragment = document.createDocumentFragment();
  for (const feature of filteredFeatures) {
    const properties = feature.properties;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "church-card";
    card.dataset.qid = properties.id;
    card.setAttribute(
      "aria-label",
      `Apri ${properties.name}, ${formatChurchDate(properties)}`,
    );

    if (properties.hero_image) {
      const image = document.createElement("img");
      image.src = properties.hero_image;
      image.alt = "";
      image.loading = "lazy";
      card.appendChild(image);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "image-placeholder";
      placeholder.setAttribute("aria-hidden", "true");
      placeholder.textContent = "†";
      card.appendChild(placeholder);
    }

    const copy = document.createElement("span");
    copy.className = "card-copy";
    const title = document.createElement("strong");
    title.textContent = properties.name;
    const metadata = document.createElement("span");
    metadata.textContent = [
      formatChurchDate(properties),
      TYPE_LABELS[properties.church_type] ?? properties.church_type,
    ].join(" · ");
    copy.append(title, metadata);
    card.appendChild(copy);

    card.addEventListener("click", () => {
      showDetails(feature, true);
      setMobileView("map");
    });
    fragment.appendChild(card);
  }
  churchList.appendChild(fragment);
}


function filteredCollection(): ChurchFeatureCollection {
  return {
    type: "FeatureCollection",
    features: filteredFeatures,
  };
}


function applyFilters(): void {
  filteredFeatures = sortChurches(
    filterChurches(allFeatures, filters),
  );
  renderList();
  const source = map?.getSource("churches") as GeoJSONSource | undefined;
  if (source) {
    source.setData(filteredCollection());
  }
  if (
    selectedId
    && !filteredFeatures.some((item) => item.properties.id === selectedId)
  ) {
    hideDetails();
  }
}


function fitCatalogBounds(instance: Map): void {
  if (!allFeatures.length) {
    return;
  }
  const bounds = new LngLatBounds();
  for (const feature of allFeatures) {
    bounds.extend(feature.geometry.coordinates);
  }
  instance.fitBounds(bounds, {
    padding: 64,
    maxZoom: 8,
    duration: 0,
  });
}


function initializeMap(): void {
  map = new Map({
    container: "map",
    style: (
      import.meta.env.VITE_MAP_STYLE_URL
      ?? "https://tiles.openfreemap.org/styles/liberty"
    ),
    center: [11.0, 43.3],
    zoom: 6.5,
  });
  map.addControl(new NavigationControl(), "top-right");

  map.on("load", () => {
    if (!map) {
      return;
    }
    map.addSource("churches", {
      type: "geojson",
      data: filteredCollection(),
      cluster: true,
      clusterMaxZoom: 12,
      clusterRadius: 48,
    });
    map.addLayer({
      id: "clusters",
      type: "circle",
      source: "churches",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": "#9f6a31",
        "circle-radius": ["step", ["get", "point_count"], 18, 20, 24, 50, 30],
        "circle-stroke-color": "#f6eddd",
        "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "cluster-count",
      type: "symbol",
      source: "churches",
      filter: ["has", "point_count"],
      layout: {
        "text-field": "{point_count_abbreviated}",
        "text-size": 12,
      },
      paint: { "text-color": "#ffffff" },
    });
    map.addLayer({
      id: "churches",
      type: "circle",
      source: "churches",
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": "#6e331f",
        "circle-radius": 6,
        "circle-stroke-color": "#fffaf1",
        "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "selected-church",
      type: "circle",
      source: "churches",
      filter: ["==", ["get", "id"], selectedId ?? ""],
      paint: {
        "circle-color": "#f6c667",
        "circle-radius": 11,
        "circle-stroke-color": "#4a2117",
        "circle-stroke-width": 3,
      },
    });

    map.on("click", "clusters", async (event) => {
      if (!map) {
        return;
      }
      const feature = map.queryRenderedFeatures(
        event.point,
        { layers: ["clusters"] },
      )[0];
      if (!feature || feature.geometry.type !== "Point") {
        return;
      }
      const clusterId = feature.properties?.cluster_id as number;
      const source = map.getSource("churches") as GeoJSONSource;
      const zoom = await source.getClusterExpansionZoom(clusterId);
      map.easeTo({
        center: feature.geometry.coordinates as [number, number],
        zoom,
      });
    });

    map.on("click", "churches", (event) => {
      const qid = event.features?.[0]?.properties?.id as string | undefined;
      const feature = allFeatures.find((item) => item.properties.id === qid);
      if (feature) {
        showDetails(feature);
      }
    });

    for (const layer of ["clusters", "churches"]) {
      map.on("mouseenter", layer, () => {
        if (map) {
          map.getCanvas().style.cursor = "pointer";
        }
      });
      map.on("mouseleave", layer, () => {
        if (map) {
          map.getCanvas().style.cursor = "";
        }
      });
    }

    fitCatalogBounds(map);
    const requestedId = new URL(window.location.href)
      .searchParams.get("church");
    const requested = allFeatures.find(
      (item) => item.properties.id === requestedId,
    );
    if (requested) {
      showDetails(requested, true);
    }
  });
}


async function loadCatalog(): Promise<void> {
  try {
    const response = await fetch(
      `${import.meta.env.BASE_URL}data/churches.geojson`,
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json() as ChurchFeatureCollection;
    if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) {
      throw new Error("Formato GeoJSON non valido");
    }
    allFeatures = sortChurches(data.features);
    configureFilters();
    applyFilters();
    initializeMap();
  } catch (error) {
    resultCount.textContent = "0 risultati";
    statusMessage.classList.add("error");
    statusMessage.textContent = (
      "Impossibile caricare il catalogo. "
      + (error instanceof Error ? error.message : "Errore sconosciuto")
    );
  }
}


searchInput.addEventListener("input", () => {
  filters.query = searchInput.value;
  applyFilters();
});
typeSelect.addEventListener("change", () => {
  filters.churchType = typeSelect.value;
  applyFilters();
});
centurySelect.addEventListener("change", () => {
  filters.century = centurySelect.value;
  applyFilters();
});
regionSelect.addEventListener("change", () => {
  filters.region = regionSelect.value;
  applyFilters();
});
clearFilters.addEventListener("click", () => {
  searchInput.value = "";
  typeSelect.value = "";
  centurySelect.value = "";
  if (!regionSelect.disabled) {
    regionSelect.value = "";
  }
  filters.query = "";
  filters.churchType = "";
  filters.century = "";
  filters.region = regionSelect.disabled ? regionSelect.value : "";
  applyFilters();
  searchInput.focus();
});
closeDetail.addEventListener("click", () => hideDetails(true));
for (const button of viewButtons) {
  button.addEventListener("click", () => {
    setMobileView(button.dataset.view ?? "list");
  });
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !detailPanel.hidden) {
    hideDetails(true);
  }
});

void loadCatalog();
