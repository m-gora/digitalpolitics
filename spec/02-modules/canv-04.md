# Post-Mortem and Knowledge Retention
After closing a campaign, a structured retrospective shall be conducted.

## Trigger
The retrospective is triggered automatically when a campaign transitions to `Finished` or `Aborted` (see canv-05). Both trigger a retrospective — an aborted campaign's retrospective may end up lighter in practice, but the structure is offered in both cases so the reasons for aborting are captured, not lost.

## Proposed structure
(Draft — refine as needed)
- Zielerreichung: Soll/Ist-Vergleich gegen das Ziel-Feld aus der Zieldefinition.
- Was lief gut?
- Was lief schlecht?
- Handlungsempfehlungen für künftige Kampagnen.

## Knowledge retention
`Finished` and `Archived` campaigns remain globally readable (arch-02) and forkable (canv-03), forming the knowledge base of past campaigns and their retrospectives.
