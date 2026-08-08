import {
  GeoJSONSource,
  LngLatBounds,
  Map,
  NavigationControl,
  setWorkerUrl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  availableCenturies,
  centuryLabel,
  filterChurches,
  formatChurchDate,
  formatPeriod,
  phaseLabel,
  sortChurches,
  typeLabel,
  uniqueValues,
} from "./catalog";
import { i18n, initializeI18n } from "./i18n";
import "./style.css";
import type {
  CatalogFilters,
  ChurchFeature,
  ChurchFeatureCollection,
} from "./types";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";


setWorkerUrl(workerUrl);


const REGION_LABELS: Record<string, string> = {
  Tuscany: "Toscana",
  Umbria: "Umbria",
  Marche: "Marche",
  Molise: "Molise",
};


function element<T extends Element>(selector: string): T {
  const result = document.querySelector<T>(selector);
  if (!result) {
    throw new Error(`${i18n.t("app.elementNotFound")}: ${selector}`);
  }
  return result;
}


let app: HTMLDivElement;
let shell: HTMLDivElement;
let searchInput: HTMLInputElement;
let typeSelect: HTMLSelectElement;
let centurySelect: HTMLSelectElement;
let regionSelect: HTMLSelectElement;
let clearFilters: HTMLButtonElement;
let resultCount: HTMLOutputElement;
let statusMessage: HTMLDivElement;
let churchList: HTMLDivElement;
let detailPanel: HTMLElement;
let detailContent: HTMLDivElement;
let closeDetail: HTMLButtonElement;
let viewButtons: HTMLButtonElement[] = [];

let allFeatures: ChurchFeature[] = [];
let filteredFeatures: ChurchFeature[] = [];
let selectedId: string | null = null;
let map: Map | null = null;
let detailReturnFocus: HTMLElement | null = null;


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


function createLanguageSwitcher(): HTMLElement {
  const container = document.createElement("div");
  container.className = "language-switch";
  container.setAttribute("role", "group");
  container.setAttribute("aria-label", i18n.t("app.language"));

  for (const lang of ["en", "it"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.value = lang;
    button.textContent = lang.toUpperCase();
    button.setAttribute(
      "aria-pressed",
      String(i18n.language === lang),
    );
    if (i18n.language === lang) {
      button.classList.add("active");
    }
    button.addEventListener("click", async () => {
      await i18n.changeLanguage(lang);
      window.location.reload();
    });
    container.appendChild(button);
  }

  return container;
}


function renderAppShell(): void {
  app.innerHTML = `
    <div class="site-shell" data-mobile-view="list">
      <header class="site-header">
        <div>
          <p class="eyebrow">${i18n.t("app.eyebrow")}</p>
          <h1>${i18n.t("app.title")}</h1>
          <p class="intro">
            ${i18n.t("app.intro")}
          </p>
        </div>
        <div class="header-controls">
          <div class="view-switch" aria-label="${i18n.t("app.switchView")}">
            <button type="button" data-view="list" aria-pressed="true">${i18n.t("app.list")}</button>
            <button type="button" data-view="map" aria-pressed="false">${i18n.t("app.map")}</button>
          </div>
        </div>
      </header>

      <main class="workspace">
        <aside class="directory" aria-label="${i18n.t("app.listLabel")}">
          <form class="filters" id="filters-form">
            <label class="search-field">
              <span>${i18n.t("app.searchByName")}</span>
              <input id="search" type="search" placeholder="${i18n.t("app.searchPlaceholder")}" autocomplete="off" />
            </label>
            <div class="filter-grid">
              <label>
                <span>${i18n.t("app.type")}</span>
                <select id="type-filter"><option value="">${i18n.t("app.allTypes")}</option></select>
              </label>
              <label>
                <span>${i18n.t("app.century")}</span>
                <select id="century-filter"><option value="">${i18n.t("app.allCenturies")}</option></select>
              </label>
              <label>
                <span>${i18n.t("app.region")}</span>
                <select id="region-filter"><option value="">${i18n.t("app.allRegions")}</option></select>
              </label>
            </div>
            <button class="clear-filters" id="clear-filters" type="button">${i18n.t("app.clearFilters")}</button>
          </form>

          <div class="results-heading">
            <h2>${i18n.t("app.verifiedChurches")}</h2>
            <output id="result-count" aria-live="polite">${i18n.t("app.loading")}</output>
          </div>
          <div id="status-message" class="status-message" role="status"></div>
          <div id="church-list" class="church-list"></div>
        </aside>

        <section class="map-panel" aria-label="${i18n.t("app.mapLabel")}">
          <div id="map"></div>
          <p class="map-credit">${i18n.t("app.mapCredit")}</p>
        </section>

        <aside id="detail-panel" class="detail-panel" aria-label="${i18n.t("app.detailLabel")}" hidden>
          <button id="close-detail" class="close-detail" type="button" aria-label="${i18n.t("app.closeDetails")}">×</button>
          <div id="detail-content"></div>
        </aside>
      </main>
    </div>
  `;
}


function queryElements(): void {
  shell = element<HTMLDivElement>(".site-shell");
  searchInput = element<HTMLInputElement>("#search");
  typeSelect = element<HTMLSelectElement>("#type-filter");
  centurySelect = element<HTMLSelectElement>("#century-filter");
  regionSelect = element<HTMLSelectElement>("#region-filter");
  clearFilters = element<HTMLButtonElement>("#clear-filters");
  resultCount = element<HTMLOutputElement>("#result-count");
  statusMessage = element<HTMLDivElement>("#status-message");
  churchList = element<HTMLDivElement>("#church-list");
  detailPanel = element<HTMLElement>("#detail-panel");
  detailContent = element<HTMLDivElement>("#detail-content");
  closeDetail = element<HTMLButtonElement>("#close-detail");
  viewButtons = Array.from(
    document.querySelectorAll<HTMLButtonElement>("[data-view]"),
  );
}


function attachEventListeners(): void {
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
}


function configureFilters(): void {
  typeSelect.replaceChildren(
    option("", i18n.t("app.allTypes")),
  );
  for (const type of uniqueValues(allFeatures, "church_type")) {
    typeSelect.appendChild(option(type, typeLabel(type)));
  }

  centurySelect.replaceChildren(
    option("", i18n.t("app.allCenturies")),
  );
  for (const century of availableCenturies(allFeatures)) {
    centurySelect.appendChild(
      option(String(century), centuryLabel(century)),
    );
  }

  regionSelect.replaceChildren(
    option("", i18n.t("app.allRegions")),
  );
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
    typeLabel(properties.church_type),
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
        properties.hero_artist || i18n.t("app.imageOnCommons"),
        properties.hero_description_url,
      );
      if (commonsLink) {
        caption.appendChild(commonsLink);
      } else {
        caption.textContent = properties.hero_artist ?? "";
      }
      const licenseLink = createLink(
        properties.hero_license_name ?? i18n.t("app.license"),
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
  dateTitle.textContent = i18n.t("app.historicDate");
  const dateValue = document.createElement("p");
  dateValue.className = "primary-date";
  dateValue.textContent = formatChurchDate(properties);
  dateBlock.append(dateTitle, dateValue);

  const dateSources = properties.date_sources.length
    ? properties.date_sources
    : [{
        name: properties.date_source_name ?? (
          properties.date_source === "manual"
            ? i18n.t("app.manualSource")
            : properties.date_source === "wikidata"
              ? "Wikidata"
              : i18n.t("app.unspecifiedSource")
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
    phasesTitle.textContent = i18n.t("app.documentedPhases");
    const phasesList = document.createElement("ul");
    phasesList.className = "historical-phases";
    for (const phase of properties.historical_phases) {
      const item = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = phaseLabel(phase.evidence_type);
      const period = document.createElement("span");
      period.textContent = formatPeriod(phase.period);
      item.append(label, period);
      if (phase.building_part) {
        const part = document.createElement("small");
        part.textContent = phase.building_part;
        item.appendChild(part);
      }
      const phaseSource = createLink(
        phase.source_name ?? i18n.t("app.source"),
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
  sourcesTitle.textContent = i18n.t("app.sourcesAndLinks");
  const sourceLinks = document.createElement("div");
  sourceLinks.className = "source-links";
  const links = [
    createLink(i18n.t("app.wikipedia"), properties.wikipedia_url),
    createLink(i18n.t("app.wikidata"), properties.wikidata_url),
    createLink(i18n.t("app.openStreetMap"), properties.osm_url),
    createLink(i18n.t("app.officialWebsite"), properties.website),
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
  resultCount.textContent = i18n.t(
    "app.results",
    {
      count: filteredFeatures.length,
    },
  );
  statusMessage.textContent = filteredFeatures.length
    ? ""
    : i18n.t("app.noResults");

  const fragment = document.createDocumentFragment();
  for (const feature of filteredFeatures) {
    const properties = feature.properties;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "church-card";
    card.dataset.qid = properties.id;
    card.setAttribute(
      "aria-label",
      i18n.t("app.openDetails", {
        name: properties.name,
        date: formatChurchDate(properties),
      }),
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
      typeLabel(properties.church_type),
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
      throw new Error(i18n.t("app.invalidGeoJSON"));
    }
    allFeatures = sortChurches(data.features);
    configureFilters();
    applyFilters();
    initializeMap();
  } catch (error) {
    resultCount.textContent = i18n.t("app.results", { count: 0 });
    statusMessage.classList.add("error");
    statusMessage.textContent = (
      `${i18n.t("app.loadError")} `
      + (error instanceof Error ? error.message : i18n.t("app.unknownError"))
    );
  }
}


async function initApp(): Promise<void> {
  await initializeI18n();

  app = element<HTMLDivElement>("#app");
  renderAppShell();
  queryElements();

  const headerControls = document.querySelector(".header-controls");
  if (headerControls) {
    headerControls.prepend(createLanguageSwitcher());
  }

  attachEventListeners();
  void loadCatalog();
}


void initApp();
