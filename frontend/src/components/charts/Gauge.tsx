import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from 'recharts';

interface GaugeProps {
  value: number;              // 0..100
  height?: number;
  label?: string;
  color?: string;
  suffix?: string;            // default "%"
}

/** Single-metric radial gauge (on-time %, utilisation, …). */
export default function Gauge({ value, height = 180, label, color, suffix = '%' }: GaugeProps) {
  const v = Math.max(0, Math.min(100, value));
  const tone = color ?? (v >= 80 ? 'var(--success)' : v >= 50 ? 'var(--warning)' : 'var(--danger)');
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart innerRadius="72%" outerRadius="100%" data={[{ value: v }]}
          startAngle={220} endAngle={-40}>
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar background={{ fill: 'var(--bg-3)' }} dataKey="value"
            cornerRadius={20} fill={tone} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="metric text-3xl font-bold" style={{ color: 'var(--fg-1)' }}>
          {Math.round(v)}<span className="text-lg" style={{ color: 'var(--fg-3)' }}>{suffix}</span>
        </span>
        {label && <span className="text-[10px] uppercase tracking-wider mt-0.5" style={{ color: 'var(--fg-3)' }}>{label}</span>}
      </div>
    </div>
  );
}
