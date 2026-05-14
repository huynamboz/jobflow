# Implementation Plan: Port NODE Design Tokens to Admin App

**Branch**: `004-node-design-tokens` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)

## Summary

Copy `colors_and_type.css` from the NODE Economy V1 design system into
`admin/src/styles/node-tokens.css`. Import it from `globals.css` before
the existing `@theme` block. Add a parallel `@theme` block that exposes
every NODE token as a Tailwind utility (`bg-node-*`, `rounded-node-*`,
`shadow-node-*`, `font-node-*`, `space-node-*`). Override HeroUI's
semantic color slots in `tailwind.config.js` to use NODE accents. Delete
unused `jb-*` tokens (none have consumers — confirmed by grep).

No component refactor. The dashboard and other admin pages pick up the
new look via the theme layer.

## Technical Context

**Language/Version**: TypeScript 5.x + React 18 (admin app).

**Primary Dependencies**: Tailwind v4 (existing), `@heroui/theme`
(existing), no new packages.

**Storage**: N/A — design tokens are pure CSS variables.

**Testing**: `npx tsc --noEmit` clean; `npm run build` succeeds with
bundle delta ≤+10 KB gzipped. Visual smoke against the dashboard page
to confirm the look adopts the new tokens.

**Target Platform**: Same as before — modern browsers, light mode.

**Project Type**: Frontend-only change. No backend, no Django, no DB.

**Performance Goals**: Bundle delta ≤+10 KB gzipped. Page paint is
unaffected — tokens are static CSS.

**Constraints**:
- HeroUI components stay; primitives are NOT replaced.
- No new dependencies.
- Tailwind v4 `@theme` block is the modern path; legacy `colors:{}`
  in `tailwind.config.js` is reserved for HeroUI plugin only.
- Light mode only; `darkMode: 'class'` is preserved but no dark
  variables are populated.

**Scale/Scope**: One CSS file copied, one `@theme` block extended,
one Tailwind config edit, one cleanup pass. ~3-4 hours.

## Constitution Check

Placeholder constitution. No gates apply.

## Project Structure

### Documentation (this feature)

```text
specs/004-node-design-tokens/
├── plan.md
├── spec.md
├── tasks.md
└── checklists/requirements.md   (optional; small feature)
```

### Source Code (affected files)

```text
admin/
├── src/
│   └── styles/
│       ├── globals.css                      EDIT — replace jb-* block with @theme node-*
│       └── node-tokens.css                  NEW — verbatim copy of colors_and_type.css
├── tailwind.config.js                       EDIT — HeroUI theme override with NODE accents
└── (no component changes in v1)
```

NODE source remains untouched at
`/Users/huynam/Documents/WORK/UPWORK/NODE · Economy V1 Design System/colors_and_type.css`.

**Structure Decision**: Token CSS lives next to the existing `globals.css`
so the import chain is local; the file is copied (not symlinked) so the
admin app has no external path dependency at runtime.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Two `@theme` blocks (current + new) instead of one merged block | Keeps the migration diff readable — reviewer sees exactly which tokens were added. | A merged block hides the boundary between old and new tokens during review. |

(No other deviations.)
