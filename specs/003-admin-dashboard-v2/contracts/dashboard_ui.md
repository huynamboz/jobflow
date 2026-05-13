# Contract: Dashboard Frontend Components

**Location**: `admin/src/components/dashboard/` and `admin/src/pages/admin/dashboard.tsx`.

---

## `SectionCard` (shared shell)

```tsx
interface SectionCardProps {
  title: string;
  description?: string;
  loading: boolean;
  error: Error | null;
  empty?: boolean;
  emptyMessage?: string;     // default: "No data yet"
  onRetry?: () => void;      // shown when error is truthy
  children: ReactNode;       // rendered only when !loading && !error && !empty
}
```

States rendered:
- **loading**: HeroUI Skeleton placeholder shaped like the chart, plus an aria-live="polite" status text.
- **error**: red icon + message + Retry button (calls `onRetry`).
- **empty**: gray icon + `emptyMessage`.
- **success**: passes `children` straight through.

Used by all six section components.

---

## Section components (each owns its own fetch)

All sections export a default React component that takes no props. They:
1. Hold `loading: boolean`, `error: Error | null`, and the typed payload in local state.
2. Fetch from `dashboardService` on mount.
3. Render inside a `<SectionCard>`.
4. Expose a stable `aria-label` matching the section title.

Component → endpoint mapping:

| Component | Endpoint | Payload type |
|-----------|----------|--------------|
| `KpiStrip` | `kpi/` | `KpiSnapshot` |
| `CatalogComposition` | `catalog/` | `CatalogComposition` |
| `FreshnessActivity` | `freshness/` | `FreshnessActivity` |
| `VerifierExtractorOps` | `ops/` | `OpsHealth` |
| `LabelingProgress` | `labeling/` | `LabelingSnapshot` |
| `ModelStatus` | `model/` | `ModelSnapshot` |

---

## Chart wrappers (in `components/dashboard/charts/`)

Tiny adapters over Recharts so section code doesn't import Recharts directly. Lets us swap libraries later without churn.

```tsx
// Donut.tsx
interface DonutProps {
  data: Array<{ key: string; count: number }>;
  height?: number;       // default 200
  ariaLabel: string;
  colorBy?: (key: string, idx: number) => string;
}

// BarH.tsx — horizontal bar chart (good for category labels)
interface BarHProps {
  data: Array<{ key: string; count: number; label?: string }>;
  height?: number;
  ariaLabel: string;
}

// AreaSeries.tsx — single-series area chart
interface AreaSeriesProps {
  data: Array<{ day: string; count: number }>;
  height?: number;
  ariaLabel: string;
  yLabel?: string;
}

// StackedBar.tsx — multi-series stacked bars, used for verifier outcomes
interface StackedBarProps {
  data: Array<{ day: string; [seriesKey: string]: string | number }>;
  series: Array<{ key: string; color: string; label: string }>;
  height?: number;
  ariaLabel: string;
}
```

**Tooltip behaviour**: every chart shows on hover: the X-axis label, every series value with its label, and absolute count. Numbers formatted via `Intl.NumberFormat`.

**Empty state**: each wrapper checks `data.length === 0` and renders a placeholder grid + "No data" centered. The section component does NOT need to gate this — chart handles it.

---

## `dashboard.tsx` (page composition)

```tsx
export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <DashboardHeader onRefresh={...} />
      <AuthStateBanner />                 {/* only renders if li_at missing */}
      <KpiStrip />
      <div className="grid gap-4 lg:grid-cols-2">
        <CatalogComposition />
        <FreshnessActivity />
      </div>
      <VerifierExtractorOps />
      <div className="grid gap-4 lg:grid-cols-2">
        <LabelingProgress />
        <ModelStatus />
      </div>
    </div>
  );
}
```

Refresh button at top-right re-fetches every section. Each section component MUST expose its fetcher via a ref or context so the page can trigger refresh.

---

## `dashboard.service.ts`

```ts
class DashboardService {
  async getKpi(): Promise<KpiSnapshot> { ... }
  async getCatalog(): Promise<CatalogComposition> { ... }
  async getFreshness(opts?: { daysAdded?: number; daysOutcomes?: number }): Promise<FreshnessActivity> { ... }
  async getOps(opts?: { recentRunsLimit?: number }): Promise<OpsHealth> { ... }
  async getLabeling(): Promise<LabelingSnapshot> { ... }
  async getModel(): Promise<ModelSnapshot> { ... }
}
```

All methods hit the corresponding endpoint, unwrap `data` from the envelope, and propagate errors. They DO NOT retry on their own — that's the section's responsibility.

---

## Accessibility checklist

- All charts have `aria-label`.
- Section retry buttons are keyboard-focusable.
- Tooltips are reachable via tab + arrow (Recharts supports this with `accessibilityLayer={true}`).
- Color choices clear 3:1 contrast against the section background.
- Time-ago strings have a tooltip with the full ISO-8601 UTC timestamp.

---

## Performance budget

- Recharts: ~50 kB gzipped after tree-shaking only the chart types used.
- Each section: <30 kB of code (most is HeroUI which is shared).
- Initial page bundle delta over the current dashboard: ≤100 kB gzipped (SC budget).
- Each chart render <16 ms (60 fps).
