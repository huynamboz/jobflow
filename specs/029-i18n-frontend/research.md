# Phase 0 Research: Frontend i18n

## Decision 1 — i18n library

**Decision**: `i18next` + `react-i18next` + `i18next-browser-languagedetector`.

**Rationale**:
- De-facto standard for React; first-class hook API (`useTranslation`), namespace
  support (maps directly to FR-008 "split files per module"), interpolation +
  pluralization (FR-010), and a missing-key fallback chain (FR-009).
- The language detector plugin natively supports `localStorage` order + caching
  (FR-004/FR-006) with a configurable key and fallback — no custom persistence code.
- No backend; pure client bundle, fits the Vite SPA with zero server work.

**Alternatives considered**:
- `react-intl` (FormatJS): heavier ICU message authoring, less ergonomic namespace
  splitting, more boilerplate per string. Rejected — overkill for vi/en chrome.
- `lingui`: nice macro DX but adds a Babel/SWC macro build step into Vite and a CLI
  extraction toolchain. Rejected — extra build complexity for 2 languages.
- Hand-rolled context + JSON maps: no pluralization/interpolation/fallback for free;
  re-implements what i18next already hardens. Rejected.

## Decision 2 — Resource loading strategy

**Decision**: Eager-bundle all locale JSON via static imports registered in
`src/i18n/resources.ts`; pass as `resources` to `i18next.init`.

**Rationale**: Total string volume for a 2-language admin tool is small (tens of KB);
eager import keeps switching instant (SC-001, no async flash) and the setup trivial.
Lazy `i18next-http-backend` would add network round-trips and a public assets path for
no real payoff at this size. Revisit only if a 3rd/4th language balloons the bundle.

**Alternatives considered**: HTTP backend lazy loading (rejected — needless async +
flash of keys), Vite dynamic `import.meta.glob` (viable but premature; static is simpler
and tree-shakeable enough here).

## Decision 3 — Persistence + detection

**Decision**: `languagedetector` with `order: ['localStorage']`, `caches:
['localStorage']`, `lookupLocalStorage: 'jobflow.lang'`, `fallbackLng: 'vi'`,
`supportedLngs: ['vi','en']`, `nonExplicitSupportedLngs: true`.

**Rationale**: Reads stored choice on load (FR-004), writes on change (the switcher
calls `i18n.changeLanguage` → detector caches it), and `fallbackLng` +
`supportedLngs` guarantee a corrupt/unsupported stored value degrades to `vi`
(FR-006). Default-on-first-visit = `vi` (FR-005). We intentionally do NOT include
`'navigator'` in the order so the app is deterministically Vietnamese by default rather
than guessing from browser locale.

**Alternatives considered**: navigator-first detection (rejected — spec fixes the
default to Vietnamese, browser-locale guessing would surprise users); custom
`localStorage` read in a Zustand store (rejected — duplicates the plugin, more code).

## Decision 4 — Namespace map (file splitting)

**Decision**: One namespace = one module/page group; `common` + `nav` are global.
Files: `common`, `nav`, `dashboard`, `employees`, `jobs`, `mail`, `schedule`,
`labeling`, `cvs`, `llm`, `settings`, `auth`, `integrations`. `defaultNS: 'common'`.

**Rationale**: Mirrors the existing `src/pages/admin/*` + Staffing/System nav grouping,
so each screen mostly imports a single namespace via `useTranslation('employees')`.
Directly satisfies FR-008/SC-005 ("no single monolithic file"). Shared chrome (buttons,
statuses, table headers, toasts) lives in `common` to avoid duplication.

**Alternatives considered**: one big `translation.json` (rejected — violates FR-008),
per-component files (rejected — too granular, fragments shared strings, hurts reuse).

## Decision 5 — Key naming + interpolation

**Decision**: Nested keys, lowerCamelCase leaf paths, namespaced access
(`t('employees:list.emptyState')`). Interpolation via `{{var}}`; counts via i18next
plural suffix keys (`_one`/`_other`) with `{{count}}`. Default value = the key path so a
missing entry renders the key, never blank (FR-009/SC-007).

**Rationale**: Predictable, greppable, stable language-agnostic keys (FR-007/FR-011);
interpolation/pluralization handled by the library (FR-010).

**Alternatives considered**: English-source-as-key (natural-language keys) — rejected
because the app is Vietnamese-first and source strings change wording often, which would
churn keys.

## Decision 6 — Migration approach (extraction)

**Decision**: Incremental, screen-by-screen. Foundation (switch + nav + common) ships
first as the MVP (US1+US2); then waves of screens (US3) replace hardcoded JSX text and
string literals with `t(...)` calls, adding entries to the matching namespace in both
`vi` and `en` in the same change.

**Rationale**: Matches the spec's MVP framing and keeps each PR/slice independently
testable and shippable; avoids one giant untestable diff across 70 files.

**Verification per screen**: switch language → 0 strings remain in the previous language
(SC-003); `tsc --noEmit` + `npm run build` stay green.

## Open item resolved

- **Default language**: Vietnamese (`vi`) — confirmed from the current Vietnamese-first
  UI and the spec assumption. English (`en`) is the secondary.
