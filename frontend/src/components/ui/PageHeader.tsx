import { RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
  actions?: ReactNode;
}

export default function PageHeader({ title, subtitle, onRefresh, refreshing, actions }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--fg-1)' }}>{title}</h1>
        {subtitle && (
          <p className="text-sm mt-1" style={{ color: 'var(--fg-3)' }}>{subtitle}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {actions}
        {onRefresh && (
          <button onClick={onRefresh} className="btn-ghost flex items-center gap-2">
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        )}
      </div>
    </div>
  );
}
