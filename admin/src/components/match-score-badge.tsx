import { Chip } from "@heroui/chip";
import { useTranslation } from "react-i18next";

interface Props {
  score: number; // 0..1
  size?: "sm" | "md";
}

export function MatchScoreBadge({ score, size = "sm" }: Props) {
  const { t } = useTranslation("employees");
  const pct = Math.round(score * 100);
  const color =
    pct >= 80 ? "success" : pct >= 60 ? "warning" : "default";
  return (
    <Chip color={color} size={size} variant="flat">
      {t("matchScore.percent", { pct })}
    </Chip>
  );
}
