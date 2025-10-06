
require([
  "esri/Map",
  "esri/views/MapView",
  "esri/layers/GeoJSONLayer",
  "esri/widgets/Legend",
  "esri/widgets/Expand",
  "esri/widgets/TimeSlider"
], (Map, MapView, GeoJSONLayer, Legend, Expand, TimeSlider) => {

 
  const USE_HOSTED = false; // set true after publishing and fill HOSTED_URLS

  const LOCAL_URLS = {
    incidents: `${location.origin}/data/traffic_incidents.geojson`,
    hex:       `${location.origin}/data/hotspots_hex.geojson`,
    weather:   `${location.origin}/data/weather_forecast.geojson`,
    warnings:  `${location.origin}/data/weather_warnings.json`
  };

  // Fill these with your FeatureServer layer URLs after publish_to_arcgis.py
  const HOSTED_URLS = {
    incidents: "<FEATURESERVER_LAYER_URL_FOR_TRAFFIC_INCIDENTS>", // .../FeatureServer/0
    hex:       "<FEATURESERVER_LAYER_URL_FOR_HEX>",               // .../FeatureServer/0
    weather:   "<FEATURESERVER_LAYER_URL_FOR_WEATHER>",           // .../FeatureServer/0
    warnings:  null // panel only
  };

  const URLS = USE_HOSTED ? HOSTED_URLS : LOCAL_URLS;
  console.log("[DATA] Using URLs:", URLS);

  

  // Traffic points with rich popup
  const pointsLayer = new GeoJSONLayer({
    url: URLS.incidents,
    title: "Traffic Incidents (MRT) • Points",
    timeInfo: { startField: "timestamp" }, // ISO date string in properties
    renderer: {
      type: "simple",
      symbol: { type: "simple-marker", size: 7, color: "red", outline: { color: "white", width: 0.5 } }
    },
    popupTemplate: {
      title: "{title}",
      content: [
        {
          type: "text",
          text:
            `<div style="line-height:1.35">
              <div><b>Date (start):</b> {start_date}</div>
              <div><b>Date (end):</b> {end_date}</div>
              <div><b>Activity time:</b> {activity_time}</div>
              <div><b>Location:</b> {location_text}</div>
              <hr style="border:none;border-top:1px solid #eee;margin:8px 0" />
              <div><b>Description</b><br>{description}</div>
              <div style="margin-top:6px"><b>Activity</b><br>{activity}</div>
              <hr style="border:none;border-top:1px solid #eee;margin:8px 0" />
              <div>
                <a href="{post_url}" target="_blank" rel="noopener">Open source post</a>
                <span style="margin:0 6px">·</span>
                <a href="{media_release}" target="_blank" rel="noopener">Media release</a>
              </div>
            </div>`
        }
      ]
    }
  });

  // Traffic heatmap (same incidents)
  const heatLayer = new GeoJSONLayer({
    url: URLS.incidents,
    title: "Traffic Incidents (MRT) • Heatmap",
    timeInfo: { startField: "timestamp" },
    renderer: {
      type: "heatmap",
      colorStops: [
        { ratio: 0.00, color: "rgba(0,0,0,0)" },
        { ratio: 0.20, color: "rgba(63,40,102,0.6)" },
        { ratio: 0.50, color: "rgba(0,146,214,0.85)" },
        { ratio: 0.80, color: "rgba(255,191,0,0.95)" },
        { ratio: 1.00, color: "rgba(255,64,0,0.98)" }
      ],
      minPixelIntensity: 0,
      maxPixelIntensity: 60
    }
  });

  // Hexagon hotspots (choropleth by density)
  const hexLayer = new GeoJSONLayer({
    url: URLS.hex,
    title: "Hotspots (Hex)",
    renderer: {
      type: "simple",
      symbol: { type: "simple-fill", color: [255,0,0,0.12], outline: { color: [200,0,0,0.7], width: 0.6 } },
      visualVariables: [{
        type: "color",
        field: "density_per_km2",
        stops: [
          { value: 0,  color: "#ffffff00" },
          { value: 1,  color: "#fee08b" },
          { value: 5,  color: "#f46d43" },
          { value: 15, color: "#a50026" }
        ]
      }]
    },
    popupTemplate: {
      title: "Hotspot (Hex)",
      content: [{ type: "fields", fieldInfos: [
        { fieldName: "value", label: "Count" },
        { fieldName: "density_per_km2", label: "Density (/km²)", format: { places: 2 } },
        { fieldName: "area_km2", label: "Hex area (km²)", format: { places: 2 } }
      ]}]
    }
  });

  // Weather forecasts (points) with rich popup
  const weatherLayer = new GeoJSONLayer({
    url: URLS.weather,
    title: "Weather Forecast",
    renderer: {
      type: "simple",
      symbol: { type: "simple-marker", size: 6, color: [0, 120, 255, 0.85], outline: { color: "white", width: 0.5 } }
    },
    popupTemplate: {
      title: "{location_name} • {date}",
      content: [
        {
          type: "text",
          text:
            `<div style="line-height:1.35">
               <div style="margin-bottom:6px"><b>Forecast:</b> {forecast}</div>
               <div><b>Temperature:</b> {temp_min}–{temp_max} °C</div>
               <div><b>Rain chance:</b> {rain_chance}%</div>
               <div><b>Wind:</b> {wind_speed} km/h {wind_dir}</div>
               <div><b>Humidity:</b> {humidity}%</div>
             </div>`
        }
      ]
    }
  });


  const map = new Map({
    basemap: "gray-vector",
    layers: [hexLayer, heatLayer, pointsLayer, weatherLayer] 
  });

  const view = new MapView({
    container: "view",
    map,
    center: [103.76, 1.46],
    zoom: 12
  });

  // TimeSlider bound to incidents
  const timeSlider = new TimeSlider({ view, mode: "time-window", stops: { interval: { value: 1, unit: "days" } } });
  view.ui.add(timeSlider, "bottom-left");

  pointsLayer.when(async () => {
    const count = await pointsLayer.queryFeatureCount();
    console.log("[INFO] incidents feature count:", count);
    if (count > 0) {
      const ext = await pointsLayer.queryExtent();
      if (ext && ext.extent) view.goTo(ext.extent.expand(1.2));
    }
    const te = pointsLayer.timeInfo?.fullTimeExtent;
    if (te) { timeSlider.fullTimeExtent = te; timeSlider.timeExtent = te; }
  });

  // Weather warnings panel
  const warnDiv = document.createElement("div");
  warnDiv.className = "a-panel";
  warnDiv.innerHTML = "<em>Loading warnings…</em>";
  if (URLS.warnings) {
    fetch(URLS.warnings).then(r => r.json()).then(j => {
      const list = Array.isArray(j) ? j : (j?.warnings ?? []);
      if (!list || list.length === 0) { warnDiv.innerHTML = "<small>No active warnings.</small>"; return; }
      warnDiv.innerHTML = "";
      list.forEach(w => {
        const card = document.createElement("div"); card.className = "warn";
        const title = w.title || w.type || "Warning";
        const desc  = w.description || w.details || "";
        const ts    = w.time || w.issued || "";
        card.innerHTML = `<h4>${title}</h4><div>${desc}</div><small>${ts}</small>`;
        warnDiv.appendChild(card);
      });
    }).catch(() => { warnDiv.innerHTML = "<small>Could not load warnings.</small>"; });
  } else {
    warnDiv.innerHTML = "<small>Warnings panel (configure URLS.warnings)</small>";
  }
  view.ui.add(new Expand({ view, content: warnDiv, expanded: false, expandTooltip: "Weather Warnings" }), "top-right");

  // Legend
  view.ui.add(new Legend({ view }), "bottom-right");


  const $ = id => document.getElementById(id);
  const chkPoints  = $("chkPoints");
  const chkHeat    = $("chkHeat");
  const chkHex     = $("chkHex");
  const chkWeather = $("chkWeather");

  function syncVisibility() {
    pointsLayer.visible  = !!chkPoints.checked;
    heatLayer.visible    = !!chkHeat.checked;
    hexLayer.visible     = !!chkHex.checked;
    weatherLayer.visible = !!chkWeather.checked;
  }
  chkPoints.addEventListener("change", syncVisibility);
  chkHeat.addEventListener("change", syncVisibility);
  chkHex.addEventListener("change", syncVisibility);
  chkWeather.addEventListener("change", syncVisibility);
  syncVisibility();
});
