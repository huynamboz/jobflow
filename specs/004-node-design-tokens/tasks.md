---
description: "Task list — Port NODE design tokens to admin app"
---

# Tasks: NODE Design Tokens

**Input**: Design docs in `/specs/004-node-design-tokens/`.

**Prerequisites**: spec.md, plan.md.

**Tests**: No unit tests (pure CSS / theme change). Quality gates are
`tsc --noEmit`, `npm run build`, and a visual smoke against the
dashboard page.

**Organization**: Single user story (US1 = picks up NODE look).

## Format: `[ID] [P?] Description`

---

## Phase 1: Copy + wire tokens

- [ ] T001 Copy `colors_and_type.css` from
  `/Users/huynam/Documents/WORK/UPWORK/NODE · Economy V1 Design System/colors_and_type.css`
  to `admin/src/styles/node-tokens.css` verbatim. Add a short header
  comment noting the source path + date copied.
- [ ] T002 Edit `admin/src/styles/globals.css`:
  - At top, add `@import "./node-tokens.css";` BEFORE `@import "tailwindcss";`
    so the `:root` declarations are available everywhere.
  - Add a new `@theme` block that maps NODE CSS vars to Tailwind
    utilities — namespace `node-*` (e.g. `--color-node-surface`,
    `--radius-node-12`, `--shadow-node-card`, `--font-node-sans`,
    `--font-node-mono`).
  - Audit the existing `--color-jb-*` block: grep `admin/src/` for
    `jb-` usage. If zero matches, delete the `jb-*` block. If matches
    exist, leave the block but flag in commit message.
- [ ] T003 Edit `admin/tailwind.config.js`: pass a `colors` override to
  the `heroui({...})` call mapping HeroUI semantic colors to NODE
  accents:
  - `primary: { DEFAULT: 'var(--blue)', foreground: '#fff' }`
  - `success: { DEFAULT: 'var(--green)', foreground: '#fff' }`
  - `warning: { DEFAULT: 'var(--yellow)', foreground: 'var(--ink)' }`
  - `danger:  { DEFAULT: 'var(--red)',   foreground: '#fff' }`
  - `default: { DEFAULT: 'var(--c3)', foreground: 'var(--ink)' }`
  - `background: 'var(--bg)'`, `foreground: 'var(--ink)'`
  - Verify HeroUI's `radius` block (`small=10, medium=14, large=20`)
    is consistent with NODE radii; the medium (14px) is non-NODE,
    swap to `12px` to align with NODE's `--r-12`.
- [ ] T004 Verify Inter + JetBrains Mono load: NODE's CSS already
  contains the Google Fonts `@import`, so importing `node-tokens.css`
  in step T002 pulls them in transitively. Add `font-node-sans` to the
  `<body>` element via `body { font-family: var(--font-node-sans); }` or
  by setting Tailwind's default `font-sans` to the NODE stack.

## Phase 2: Quality gates

- [ ] T005 Run `cd admin && npx tsc --noEmit`. MUST be clean.
- [ ] T006 Run `cd admin && npm run build`. MUST succeed. Bundle delta
  must be ≤+10 KB gzipped over the previous build (SC-004).
- [ ] T007 Start dev server (`npm run dev`) and visually verify:
  - The dashboard primary "Refresh" button shows NODE blue
    (`#3582ff`).
  - Cards on the dashboard use the NODE surface + shadow.
  - Body text uses Inter (not the system font).
  - Numbers in metric cards use JetBrains Mono if explicitly classed
    `font-node-mono` (the v1 doesn't auto-mono numbers).
- [ ] T008 Grep test: `grep -r 'color-jb-\|bg-jb-\|rounded-jb-' admin/src/`
  must return zero (SC-002). If a match shows up that isn't trivially
  removable, file a follow-up to migrate it instead.

## Phase 3: Documentation + commit

- [ ] T009 Add a short note to `roadmap/commands.md` (existing file)
  mentioning where the tokens live and how to use them
  (`bg-node-surface`, `rounded-node-12`, etc.).
- [ ] T010 One commit per significant change, or one squash commit
  summarising:
  ```
  feat(admin): port NODE design tokens to Tailwind + HeroUI

  - copy NODE colors_and_type.css → admin/src/styles/node-tokens.css
  - expose tokens as Tailwind utilities under node-* namespace
  - map HeroUI semantic colors to NODE accents (blue/green/yellow/red)
  - load Inter + JetBrains Mono via NODE's Google Fonts import
  - delete unused jb-* token block (zero consumers)
  ```

---

## Dependency graph

```text
T001 (copy CSS)
   │
   ▼
T002 (globals.css wiring)
   │
   ▼
T003 (HeroUI override) ─── T004 (font verification)
   │                              │
   ▼                              ▼
T005 (tsc) → T006 (build) → T007 (visual smoke) → T008 (grep cleanup)
   │
   ▼
T009 (docs) → T010 (commit)
```

## Effort estimate

| Phase | Hours |
|-------|-------|
| 1 Copy + wire | 1.5 |
| 2 Quality gates | 0.5 |
| 3 Docs + commit | 0.5 |
| **Total** | **~2.5h** |

Smaller than the 3-4h spec-prep estimate; most "work" is verifying the
tokens propagated correctly.
