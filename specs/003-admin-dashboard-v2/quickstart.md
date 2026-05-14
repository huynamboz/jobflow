# Quickstart — adding a new dashboard section

The dashboard is designed for incremental growth. Each section is independent: one endpoint + one component + one chart wrapper if needed. This file is the recipe.

---

## Adding a backend endpoint

1. **Define the payload shape** in `data-model.md` first. Decide what aggregates the frontend needs, NOT what Django models exist.

2. **Add a service function** in `apps/admin_dashboard/services.py`:
   ```python
   def compute_my_section(*, now: datetime | None = None) -> dict:
       now = now or datetime.now(timezone.utc)
       # ORM queries + return a dict matching the payload shape
       return {...}
   ```
   Pure function — no DB writes, no HTTP. Easy to unit-test.

3. **Add a view** in `apps/admin_dashboard/views.py`:
   ```python
   class MySectionView(APIView):
       permission_classes = [IsAuthenticated]
       def get(self, request):
           data = services.compute_my_section()
           return Response({"success": True, "data": data})
   ```

4. **Wire the route** in `apps/admin_dashboard/urls.py`:
   ```python
   path("my-section/", MySectionView.as_view(), name="dashboard-my-section"),
   ```

5. **Write tests** in `tests_ml/test_dashboard_endpoints.py`:
   - Happy path with a representative DB fixture.
   - Empty-DB case.
   - One edge case (e.g., row with a NULL field that the query handles).

---

## Adding a frontend section

1. **Add the TS type** in `admin/src/types/dashboard.types.ts`:
   ```ts
   export interface MySectionPayload { /* mirror the backend shape */ }
   ```

2. **Add the fetcher** in `admin/src/services/dashboard.service.ts`:
   ```ts
   async getMySection(): Promise<MySectionPayload> {
     const res = await apiClient.get(`/admin-dashboard/my-section/`);
     return res.data.data;
   }
   ```

3. **Create the component** in `admin/src/components/dashboard/MySection.tsx`:
   ```tsx
   export default function MySection() {
     const [data, setData] = useState<MySectionPayload | null>(null);
     const [loading, setLoading] = useState(true);
     const [error, setError] = useState<Error | null>(null);

     const fetch = useCallback(() => {
       setLoading(true); setError(null);
       dashboardService.getMySection()
         .then((d) => setData(d))
         .catch((e) => setError(e))
         .finally(() => setLoading(false));
     }, []);

     useEffect(() => { fetch(); }, [fetch]);

     return (
       <SectionCard
         title="My section"
         loading={loading} error={error}
         empty={data != null && /* zero-state check */ }
         onRetry={fetch}
       >
         {data && <Donut data={data.buckets} ariaLabel="My section" />}
       </SectionCard>
     );
   }
   ```

4. **Compose into the page** in `dashboard.tsx`:
   ```tsx
   <MySection />
   ```

5. **Add a unit test** that:
   - Renders the loading state.
   - Renders the error state and verifies the retry button calls the fetcher.
   - Renders the success state with a mock payload.

---

## Adding a new chart type

Only do this if existing wrappers (`Donut`, `BarH`, `AreaSeries`, `StackedBar`) don't fit.

1. **Create the wrapper** in `admin/src/components/dashboard/charts/<MyChart>.tsx`. Export a typed interface for props. Always include `ariaLabel`.
2. **Empty state** is the wrapper's responsibility — render a "No data" placeholder when `data.length === 0`.
3. **Don't leak Recharts imports** to section components — every Recharts symbol goes through the wrapper.
4. **Test the wrapper** with a small representative dataset and an empty array.

---

## Operator how-to (post-ship)

Once the dashboard ships, an operator simply:

1. Opens `https://<admin host>/admin/dashboard`.
2. Glances at the KPI strip for the red/amber/green at-a-glance status.
3. Clicks Refresh after running a verifier batch to see numbers update.
4. Hovers over chart bars for exact values.

If any section shows an error: click Retry on that section's card. If the whole page is unresponsive, the backend is down — check the service status (`systemctl status jobflow-backend`) before debugging endpoints.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| KPI strip shows red "Auth state invalid" | `li_at` missing from `auth/linkedin_state.json` | Run `linkedin_auth.py` |
| One section perma-errors but others work | Endpoint-specific bug or DB index missing | Check `/var/log/jobflow/server.log` for the matching endpoint |
| "Last verifier run" stays "never" after running the command | `VerifierRunLog` INSERT failed in the command | Check DB connectivity from the command's environment |
| All sections show loading > 5s | DB connection pool exhausted or query missing an index | Check Postgres `pg_stat_activity` for the slow query |
| Chart tooltips not appearing on hover | Recharts `accessibilityLayer` disabled | Verify wrapper passes `accessibilityLayer={true}` |
