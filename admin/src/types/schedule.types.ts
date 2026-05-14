export type ScheduleCommand = "verify_job_status" | "extract_job_dates";

export interface ScheduleActiveRun {
  pid: number | null;
  started_at: string | null;
  log_path: string | null;
  is_alive: boolean;
}

export interface ScheduleConfig {
  command: ScheduleCommand;
  enabled: boolean;
  batch_size: number;
  batches_per_day: number;
  hours_utc: number[];
  use_no_auth_check: boolean;
  platform: string;
  active_run: ScheduleActiveRun;
  last_fired_at: string | null;
  updated_at: string;
}

export interface ScheduleLiveLog {
  since: number;
  offset: number;
  text: string;
  is_alive: boolean;
  log_path: string | null;
}

export interface ScheduleRunRow {
  id: number;
  command: ScheduleCommand;
  started_at: string;
  finished_at: string;
  wall_clock_s: number;
  total_examined: number;
  counts_by_outcome: Record<string, number>;
  dry_run: boolean;
}

export interface ScheduleLogFileEntry {
  name: string;
  size_bytes: number;
  mtime: string;
}

export interface ScheduleHistory {
  runs: ScheduleRunRow[];
  logs: ScheduleLogFileEntry[];
}
