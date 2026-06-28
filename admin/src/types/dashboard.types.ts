// Frontend mirror of backend payloads.
// See specs/003-admin-dashboard-v2/data-model.md and contracts/dashboard_api.md.

export type Freshness = "fresh" | "stale" | "very_stale" | "never";

export interface LastRunSummary {
  started_at: string | null;     // ISO-8601 UTC, null = never
  command: "verify_job_status" | "extract_job_dates";
  freshness: Freshness;
}

export interface AuthState {
  file_exists: boolean;
  has_li_at: boolean;
}

export interface ModelMeta {
  checkpoint_name: string | null;
  trained_at: string | null;
  metrics: {
    test_auc_roc: number | null;
    ndcg_at_5: number | null;
    mrr: number | null;
    precision_at_5: number | null;
  };
  calibration: { a: number; b: number } | null;
}

export interface KpiSnapshot {
  jobs_total: number;
  jobs_by_lifecycle: {
    active: number;
    stale: number;
    expired: number;
    unverified: number;
  };
  cv_total: number;
  cv_uploads_last_7d: number;
  verifier_last_run: LastRunSummary;
  extractor_last_run: LastRunSummary;
  auth_state: AuthState;
  model: ModelMeta;
}

export interface CountBucket {
  key: string;
  count: number;
}

export interface SeniorityBucket {
  key: number;
  label: string;
  count: number;
}

export interface CatalogComposition {
  by_platform: CountBucket[];
  by_lifecycle: CountBucket[];
  by_role_category: CountBucket[];
  by_seniority: SeniorityBucket[];
}

export interface DailyCount {
  day: string;          // YYYY-MM-DD (UTC midnight)
  count: number;
}

export interface DailyVerifierOutcomes {
  day: string;
  active: number;
  expired: number;
  unknown: number;
  error: number;
  session_expired: number;
}

export interface FreshnessActivity {
  jobs_added_per_day: DailyCount[];
  verifier_outcomes_per_day: DailyVerifierOutcomes[];
}

export interface VerifierRunRow {
  id: number;
  command: "verify_job_status" | "extract_job_dates";
  started_at: string;
  finished_at: string;
  wall_clock_s: number;
  total_examined: number;
  counts_by_outcome: Record<string, number>;
  dry_run: boolean;
}

export interface OpsHealth {
  coverage: {
    linkedin_with_date_posted_pct: number;       // 0-1
    linkedin_verified_last_30d_pct: number;
  };
  recent_runs: VerifierRunRow[];
}

export interface LabelingByGroup {
  [group: string]: { labeled: number; total: number };
}

export interface LabelingSnapshot {
  total_pairs: number;
  labeled: number;
  skipped: number;
  pending: number;
  by_reason: LabelingByGroup;
  by_split: LabelingByGroup;
}

export type ModelSnapshot = ModelMeta;

export interface JobsOverview {
  stats: {
    total: number;
    active: number;
    inactive: number;
    new_today: number;
    applied: number;
    suitable_today: number;
  };
  per_day: { day: string; count: number }[];
  by_provider: { key: string; count: number }[];
  active_inactive: { key: string; count: number }[];
}
