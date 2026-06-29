import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { IconRefresh } from "@tabler/icons-react";

import { Button, Card, PageHeader, Segmented, useReveal } from "@/components/ui";
import MatchOverviewBento from "@/components/dashboard/MatchOverviewBento";
import MatchOverviewDetail from "@/components/dashboard/MatchOverviewDetail";
import MailRepliesBlock from "@/components/dashboard/MailRepliesBlock";
import { dashboardService } from "@/services/dashboard.service";
import { staffingDashboardService } from "@/services/staffing-dashboard.service";
import type { JobsOverview } from "@/types/dashboard.types";
import type { StaffingDashboard as TStaffing } from "@/types/staffing-dashboard.types";

type RangeKey = "today" | "week" | "month";
const RANGE_DAYS: Record<RangeKey, number> = { today: 3, week: 7, month: 30 };

export default function DashboardPage() {
  const { t } = useTranslation("dashboard");
  const [jobs, setJobs] = useState<JobsOverview | null>(null);
  const [staffing, setStaffing] = useState<TStaffing | null>(null);
  // Re-scan reveals once the async bento/detail content has mounted.
  const reveal = useReveal([jobs, staffing]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [range, setRange] = useState<RangeKey>("month");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Full (re)load: both datasets together. Range changes refetch jobs only.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    Promise.all([
      dashboardService.getJobsOverview(RANGE_DAYS[range]),
      staffingDashboardService.get(),
    ])
      .then(([j, s]) => {
        if (!alive) return;
        setJobs(j);
        setStaffing(s);
      })
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const onRange = useCallback((key: RangeKey) => {
    setRange(key);
    dashboardService.getJobsOverview(RANGE_DAYS[key]).then(setJobs).catch(() => {});
  }, []);

  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <div ref={reveal} className="flex flex-col gap-5">
      <PageHeader
        className="jn-reveal"
        title={t("matchOverview.title")}
        subtitle={
          <span className="flex items-center gap-2">
            <span className="h-[7px] w-[7px] rounded-full bg-jn-green" style={{ animation: "jb-pulse 1.6s ease-in-out infinite" }} />
            {t("matchOverview.liveStatus")}
          </span>
        }
        actions={
          <>
            <Segmented
              value={range}
              onChange={onRange}
              items={[
                { key: "today", label: t("jobsOverview.rangeDays", { count: RANGE_DAYS.today }) },
                { key: "week", label: t("jobsOverview.rangeDays", { count: RANGE_DAYS.week }) },
                { key: "month", label: t("jobsOverview.rangeDays", { count: RANGE_DAYS.month }) },
              ]}
            />
            <Button variant="secondary" leftIcon={<IconRefresh size={15} />} onClick={refresh}>
              {t("common:actions.refresh")}
            </Button>
          </>
        }
      />

      {loading && !jobs && (
        <Card className="grid place-items-center py-20 text-[13px] text-jn-muted">
          {t("jobsOverview.loading")}
        </Card>
      )}

      {error && !jobs && (
        <Card className="py-6 text-center text-[13px] text-jn-red">{t("staffing.loadError")}</Card>
      )}

      {jobs && staffing && <MatchOverviewBento jobs={jobs} staffing={staffing} />}

      <MailRepliesBlock refreshKey={refreshKey} />

      {staffing && <MatchOverviewDetail staffing={staffing} />}
    </div>
  );
}
