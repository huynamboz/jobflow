# Quickstart: Frontend i18n

## 1. Install dependencies

```bash
cd admin
npm install i18next react-i18next i18next-browser-languagedetector
```

## 2. Wire the runtime (once)

- Create `src/i18n/resources.ts` — static-import every `locales/<lang>/<ns>.json`,
  export the `resources` object keyed `{ vi: { common: …, nav: … }, en: { … } }`.
- Create `src/i18n/index.ts` — `i18n.init(...)` per [contracts/i18n-contract.md](contracts/i18n-contract.md) §1; export the configured `i18n`.
- In `src/main.tsx`, add `import './i18n';` **before** the `ReactDOM.createRoot(...).render(<App/>)` call so i18n initializes before the first render.

## 3. Add the switcher to the header

- New `src/components/language-switcher.tsx` (contract §3).
- Mount it in `src/components/admin/admin-header.tsx` in the right-hand cluster
  (next to `NotificationBell`).

## 4. Seed foundation namespaces

- `locales/vi/common.json`, `locales/en/common.json` — shared chrome.
- `locales/vi/nav.json`, `locales/en/nav.json` — nav labels.
- Replace label strings in `src/config/admin.ts` with `nav:` keys (resolve via `t` at
  render in the sidebar, or keep keys in config and translate where rendered).

## 5. Migrate a screen (repeat per module)

1. `const { t } = useTranslation('<namespace>');`
2. Replace each user-facing literal with `t('<key>')`; add the key to BOTH
   `locales/vi/<ns>.json` and `locales/en/<ns>.json`.
3. For dynamic text use interpolation: `t('greeting', { name })` with value
   `"Xin chào {{name}}"` / `"Hello {{name}}"`.
4. For counts use plural keys: `count_one` / `count_other` + `t('count', { count })`.

## 6. Verify (gates)

```bash
cd admin
npx tsc --noEmit        # type gate — must pass
npm run build           # Vite build gate — must pass
npm run dev             # manual check (restart Vite after i18n wiring)
```

Manual switch check per migrated screen:
- Click the header switcher → choose the other language.
- Confirm: page updates in < 1s, no full reload, **0 strings remain in the previous
  language**, active language is highlighted.
- Reload the page → app comes back in the chosen language (localStorage `jobflow.lang`).
- In DevTools, set `localStorage['jobflow.lang'] = 'zz'` (invalid) → reload → app
  falls back to Vietnamese with no error.

## 7. Find residual hardcoded strings (sweep)

```bash
cd admin
# crude scan for Vietnamese diacritics still hardcoded in JSX/TS (review hits)
grep -rnE '[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]' src/pages src/components --include=*.tsx | grep -v 'locales/'
# scan for likely English UI literals in JSX text (review hits)
grep -rnE '>[A-Z][a-zA-Z ]{3,}<' src/pages src/components --include=*.tsx
```

Treat hits as a worklist; ignore matches inside `locales/`, code identifiers, and
API/data-bound values.
