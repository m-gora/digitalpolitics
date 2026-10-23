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
Each initiative shall have separate AI-assisted domain and narrative similarity scores, produced by TypeSafe rubric scoring (adr-06):

- **Domain similarity** evaluates how similar the member campaigns' Thema values are in subject matter.
- **Narrative similarity** evaluates how coherently the member campaigns' Ziel and Storytelling work together toward the initiative description.

Each dimension is scored on a five-level rubric (0-4) and stored normalized to 0-1. Scores are displayed as decimals (not probabilities or percentages) and are heuristics, not authoritative metrics. A dimension is unavailable when fewer than two member campaigns have text for it (Thema for domain; Ziel or Storytelling for narrative); missing text in one dimension does not exclude a campaign from the other dimension.

When at least three member campaigns have text, the same request asks which campaign, if any, is the clearest relative outlier in the initiative. The initiative detail highlights that campaign as an outlier candidate for human review and highlights nothing when no campaign is clearly less coherent (`none_clear`). The UI shall make clear that this is a relative indicator for human review with no fixed outlier threshold; there are no per-campaign scores.

Scores are recomputed in the background when membership changes, when a member campaign's Thema, Ziel, or Storytelling changes, and when the initiative's name or description changes. If TypeSafe is not configured or a request fails, the previously stored values are kept.

### Future extensibility (out of scope for v1)
A broader narrative-alignment view across unrelated hierarchy branches (independent of an initiative's anchor subtree and formal membership) is a plausible future enhancement. The v1 design should not preclude it, but it is not built now.
