export interface JobCompany {
  id: number;
  name: string;
  industry: string;
  size: string;
  location: string;
}

export interface JobPlatform {
  id: number;
  name: string;
  slug: string;
  logo_url?: string;
}

export interface JobSkill {
  skill_name: string;
  category: number;
  importance: number;
}

export interface AdminPlatform {
  id: number;
  name: string;
  slug: string;
  logo_url?: string;
  is_active: boolean;
  job_count: number;
}

export interface JobListItem {
  id: number;
  title: string;
  company_name: string;
  platform_name: string;
  platform_logo?: string;
  location: string;
  seniority: number;
  job_type: string;
  salary_min: number;
  salary_max: number;
  salary_currency: string;
  salary_period: string;
  salary_usd_annual_min: number;
  salary_usd_annual_max: number;
  applicant_count: string;
  is_active: boolean;
  date_posted: string | null;
  created_at: string;
}

export interface JobDetail {
  id: number;
  title: string;
  company: JobCompany | null;
  platform: JobPlatform | null;
  location: string;
  seniority: number;
  job_type: string;
  salary_min: number;
  salary_max: number;
  salary_currency: string;
  salary_period: string;
  salary_usd_annual_min: number;
  salary_usd_annual_max: number;
  is_active: boolean;
  date_posted: string | null;
  created_at: string;
  description: string;
  responsibilities: string;
  requirements: string;
  source_url: string;
  applicant_count: number | null;
  skills: JobSkill[];
}

export interface JobListResponse {
  success: boolean;
  data: JobListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface JDExtractSkill {
  name: string;
  importance: number;
}

export interface JDExtractResult {
  title: string;
  company: string;
  location: string;
  is_remote: boolean;
  role_category: string;
  seniority: number;
  job_type: string;
  salary_min: number;
  salary_max: number;
  salary_currency: string;
  salary_type: string;
  salary_usd_annual_min: number;
  salary_usd_annual_max: number;
  experience_min: number;
  experience_max: number | null;
  degree_requirement: number;
  skills: JDExtractSkill[];
}

export type BatchStatus = "pending" | "running" | "done" | "error" | "cancelled";
export type RecordStatus = "pending" | "processing" | "done" | "error";

export interface JDBatch {
  id: number;
  file_path: string;
  fields_config: string[];
  status: BatchStatus;
  total: number;
  done_count: number;
  error_count: number;
  workers: number;
  created_at: string;
}

export interface JDBatchRecord {
  id: number;
  index: number;
  status: RecordStatus;
  error_msg: string;
  title: string;
  company: string;
  result?: JDExtractResult | null;
  combined_text?: string;
}

export interface JDBatchDetail {
  batch: JDBatch;
  records: JDBatchRecord[];
  total_records: number;
  page: number;
  page_size: number;
}
