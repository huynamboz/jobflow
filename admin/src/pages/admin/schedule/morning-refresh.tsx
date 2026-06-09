import SchedulePage from "./_schedule-page";

export default function MorningRefreshSchedulePage() {
  return (
    <SchedulePage
      command="morning_refresh"
      title="Morning refresh"
      description="Daily tick — re-match all employees against fresh jobs (no LLM, no duplicates), then send the HR digest. Toggle on, set the UTC hour, watch the live log + history."
      showCrawlOptions={false}
    />
  );
}
