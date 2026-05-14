import SchedulePage from "./_schedule-page";

export default function ExtractSchedulePage() {
  return (
    <SchedulePage
      command="extract_job_dates"
      title="Extract schedule"
      description="Daily date-backfill (also runs the bundled verify pass) · auto-fire + manual runs · live log + history."
    />
  );
}
