export interface Employee {
  id: number;
  full_name: string;
  email: string;
  phone?: string;
  position: string;
  seniority: number;
  experience_years: number | null;
  skills: string[];
  cv_file: string | null;
  is_parse_failed: boolean;
  parsed_at: string | null;
  match_count?: number;
  matches_count_by_status?: Record<string, number>;
  notes: string;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Employee[];
}

export interface BulkUploadResponse {
  success: boolean;
  data: Employee[];
}
