# ADR 04: Embedding Provider Exception to Privacy By Design

## Context
arch-04 (Privacy By Design) requires tracking data and PII to be strictly separated, and establishes privacy-by-design as a general principle. The initiative coherence score (canv-01) needs text embeddings to compare campaign narratives.

## Decision
The prototype uses the OpenAI embeddings API to compute narrative embeddings. This is a deliberate, scoped exception to arch-04:

- Only three narrative canvas fields are sent: Thema, Ziel, Storytelling.
- No PII, citizen data, or Data Harvest content is sent.
- The sole purpose is computing the heuristic initiative coherence score (canv-01).

## Consequences
- Campaign strategy text (not citizen/personal data) leaves the system boundary to a third-party API.
- If this is later found unacceptable, the exception is scoped narrowly enough to swap in a local/open-source embedding model (see the alternative considered in adr-01) without touching the rest of the coherence score design.
- This exception does not extend to any other module; the street feedback module's PII scrubbing (arch-04) is unaffected and remains a separate, stricter requirement.
