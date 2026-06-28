# Implementation Plan: Frontend Internationalization (i18n)

**Branch**: `029-i18n-frontend` | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/029-i18n-frontend/spec.md`

## Summary

Add a two-language (Vietnamese default, English) internationalization layer to the
`admin/` React SPA. Wire `i18next` + `react-i18next` with namespace-split JSON
resource files under `admin/src/locales/{vi,en}/`, a header language switcher that
persists the choice to `localStorage` and restores it on load, and incrementally
migrate every hardcoded user-facing string (37 pages + 29 components) to translation
keys grouped by module. The i18n runtime is wired once at the app root; string
extraction proceeds screen-by-screen so the working switch (MVP) ships before full
coverage.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18, Vite 6

**Primary Dependencies**: `i18next`, `react-i18next`, `i18next-browser-languagedetector` (new); existing HeroUI, Tailwind v4, React Router, Zustand

**Storage**: Browser `localStorage` (key `jobflow.lang`) for the language preference — no backend changes

**Testing**: `npx tsc --noEmit` (type gate) + `npm run build` (Vite build gate); manual switch verification per screen; optional Vitest unit test for the i18n init + persistence

**Target Platform**: Modern browsers (admin SPA), dev server Vite on :5173

**Project Type**: Web application — frontend only (`admin/`)

**Performance Goals**: Language switch re-renders the current page in < 1s with no full reload (SC-001); namespace resources eager-bundled, no perceptible load cost

**Constraints**: No backend/API changes; API-sourced data (job text, LLM output, errors from server) is NOT translated; both languages are LTR; default = Vietnamese; adding a 3rd language must require only new files + a switcher entry (FR-011/SC-006)

**Scale/Scope**: ~70 `.tsx` files (37 pages, 29 components) under `admin/src`; one switcher; ~10–14 namespaces (one per major module/page group: common, nav, dashboard, employees, jobs, mail, schedule, labeling, cvs, llm, settings, auth, integrations)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unpopulated template
with no ratified principles, so there are no formal gates to evaluate. Applying the
project's de-facto conventions from `CLAUDE.md` instead:

- **Prefer Tailwind utilities + HeroUI semantic colors** — switcher reuses existing UI primitives, no ad-hoc styling beyond header norms. ✅
- **Restart Vite after theme/config changes** — i18n init touches `main.tsx`/provider, not tailwind config; standard restart noted in quickstart. ✅
- **No scope creep into backend** — feature is FE-only; no Django/DRF changes. ✅
- **Incremental, independently shippable slices** — US1+US2 (switch + persistence) ship before US3 (full extraction), matching the spec's MVP framing. ✅

No violations. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/029-i18n-frontend/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 — stack & pattern decisions
├── data-model.md        # Phase 1 — i18n resource/entity model
├── quickstart.md        # Phase 1 — dev setup + verification + migration recipe
├── contracts/
│   └── i18n-contract.md # Phase 1 — runtime config, key naming, namespace map
├── checklists/
│   └── requirements.md  # Spec quality checklist (done)
└── tasks.md             # Phase 2 — created by /speckit-tasks (NOT here)
```

### Source Code (repository root)

```text
admin/
├── src/
│   ├── i18n/
│   │   ├── index.ts             # i18next init: namespaces, detection, fallback, resources
│   │   └── resources.ts         # eager imports of all locale JSON, typed registration
│   ├── locales/
│   │   ├── vi/
│   │   │   ├── common.json       # shared: buttons, status, table chrome, toasts
│   │   │   ├── nav.json          # sidebar/header nav labels (config/admin.ts)
│   │   │   ├── dashboard.json
│   │   │   ├── employees.json
│   │   │   ├── jobs.json
│   │   │   ├── mail.json
│   │   │   ├── schedule.json
│   │   │   ├── labeling.json
│   │   │   ├── cvs.json
│   │   │   ├── llm.json
│   │   │   ├── settings.json
│   │   │   ├── auth.json
│   │   │   └── integrations.json
│   │   └── en/                   # same filenames, English values
│   │       └── … (mirror of vi/)
│   ├── components/
│   │   ├── language-switcher.tsx # NEW — header control
│   │   └── admin/admin-header.tsx# MODIFY — mount switcher
│   ├── config/admin.ts           # MODIFY — nav labels become i18n keys
│   ├── main.tsx / provider.tsx   # MODIFY — import './i18n' before render
│   └── pages/** , components/**  # MODIFY incrementally — useTranslation()
└── package.json                  # MODIFY — add i18next deps
```

**Structure Decision**: Frontend-only change confined to `admin/`. A dedicated
`src/i18n/` holds runtime wiring; `src/locales/<lang>/<namespace>.json` holds the
split resources (one file per module → satisfies FR-008/SC-005). Screens consume
strings through `react-i18next`'s `useTranslation(namespace)` hook. No new top-level
projects; this is an additive layer over the existing SPA.

## Implementation Phases (delivery order)

1. **Runtime foundation (US1+US2 MVP)** — add deps; create `src/i18n/index.ts` with
   `vi` default + `en`, `localStorage` detection/caching (`jobflow.lang`), key/key
   fallback; import in `main.tsx`; build `language-switcher.tsx`; mount in header;
   seed `common.json` + `nav.json` for both languages; migrate `config/admin.ts` nav
   labels. **Demoable:** header switch toggles nav + common chrome, persists across reload.
2. **High-traffic screens (US3 wave 1)** — extract Dashboard, Employees, Jobs, Mail
   namespaces (the daily Staffing surface).
3. **Remaining Staffing + System screens (US3 wave 2)** — schedule, job-tracking,
   labeling, cvs, llm, settings, integrations, auth/login.
4. **Sweep + gate** — grep for residual hardcoded display strings; verify `tsc --noEmit`
   + `npm run build`; per-screen switch check (0 stale-language strings).

## Complexity Tracking

No constitution violations; section intentionally empty.
