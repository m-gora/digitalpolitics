# Design system v1

The visual language of the platform, defined once so templates, JavaScript-rendered
UI and the planned Go/Fiber rewrite all agree on the same contract.

Two sources feed it:

- **FDP Designportal** (`mitgliederportal.fdp.de/designportal`) — brand colours,
  typography, logo rules and "Der Balken". Authoritative for anything the party
  defines.
- **This document** — the application layer (surfaces, feedback colours, form
  controls, density). The corporate design has no opinion on admin UI.

## Live reference

`/_design` (development only; 404 elsewhere) renders every token and, as they
land, every component. Review UI changes there, not by reading class strings.

```sh
cd app
uv run uvicorn dpp.main:app --port 8000 --reload
./bin/tailwindcss -i src/dpp/static/css/input.css -o src/dpp/static/css/output.css --watch
```

## Tokens

All tokens live in `@theme` in `app/src/dpp/static/css/input.css`. Tailwind
derives utilities from them (`bg-surface`, `text-ink-soft`, `rounded-card`,
`shadow-card`, `max-w-admin`).

### Colour

| Token | Value | Use |
|---|---|---|
| `--color-brand-yellow` | `#FFE000` | accent, dev bar, highlight surfaces |
| `--color-brand-blue` | `#032D67` | primary surfaces, headings, buttons |
| `--color-brand-blue-700` | `#043C8B` | links and hover **on light surfaces** |
| `--color-brand-blue-900` | `#021B3E` | dark accents |
| `--color-brand-cyan` | `#00A7E7` | the Balken, focus ring, graphics |
| `--color-surface` | `#F4F6FA` | page background |
| `--color-surface-tint-blue` | `#EAF0FA` | quiet panels, hover rows |
| `--color-surface-tint-cyan` | `#E1F4FC` | accent panels |
| `--color-line` | `#D5DDEC` | borders, dividers |
| `--color-ink` | `#000000` | primary text |
| `--color-ink-soft` | `#333333` | body and secondary text |
| `--color-info` / `-surface` / `-line` | `#0369A1` / `#F0F9FF` / `#BAE6FD` | informational |
| `--color-success` / `-surface` / `-line` | `#15803D` / `#F0FDF4` / `#BBF7D0` | success |
| `--color-warning` / `-surface` / `-line` | `#B45309` / `#FFFBEB` / `#FDE68A` | warning |
| `--color-danger` / `-surface` / `-line` | `#B91C1C` / `#FEF2F2` / `#FECACA` | errors, destructive |

**Contrast is a rule, not a preference.** The Designportal says text and logo
colour are always chosen by the higher contrast. Measured consequences:

| Pair | Ratio | Verdict |
|---|---|---|
| `#FFE000` on `#032D67` | 10.1:1 | use freely |
| `#032D67` on white | 13.3:1 | use freely |
| `#043C8B` on `#EAF0FA` | 9.1:1 | use freely |
| `#00A7E7` on `#032D67` | 4.9:1 | ok for text on dark blue |
| `#00A7E7` on white | **2.7:1** | **never small text** — graphics, bars, focus only |

That is why cyan is not a link colour. `text-brand-cyan` on light surfaces is a
bug, not a style choice.

### Typography

Public Sans, loaded from Google Fonts in `base.html`. Semantic classes rather
than ad-hoc `text-2xl font-black`:

| Class | Size | Weight | Tracking | Line height |
|---|---|---|---|---|
| `.type-display` | 36–48px (fluid) | 900 | −2% | 1.02 |
| `.type-h1` | 30–40px (fluid) | 900 | −2% | 1.05 |
| `.type-h2` | 24px | 800 | −2% | 1.15 |
| `.type-h3` | 18px | 800 | 0 | 1.3 |
| `.type-body` | 16px | 400 | 0 | **1.5** |
| `.type-body-sm` | 14px | 400 | 0 | **1.5** |
| `.type-caption` | 12px | 400 | 0 | 1.4 |
| `.type-eyebrow` | 12px | 800 | +6%, uppercase | 1.3 |

Headings are `brand-blue`, matching the Designportal.

**Deliberate deviation:** the corporate design allows 110–130% line height for
body copy. UI body text uses 150% because longer help texts, form labels and
table cells read better that way — and the portal's own stated goal is better
readability and accessibility. Headlines keep the tight corporate values.

### Radii, shadows, containers, motion

| Token | Value | Use |
|---|---|---|
| `--radius-control` | 6px | buttons, inputs, selects |
| `--radius-card` | 6px | cards, panels, list rows |
| `--radius-overlay` | 12px | dialogs, overlays |
| `--shadow-card` | `0 1px 2px rgb(0 0 0/.06)` | resting cards |
| `--shadow-raised` | `0 4px 6px -1px …` | hover, floating elements |
| `--shadow-overlay` | `0 20px 25px -5px …` | dialogs |
| `--container-admin` | 64rem | admin pages (matches the current `max-w-5xl`) |
| `--container-form` | 48rem | focused forms, prose |
| `--container-kiosk` | 52rem | respondent kiosk |
| `--ease-standard` | `cubic-bezier(.2,.6,.2,1)` | transitions |

### Der Balken

The signature element, specified digitally by the Designportal: 6px high, cyan,
1/3 logo-height clear space, above or below headings, as a section marker or to
highlight a module. Sparingly on white.

`.rule` (52px), `.rule--short` (24px), `.rule--full` (100%).

## Focus

One global treatment in the base layer: `outline: 2px solid var(--color-brand-cyan)`
with `outline-offset: 2px`. Components may tighten the offset; they must not
remove the outline.

## Components

Thin Jinja adapters in `app/src/dpp/templates/components/ui/`. Import what a
template needs; there is no global registry.

```jinja
{% from "components/ui/button.html" import button, link_button %}
{% from "components/ui/card.html" import card %}

{{ button("Speichern") }}
{% call card(padding="lg") %}…{% endcall %}
```

| Component | Classes | Macro | Notes |
|---|---|---|---|
| Button | `.btn`, `--primary/--secondary/--danger/--warning/--ghost`, `--sm/--md/--lg`, `--block` | `button()`, `link_button()` | primary hover darkens to `blue-700` |
| Icon button | `.icon-btn`, `--sm` | `icon_button()` | requires an `aria-label` |
| Badge | `.badge`, `--neutral/--info/--warning/--success/--danger`, `--sm/--md/--lg` | `badge()` | |
| Card | `.card`, `--default/--outlined/--interactive`, `--pad-none/sm/md/lg`, `__header/__title/__body/__footer` | `card()` (block) | `padding="none"` when using sections |
| Alert | `.alert`, `--info/--success/--warning/--danger` | `alert()` | caller adds `role` only for dynamic content |
| Dialog | `.dialog`, `__header/__title/__description/__heading/__body/__footer` | `dialog()` (block) | native `<dialog>`; open via `data-open-dialog` |
| Field | `.field`, `__label/__help/__error` | part of the control macros | wires `aria-describedby`/`aria-invalid` |
| Input / Textarea / Select / Checkbox | `.input`, `.textarea`, `.select`, `.checkbox`, `.checkbox-row` | `text_input()`, `textarea()`, `select()`, `checkbox()` | `select()` takes `options` as `{value,label,selected?,disabled?}` |
| Back link | `.back-link` | `back_link()` | arrow is `aria-hidden` |
| Empty state | `.empty-state`, `--plain` | `empty_state()` | |
| Stat | `.stat__value/__label/__hint` | `stat()` | score cards, summary tiles |

Conventions:

- Appearance lives in CSS; macros only emit classes and structure.
- `attrs="…"` passes htmx/`data-*`/`disabled` through unescaped — developer
  literals only, never user data.
- `icon_left`/`icon_right` take glyph characters (`+`, `→`, `×`), not HTML
  entities; they are escaped like normal text.
- Optional `class_name`/`class` parameters are for layout utilities only.

## Patterns

Larger compositions live in `app/src/dpp/templates/components/patterns/`. A
pattern earns a macro once it appears in three places; until then it is a
composition of primitives.

| Pattern | Classes | Macro | Notes |
|---|---|---|---|
| Page header | `.page-header`, `__main/__meta/__description/__actions` | `page_header()` (block for actions) | eyebrow, title, meta, description left; actions right |
| Filter bar | `.filter-bar`, `__grow/__fixed` | `filter_bar()` (block) | stacks below `sm`, one row above; `role="search"` |
| List row | `.list-row`, `--interactive/--split`, `__head/__body/__title/__meta/__aside` | `list_row()` (block) | `href` toggles link + hover; `split` for body/aside on wide screens |
| Action bar | `.action-bar`, `__group` | `action_bar()` (block) | top rule; groups push primary right |
| Stepper | `.stepper`, `__item/--current/--done/--upcoming`, `__number/__sep` | `stepper()` | data-driven; `state` drives current/done/upcoming |

## Rules

1. No raw hex in templates. Tokens or component classes only.
2. Utilities are for layout, spacing and responsive behaviour. Appearance belongs
   to a component class.
3. New visual need → add a token or a component, then an entry on `/_design`.
   Never a one-off class string.
4. Arbitrary values (`w-[calc(100%-2rem)]`) need a reason.
5. Accessibility is part of the contract: visible focus, labelled controls,
   44px targets in the kiosk, reduced motion respected.

## Status

| Layer | State |
|---|---|
| Tokens, type scale, base layer, Balken | **done** (v1 foundations) |
| Primitives: button, icon button, badge, card, alert, dialog, fields, back link, empty state, stat | **done** |
| Styleguide `/_design` | foundations, primitives and patterns render |
| Patterns: page header, filter bar, list row, action bar, stepper | **done** (v1) |
| Template migration | lists and campaigns module migrated (`list`, `detail`, `new`, `wizard`, `retrospective`); initiatives detail, crowd suite and landing next |
| Status banner | keep using `alert()`; add a pattern only if a page needs more than one |
| Legacy CSS (`help-badge`, `district-editor-dialog`, module carousel) | folded into components during migration |

## Portability

The class/HTML contract is framework-agnostic. Jinja macros today and Go
`html/template` (or `templ`) after the Fiber v3 rewrite are thin adapters that
emit the same classes. Keeping appearance in CSS rather than in utility strings
is what makes that port mechanical.
