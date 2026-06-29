import type { LucideIcon } from 'lucide-react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { motion } from 'framer-motion';

interface KpiCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: string;                       // small caption under the value
  tone?: 'default' | 'success' | 'warning' | 'danger';
  delta?: number;                       // optional +/- change, rendered as a chip
  index?: number;                       // stagger animation order
}

const toneColor: Record<NonNullable<KpiCardProps['tone']>, string> = {
  default: 'var(--accent)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
};

export default function KpiCard({ label, value, icon: Icon, trend, tone = 'default', delta, index = 0 }: KpiCardProps) {
  const color = toneColor[tone];
  const deltaUp = (delta ?? 0) >= 0;

  return (
    <motion.div
      className="card card-hover relative overflow-hidden"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.04 }}
    >
      {/* tonal accent wash in the corner */}
      <div className="absolute -top-8 -right-8 w-24 h-24 rounded-full blur-2xl pointer-events-none"
        style={{ background: color, opacity: 0.14 }} />

      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] uppercase tracking-wider font-medium" style={{ color: 'var(--fg-3)' }}>
          {label}
        </div>
        <span className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: `${color}1f`, boxShadow: `0 0 20px -8px ${color}` }}>
          <Icon style={{ color, width: 18, height: 18 }} />
        </span>
      </div>

      <div className="metric text-3xl font-bold mt-2 leading-none" style={{ color: 'var(--fg-1)' }}>
        {value}
      </div>

      <div className="flex items-center gap-2 mt-2 min-h-[18px]">
        {delta !== undefined && (
          <span className="inline-flex items-center gap-0.5 text-[11px] font-semibold px-1.5 py-0.5 rounded-md"
            style={{ background: deltaUp ? 'rgba(34,197,94,0.14)' : 'rgba(239,68,68,0.14)', color: deltaUp ? 'var(--success)' : 'var(--danger)' }}>
            {deltaUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {deltaUp ? '+' : ''}{delta}%
          </span>
        )}
        {trend && <div className="text-[11px] font-medium truncate" style={{ color }}>{trend}</div>}
      </div>
    </motion.div>
  );
}
