import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Series { key: string; color: string; label: string }
interface StackedBarProps {
  data: Array<{ day: string; [k: string]: string | number }>;
  series: Series[];
  height?: number;
  ariaLabel: string;
}

const fmt = new Intl.NumberFormat();

function shortDay(iso: string) {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function StackedBar({ data, series, height = 240, ariaLabel }: StackedBarProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-default-400" role="img" aria-label={`${ariaLabel}: no data`}>
        No data
      </div>
    );
  }
  const display = data.map((d) => ({ ...d, label: shortDay(String(d.day)) }));
  return (
    <ResponsiveContainer width="100%" height={height} role="img" aria-label={ariaLabel}>
      <BarChart data={display} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
        <CartesianGrid stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ borderRadius: 8, fontSize: 12 }}
          formatter={(v: number, name: string) => [fmt.format(v), name]}
          labelFormatter={(_, payload) => {
            const iso = (payload as any)?.[0]?.payload?.day;
            return iso ? new Date(iso + "T00:00:00Z").toLocaleDateString() : "";
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
