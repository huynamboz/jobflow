# Feature Specification: Port NODE Design Tokens to Admin App

**Feature Branch**: `004-node-design-tokens`

**Created**: 2026-05-13

**Status**: Draft

**Input**: User description: "Port NODE design tokens to admin Tailwind + HeroUI"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Admin app picks up NODE's visual identity (Priority: P1)

An operator opening any page of the admin app today sees the default
HeroUI palette — generic blue primary, default greys, default radii.
The NODE Economy V1 design system already defines a tuned palette
(soft cool greys + 6 calibrated accents), a specific radii scale
(`r-2` through `r-32`), seven distinct shadows tuned per surface
(card, popover, modal, button), and a typography pair (Inter + JetBrains
Mono). The fix imports those tokens into the admin app's Tailwind + HeroUI
configuration so every existing page, including the dashboard, picks up
the NODE look without any per-component refactor.

**Why this priority**: The admin app currently has a mix of HeroUI defaults
plus a half-finished `jb-*` palette in `globals.css` that nothing reads
from. A clean, single source of truth (NODE tokens) ends the drift.

**Independent Test**: After this feature ships, opening
`/admin/dashboard` (or any other admin page) shows components with NODE's
specific cool-grey surface, NODE's blue accent on primary buttons, and
the NODE card shadow. The match doesn't have to be pixel-perfect against
the source NODE preview, but the named tokens (`bg-node-surface`,
`shadow-node-card`, `rounded-node-12`) MUST resolve to the documented
values from `colors_and_type.css`.

**Acceptance Scenarios**:

1. **Given** a developer adds `<div class="bg-node-surface rounded-node-12 shadow-node-card">` to any admin component, **When** the dev server renders the page, **Then** the div uses `#fcfcfc` background, `12px` border radius, and NODE's calibrated card shadow.
2. **Given** a HeroUI `<Button color="primary">` is rendered, **When** the user inspects it, **Then** the button background is `#3582ff` (NODE blue), not HeroUI's default `#006FEE`.
3. **Given** any text on the page that uses the default font, **When** the page renders, **Then** the font is Inter loaded from the Google Fonts URL specified in `colors_and_type.css`.

---

### Edge Cases

- **HeroUI components that hardcode hex colors**: a small number of HeroUI internals reference colors outside the theme — accept that those stay HeroUI-default in v1. The feature MUST NOT patch HeroUI source.
- **Existing pages using `jb-*` classes**: these classes have no consumers in the codebase (verified by grep before shipping); they can be removed in the same change or left in place. Either is fine.
- **Tailwind v4 `@theme` directive**: the admin app uses Tailwind v4. New tokens are added through the `@theme` block in `globals.css` AND through the Tailwind config (for HeroUI's color extension) — both paths so HeroUI's theming layer and arbitrary `bg-node-*` classes both work.
- **Font load failure**: if Google Fonts is blocked, the page falls back to `system-ui, sans-serif` (existing browser stack); no broken rendering.
- **Dark mode**: out of scope. The admin app continues to render in light only. Tailwind's `darkMode: 'class'` config is left intact for future use; no dark variants are populated in this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A single CSS file in `admin/src/styles/` MUST contain all NODE token CSS variables (`--c1`..`--c9`, `--blue`/`--orange`/`--yellow`/`--red`/`--purple`/`--green`, `--bg`/`--surface`/`--raised`/`--sunken`/`--line`/`--line-2`/`--ink`/`--ink-soft`/`--muted`, `--r-2`..`--r-32`, all `--shadow-*`, all `--s-*`, the font imports). Source: `colors_and_type.css` from the NODE repo.
- **FR-002**: Tailwind's `@theme` block in `globals.css` MUST expose every NODE token to utility classes via the `node-*` namespace (e.g. `bg-node-surface`, `text-node-ink`, `rounded-node-12`, `shadow-node-card`, `font-node-mono`).
- **FR-003**: HeroUI's theme configuration MUST be overridden so its semantic colors (`primary`, `success`, `warning`, `danger`, `default`, `foreground`, `background`) map to NODE tokens. HeroUI's existing `radius` already specifies `small=10px, medium=14px, large=20px`; aligned to NODE's radii — these stay or move to `r-10/r-12/r-20`.
- **FR-004**: The admin app's body font MUST be Inter, loaded from the Google Fonts URL specified in `colors_and_type.css`. Monospace font for code / numbers MUST be JetBrains Mono.
- **FR-005**: Existing `jb-*` tokens that have no consumers MUST be removed in the same change (after a grep check confirms zero references). Tokens with consumers stay until those consumers migrate.
- **FR-006**: Adding a `<div class="bg-node-raised rounded-node-12 shadow-node-card p-4">…</div>` in any admin component MUST render with NODE's values without further configuration.
- **FR-007**: The TypeScript compiler MUST pass (`npx tsc --noEmit` clean) and the production build (`npm run build`) MUST succeed after the change.

### Key Entities

- **NODE token set**: the CSS variable inventory copied from `colors_and_type.css`. Single source of truth.
- **Tailwind theme block**: `@theme` declarations in `globals.css` that expose those CSS vars as Tailwind utility classes.
- **HeroUI theme block**: the `heroui({...})` call in `tailwind.config.js` that maps NODE accents into HeroUI's semantic color slots.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A grep of `admin/src/` for `bg-node-` / `rounded-node-` / `shadow-node-` / `font-node-` MUST return real matches in at least one new component after migration — i.e. the tokens are not just declared, they are usable.
- **SC-002**: A grep of `admin/src/` for `color-jb-` / `bg-jb-` / `rounded-jb-` MUST return zero matches after the change (legacy tokens cleaned up).
- **SC-003**: Default HeroUI button (`<Button color="primary">`) renders with NODE blue `#3582ff` ± nominal anti-alias.
- **SC-004**: The admin app's `npm run build` succeeds with bundle delta ≤+10 KB gzipped over baseline (tokens are pure CSS — minimal payload).
- **SC-005**: The dashboard page (v2 from spec 003) visually adopts the NODE surface/radius/shadow without any component code change beyond what FR-002 enables (i.e. the Tailwind theme layer carries the change).

## Assumptions

- The admin app keeps HeroUI as its primary component library. Replacing HeroUI primitives with NODE primitives is out of scope for this feature.
- The NODE source `colors_and_type.css` is the canonical token list; values are copied verbatim from `/Users/huynam/Documents/WORK/UPWORK/NODE · Economy V1 Design System/colors_and_type.css`.
- Tailwind v4's `@theme` block is the modern way to expose tokens in the admin app's `globals.css`. The classic `tailwind.config.js` is kept only for the HeroUI plugin invocation.
- No new fonts are self-hosted; Google Fonts CDN is acceptable for v1.
- Existing chart wrappers (Recharts) use inline color literals (e.g., `#0ea5e9`). They are left as-is for v1; future polish can migrate them to NODE accents.
- Dashboard sections (KpiStrip, Catalog…) need no code change to pick up new tokens — they already use HeroUI Card + Tailwind utilities that resolve through the theme layer.
