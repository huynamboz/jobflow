import SchedulePage from "./_schedule-page";

export default function VerifySchedulePage() {
  return (
    <SchedulePage
      command="verify_job_status"
      title="Verify schedule"
      description="Daily lifecycle re-checking · auto-fire daemon + manual runs · live log + history."
    />
  );
}
