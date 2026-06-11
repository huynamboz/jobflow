export type MatchStatus =
  | "suggested"
  | "pursuing"
  | "applied"
  | "won"
  | "in_progress"
  | "completed"
  | "lost"
  | "dismissed";

export interface JobLite {
  id: number;
  title: string;
  company_name?: string;
  platform_name?: string;
  location?: string;
  seniority?: number;
  job_type?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  applicant_count?: string;
  is_active?: boolean;
  date_posted?: string | null;
  source_url?: string;
  created_at?: string;
}

export interface EmployeeJobMatch {
  id: number;
  employee: number;
  employee_name: string;
  job: JobLite;
  status: MatchStatus;
  match_score: number;
  matched_skills: string[];
  missing_skills: string[];
  /** 025: missing skills the employee likely covers via a related skill → {"html_css": "sass"} */
  covered_skills?: Record<string, string>;
  seniority_gap: number | null;
  dim_scores?: Record<string, number | string>; // skill_fit/experience_fit/seniority_fit/domain_fit → 0..1 (legacy: good|ok|weak)
  assigned_to: number | null;
  notes: string;
  applied_at: string | null;
  won_at: string | null;
  lost_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineKpi {
  total_employees: number;
  matches_this_week: Record<string, number>;
  top_employees_pursuing: { id: number; full_name: string; active_matches: number }[];
}
