# Geospatial Analysis
The third screen of the crowdsourcing module. It is for authenticated users only, with global read access (arch-02).

## Map
- Leaflet with vendored assets (adr-08). The tile URL is configurable (`MAP_TILE_URL`); the default is OpenStreetMap, which is a prototype choice only.
- Points are shown clustered. A toggle switches between point and heatmap view.
- The initial view is fitted to the filtered data.

## Filters
- Questionnaire (required, since questions differ per questionnaire).
- Campaign, which narrows the questionnaire list.
- Date range on `received_at`.

## Colouring by choice
The user can select a single-choice question. Points are then coloured by the selected option, with a legend.

## Aggregates panel
Scoped to the current map viewport and filters, and refreshed on map `moveend` via htmx:
- Response count.
- For each choice question: count and share per option.
- For each text question: a paginated list of scrubbed answers.

## Backend
- Bounding-box filtering with PostGIS (`ST_MakeEnvelope`, `&&`) on a GiST index.
- The points endpoint returns GeoJSON, capped at 10,000 points without server-side clustering. The UI shows a notice when the cap is hit.

## Live updates
`crowd.response_received` triggers a refresh of count and map data. On reconnect the client refetches (arch-03).

## Out of scope for v1
CSV/GeoJSON export, AI summaries of free text, drawn polygon selection, minimum-group-size thresholds.
