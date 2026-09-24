# Hierarchical campaign clustering
The campaign module shall work hierarchical. Eg. 
```
    LV Berlin 
    -> BV Friedrichshain-Kreuzberk 
       -> OV Kreuzberg
```

Each level of hierarchy can have an unbounded numbers of campaign canvasses.
However the number of hierarchies shall be flexible to allow a frictionless scale out later on: the hierarchy is an arbitrary-depth tree of party units ("Gliederungen"), not a fixed three-level model. LV/BV/OV above is one example instance, not the schema.

## Initiatives
Grouping of campaigns shall also be possible into an initiative. Therefore multiple smaller campaigns can pay into a bigger initiative.

For v1, an initiative clusters campaigns **within a single hierarchy node** (i.e. one district's own campaigns). Cross-district initiatives are out of scope for v1, to keep the prototype simple. Managing an initiative's membership requires the same write access as its member campaigns' district.

### Coherence score
Each initiative shall have an AI/LLM-assisted coherence score: a heuristic estimate of how well its member campaigns' narratives align, derived by comparing their canvas fields (e.g. Thema, Ziel, Storytelling). This is an indicative estimate for campaigners, not an authoritative metric.

### Future extensibility (out of scope for v1)
A broader, cross-hierarchy narrative-alignment view (e.g. comparing a Landesverband's overall campaigns against a sub-district's campaigns, independent of formal initiative membership) is a plausible future enhancement. The v1 design should not preclude it, but it is not built now.