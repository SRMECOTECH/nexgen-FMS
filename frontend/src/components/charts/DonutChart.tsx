import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { SERIES, ChartTooltip } from './theme';

export interface DonutDatum { name: string; value: number; color?: string }

interface DonutChartProps {
  data: DonutDatum[];
  height?: number;
  unit?: string;
  centerLabel?: string;       // small caption under the big number
  centerValue?: string | number;
}

/** Donut with a centred total and a compact legend list beside it. */
export default function DonutChart({ data, height = 200, unit, centerLabel, centerValue }: DonutChartProps) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const big = centerValue ?? total.toLocaleString();

  return (
    <div className="flex items-center gap-4">
      <div className="relative shrink-0" style={{ width: height, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
              innerRadius="64%" outerRadius="92%" paddingAngle={2} stroke="none">
              {data.map((d, i) => <Cell key={i} fill={d.color ?? SERIES[i % SERIES.length]} />)}
            </Pie>
            <Tooltip content={(p: any) => <ChartTooltip {...p} unit={unit} />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="metric text-2xl font-bold" style={{ color: 'var(--fg-1)' }}>{big}</span>
          {centerLabel && <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--fg-3)' }}>{centerLabel}</span>}
        </div>
      </div>

      <ul className="flex-1 min-w-0 space-y-1.5">
        {data.map((d, i) => (
          <li key={d.name} className="flex items-center gap-2 text-xs">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: d.color ?? SERIES[i % SERIES.length] }} />
            <span className="truncate" style={{ color: 'var(--fg-2)' }}>{d.name}</span>
            <span className="ml-auto tabular font-semibold" style={{ color: 'var(--fg-1)' }}>{d.value.toLocaleString()}</span>
            <span className="tabular w-10 text-right" style={{ color: 'var(--fg-3)' }}>
              {total ? Math.round((d.value / total) * 100) : 0}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
