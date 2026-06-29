import {
  BarChart as RBarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { AXIS, GRID, SERIES, ChartTooltip } from './theme';

export interface BarDatum { label: string; value: number; color?: string }

interface BarChartProps {
  data: BarDatum[];
  height?: number;
  unit?: string;
  horizontal?: boolean;       // true = ranked list (label on Y axis)
  color?: string;
  highlightMax?: boolean;     // emphasise the largest bar
}

/** Theme-consistent bar chart. Horizontal mode is ideal for top-N rankings. */
export default function BarChart({
  data, height = 220, unit, horizontal = false, color = 'var(--accent)', highlightMax = false,
}: BarChartProps) {
  const max = Math.max(...data.map((d) => d.value), 0);
  const fillFor = (d: BarDatum, i: number) =>
    d.color ?? (highlightMax ? (d.value === max ? 'var(--accent-hover)' : 'var(--accent)') : (color === 'series' ? SERIES[i % SERIES.length] : color));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RBarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'}
        margin={{ top: 4, right: 8, bottom: 0, left: horizontal ? 4 : -16 }}>
        <CartesianGrid {...GRID} horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...AXIS} />
            <YAxis type="category" dataKey="label" {...AXIS} width={108}
              tick={{ fill: 'var(--fg-3)', fontSize: 11 }} />
          </>
        ) : (
          <>
            <XAxis type="category" dataKey="label" {...AXIS} interval={0} />
            <YAxis type="number" {...AXIS} />
          </>
        )}
        <Tooltip cursor={{ fill: 'var(--accent-soft)' }} content={(p: any) => <ChartTooltip {...p} unit={unit} />} />
        <Bar dataKey="value" radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={horizontal ? 18 : 44}>
          {data.map((d, i) => <Cell key={i} fill={fillFor(d, i)} />)}
        </Bar>
      </RBarChart>
    </ResponsiveContainer>
  );
}
