import type { Icon } from "@tabler/icons-react";

import {
  IconBrain,
  IconBriefcase,
  IconCalendarTime,
  IconClipboardList,
  IconClock,
  IconFiles,
  IconLayoutDashboard,
  IconFileStack,
  IconRobot,
  IconScan,
  IconSparkles,
  IconTags,
  IconUserScan,
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
      title: "General",
      items: [
        { label: "Dashboard", href: "/admin",          icon: IconLayoutDashboard },
        { label: "Models",    href: "/admin/models",   icon: IconBrain },
        { label: "Labeling",  href: "/admin/labeling", icon: IconTags },
        { label: "Recommend", href: "/admin/recommend", icon: IconSparkles },
      ],
    },
    {
      title: "Data",
      items: [
        { label: "Jobs", href: "/admin/jobs", icon: IconBriefcase },
        { label: "CVs",  href: "/admin/cvs",  icon: IconFiles },
      ],
    },
    {
      title: "AI",
      items: [
        { label: "LLM Providers", href: "/admin/llm-providers", icon: IconRobot },
        { label: "LLM Logs",      href: "/admin/llm-logs",      icon: IconClipboardList },
      ],
    },
    {
      title: "Extraction",
      items: [
        { label: "JD Extract",   href: "/admin/jd-extract",   icon: IconScan },
        { label: "JD Batch",     href: "/admin/jd-batch",     icon: IconFileStack },
        { label: "CV Batch",     href: "/admin/cv-batch",     icon: IconUserScan },
        { label: "Label Batch",  href: "/admin/label-batch",  icon: IconTagStarred },
      ],
    },
    {
      title: "Schedule",
      items: [
        { label: "Verify schedule",  href: "/admin/schedule/verify",  icon: IconClock },
        { label: "Extract schedule", href: "/admin/schedule/extract", icon: IconCalendarTime },
      ],
    },
  ] as AdminNavSection[],
};
