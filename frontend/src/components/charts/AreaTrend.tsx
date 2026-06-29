import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { AXIS, GRID, ChartTooltip } from './theme';

interface AreaTrendProps {
  data: any[];
  xKey: string;
  yKey: string;
  height?: number;
  unit?: string;
  color?: string;
}

/** Smooth gradient-filled area for a single time series / trend. */
export default function AreaTrend({ data, xKey, yKey, height = 200, unit, color = 'var(--accent)' }: AreaTrendProps) {
  const gid = `grad-${yKey}`;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} />
        <Tooltip content={(p: any) => <ChartTooltip {...p} unit={unit} />} />
        <Area type="monotone" dataKey={yKey} stroke={color} strokeWidth={2}
          fill={`url(#${gid})`} dot={false} activeDot={{ r: 4, fill: color }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
