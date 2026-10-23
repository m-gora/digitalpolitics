# ADR 08: PostGIS Storage and Leaflet Map

## Decision
- Response locations are stored as `geography(Point, 4326)` with a GiST index, using the `postgis` extension already provisioned (adr-01) and accessed via GeoAlchemy2.
- The analysis map (crowd-05) uses Leaflet with MarkerCluster and a heat layer, all vendored in `static/`.

## Consequences
- Leaflet fits the server-rendered + htmx approach (adr-01) without a build step. MapLibre would need a build step or vector tiles.
- A new Python dependency (`geoalchemy2`) is added.
- The default OpenStreetMap tile source is not suitable for production load; a production tile source is an open item.
