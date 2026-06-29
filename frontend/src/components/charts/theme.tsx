import type { ReactNode } from 'react';

/** Shared palette for categorical series — cyan-led, theme-consistent. */
export const SERIES = [
  '#22d3ee', // cyan (accent)
  '#38bdf8', // sky
  '#0ea5e9', // sea
  '#818cf8', // indigo
  '#34d399', // emerald
  '#fbbf24', // amber
  '#f472b6', // pink
  '#a78bfa', // violet
];

export const AXIS = {
  stroke: 'var(--fg-3)',
  fontSize: 11,
  tickLine: false as const,
  axisLine: false as const,
};

export const GRID = {
  stroke: 'var(--border)',
  strokeDasharray: '3 3',
  vertical: false as const,
};

/** Themed tooltip — replaces recharts' default white box. */
export function ChartTooltip({ active, payload, label, unit, labelMap }: {
  active?: boolean;
  payload?: any[];
  label?: string | number;
  unit?: string;
  labelMap?: (k: string) => string;
}): ReactNode {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      style={{
        background: 'var(--bg-2)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: '8px 10px',
        boxShadow: '0 12px 30px -12px rgba(0,0,0,0.8)',
        fontSize: 12,
      }}
    >
      {label !== undefined && label !== '' && (
        <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 4 }}>{label}</div>
      )}
      {payload.map((p, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--fg-1)' }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color ?? p.fill ?? 'var(--accent)' }} />
          <span style={{ color: 'var(--fg-3)' }}>{labelMap ? labelMap(p.name) : p.name}:</span>
          <span className="tabular" style={{ fontWeight: 600 }}>
            {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}{unit ?? ''}
          </span>
        </div>
      ))}
    </div>
  );
}
