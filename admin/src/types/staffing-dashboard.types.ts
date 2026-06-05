export interface DashboardKpi {
  utilization_pct: number;
  bench_count: number;
  in_progress: number;
  won_this_week: number;
  lost_this_week: number;
  new_jobs_24h: number;
  new_jobs_7d: number;
}

export interface TopNewMatch {
  id: number;
  full_name: string;
  new_count: number;
}

export interface BenchStale {
  id: number;
  full_name: string;
  days_on_bench: number;
}

export interface StaleApplied {
  match_id: number;
  employee_id: number;
  employee_name: string;
  job_title: string;
  days_since_applied: number | null;
}

export interface DashboardActionQueue {
  top_new_matches: TopNewMatch[];
  bench_stale: BenchStale[];
  stale_applied: StaleApplied[];
}

export type DashboardFunnel = Record<
  "suggested" | "pursuing" | "applied" | "won" | "lost",
  number
>;

export interface ParseFailedEmp {
  id: number;
  full_name: string;
}

export interface ScoredMatchAlert {
  match_id: number;
  employee_id: number;
  employee_name: string;
  job_title: string;
  score?: number;
  lifecycle?: string;
}

export interface DashboardAlerts {
  parse_failed: ParseFailedEmp[];
  high_score_unapplied: ScoredMatchAlert[];
  expiring_pursuing: ScoredMatchAlert[];
}

export interface RecentWonLost {
  match_id: number;
  employee_name: string;
  job_title: string;
  status: "won" | "lost";
  when: string;
}

export interface RecentJob {
  id: number;
  title: string;
  company: string;
  created_at: string;
}

export interface RecentEmployee {
  id: number;
  full_name: string;
  created_at: string;
}

export interface DashboardRecent {
  won_lost: RecentWonLost[];
  new_jobs: RecentJob[];
  new_employees: RecentEmployee[];
}

export interface StaffingDashboard {
  kpi: DashboardKpi;
  action_queue: DashboardActionQueue;
  funnel: DashboardFunnel;
  alerts: DashboardAlerts;
  recent: DashboardRecent;
}
