# Hierarchical campaign clustering
The campaign module shall work hierarchical. Eg. 
```
    LV Berlin 
    -> BV Friedrichshain-Kreuzberk 
       -> OV Kreuzberg
```

Each level of hierarchy can have an unbounded numbers of campaign canvasses.
However the number of hierarchies shall be flexible to allow a frictionless scale out later on: the hierarchy is an arbitrary-depth tree of party units ("Gliederungen"), not a fixed three-level model. LV/BV/OV above is one example instance, not the schema.

## Hierarchy administration
Any authenticated user may create a new root-level Gliederung. Creating a child Gliederung, renaming a Gliederung, or deleting one requires district write access to its parent or to the affected Gliederung, respectively. Only leaf Gliederungen may be deleted, and deletion is blocked while campaigns or initiatives still reference the Gliederung. The districts page provides these management actions.

## Initiatives
Grouping of campaigns shall also be possible into an initiative. Multiple campaigns can align around a shared political narrative and act as a stronger, coordinated unit.

Each initiative has a **coordinating Gliederung** as its anchor. Member campaigns may belong to that Gliederung or any Gliederung beneath it in the hierarchy. For example, an initiative anchored at LV Berlin may include campaigns from BV Friedrichshain-Kreuzberg and OV Kreuzberg. Campaigns from unrelated branches outside the anchor's subtree cannot join.

Managing an initiative (including its name, description, and membership) requires write access to its coordinating Gliederung. The coordinating Gliederung is fixed after creation; the name and description may be edited, and the initiative may be deleted. Deleting an initiative removes only its campaign associations, not the campaigns themselves. The UI shall show which Gliederungen are represented by its member campaigns.

### Coherence score
Each initiative shall have separate AI-assisted domain and narrative similarity scores:

- **Domain similarity** is derived only from each campaign's Thema embedding.
- **Narrative similarity** is derived only from each campaign's Ziel and Storytelling embedding.

For each dimension, the initiative score is the mean cosine similarity across all pairs of member campaigns with an embedding for that dimension. Scores are displayed as decimals (not probabilities or percentages) and are heuristics, not authoritative metrics. A dimension is unavailable when fewer than two member campaigns have an embedding for it; missing text or embeddings in one dimension do not exclude a campaign from the other dimension.

The initiative detail shall show each campaign's mean cosine similarity to its peers separately for each dimension. For each dimension, when at least three campaigns have embeddings, the lowest-ranked campaign is highlighted as a relative outlier candidate for human review. The UI shall make clear that these are relative indicators with no fixed outlier threshold. Campaigns without an embedding for a dimension are excluded from that dimension's aggregate and ranking; fewer than two embedded campaigns are insufficient for comparisons.

### Future extensibility (out of scope for v1)
A broader narrative-alignment view across unrelated hierarchy branches (independent of an initiative's anchor subtree and formal membership) is a plausible future enhancement. The v1 design should not preclude it, but it is not built now.
