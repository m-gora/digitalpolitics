# ADR 02: Tenancy Model

## Decision
The platform is single-tenant, built for one specific political party. This is consistent with arch-06 (German-only, no i18n) and arch-07 (brand colors, typography and logo are hard-coded for one party).

## Consequences
- No org/tenant concept in the data model; the hierarchy (canv-01) is the only structural grouping.
- Design tokens (arch-07) can be hard-coded rather than made themeable.
- If multi-party support is ever needed, it is a deliberate future re-architecture, not an incremental extension.
