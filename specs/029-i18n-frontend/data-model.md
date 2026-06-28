# Phase 1 Data Model: Frontend i18n

This feature has no database entities. The "data" is the in-memory/runtime i18n
configuration and the on-disk translation resources. Entities below map the spec's
Key Entities to concrete client-side artifacts.

## Entity: Language

A supported interface language.

| Field | Type | Notes |
|-------|------|-------|
| code | string | BCP-47 short code: `vi`, `en` |
| label | string | Display name in the switcher (`Tiếng Việt`, `English`) |
| isDefault | boolean | Exactly one true → `vi` |

- Validation: only codes in `supportedLngs` are accepted; anything else → `fallbackLng`.
- Source of truth: a `SUPPORTED_LANGUAGES` array in `src/i18n/index.ts` (drives both
  i18next config and the switcher options → FR-011/SC-006: add a language = add a row + files).

## Entity: Translation namespace

A named group of entries scoped to a module/page area.

| Field | Type | Notes |
|-------|------|-------|
| name | string | `common`, `nav`, `dashboard`, `employees`, `jobs`, `mail`, `schedule`, `labeling`, `cvs`, `llm`, `settings`, `auth`, `integrations` |
| perLanguageFile | path | `src/locales/<code>/<name>.json` |
| defaultNS | — | `common` is the default namespace |

- Invariant: every namespace file MUST exist for every supported language (same
  filename set under `vi/` and `en/`).
- `nav` is consumed by `config/admin.ts` + sidebar/header; `common` holds shared chrome.

## Entity: Translation entry

A single key/value within a namespace file.

| Field | Type | Notes |
|-------|------|-------|
| key | string | Nested path, lowerCamelCase leaves, e.g. `list.emptyState`, `actions.save` |
| value | string | Display text for one language; may contain `{{placeholders}}` |
| pluralForms | optional | i18next `_one` / `_other` suffixed sibling keys when `{{count}}` is used |

- Validation: keys are stable & language-agnostic; the `vi` and `en` files for a
  namespace SHOULD have matching key sets (missing key → key/default fallback, FR-009).
- Interpolation values are inserted at render with `t(key, { name, count, ... })`.

## Entity: Language preference

The persisted user choice.

| Field | Type | Notes |
|-------|------|-------|
| storageKey | string | `localStorage` key `jobflow.lang` |
| value | string | `vi` or `en` |
| lifecycle | — | written on `changeLanguage`; read on app init by the detector |

- States: **unset** (first visit → default `vi`, FR-005) → **set** (persists, FR-004)
  → **invalid/unsupported** (corrupt value → fallback `vi`, FR-006).

## Relationships

```
Language (1) ──has──> (N) Translation namespace (per-language file)
Translation namespace (1) ──contains──> (N) Translation entry
Language preference ──selects──> active Language (drives which entry values render)
```

## Derived rule for "add a 3rd language" (SC-006)

1. Add a row to `SUPPORTED_LANGUAGES` (code + label).
2. Add `src/locales/<newcode>/<namespace>.json` for every existing namespace.
3. No screen/component code changes. Switcher renders the new option automatically.
