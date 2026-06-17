import { useTranslation } from "react-i18next";

import SchedulePage from "./_schedule-page";

export default function MorningRefreshSchedulePage() {
  const { t } = useTranslation("schedule");

  return (
    <SchedulePage
      command="morning_refresh"
      title={t("pages.morningRefresh.title")}
      description={t("pages.morningRefresh.description")}
      showCrawlOptions={false}
    />
  );
}
