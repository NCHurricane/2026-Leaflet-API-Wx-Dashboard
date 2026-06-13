flowchart TD

subgraph group_grp_api["API"]
  node_main["Main app<br/>FastAPI entrypoint<br/>[main.py]"]
  node_health["Health<br/>status route<br/>[health.py]"]
end

subgraph group_grp_ui["UI"]
  node_index_html["Home page<br/>static HTML<br/>[index.html]"]
  node_weather_html["Weather page<br/>workflow HTML<br/>[weather.html]"]
  node_js_shared["Shared JS<br/>browser client<br/>[shared.js]"]
  node_js_weather["Weather JS<br/>browser client<br/>[weather.js]"]
  node_js_satellite["Satellite JS<br/>browser client<br/>[satellite.js]"]
  node_js_radar_sites["Radar sites<br/>browser data"]
end

subgraph group_grp_core["Core workflows"]
  node_surface["Surface<br/>[surface_utils.py]"]
  node_alerts["Alerts<br/>warning product<br/>[alerts_utils.py]"]
  node_radar["Radar<br/>[radar_utils.py]"]
  node_mrms["MRMS<br/>precip product<br/>[mrms_utils.py]"]
  node_rtma["RTMA<br/>analysis product<br/>[rtma_utils.py]"]
  node_spc["SPC<br/>forecast product<br/>[spc_utils.py]"]
end

subgraph group_grp_sat["Satellite v2"]
  node_sat_service["Sat service<br/>satellite orchestration<br/>[service.py]"]
  node_sat_catalog["Catalog<br/>satellite metadata<br/>[catalog.py]"]
  node_sat_provider["AWS provider<br/>data source client<br/>[provider_aws.py]"]
  node_sat_cache["Cache<br/>[cache.py]"]
  node_sat_renderer["Renderer<br/>[renderer.py]"]
  node_sat_tiler["Tiler<br/>tile generator<br/>[tiler.py]"]
end

subgraph group_grp_workers["Workers"]
  node_workers["Workers<br/>job system<br/>[scheduler.py]"]
end

subgraph group_grp_assets["Assets"]
  node_lib["Shared lib<br/>utilities<br/>[__init__.py]"]
  node_config["Config<br/>[__init__.py]"]
  node_data[("Data assets<br/>local datasets<br/>[us-cities.json]")]
  node_shapefiles[("Shapefiles<br/>geometry assets")]
  node_media[("Media assets<br/>fonts/sounds/raster")]
end

node_external_sources(("External sources<br/>NWS/IEM/NOAA/UCAR"))

node_main -->|"includes"| node_health
node_main -->|"serves"| node_index_html
node_main -->|"serves"| node_weather_html
node_main -->|"mounts"| node_js_shared
node_main -->|"uses state"| node_workers
node_index_html -->|"loads"| node_js_shared
node_weather_html -->|"loads"| node_js_weather
node_weather_html -->|"loads"| node_js_satellite
node_weather_html -->|"loads"| node_js_shared
node_js_weather -->|"calls API"| node_main
node_js_satellite -->|"calls API"| node_main
node_js_radar_sites -.->|"supports"| node_radar
node_workers -->|"runs"| node_surface
node_workers -->|"runs"| node_alerts
node_workers -->|"runs"| node_radar
node_workers -->|"runs"| node_mrms
node_workers -->|"runs"| node_rtma
node_workers -->|"runs"| node_spc
node_workers -->|"runs"| node_sat_service
node_surface -->|"fetches"| node_external_sources
node_alerts -->|"fetches"| node_external_sources
node_radar -->|"fetches"| node_external_sources
node_mrms -->|"fetches"| node_external_sources
node_rtma -->|"fetches"| node_external_sources
node_spc -->|"fetches"| node_external_sources
node_sat_service -->|"orchestrates"| node_sat_catalog
node_sat_service -->|"orchestrates"| node_sat_cache
node_sat_service -->|"orchestrates"| node_sat_renderer
node_sat_service -->|"orchestrates"| node_sat_tiler
node_sat_catalog -->|"reads from"| node_sat_provider
node_sat_renderer -->|"uses"| node_config
node_sat_renderer -->|"uses"| node_media
node_sat_tiler -->|"reads/writes"| node_sat_cache
node_surface -->|"uses"| node_config
node_alerts -->|"uses"| node_config
node_radar -->|"uses"| node_config
node_mrms -->|"uses"| node_config
node_rtma -->|"uses"| node_config
node_spc -->|"uses"| node_config
node_main -->|"depends on"| node_lib
node_surface -->|"depends on"| node_lib
node_alerts -->|"depends on"| node_lib
node_radar -->|"depends on"| node_lib
node_mrms -->|"depends on"| node_lib
node_rtma -->|"depends on"| node_lib
node_spc -->|"depends on"| node_lib
node_main -->|"reads"| node_data
node_main -->|"reads"| node_shapefiles

click node_main "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/main.py"
click node_health "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/routes/health.py"
click node_index_html "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/index.html"
click node_weather_html "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/weather.html"
click node_js_shared "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/js/shared.js"
click node_js_weather "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/js/weather.js"
click node_js_satellite "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/js/satellite.js"
click node_js_radar_sites "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/js/radar-site-locations.js"
click node_surface "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/surface/surface_utils.py"
click node_alerts "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/alerts/alerts_utils.py"
click node_radar "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/radar/radar_utils.py"
click node_mrms "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/mrms/mrms_utils.py"
click node_rtma "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/rtma/rtma_utils.py"
click node_spc "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/spc/spc_utils.py"
click node_sat_service "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/satellite_v2/service.py"
click node_sat_catalog "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/satellite_v2/catalog.py"
click node_sat_provider "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/satellite_v2/provider_aws.py"
click node_sat_cache "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/satellite_v2/cache.py"
click node_sat_renderer "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/satellite_v2/renderer.py"
click node_sat_tiler "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/satellite_v2/tiler.py"
click node_workers "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/workers/scheduler.py"
click node_lib "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/lib/__init__.py"
click node_config "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/config/__init__.py"
click node_data "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/data/us-cities.json"
click node_shapefiles "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/shapefiles/cb_2025_us_state_500k.shp"
click node_media "https://github.com/nchurricane/2026-leaflet-api-wx-dashboard/blob/main/img/BlackMarble_2016_01deg_geo.tif"

classDef toneNeutral fill:#f8fafc,stroke:#334155,stroke-width:1.5px,color:#0f172a
classDef toneBlue fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef toneAmber fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef toneMint fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef toneRose fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef toneIndigo fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81
classDef toneTeal fill:#ccfbf1,stroke:#0f766e,stroke-width:1.5px,color:#134e4a
class node_main,node_health toneBlue
class node_index_html,node_weather_html,node_js_shared,node_js_weather,node_js_satellite,node_js_radar_sites toneAmber
class node_surface,node_alerts,node_radar,node_mrms,node_rtma,node_spc toneMint
class node_sat_service,node_sat_catalog,node_sat_provider,node_sat_cache,node_sat_renderer,node_sat_tiler toneRose
class node_workers toneIndigo
class node_lib,node_config,node_data,node_shapefiles,node_media toneTeal
class node_external_sources toneNeutral