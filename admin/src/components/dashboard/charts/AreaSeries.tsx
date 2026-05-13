import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Datum { day: string; count: number }
interface AreaSeriesProps {
  data: Datum[];
  height?: number;
  ariaLabel: string;
  color?: string;
}

const fmt = new Intl.NumberFormat();

function shortDay(iso: string) {
  // YYYY-MM-DD → MMM dd in local time
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function AreaSeries({ data, height = 220, ariaLabel, color = "#0ea5e9" }: AreaSeriesProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-default-400" role="img" aria-label={`${ariaLabel}: no data`}>
        No data
      </div>
    );
  }
  const display = data.map((d) => ({ ...d, label: shortDay(d.day) }));
  return (
    <ResponsiveContainer width="100%" height={height} role="img" aria-label={ariaLabel}>
      <AreaChart data={display} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
        <defs>
          <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ borderRadius: 8, fontSize: 12 }}
          formatter={(v: number) => [fmt.format(v), "jobs"]}
          labelFormatter={(_, payload) => {
            const iso = (payload as any)?.[0]?.payload?.day;
            return iso ? new Date(iso + "T00:00:00Z").toLocaleDateString() : "";
          }}
        />
        <Area type="monotone" dataKey="count" stroke={color} fill="url(#area-fill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
