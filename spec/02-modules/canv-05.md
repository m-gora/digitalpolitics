# Campaign Lifecycle

A campaign shall move through the following statuses:

```
Draft -> Review -> Running -> Finished / Aborted -> Archived
                ^______|
        (Review can send back to Draft)
```

## Statuses
- **Draft**: fully editable. Zieldefinition, Zielgruppen & Kanäle, and Material, Organisation & Storytelling fields are all available, gated sequentially per canv-02 (Zieldefinition before Zielgruppen & Kanäle, then Material, Organisation & Storytelling).
- **Review**: the canvas is locked from further edits. From here, any district write-access holder can either promote the campaign to `Running` or send it back to `Draft` for revisions. There is no separate approval role for v1 — the same write-access group reviews its own work.
- **Running**: the campaign is executing. The canvas is read-only; the plan is locked in once execution starts.
- **Finished** / **Aborted**: the campaign is closed. Triggers the post-mortem retrospective (canv-04). Canvas remains read-only.
- **Archived**: final state. Read-only, retained for template forking (canv-03) and knowledge retention (canv-04).

## Permissions
Status transitions require the same district-scoped write access as editing the campaign (arch-02) — no separate approval role for v1.

## Events
Every status transition pushes a `campaign.status_changed` SSE event (see arch-03).
