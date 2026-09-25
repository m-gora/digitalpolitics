# Campaign Definition
The campaign shall be a guided workflow following the campaign canvas.
Per definition the campaign canvas should be filled from the center to the outside.
However in a digital application we want to guide the campaigner through it step by step.

Zieldefinition:
- Thema: Worum geht es?
- Ziel: Was ist das Ziel (politisch und kommunikativ)?

Zielgruppen & Kanäle:
- Zielgruppen: Gibt es spezielle Zielgruppen?
- Kanäle: Welche Zulieferer brauchen wir? Wo erreichen wir die Zielgruppe?
- Momentum: Welche Multiplikatoren haben wir in unserem Umfeld? Welche Stakeholder und Partner können wir aktivieren?
- Motiv: Warum sollte jemand mitmachen?

Material, Organisation & Storytelling:
- Service: Was sollte man den Aktivisten zur Verfügung stellen?
- Data Harvest: Welche Daten unserer Zielgruppe wären besonders nützlich für eine nutzenstiftende Kommunikation? Was passiert im Anschluss mit diesen Daten?
- Tools: Welche Tools könnten nützlich sein? (Apps, Petitionstools, etc.)
- Phasen & Flow: Wie startet die Aktion um erfolgreich Aufmerksamkeit zu erzeugen? Wie halten wir die Spannung? Wann gibt es Anlässe die wir nutzen können? Wie endet die Aktion?
- Storytelling: Gibt es eine spannende Perspektive, besondere Personengruppen, etc?

## Progression
The Zieldefinition must be completed before Zielgruppen & Kanäle unlocks; Zielgruppen & Kanäle must be completed before Material, Organisation & Storytelling unlocks. This gating only applies while the campaign is in `Draft` status (see canv-05); all fields remain visible/editable together during `Draft`.

## Privacy
Per arch-04 (Privacy by Design), any plan captured under Data Harvest must eventually state the legal basis and retention period for the citizen data it describes. The concrete compliance workflow for this is deferred to a future data-protection spec.

## Concurrency
Field saves use last-write-wins. Saving a field pushes a `campaign.field_updated` SSE event (see arch-03) so other connected viewers can refresh rather than working from stale data.

## Campaign list summary
Once all fields in Zieldefinition, Zielgruppen & Kanäle, and Material, Organisation & Storytelling are completed, the platform generates a concise, complete German sentence of at most 20 words and displays it in the campaign list beneath the Thema. The complete summary is shown without truncation. The summary uses all canvas fields except Data Harvest and is regenerated after subsequent edits to a completed canvas. Provider choice and external processing are specified in adr-04 and adr-05.

## Creator attribution
Each campaign records the creating identity from `X-User-Id`, displayed on the campaign detail page. A fork records the identity of the user who created the fork, not the creator of its source campaign. Existing campaigns without creator data may leave this value empty.
