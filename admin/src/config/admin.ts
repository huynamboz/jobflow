import type { Icon } from "@tabler/icons-react";

import {
  IconActivity,
  IconBrain,
  IconBriefcase,
  IconCalendarTime,
  IconClipboardList,
  IconClock,
  IconFiles,
  IconGitBranch,
  IconLayoutDashboard,
  IconFileStack,
  IconRobot,
  IconScan,
  IconSparkles,
  IconTags,
  IconUserScan,
  IconUsers,
  IconTagStarred,
} from "@tabler/icons-react";

export type AdminNavItem = {
  label: string;
  href: string;
  icon: Icon;
};

export type AdminNavSection = {
  title: string;
  items: AdminNavItem[];
};

export const adminConfig = {
  name: "JobFlow",
  navSections: [
    {
      // Everything HR touches in the daily staffing workflow.
      title: "Staffing",
      items: [
        { label: "Dashboard", href: "/admin",           icon: IconLayoutDashboard },
        { label: "Employees", href: "/admin/employees", icon: IconUsers },
        { label: "Jobs",      href: "/admin/jobs",      icon: IconBriefcase },
        { label: "Pipeline",  href: "/admin/pipeline",  icon: IconGitBranch },
        { label: "Match a CV", href: "/admin/recommend", icon: IconSparkles },
      ],
    },
    {
      // All technical / ML / data-ops tooling lives under one collapsible group.
      title: "System",
      items: [
        { label: "System overview", href: "/admin/system",        icon: IconActivity },
        { label: "Models",          href: "/admin/models",        icon: IconBrain },
        { label: "Labeling",        href: "/admin/labeling",      icon: IconTags },
        { label: "CVs (dataset)",   href: "/admin/cvs",           icon: IconFiles },
        { label: "LLM Providers",   href: "/admin/llm-providers", icon: IconRobot },
        { label: "LLM Logs",        href: "/admin/llm-logs",      icon: IconClipboardList },
        { label: "JD Extract",      href: "/admin/jd-extract",    icon: IconScan },
        { label: "JD Batch",        href: "/admin/jd-batch",      icon: IconFileStack },
        { label: "CV Batch",        href: "/admin/cv-batch",      icon: IconUserScan },
        { label: "Label Batch",     href: "/admin/label-batch",   icon: IconTagStarred },
        { label: "Verify schedule", href: "/admin/schedule/verify",  icon: IconClock },
        { label: "Extract schedule", href: "/admin/schedule/extract", icon: IconCalendarTime },
      ],
    },
  ] as AdminNavSection[],
};
