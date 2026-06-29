/**
 * JobNest design-system primitives. Import from "@/components/ui":
 *
 *   import { Button, Badge, Card, PageHeader, Tabs } from "@/components/ui";
 *
 * Tokens live in src/styles/jobnest.css (jn-* Tailwind utilities).
 */
export { Button } from "./button";
export type { ButtonProps, ButtonVariant, ButtonSize } from "./button";

export { IconButton } from "./icon-button";
export type { IconButtonProps, IconButtonVariant, IconButtonSize } from "./icon-button";

export { Badge } from "./badge";
export type { BadgeProps, BadgeColor, BadgeSize } from "./badge";

export { Card } from "./card";
export type { CardProps } from "./card";

export { StatGroup } from "./stat-card";
export type { StatGroupProps, StatItem } from "./stat-card";

export { Tabs } from "./tabs";
export type { TabsProps, TabItem } from "./tabs";

export { Segmented } from "./segmented";
export type { SegmentedProps, SegmentedItem } from "./segmented";

export { SearchInput } from "./search-input";
export type { SearchInputProps } from "./search-input";

export { Avatar, AvatarStack } from "./avatar";
export type { AvatarProps, AvatarStackProps } from "./avatar";

export { Breadcrumb } from "./breadcrumb";
export type { BreadcrumbProps, Crumb } from "./breadcrumb";

export { SectionLabel } from "./section-label";

export { PageHeader } from "./page-header";
export type { PageHeaderProps } from "./page-header";

export { useReveal } from "./use-reveal";
