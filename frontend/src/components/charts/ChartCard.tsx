import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { motion } from 'framer-motion';

interface ChartCardProps {
  title: string;
  subtitle?: string;
  icon?: LucideIcon;
  right?: ReactNode;          // optional toolbar slot (legend, toggle…)
  children: ReactNode;
  className?: string;
  delay?: number;
}

/** Consistent framed container for a chart: title row + body. */
export default function ChartCard({ title, subtitle, icon: Icon, right, children, className = '', delay = 0 }: ChartCardProps) {
  return (
    <motion.section
      className={`card ${className}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && (
            <span className="p-1.5 rounded-lg shrink-0"
              style={{ background: 'var(--accent-soft)', boxShadow: '0 0 16px -6px var(--accent-glow)' }}>
              <Icon className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            </span>
          )}
          <div className="min-w-0">
            <h3 className="font-semibold text-sm truncate" style={{ color: 'var(--fg-1)' }}>{title}</h3>
            {subtitle && <p className="text-[11px] truncate" style={{ color: 'var(--fg-3)' }}>{subtitle}</p>}
          </div>
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </div>
      {children}
    </motion.section>
  );
}
