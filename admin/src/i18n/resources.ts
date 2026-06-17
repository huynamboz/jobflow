// Eager-bundled translation resources. One import per namespace per language.
// Adding a namespace = add its JSON under locales/<lang>/ and register it here.
// Adding a language = create locales/<newlang>/<ns>.json for every namespace and
// add a block below (+ a row in SUPPORTED_LANGUAGES in ./index.ts).

import viCommon from "@/locales/vi/common.json";
import viNav from "@/locales/vi/nav.json";
import viDashboard from "@/locales/vi/dashboard.json";
import viEmployees from "@/locales/vi/employees.json";
import viJobs from "@/locales/vi/jobs.json";
import viMail from "@/locales/vi/mail.json";
import viSchedule from "@/locales/vi/schedule.json";
import viLabeling from "@/locales/vi/labeling.json";
import viCvs from "@/locales/vi/cvs.json";
import viLlm from "@/locales/vi/llm.json";
import viSettings from "@/locales/vi/settings.json";
import viIntegrations from "@/locales/vi/integrations.json";
import viAuth from "@/locales/vi/auth.json";

import enCommon from "@/locales/en/common.json";
import enNav from "@/locales/en/nav.json";
import enDashboard from "@/locales/en/dashboard.json";
import enEmployees from "@/locales/en/employees.json";
import enJobs from "@/locales/en/jobs.json";
import enMail from "@/locales/en/mail.json";
import enSchedule from "@/locales/en/schedule.json";
import enLabeling from "@/locales/en/labeling.json";
import enCvs from "@/locales/en/cvs.json";
import enLlm from "@/locales/en/llm.json";
import enSettings from "@/locales/en/settings.json";
import enIntegrations from "@/locales/en/integrations.json";
import enAuth from "@/locales/en/auth.json";

export const NAMESPACES = [
  "common",
  "nav",
  "dashboard",
  "employees",
  "jobs",
  "mail",
  "schedule",
  "labeling",
  "cvs",
  "llm",
  "settings",
  "integrations",
  "auth",
] as const;

export const defaultNS = "common" as const;

export const resources = {
  vi: {
    common: viCommon,
    nav: viNav,
    dashboard: viDashboard,
    employees: viEmployees,
    jobs: viJobs,
    mail: viMail,
    schedule: viSchedule,
    labeling: viLabeling,
    cvs: viCvs,
    llm: viLlm,
    settings: viSettings,
    integrations: viIntegrations,
    auth: viAuth,
  },
  en: {
    common: enCommon,
    nav: enNav,
    dashboard: enDashboard,
    employees: enEmployees,
    jobs: enJobs,
    mail: enMail,
    schedule: enSchedule,
    labeling: enLabeling,
    cvs: enCvs,
    llm: enLlm,
    settings: enSettings,
    integrations: enIntegrations,
    auth: enAuth,
  },
} as const;
