import { Chip } from "@heroui/chip";

import type { MatchStatus } from "@/types/match.types";

const TONE: Record<MatchStatus, "default" | "primary" | "secondary" | "success" | "warning" | "danger"> = {
  suggested: "default",
  pursuing: "primary",
  applied: "secondary",
  won: "success",
  lost: "danger",
};

const LABEL: Record<MatchStatus, string> = {
  suggested: "Suggested",
  pursuing: "Pursuing",
  applied: "Applied",
  won: "Won",
  lost: "Lost",
};

export function MatchStatusChip({ status }: { status: MatchStatus }) {
  return (
    <Chip color={TONE[status]} size="sm" variant="flat">
      {LABEL[status]}
    </Chip>
  );
}
