# Feature Specification: Frontend Internationalization (i18n)

**Feature Branch**: `029-i18n-frontend`

**Created**: 2026-06-17

**Status**: Draft

**Input**: User description: "i18n cho frontend admin SPA: trích xuất toàn bộ text hardcode trong FE thành hệ thống i18n (đa ngôn ngữ Việt + Anh). File translation chia nhỏ theo namespace/module (không gộp 1 file lớn). Có nút chuyển ngôn ngữ trên header. Lưu ngôn ngữ đã chọn vào localStorage và khôi phục khi reload."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Switch the interface language (Priority: P1)

An HR user opens the admin app and wants to read the interface in their preferred
language. They click a language switcher in the header, pick a language (Vietnamese
or English), and the entire visible interface immediately re-renders in that language —
navigation, page titles, labels, buttons, table headers, empty states, and toasts.

**Why this priority**: This is the core value of the feature. Without a working,
visible language switch the rest of the work has no user-facing payoff. It is the
minimum demonstrable slice.

**Independent Test**: Open any page, click the header switcher, choose the other
language, and confirm all visible text on that page changes language with no page
reload and no broken/missing labels.

**Acceptance Scenarios**:

1. **Given** the app is showing Vietnamese, **When** the user selects English from the header switcher, **Then** all visible interface text on the current page changes to English without a full page reload.
2. **Given** the app is showing English, **When** the user selects Vietnamese, **Then** all visible interface text changes to Vietnamese.
3. **Given** the switcher is open, **When** the user views it, **Then** the currently active language is clearly indicated.

---

### User Story 2 - Remember the chosen language across sessions (Priority: P1)

After a user picks a language, that choice persists. When they reload the page, open
a new tab, or return the next day on the same browser, the app still displays in the
language they chose — they never have to re-select it.

**Why this priority**: A switcher that forgets the choice on every reload is effectively
broken for daily use. Persistence is part of the minimum viable feature.

**Independent Test**: Select a non-default language, reload the browser, and confirm the
app comes back in the selected language.

**Acceptance Scenarios**:

1. **Given** the user has selected English, **When** they reload the page, **Then** the app loads directly in English.
2. **Given** the user has never made a choice, **When** they first open the app, **Then** the app displays in the default language.
3. **Given** a stored language value is missing or invalid, **When** the app loads, **Then** it falls back to the default language without errors.

---

### User Story 3 - All interface text is translatable (no hardcoded strings) (Priority: P2)

Every piece of user-facing text in the admin app is sourced from translation resources
rather than being hardcoded, so that switching the language leaves no stray untranslated
strings, and adding a future language requires only new translation files (no code
changes to screens).

**Why this priority**: This is the breadth/completeness work that makes the switch
trustworthy. It depends on US1/US2 existing, but delivers the "everything is covered"
guarantee. Done incrementally per screen.

**Independent Test**: For a given screen, switch languages and verify there are zero
remaining strings in the previous language; spot-check that the screen's text comes
from translation resources.

**Acceptance Scenarios**:

1. **Given** a translated screen, **When** the language is switched, **Then** no user-facing text remains in the previous language.
2. **Given** a string has a dynamic value (count, name, date), **When** rendered in either language, **Then** the value is inserted grammatically in the correct place for that language.
3. **Given** a translation key has no entry for the active language, **When** the screen renders, **Then** a readable fallback (default-language text or the key) is shown instead of a blank or crash.

---

### Edge Cases

- A translation key exists in one language file but is missing from the other → a defined fallback is shown, never a blank or error.
- Dynamic/interpolated values (counts, employee names, dates, scores) must render in the right position per language and pluralize acceptably.
- Text coming from the backend/API (e.g. error messages, job data, LLM output) is data, not interface chrome — it is explicitly out of scope for translation here.
- The language switcher must remain reachable on every authenticated screen, including narrow/mobile widths.
- Stored language preference is corrupted or set to an unsupported code → fall back to default.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support at least two interface languages — Vietnamese (`vi`) and English (`en`).
- **FR-002**: System MUST provide a language switcher control in the application header, available on every authenticated screen.
- **FR-003**: Selecting a language MUST update all visible interface text immediately, without a full page reload.
- **FR-004**: System MUST persist the selected language to browser local storage and restore it on subsequent loads (reload, new tab, return visit on the same browser).
- **FR-005**: On first visit with no stored preference, System MUST display a defined default language.
- **FR-006**: When a stored preference is missing, invalid, or unsupported, System MUST fall back to the default language without errors.
- **FR-007**: All user-facing interface text MUST be sourced from translation resources rather than hardcoded in screens.
- **FR-008**: Translation resources MUST be organized into multiple smaller files grouped by module/namespace (e.g. per feature area or page group), not a single monolithic file.
- **FR-009**: When a translation entry is missing for the active language, System MUST show a defined fallback (default-language value or the key) instead of a blank or a crash.
- **FR-010**: System MUST support inserting dynamic values (counts, names, dates) into translated text with correct placement per language.
- **FR-011**: Adding a future language MUST require only adding translation files, with no changes to individual screen logic.
- **FR-012**: The switcher MUST clearly indicate the currently active language.

### Key Entities *(include if feature involves data)*

- **Language**: A supported interface language, identified by a short code (`vi`, `en`), with a human-readable display name for the switcher. One language is designated the default/fallback.
- **Translation namespace**: A named group of translation entries scoped to a module or page area (e.g. navigation, employees, jobs, common). Each namespace exists per supported language.
- **Translation entry**: A key/value pair within a namespace; the key is stable and language-agnostic, the value is the displayed text for one language, possibly containing placeholders for dynamic values.
- **Language preference**: The user's selected language persisted in browser local storage; read on app load to determine the active language.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can switch the interface between Vietnamese and English from the header in 1 action, and the visible page updates in under 1 second with no reload.
- **SC-002**: The selected language survives a page reload and a new tab 100% of the time on the same browser.
- **SC-003**: On every translated screen, 0 user-facing strings remain in the previous language after switching.
- **SC-004**: 100% of user-facing interface text in covered screens resolves through translation resources (no hardcoded display strings).
- **SC-005**: No single translation file contains the entire app's strings — translations are split across at least one namespace per major module/page group.
- **SC-006**: Adding a hypothetical third language requires only new translation files and a switcher entry, with zero edits to screen components (verified by inspection of the design).
- **SC-007**: A missing translation key never produces a blank UI region or a runtime error — a fallback is always shown.

## Assumptions

- Scope is the `admin/` React SPA only; backend/API responses and stored data (job text, LLM output, employee data) are not translated by this feature.
- Two languages ship in this feature: Vietnamese and English. Vietnamese is the default given the current primarily-Vietnamese UI, unless decided otherwise during planning.
- Translation completeness is delivered incrementally by screen/module (US3); US1 + US2 (working, persisted switch) are the MVP and can ship before every screen is fully extracted.
- Language preference is per-browser (local storage), not per-user-account synced to the server.
- Right-to-left layouts are out of scope (both shipped languages are left-to-right).
- Date/number locale formatting follows each language's common convention where translation tooling supports it, but deep locale formatting is a nice-to-have, not a gating requirement.
