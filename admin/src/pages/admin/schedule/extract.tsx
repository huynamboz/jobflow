import { useTranslation } from "react-i18next";

import SchedulePage from "./_schedule-page";

export default function ExtractSchedulePage() {
  const { t } = useTranslation("schedule");

  return (
    <SchedulePage
      command="extract_job_dates"
      title={t("pages.extract.title")}
      description={t("pages.extract.description")}
    />
  );
}
