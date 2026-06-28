# Tasks: Frontend Internationalization (i18n)

**Feature**: 029-i18n-frontend | **Branch**: `029-i18n-frontend`
**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/i18n-contract.md](contracts/i18n-contract.md), [quickstart.md](quickstart.md)

All paths are relative to repo root. Frontend lives in `admin/`.

**Tests**: No automated test suite is requested for this feature; verification is the
type gate (`npx tsc --noEmit`), the build gate (`npm run build`), and manual per-screen
language-switch checks (SC-001/002/003). One optional unit test is included in Polish.

**Migration convention** (applies to every US3 screen task): replace each user-facing
literal with `t('<key>')`, and add the key to BOTH `admin/src/locales/vi/<ns>.json` and
`admin/src/locales/en/<ns>.json`. API/server-sourced text is NOT translated.

---

## Phase 1: Setup

- [ ] T001 Add deps in `admin/package.json`: run `cd admin && npm install i18next react-i18next i18next-browser-languagedetector` (verify they appear under dependencies).
- [ ] T002 Create locale directories `admin/src/locales/vi/` and `admin/src/locales/en/` and `admin/src/i18n/`.

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ MUST complete before any user story phase.**

- [ ] T003 Create `admin/src/i18n/resources.ts` — static-import every namespace JSON for `vi` and `en`, export `resources` object `{ vi: {...}, en: {...} }` per contract §1. Start with `common` + `nav` (extend as namespaces are added).
- [ ] T004 Create `admin/src/i18n/index.ts` — `i18next.use(LanguageDetector).use(initReactI18next).init({...})` per [contracts/i18n-contract.md](contracts/i18n-contract.md) §1: `fallbackLng:'vi'`, `supportedLngs:['vi','en']`, `defaultNS:'common'`, detection `order/caches:['localStorage']`, `lookupLocalStorage:'jobflow.lang'`, `returnNull:false`, `interpolation.escapeValue:false`. Export `SUPPORTED_LANGUAGES` and the `i18n` instance.
- [ ] T005 In `admin/src/main.tsx` add `import "./i18n";` before `ReactDOM.createRoot(...).render(...)` so i18n initializes before first render.

**Checkpoint**: `npx tsc --noEmit` passes; app boots in Vietnamese; `i18n` available app-wide.

---

## Phase 3: User Story 1 + 2 — Working, persisted language switch (Priority: P1) 🎯 MVP

**Goal**: Header switcher toggles vi/en with no reload (US1) and the choice persists
across reload/new-tab via localStorage (US2). Demonstrated on nav + shared chrome.

**Independent test**: Open any page → switch language from the header → nav/common
chrome changes language in <1s, no reload, active language highlighted → reload →
app returns in the chosen language → set an invalid `jobflow.lang` → reload → falls
back to Vietnamese.

- [ ] T006 [P] [US1] Seed `admin/src/locales/vi/common.json` and `admin/src/locales/en/common.json` — shared chrome keys: `actions.*` (save, cancel, delete, edit, add, close, confirm, retry…), `status.*`, `table.*` (empty, loading, columns), `toast.*`, `language.*` (label, vi, en). (per contract §4)
- [ ] T007 [P] [US1] Seed `admin/src/locales/vi/nav.json` and `admin/src/locales/en/nav.json` — every sidebar item label + section titles ("Staffing"/"System") from `admin/src/config/admin.ts`, plus header items.
- [ ] T008 [US1] Create `admin/src/components/language-switcher.tsx` — render an option per `SUPPORTED_LANGUAGES`, highlight `i18n.resolvedLanguage`, on select call `i18n.changeLanguage(code)`. Use HeroUI `Popover`/`Button` + Tailwind/HeroUI semantic colors consistent with `admin-header.tsx` controls (per contract §3).
- [ ] T009 [US1] Mount `<LanguageSwitcher/>` in `admin/src/components/admin/admin-header.tsx` right-hand cluster (beside `NotificationBell`); keep reachable at narrow widths.
- [ ] T010 [US1] Migrate nav labels: in `admin/src/config/admin.ts` change `label` values to `nav:` keys (or keep keys + translate at render). Update `admin/src/components/admin/admin-sidebar.tsx` to render labels via `useTranslation('nav')`/`t(item.label)`.
- [ ] T011 [US2] Verify persistence behavior end-to-end (manual per quickstart §6): localStorage write on switch, restore on reload, invalid-value fallback to `vi`. Fix detector config in `admin/src/i18n/index.ts` if any check fails.

**Checkpoint**: MVP shippable — switch + persistence work on nav/common; `tsc --noEmit` + `npm run build` green.

---

## Phase 4: User Story 3 Wave 1 — High-traffic Staffing screens (Priority: P2)

**Goal**: Full string extraction for the daily Staffing surface. Each task migrates one
screen/module to `t(...)` and fills both language files for its namespace.

**Independent test**: For each migrated screen, switch language → 0 strings remain in
the previous language; dynamic values (counts/names/dates) render correctly.

- [ ] T012 [P] [US3] Migrate Dashboard → ns `dashboard`: `admin/src/pages/admin/dashboard.tsx` + `admin/src/components/dashboard/*.tsx` (KpiStrip, StaffingDashboard, SectionCard, CatalogComposition, FreshnessActivity, LabelingProgress, MailRepliesBlock, ModelStatus, VerifierExtractorOps, AuthStateBanner, charts). Add `vi/en` `dashboard.json`.
- [ ] T013 [P] [US3] Migrate Employees → ns `employees`: `admin/src/pages/admin/employees/{index,detail,info}.tsx` + `admin/src/components/admin/cv-versions-card.tsx` + `admin/src/components/admin/email-account-card.tsx` + `admin/src/components/match-score-badge.tsx` + `admin/src/components/match-status-chip.tsx`. Add `vi/en` `employees.json`.
- [ ] T014 [P] [US3] Migrate Jobs → ns `jobs`: `admin/src/pages/admin/jobs/{index,_job-card,_job-drawer,_primitives}.tsx` + `admin/src/pages/admin/job-tracking.tsx`. Add `vi/en` `jobs.json`.
- [ ] T015 [P] [US3] Migrate Mail → ns `mail`: `admin/src/pages/admin/{mail,mail-detail,apply-email}.tsx` + the `NotificationBell` strings in `admin/src/components/admin/admin-header.tsx` ("Notifications", "Mark all read", "You're all caught up", "View all mail", relTime suffixes). Add `vi/en` `mail.json`.

**Checkpoint**: Daily Staffing screens fully translatable; gates green.

---

## Phase 5: User Story 3 Wave 2 — Remaining Staffing + System screens (Priority: P2)

- [ ] T016 [P] [US3] Migrate Schedule → ns `schedule`: `admin/src/pages/admin/schedule/{_schedule-page,extract,morning-refresh,verify}.tsx`. Add `vi/en` `schedule.json`.
- [ ] T017 [P] [US3] Migrate Labeling → ns `labeling`: `admin/src/pages/admin/{labeling}.tsx` + `admin/src/pages/admin/label-batch/{index,overview,detail}.tsx` + `admin/src/components/labeling/*.tsx` (CVPanel, DimScoreInput, JobCard, LabelingProgress, OverallSelector). Add `vi/en` `labeling.json`.
- [ ] T018 [P] [US3] Migrate CVs → ns `cvs`: `admin/src/pages/admin/{cvs,cv-upload,cv-batch}.tsx` + `admin/src/pages/admin/cv-batch/{overview,detail}.tsx`. Add `vi/en` `cvs.json`.
- [ ] T019 [P] [US3] Migrate LLM → ns `llm`: `admin/src/pages/admin/{llm-providers,llm-logs,jd-batch}.tsx` + `admin/src/pages/admin/jd-batch/{overview,new,detail,_primitives,_record-drawer}.tsx`. Add `vi/en` `llm.json`.
- [ ] T020 [P] [US3] Migrate Settings/System → ns `settings`: `admin/src/pages/admin/{settings,system}.tsx`. Add `vi/en` `settings.json`.
- [ ] T021 [P] [US3] Migrate Integrations → ns `integrations`: `admin/src/pages/admin/integrations.tsx`. Add `vi/en` `integrations.json`.
- [ ] T022 [P] [US3] Migrate Auth/public → ns `auth`: login + `admin/src/components/{admin-route,public-route}.tsx` + any auth screens. Add `vi/en` `auth.json`.
- [ ] T023 [US3] Register all new namespaces in `admin/src/i18n/resources.ts` and the `ns:[...]` list in `admin/src/i18n/index.ts` (ensure every namespace imported for both languages).

**Checkpoint**: All screens translatable; gates green.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T024 Sweep for residual hardcoded strings per quickstart §7 (grep Vietnamese diacritics + English JSX literals in `admin/src/pages` + `admin/src/components`); migrate stragglers into the matching namespace.
- [ ] T025 [P] Verify key-set parity between `vi/` and `en/` for every namespace (no missing keys → no fallback gaps); fix mismatches.
- [ ] T026 [P] (Optional) Add a Vitest unit test in `admin/src/components/__tests__/` asserting i18n init defaults to `vi`, `changeLanguage('en')` updates `resolvedLanguage`, and an invalid stored value falls back to `vi`.
- [ ] T027 Final gates: `cd admin && npx tsc --noEmit && npm run build`; manual full-app switch pass (every nav destination, both languages, reload persistence). Restart Vite to confirm clean boot.

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T005)** block everything.
- **US1+US2 (T006–T011)** = MVP, depends only on Foundational. T006/T007 are [P]; T008→T009→T010 sequential (switcher → mount → nav render); T011 after.
- **US3 Wave 1 (T012–T015)** and **Wave 2 (T016–T022)** each touch disjoint files → all `[P]` within their wave; depend on Foundational (and benefit from `common` from T006). T023 after all namespaces created.
- **Polish (T024–T027)** last.

## Parallel Execution Examples

- After T005: run T006 and T007 in parallel (different files).
- Wave 1: T012, T013, T014, T015 in parallel (disjoint screens/namespaces).
- Wave 2: T016–T022 in parallel (disjoint screens/namespaces).

## Implementation Strategy

1. **MVP** = Phases 1–3 (T001–T011): a working, persisted header language switch over
   nav + shared chrome. Demoable and shippable on its own.
2. **Incremental coverage** = Phases 4–5: extract screens wave by wave; each screen is
   independently verifiable (switch → 0 stale strings).
3. **Harden** = Phase 6: sweep, parity check, gates.

## Total

27 tasks — Setup 2, Foundational 3, US1+US2 6, US3 Wave 1 4, US3 Wave 2 8, Polish 4.
