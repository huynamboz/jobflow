import type { Icon } from "@tabler/icons-react";

import {
  IconActivity,
  IconListCheck,
  IconBriefcase,
  IconCalendarTime,
  IconClipboardList,
  IconClock,
  IconFiles,
  IconLayoutDashboard,
  IconFileStack,
  IconRobot,
  IconTags,
  IconUserScan,
  IconUsers,
  IconTagStarred,
  IconMail
} from "@tabler/icons-react";

export type AdminNavItem = {
  /** i18n key in the `nav` namespace, e.g. "items.dashboard". */
  labelKey: string;
  href: string;
  icon: Icon;
};

export type AdminNavSection = {
  /** Stable identifier — used as the collapse-state key (language-agnostic). */
  id: string;
  /** i18n key in the `nav` namespace, e.g. "sections.staffing". */
  titleKey: string;
  items: AdminNavItem[];
};

export const adminConfig = {
  name: "JobFlow",
  navSections: [
    {
      // Everything HR touches in the daily staffing workflow.
      id: "Staffing",
      titleKey: "sections.staffing",
      items: [
        { labelKey: "items.dashboard",    href: "/admin",           icon: IconLayoutDashboard },
        { labelKey: "items.employees",    href: "/admin/employees", icon: IconUsers },
        { labelKey: "items.jobs",         href: "/admin/jobs",      icon: IconBriefcase },
        { labelKey: "items.jobTracking",  href: "/admin/job-tracking", icon: IconListCheck },
        { labelKey: "items.mail",         href: "/admin/mail",         icon: IconMail },
      ],
    },
    {
      // All technical / ML / data-ops tooling lives under one collapsible group.
      id: "System",
      titleKey: "sections.system",
      items: [
        { labelKey: "items.systemOverview", href: "/admin/system",        icon: IconActivity },
        { labelKey: "items.labeling",       href: "/admin/labeling",      icon: IconTags },
        { labelKey: "items.cvs",            href: "/admin/cvs",           icon: IconFiles },
        { labelKey: "items.llmProviders",   href: "/admin/llm-providers", icon: IconRobot },
        { labelKey: "items.llmLogs",        href: "/admin/llm-logs",      icon: IconClipboardList },
        { labelKey: "items.jdBatch",        href: "/admin/jd-batch",      icon: IconFileStack },
        { labelKey: "items.cvBatch",        href: "/admin/cv-batch",      icon: IconUserScan },
        { labelKey: "items.labelBatch",     href: "/admin/label-batch",   icon: IconTagStarred },
        { labelKey: "items.verifySchedule", href: "/admin/schedule/verify",  icon: IconClock },
        { labelKey: "items.extractSchedule", href: "/admin/schedule/extract", icon: IconCalendarTime },
      ],
    },
  ] as AdminNavSection[],
};
