export type MatchStatus = "suggested" | "pursuing" | "applied" | "won" | "lost";

export interface JobLite {
  id: number;
  title: string;
  company_name?: string;
  platform_name?: string;
  location?: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  applicant_count?: string;
  is_active?: boolean;
  date_posted?: string | null;
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
  assigned_to: number | null;
  notes: string;
  applied_at: string | null;
  won_at: string | null;
  lost_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PipelineKpi {
  employees: Record<string, number>;
  matches_this_week: Record<string, number>;
  top_employees_pursuing: { id: number; full_name: string; active_matches: number }[];
}
