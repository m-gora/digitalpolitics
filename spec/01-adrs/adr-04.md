# ADR 04: AI Processing Scope and Privacy By Design

## Context
arch-04 (Privacy By Design) requires tracking data and PII to be strictly separated and establishes privacy-by-design as a general principle. Two campaign features use external AI processing: initiative coherence embeddings (canv-01) and completed-campaign summaries (canv-02).

## Decision
The prototype sends campaign-planning text to the deployment-selected AI provider (see adr-05) for these narrowly defined purposes:

- **Initiative similarity:** Thema is embedded separately for domain similarity; Ziel and Storytelling are embedded together for narrative similarity. Operational fields are excluded.
- **Campaign summary:** all canvas fields are sent except Data Harvest; the response is a concise German summary for the campaign list.
- Data Harvest is deliberately excluded because it describes planned handling of citizen data.
- No street-feedback records or collected citizen data are submitted by these features.

## Consequences
- Campaign strategy text leaves the application boundary for embedding and summary generation.
- The included fields are free text and may be populated by users. The prototype does not detect or scrub accidental personal data in these fields; campaign users must not enter citizen PII there.
- The summary feature expands the fields processed externally beyond the three narrative fields used for embeddings. Data Harvest remains excluded.
- This exception does not extend to other modules; the street-feedback module's PII scrubbing (arch-04) remains a separate, stricter requirement.
