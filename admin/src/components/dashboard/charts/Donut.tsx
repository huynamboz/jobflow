import { useTranslation } from "react-i18next";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

interface Datum { key: string; count: number }
interface DonutProps {
  data: Datum[];
  height?: number;
  ariaLabel: string;
  colors?: string[];
}

const DEFAULT_COLORS = [
  "#0ea5e9", "#22c55e", "#f97316", "#a855f7",
  "#ef4444", "#eab308", "#14b8a6", "#6366f1",
  "#ec4899", "#84cc16",
];

const fmt = new Intl.NumberFormat();

export default function Donut({ data, height = 220, ariaLabel, colors = DEFAULT_COLORS }: DonutProps) {
  const { t } = useTranslation("dashboard");
  if (!data.length) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-default-400" role="img" aria-label={t("chart.noDataAria", { label: ariaLabel })}>
        {t("chart.noData")}
      </div>
    );
  }
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <ResponsiveContainer width="100%" height={height} role="img" aria-label={ariaLabel}>
      <PieChart>
        <Pie data={data} dataKey="count" nameKey="key" innerRadius="55%" outerRadius="85%" paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={colors[i % colors.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ borderRadius: 8, fontSize: 12 }}
          formatter={(v: number, _name, p) => [
            `${fmt.format(v)} (${total ? ((v / total) * 100).toFixed(1) : 0}%)`,
            p?.payload?.key,
          ]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
