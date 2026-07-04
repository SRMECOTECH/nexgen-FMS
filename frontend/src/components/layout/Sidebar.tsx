import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity, Wand2, FileSpreadsheet, Microscope, ExternalLink,
  Compass, Eye, Brain, TrendingUp, Lightbulb, Zap, GraduationCap, Settings,
  ScrollText, Database,
} from 'lucide-react';
import { fetchHealth, type HealthStatus } from '../../lib/api';

interface NavItem {
  to: string;
  label: string;
  icon: typeof Activity;
  external?: boolean;
}

interface NavSection {
  title: string;
  /** Shown as a tooltip on the section header — not inline, to keep the rail clean. */
  hint?: string;
  items: NavItem[];
}

// ============================================================================
// AI Operating System IA — organised by *intelligence stage*, not DB tables.
// The shape (Observe → Understand → Predict → Recommend → Act → Learn) is the
// loop the platform thinks in. Section hints live in tooltips so the rail
// stays scannable; labels are short nouns, not sentences.
// ============================================================================
const sections: NavSection[] = [
  {
    title: 'Mission Control',
    hint: 'What deserves your attention right now',
    items: [
      { to: '/mission-control', label: 'Today',            icon: Compass },
      { to: '/live-thinking',   label: 'Live AI Thinking', icon: Zap },
    ],
  },
  {
    title: 'Observe',
    hint: 'Raw signal from the fleet',
    items: [
      { to: '/observe', label: 'Live Telemetry', icon: Eye },
    ],
  },
  {
    title: 'Understand',
    hint: 'AI-derived structure & insight',
    items: [
      { to: '/route-intel',           label: 'Route Intelligence',   icon: FileSpreadsheet },
      { to: '/route-intel/insights',  label: 'AI Insights Feed',     icon: Wand2 },
      { to: '/understand',            label: 'Fleet Overview',       icon: Brain },
      { to: 'http://127.0.0.1:8501',  label: 'Detailed GPS Analysis', icon: Microscope, external: true },
    ],
  },
  {
    title: 'Predict',
    hint: 'What will happen next',
    items: [
      { to: '/predict', label: 'ETA · SLA · Demand', icon: TrendingUp },
    ],
  },
  {
    title: 'Recommend',
    hint: 'What you should do about it',
    items: [
      { to: '/recommend', label: 'Recommendations', icon: Lightbulb },
    ],
  },
  {
    title: 'Act',
    hint: 'Approve, dispatch, alert',
    items: [
      { to: '/act', label: 'Actions & Approvals', icon: Zap },
    ],
  },
  {
    title: 'Learn',
    hint: 'Model registry & feedback loop',
    items: [
      { to: '/learn', label: 'Model Registry', icon: GraduationCap },
    ],
  },
  {
    title: 'System',
    hint: 'Configuration, database & logs',
    items: [
      { to: '/settings', label: 'Settings', icon: Settings },
      { to: '/logs',     label: 'Logs',     icon: ScrollText },
    ],
  },
];

/** "EXCEL→MYSQL" → "Excel → MySQL" — machine label to human label. */
function friendlySource(mode: string | undefined): string {
  if (!mode) return '';
  const pretty: Record<string, string> = {
    EXCEL: 'Excel', ICEBERG: 'Iceberg', MYSQL: 'MySQL',
    POSTGRES: 'Postgres', WAREHOUSE: 'Warehouse', MOCK: 'Mock data',
  };
  return mode
    .split('→')
    .map((p) => pretty[p.trim()] ?? p.trim())
    .join(' → ');
}

export default function Sidebar() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let on = true;
    const poll = () =>
      fetchHealth()
        .then((h) => { if (on) { setHealth(h); setFailed(false); } })
        .catch(() => { if (on) setFailed(true); });
    poll();
    const t = setInterval(poll, 30_000);
    return () => { on = false; clearInterval(t); };
  }, []);

  const live = !!health && health.status === 'ok' && !failed;
  const statusLabel = live ? 'All systems online' : failed ? 'API offline' : 'Checking status…';
  const statusColor = live ? 'var(--success)' : failed ? 'var(--danger)' : 'var(--warning)';

  return (
    <aside
      className="w-64 flex flex-col border-r overflow-y-auto"
      style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
    >
      {/* ===== Brand ===== */}
      <div
        className="px-5 py-5 flex items-center gap-3 border-b sticky top-0 z-10"
        style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
      >
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center animate-pulse-accent"
          style={{ background: 'var(--accent)' }}
        >
          <Activity className="w-5 h-5" color="#000" />
        </div>
        <div>
          <div className="text-sm font-bold tracking-wide" style={{ color: 'var(--fg-1)' }}>
            ne<span style={{ color: 'var(--accent)' }}>X</span>gen-FMS
          </div>
          <div className="text-[10px] uppercase tracking-[0.15em]" style={{ color: 'var(--accent)' }}>
            Fleet Intelligence OS
          </div>
        </div>
      </div>

      {/* ===== Navigation ===== */}
      <nav className="flex-1 px-3 py-4 space-y-6">
        {sections.map(({ title, hint, items }) => (
          <div key={title}>
            <div
              className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] cursor-default"
              style={{ color: 'var(--fg-3)' }}
              title={hint}
            >
              {title}
            </div>
            <div className="space-y-0.5">
              {items.map(({ to, label, icon: Icon, external }) => external ? (
                <a
                  key={to}
                  href={to}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-all hover:bg-[var(--bg-2)]"
                  style={{
                    color: 'var(--fg-2)',
                    borderLeft: '3px solid transparent',
                  }}
                  title="Opens the Streamlit deep-dive in a new tab"
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span className="flex-1">{label}</span>
                  <ExternalLink className="w-3 h-3 opacity-60" />
                </a>
              ) : (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/' || to === '/route-intel'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all ${
                      isActive ? 'font-semibold' : 'font-medium hover:bg-[var(--bg-2)]'
                    }`
                  }
                  style={({ isActive }) => ({
                    color: isActive ? 'var(--accent)' : 'var(--fg-2)',
                    background: isActive ? 'var(--accent-soft)' : 'transparent',
                    borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                  })}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* ===== Status footer ===== */}
      <div
        className="px-5 py-3.5 border-t sticky bottom-0 space-y-1.5"
        style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-[11px] font-medium" style={{ color: 'var(--fg-2)' }}>
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: statusColor, boxShadow: live ? `0 0 6px ${statusColor}` : 'none' }}
            />
            {statusLabel}
          </span>
          <span className="mono text-[10px]" style={{ color: 'var(--fg-4)' }}>
            v{health?.version ?? '0.2.0'}
          </span>
        </div>
        {live && health?.data_source && (
          <div
            className="flex items-center gap-1.5 text-[10px]"
            style={{ color: 'var(--fg-3)' }}
            title={health.warehouse_host ? `Warehouse: ${health.warehouse_host}` : undefined}
          >
            <Database className="w-3 h-3 shrink-0" />
            <span className="truncate">{friendlySource(health.data_source)}</span>
          </div>
        )}
      </div>
    </aside>
  );
}
