# Server Sent Events
Changes of the backend state shall be pushed to connected clients via SSE.
SSE channels are scoped by modules, so that the client does not need to drop events for pages it does not render currently.

## Campaign canvas module event catalog
- `campaign.field_updated` — a field in Zieldefinition, Zielgruppen & Kanäle, or Material, Organisation & Storytelling was saved.
- `campaign.status_changed` — a campaign transitioned between lifecycle statuses (see canv-05).
- `campaign.summary_updated` — a completed campaign's AI-generated list summary was saved (see canv-02).
- `initiative.updated` — an initiative was created, edited, deleted, or had a member added or removed; the event includes its id and change kind.
- `initiative.coherence_updated` — an initiative's domain and/or narrative similarity scores were recomputed; the event includes both score values.

## Concurrent edits
Field-level writes use last-write-wins. When a field is saved, `campaign.field_updated` is pushed so other connected viewers can refresh the field rather than silently overwriting each other's view.

## Reconnects
On reconnect, the client refetches current state rather than replaying missed events. There is no event log/offset tracking in v1.

## Crowdsourcing module event catalog
Events use a separate `crowd` channel (see crowd-01, crowd-03, crowd-05).
- `crowd.questionnaire_status_changed` — a questionnaire moved between Draft, Active and Closed.
- `crowd.response_received` — a response was stored; carries the questionnaire id and new total count, never location or content.
