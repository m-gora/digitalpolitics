# ADR 05: AI Provider Abstraction and Campaign Summaries

## Context
The campaign coherence feature currently uses an OpenAI-specific embedding client. The platform also needs to generate a short summary for each fully completed campaign canvas. Both are AI capabilities, so provider-specific API details should not be coupled to campaign business logic.

## Decision
- Introduce a shared provider interface for text embeddings and text generation.
- Select one AI provider per deployment using `AI_PROVIDER=openai|google`; the selected provider handles both embeddings and text generation.
- Support OpenAI and Google's `google-genai` SDK.
- OpenAI defaults: `text-embedding-3-small` for embeddings and `gpt-4o-mini` for summaries.
- Google defaults: `gemini-embedding-2` for embeddings and `gemini-3.5-flash-lite` for summaries.
- For Google's symmetric campaign domain and narrative similarity embeddings, prefix all texts identically with `task: sentence similarity | query: ` and request 1536 output dimensions to match the pgvector columns. Domain and narrative inputs are embedded separately (see canv-01).
- Generate a concise German, one-sentence campaign summary of at most 20 words after all fields in Zieldefinition, Zielgruppen & Kanäle, and Material, Organisation & Storytelling are complete. Prompt the provider to return one complete sentence with no ellipsis; store and display its full response without hard truncation. Regenerate it after later edits while the canvas remains complete.
- The summary prompt includes all campaign canvas fields except Data Harvest (see adr-04). Summaries are stored with their generation timestamp and displayed below the campaign Thema in the campaign list.
- If the selected provider's API key is absent or a request fails, the application remains usable; the corresponding AI output is left empty or unchanged.

## Consequences
- Campaign logic depends on the shared provider interface, not directly on an SDK.
- Changing providers or the similarity input split does not make stored embeddings comparable: all existing campaign embeddings must be recomputed before domain or narrative scores are trusted. Automated bulk re-embedding is out of scope for this prototype.
- The provider choice and model settings are deployment configuration; changing them does not change the database schema.
- External processing and its field scope are documented in adr-04.
