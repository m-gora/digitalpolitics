# ADR 06: TypeSafe Rubric Scoring for Initiative Coherence

## Context
Initiative domain and narrative similarity (canv-01) were computed as the mean pairwise cosine similarity of campaign embeddings (adr-05). Cosine similarity only measures text proximity: it cannot take the initiative's description into account, and it yields no statement about whether a group of campaigns works together toward a shared purpose. The `experiments/jev.ipynb` notebook compared this baseline with TypeSafe (`typesafe-sdk`), which answers ordered rubric (`Score`) and `Choice` questions about structured state.

## Decision
- Replace embedding and cosine scoring with a TypeSafe `system_one` request per initiative, using `AsyncTypeSafeClient`.
- Domain similarity is a five-level `Score` over the member campaigns' Thema; narrative similarity is a five-level `Score` over their Ziel and Storytelling, judged against the initiative description. Raw scores (0-4) are divided by 4 and stored as 0-1 in the existing `domain_similarity_score` and `narrative_similarity_score` columns.
- With three or more member campaigns, the request includes a `Choice` question for the clearest relative outlier, with `none_clear` as an explicit option. The result is stored as `initiatives.outlier_campaign_id` (`ON DELETE SET NULL`).
- Per-campaign peer similarity scores and the separate domain/narrative outlier badges are removed; a single outlier candidate is shown instead.
- Campaigns are sent under the labels `C1..Cn`; internal ids never leave the app.
- The domain and narrative rubrics live in `dpp.campaign.coherence`. The notebook stays standalone and keeps its own copy.
- Configuration: `TYPESAFE_API_KEY` and `TYPESAFE_MODEL` (default `jev-latest`). Without a key, or if a request fails, the application remains usable and previously stored values are kept.
- Scoring runs as a background task (membership change, edit of Thema/Ziel/Storytelling, edit of initiative name/description) and notifies subscribers with `initiative.coherence_updated` after commit. `python -m dpp.campaign.backfill_coherence` rescores all initiatives.
- Drop `campaigns.domain_embedding` and `campaigns.narrative_embedding`, and remove embedding support from the AI provider interface (adr-05). The `pgvector` package and extension remain only because earlier migrations import and create them.

## Consequences
- Scores are not numerically comparable with the old cosine values. The migration clears all stored scores; run the backfill to recompute them.
- Scores are LLM judgements: they can vary between runs and depend on the rubric wording. They remain heuristics for human review, not authoritative metrics.
- Each recompute makes one external request and may take seconds, so scores appear shortly after a change rather than within the request.
- A scoring failure leaves the previous scores in place, which can briefly be stale relative to the current membership.
- Initiative name and description now leave the application boundary as well (see adr-04).
