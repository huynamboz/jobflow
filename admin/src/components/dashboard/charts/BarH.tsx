import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Datum { key: string; count: number; label?: string }
interface BarHProps {
  data: Datum[];
  height?: number;
  ariaLabel: string;
  color?: string;
}

const fmt = new Intl.NumberFormat();

export default function BarH({ data, height = 260, ariaLabel, color = "#0ea5e9" }: BarHProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-default-400" role="img" aria-label={`${ariaLabel}: no data`}>
        No data
      </div>
    );
  }
  const display = data.map((d) => ({ ...d, label: d.label ?? d.key }));
  return (
    <ResponsiveContainer width="100%" height={height} role="img" aria-label={ariaLabel}>
      <BarChart data={display} layout="vertical" margin={{ left: 0, right: 12, top: 4, bottom: 4 }}>
        <CartesianGrid stroke="#f1f5f9" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={120} />
        <Tooltip
          contentStyle={{ borderRadius: 8, fontSize: 12 }}
          formatter={(v: number, _n, p) => [fmt.format(v), p?.payload?.label]}
        />
        <Bar dataKey="count" fill={color} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
