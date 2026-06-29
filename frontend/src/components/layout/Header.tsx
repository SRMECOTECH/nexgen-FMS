import { useEffect, useState } from 'react';
import { Bell, Search, RefreshCw } from 'lucide-react';
import { fetchHealth, type HealthStatus } from '../../lib/api';

export default function Header() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setRefreshing(true);
    try { setHealth(await fetchHealth()); }
    finally { setRefreshing(false); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, []);

  const isOk = health?.status === 'ok';
  const sourceLabel = health?.data_source ?? '...';
  const healthColor = isOk ? 'var(--success)' : 'var(--danger)';

  return (
    <header
      className="h-16 border-b flex items-center justify-between px-6 shrink-0"
      style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center gap-3 flex-1 max-w-md">
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg w-full"
          style={{ background: 'var(--bg-2)', border: '1px solid var(--border)' }}
        >
          <Search className="w-4 h-4" style={{ color: 'var(--fg-3)' }} />
          <input
            placeholder="Search trips, vehicles, drivers, alerts..."
            className="bg-transparent outline-none text-sm w-full"
            style={{ color: 'var(--fg-1)' }}
          />
          <kbd
            className="hidden md:inline-block text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: 'var(--bg-1)', color: 'var(--fg-3)', border: '1px solid var(--border)' }}
          >
            ⌘K
          </kbd>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={load}
          className="p-2 rounded-lg hover:bg-[var(--bg-2)]"
          title="Refresh health"
        >
          <RefreshCw
            className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`}
            style={{ color: 'var(--fg-2)' }}
          />
        </button>

        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold uppercase tracking-wider"
          style={{
            background: isOk ? 'rgba(34, 197, 94, 0.12)' : 'rgba(239, 68, 68, 0.12)',
            borderColor: healthColor,
            color: healthColor,
          }}
        >
          <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: healthColor }} />
          {isOk ? 'System Healthy' : 'Degraded'}
          <span className="opacity-60">·</span>
          <span>{sourceLabel}</span>
        </div>

        <button className="relative p-2 rounded-lg hover:bg-[var(--bg-2)]">
          <Bell className="w-5 h-5" style={{ color: 'var(--fg-2)' }} />
          <span
            className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full"
            style={{ background: 'var(--accent)' }}
          />
        </button>

        <div className="flex items-center gap-2 pl-3 border-l" style={{ borderColor: 'var(--border)' }}>
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
            style={{ background: 'var(--accent)', color: '#000' }}
          >
            SC
          </div>
          <div className="text-sm">
            <div style={{ color: 'var(--fg-1)' }} className="font-medium">Sanjoy</div>
            <div style={{ color: 'var(--fg-3)' }} className="text-xs">Admin</div>
          </div>
        </div>
      </div>
    </header>
  );
}
