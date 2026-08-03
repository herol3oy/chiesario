import { GeoJSONSource, Map, NavigationControl, Popup, setWorkerUrl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import "./style.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

setWorkerUrl(workerUrl);

const map = new Map({
  container: "app",
  style: "https://demotiles.maplibre.org/style.json",
  center: [11.0, 43.3],
  zoom: 6.5,
});


map.addControl(
  new NavigationControl(),
  "top-right",
);


map.on("load", () => {

  map.addSource(
    "churches",
    {
      type: "geojson",

      data:
        "/data/churches.geojson",

      cluster: true,

      clusterMaxZoom: 12,

      clusterRadius: 45,
    },
  );


  // -----------------------------
  // Clusters
  // -----------------------------

  map.addLayer({
    id: "clusters",

    type: "circle",

    source: "churches",

    filter: [
      "has",
      "point_count",
    ],

    paint: {
      "circle-radius": [
        "step",
        [
          "get",
          "point_count",
        ],
        18,
        20,
        24,
        50,
        30,
      ],

      "circle-opacity": 0.8,
    },
  });


  map.addLayer({
    id: "cluster-count",

    type: "symbol",

    source: "churches",

    filter: [
      "has",
      "point_count",
    ],

    layout: {
      "text-field":
        "{point_count_abbreviated}",

      "text-size": 12,
    },
  });


  // -----------------------------
  // Individual churches
  // -----------------------------

  map.addLayer({
    id: "churches",

    type: "circle",

    source: "churches",

    filter: [
      "!",
      [
        "has",
        "point_count",
      ],
    ],

    paint: {
      "circle-radius": 7,

      "circle-stroke-width": 2,
    },
  });


  // -----------------------------
  // Cluster click
  // -----------------------------

  map.on(
    "click",
    "clusters",
    async (event) => {

      const features =
        map.queryRenderedFeatures(
          event.point,
          {
            layers: [
              "clusters",
            ],
          },
        );

      const feature =
        features[0];

      if (!feature) {
        return;
      }

      const clusterId =
        feature.properties
          ?.cluster_id;

      const source =
        map.getSource(
          "churches",
        ) as GeoJSONSource;

      const zoom =
        await source
          .getClusterExpansionZoom(
            clusterId,
          );

      const geometry =
        feature.geometry;

      if (
        geometry.type
        !== "Point"
      ) {
        return;
      }

      map.easeTo({
        center: geometry.coordinates as [number, number],
        zoom,
      });
    },
  );


  // -----------------------------
  // Church click
  // -----------------------------

  map.on(
    "click",
    "churches",
    (event) => {

      const feature =
        event.features?.[0];

      if (!feature) {
        return;
      }

      if (
        feature.geometry.type
        !== "Point"
      ) {
        return;
      }

      const p =
        feature.properties;

      const popup =
        document.createElement(
          "div",
        );

      popup.className =
        "church-popup";


      const title =
        document.createElement(
          "h2",
        );

      title.textContent =
        p.name;

      popup.appendChild(
        title,
      );


      const metadata =
        document.createElement(
          "div",
        );

      metadata.className =
        "metadata";

      metadata.textContent =
        [
          p.church_type,
          p.date_display,
        ]
          .filter(Boolean)
          .join(" · ");

      popup.appendChild(
        metadata,
      );


      if (p.hero_image) {

        const image =
          document.createElement(
            "img",
          );

        image.src =
          p.hero_image;

        image.alt =
          p.name;

        popup.appendChild(
          image,
        );
      }


      const links =
        document.createElement(
          "div",
        );

      links.className =
        "links";


      const addLink = (
        label: string,
        url?: string,
      ) => {

        if (!url) {
          return;
        }

        const link =
          document.createElement(
            "a",
          );

        link.href = url;

        link.target =
          "_blank";

        link.rel =
          "noopener noreferrer";

        link.textContent =
          label;

        links.appendChild(
          link,
        );
      };


      addLink(
        "Wikidata",
        p.wikidata_url,
      );

      addLink(
        "OpenStreetMap",
        p.osm_url,
      );

      addLink(
        "Website",
        p.website,
      );


      popup.appendChild(
        links,
      );


      new Popup({
        maxWidth: "360px",
      })
        .setLngLat(
          feature.geometry
            .coordinates as [
            number,
            number,
          ],
        )
        .setDOMContent(
          popup,
        )
        .addTo(map);
    },
  );


  // -----------------------------
  // Cursor
  // -----------------------------

  for (
    const layer
    of [
      "clusters",
      "churches",
    ]
  ) {

    map.on(
      "mouseenter",
      layer,
      () => {
        map.getCanvas()
          .style.cursor =
          "pointer";
      },
    );

    map.on(
      "mouseleave",
      layer,
      () => {
        map.getCanvas()
          .style.cursor =
          "";
      },
    );
  }
});