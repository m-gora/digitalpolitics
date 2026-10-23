# ADR 04: AI Processing Scope and Privacy By Design

## Context
arch-04 (Privacy By Design) requires tracking data and PII to be strictly separated and establishes privacy-by-design as a general principle. Two campaign features use external AI processing: initiative coherence scoring (canv-01) and completed-campaign summaries (canv-02).

## Decision
The prototype sends campaign-planning text to external AI services for these narrowly defined purposes (the deployment-selected provider for summaries, see adr-05; TypeSafe for coherence, see adr-06):

- **Initiative similarity:** Thema, Ziel and Storytelling of the member campaigns, plus the initiative's name and description, are sent to TypeSafe for rubric scoring (adr-06). Campaigns are labelled `C1..Cn`, and operational fields and internal ids are excluded.
- **Campaign summary:** all canvas fields are sent except Data Harvest; the response is a concise German summary for the campaign list.
- Data Harvest is deliberately excluded because it describes planned handling of citizen data.
- No street-feedback records or collected citizen data are submitted by these features.

## Consequences
- Campaign strategy text leaves the application boundary for coherence scoring (TypeSafe) and summary generation (the selected AI provider).
- The included fields are free text and may be populated by users. The prototype does not detect or scrub accidental personal data in these fields; campaign users must not enter citizen PII there.
- The summary feature expands the fields processed externally beyond the three narrative fields used for coherence scoring. Data Harvest remains excluded.
- This exception does not extend to other modules; the street-feedback module's PII scrubbing (arch-04) remains a separate, stricter requirement.

- **Exception (adr-07):** the crowdsourcing module may send citizen voice audio to OpenAI for transcription only. Answers, transcripts and locations are never sent.
