import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import { resources, defaultNS, NAMESPACES } from "./resources";

export const LANG_STORAGE_KEY = "jobflow.lang";

export const SUPPORTED_LANGUAGES = [
  { code: "vi", label: "Tiếng Việt", isDefault: true },
  { code: "en", label: "English" },
] as const;

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]["code"];

export const SUPPORTED_LANG_CODES = SUPPORTED_LANGUAGES.map((l) => l.code);

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "vi",
    supportedLngs: SUPPORTED_LANG_CODES,
    nonExplicitSupportedLngs: true,
    defaultNS,
    ns: NAMESPACES as unknown as string[],
    // A missing key renders its key path (never blank / never throws). FR-009/SC-007.
    returnNull: false,
    interpolation: {
      // React already escapes values, so i18next must not double-escape.
      escapeValue: false,
    },
    detection: {
      // Deterministically Vietnamese-first: no 'navigator' guessing.
      order: ["localStorage"],
      caches: ["localStorage"],
      lookupLocalStorage: LANG_STORAGE_KEY,
    },
  });

export default i18n;
