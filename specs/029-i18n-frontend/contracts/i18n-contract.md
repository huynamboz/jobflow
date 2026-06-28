# i18n Contract — admin SPA

This is the UI/runtime contract for the internationalization layer. It is the stable
surface every screen depends on.

## 1. Runtime init (`src/i18n/index.ts`)

```ts
export const SUPPORTED_LANGUAGES = [
  { code: 'vi', label: 'Tiếng Việt', isDefault: true },
  { code: 'en', label: 'English' },
] as const;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,                       // from resources.ts (eager-bundled JSON)
    fallbackLng: 'vi',
    supportedLngs: ['vi', 'en'],
    nonExplicitSupportedLngs: true,
    defaultNS: 'common',
    ns: ['common', 'nav', /* … all namespaces */],
    interpolation: { escapeValue: false },   // React already escapes
    detection: {
      order: ['localStorage'],
      caches: ['localStorage'],
      lookupLocalStorage: 'jobflow.lang',
    },
    returnNull: false,
  });
```

- MUST be imported once for side effects in `src/main.tsx` **before** `<App/>` renders.
- MUST NOT include `'navigator'` in detection order (default is deterministically `vi`).

## 2. Consuming strings (every screen/component)

```ts
const { t } = useTranslation('employees');     // namespace per screen
t('list.title');                                // → "Nhân viên" / "Employees"
t('list.count', { count: n });                  // pluralized + interpolated
t('common:actions.save');                       // cross-namespace access
```

**Rules**:
- No user-facing literal strings in JSX/attributes (`placeholder`, `aria-label`,
  `title`, toast messages, table headers, empty states) — all go through `t(...)`.
- Keys are nested, lowerCamelCase leaves. Namespaced keys use `ns:path`.
- A missing key renders its key path (never blank, never throws) — FR-009/SC-007.
- API/server-sourced text (job data, LLM output, backend error messages) is NOT
  translated — it is data, out of contract scope.

## 3. Language switcher contract (`src/components/language-switcher.tsx`)

- Renders an option per `SUPPORTED_LANGUAGES` entry; highlights the active one
  (`i18n.resolvedLanguage`).
- On select → `i18n.changeLanguage(code)`; the detector caches to `localStorage`.
- MUST update the visible page with no full reload (< 1s, SC-001).
- Mounted in `src/components/admin/admin-header.tsx` (right cluster, beside the
  notification bell), reachable on every authenticated screen (FR-002), including
  narrow widths.
- Visual: reuse HeroUI primitives (e.g. `Popover`/`Button` or a compact dropdown) +
  Tailwind/HeroUI semantic colors — consistent with existing header controls.

## 4. Namespace map

| Namespace | Owns strings for |
|-----------|------------------|
| `common` | buttons, statuses, table chrome, toasts, confirm dialogs, shared labels |
| `nav` | sidebar + header nav labels (`config/admin.ts`), group titles |
| `dashboard` | dashboard page + dashboard components |
| `employees` | employees list/detail, CV versions, matches |
| `jobs` | jobs list/detail, job-tracking, platform/salary UI |
| `mail` | mail list/detail, apply-email, notifications panel |
| `schedule` | morning-refresh, verify-schedule |
| `labeling` | labeling + label-batch |
| `cvs` | cvs dataset, cv-upload, cv-batch |
| `llm` | llm-providers, llm-logs, jd-batch |
| `settings` | settings, system overview |
| `auth` | login / public routes |
| `integrations` | integrations page |

## 5. Acceptance mapping

| Requirement | Contract element |
|-------------|------------------|
| FR-001 two languages | `SUPPORTED_LANGUAGES` (vi, en) |
| FR-002 header switcher everywhere | §3 mounted in admin-header |
| FR-003 instant, no reload | `changeLanguage` re-render, §3 |
| FR-004 persist localStorage | detection `caches: ['localStorage']`, key `jobflow.lang` |
| FR-005 default first visit | `fallbackLng: 'vi'` |
| FR-006 invalid → fallback | `supportedLngs` + `fallbackLng` |
| FR-007 no hardcoded strings | §2 rules |
| FR-008 split files | §4 one file per namespace per language |
| FR-009 missing key fallback | `returnNull:false` + key-as-default |
| FR-010 interpolation/plural | `t(key,{count,...})` |
| FR-011 add language = files only | §1 `SUPPORTED_LANGUAGES` + new locale files |
| FR-012 active language indicated | §3 highlight `resolvedLanguage` |
