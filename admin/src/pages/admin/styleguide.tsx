import { useState } from "react";
import {
  IconPlus,
  IconDownload,
  IconBell,
  IconDots,
  IconBriefcase,
  IconCoin,
  IconClock,
  IconEye,
  IconCircleCheck,
  IconMail,
  IconPhone,
} from "@tabler/icons-react";

import {
  Avatar,
  AvatarStack,
  Badge,
  Breadcrumb,
  Button,
  Card,
  IconButton,
  PageHeader,
  SearchInput,
  SectionLabel,
  Segmented,
  StatGroup,
  Tabs,
  useReveal,
  type BadgeColor,
} from "@/components/ui";

/**
 * JobFlow design-system styleguide. Live gallery of every shared primitive,
 * mounted at /admin/styleguide. Use it as the visual reference while
 * migrating pages to the JobFlow look.
 */
function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card padding={24} className="jn-reveal">
      <SectionLabel className="mb-4">{title}</SectionLabel>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </Card>
  );
}

const BADGE_COLORS: BadgeColor[] = ["blue", "green", "amber", "red", "violet", "neutral", "ink"];

export default function StyleguidePage() {
  const ref = useReveal();
  const [tab, setTab] = useState("documents");
  const [seg, setSeg] = useState("all");

  return (
    <div ref={ref} className="flex flex-col gap-6">
      <Breadcrumb
        className="jn-reveal"
        items={[{ label: "Design system", href: "/admin" }, { label: "Styleguide" }]}
      />

      <PageHeader
        className="jn-reveal"
        title="JobFlow design system"
        pill={<Badge color="blue">v1</Badge>}
        subtitle="Shared primitives + tokens powering the admin re-skin."
        actions={
          <>
            <Button variant="secondary" leftIcon={<IconDownload size={15} />}>
              Export
            </Button>
            <Button variant="primary" leftIcon={<IconPlus size={15} />}>
              Add member
            </Button>
          </>
        }
      />

      <Block title="Buttons">
        <Button variant="primary" leftIcon={<IconPlus size={15} />}>
          Primary
        </Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
        <Button variant="primary" loading>
          Loading
        </Button>
        <Button variant="secondary" size="sm">
          Small
        </Button>
        <Button variant="primary" disabled>
          Disabled
        </Button>
      </Block>

      <Block title="Icon buttons">
        <IconButton variant="ghost" dot="#0064e5">
          <IconBell size={18} />
        </IconButton>
        <IconButton variant="outline">
          <IconDots size={18} />
        </IconButton>
        <IconButton variant="soft" size="lg" shape="square" className="text-jn-green">
          <IconMail size={20} />
        </IconButton>
        <IconButton variant="soft" size="lg" className="text-jn-green">
          <IconPhone size={20} />
        </IconButton>
        <IconButton variant="ghost" shape="circle">
          <IconDots size={18} />
        </IconButton>
      </Block>

      <Block title="Badges">
        {BADGE_COLORS.map((c) => (
          <Badge key={c} color={c} dot>
            {c}
          </Badge>
        ))}
        <Badge color="blue">12 members</Badge>
        <Badge color="ink" solid>
          +2
        </Badge>
        <Badge color="green" leftIcon={<IconCircleCheck size={12} />}>
          Accepted
        </Badge>
      </Block>

      <Block title="Tabs">
        <Tabs
          className="w-full"
          value={tab}
          onChange={setTab}
          items={[
            { key: "details", label: "Details" },
            { key: "position", label: "Position" },
            { key: "documents", label: "Documents" },
            { key: "tasks", label: "Tasks", count: 7 },
          ]}
        />
      </Block>

      <Block title="Segmented">
        <Segmented
          value={seg}
          onChange={setSeg}
          items={[
            { key: "all", label: "All Documents" },
            { key: "portal", label: "Portal Milestones" },
          ]}
        />
      </Block>

      <Block title="Search">
        <SearchInput className="max-w-[420px]" placeholder="Search or type a command" />
      </Block>

      <Block title="Avatars">
        <Avatar name="Ronald Richards" size={48} />
        <Avatar name="Esther Howard" size={48} />
        <AvatarStack
          people={[{ name: "A" }, { name: "B" }, { name: "C" }, { name: "D" }, { name: "E" }]}
          size={32}
        />
      </Block>

      <div className="jn-reveal">
        <SectionLabel className="mb-3">Stat group</SectionLabel>
        <StatGroup
          items={[
            { icon: <IconClock size={15} />, label: "Docs Owed", value: 5, color: "amber" },
            { icon: <IconEye size={15} />, label: "Docs Pending Reviews", value: 4, color: "blue" },
            { icon: <IconCircleCheck size={15} />, label: "Docs Accepted", value: 12, suffix: "/13", color: "green" },
          ]}
          footer="Go to deals →"
        />
      </div>

      <div className="jn-reveal">
        <SectionLabel className="mb-3">Cards</SectionLabel>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
          <Card hoverable padding={20}>
            <span className="grid h-10 w-10 place-items-center rounded-jn-btn bg-jn-primary-soft text-jn-primary">
              <IconBriefcase size={18} />
            </span>
            <div className="mt-3 text-[15px] font-semibold text-jn-ink">Hoverable card</div>
            <div className="mt-1 text-[13px] text-jn-ink-mute">Lifts on hover.</div>
          </Card>
          <Card padding={20} radius="lg">
            <span className="grid h-10 w-10 place-items-center rounded-jn-btn bg-jn-green-bg text-jn-green">
              <IconCoin size={18} />
            </span>
            <div className="mt-3 text-[15px] font-semibold text-jn-ink">Feature card</div>
            <div className="mt-1 text-[13px] text-jn-ink-mute">20px radius.</div>
          </Card>
          <Card padding={20}>
            <div className="text-[15px] font-semibold text-jn-ink">Plain card</div>
            <div className="mt-1 text-[13px] text-jn-ink-mute">Default surface.</div>
          </Card>
        </div>
      </div>
    </div>
  );
}
