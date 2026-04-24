export interface JobMatchResult {
  job_id: number;
  score: number;
  eligible: boolean;
  matched_skills: string[];
  missing_skills: string[];
  seniority_match: boolean;
  title: string;
  company_name: string;
  location: string;
  job_type: string;
  salary_min: number;
  salary_max: number;
  salary_currency: string;
  role_category: string;
  experience_min: number | null;
  experience_max: number | null;
  source_url: string;
  match_level: "strong" | "good" | "weak" | "";
  dim_scores: {
    skill_fit?: "good" | "ok" | "weak";
    experience_fit?: "good" | "ok" | "weak";
    seniority_fit?: "good" | "ok" | "weak";
    domain_fit?: "good" | "ok" | "weak";
  };
}

export interface CVInfo {
  skills: string[];
  seniority: string;
  experience_years: number;
  education: string;
}

export interface CVMatchData {
  cv_info: CVInfo;
  jobs: JobMatchResult[];
}

export interface MatchResponse {
  success: boolean;
  data: CVMatchData;
}
