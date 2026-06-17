import { Chip } from "@heroui/chip";
import { useTranslation } from "react-i18next";

import type { MatchStatus } from "@/types/match.types";

const TONE: Record<MatchStatus, "default" | "primary" | "secondary" | "success" | "warning" | "danger"> = {
  suggested: "default",
  pursuing: "primary",
  applied: "secondary",
  won: "success",
  lost: "danger",
};

export function MatchStatusChip({ status }: { status: MatchStatus }) {
  const { t } = useTranslation("employees");
  return (
    <Chip color={TONE[status]} size="sm" variant="flat">
      {t(`matchStatus.${status}`)}
    </Chip>
  );
}
