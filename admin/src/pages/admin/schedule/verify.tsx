import { useTranslation } from "react-i18next";

import SchedulePage from "./_schedule-page";

export default function VerifySchedulePage() {
  const { t } = useTranslation("schedule");

  return (
    <SchedulePage
      command="verify_job_status"
      title={t("pages.verify.title")}
      description={t("pages.verify.description")}
    />
  );
}
