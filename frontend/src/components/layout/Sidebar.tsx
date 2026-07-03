import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity, Wand2, FileSpreadsheet, Microscope, ExternalLink,
  Compass, Eye, Brain, TrendingUp, Lightbulb, Zap, GraduationCap, Settings,
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
  /** One-line subtitle shown under the section header. */
  hint?: string;
  items: NavItem[];
}

// ============================================================================
// AI Operating System IA — organised by *intelligence stage*, not DB tables.
// The shape (Observe → Understand → Predict → Recommend → Act → Learn) is the
// loop the platform thinks in. Each section names a verb, not an object.
// Route Intelligence keeps its current pages and lives under "Understand".
// ============================================================================
const sections: NavSection[] = [
  {
    title: 'Mission Control',
    hint: 'What deserves your attention right now',
    items: [
      { to: '/mission-control', label: 'Today',             icon: Compass },
      { to: '/live-thinking',   label: 'Live AI Thinking',  icon: Zap },
    ],
  },
  {
    title: 'Observe',
    hint: 'Raw signal from the fleet',
    items: [
      { to: '/observe', label: 'Real-time telemetry', icon: Eye },
    ],
  },
  {
    title: 'Understand',
    hint: 'AI-derived structure & insight',
    items: [
      // Route Intelligence stays alive — the AI-OS shell wraps it instead of
      // replacing it. Sub-routes (uploads / trips / segments / compare) are
      // reachable from the page itself.
      { to: '/route-intel',           label: 'Route Intelligence',              icon: FileSpreadsheet },
      { to: '/route-intel/insights',  label: 'Route Insights Feed',             icon: Wand2 },
      { to: '/understand',            label: 'Understand (overview)',           icon: Brain },
      { to: 'http://127.0.0.1:8501',  label: 'Detailed GPS Analysis',           icon: Microscope, external: true },
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
    hint: "What you should do about it",
    items: [
      { to: '/recommend', label: 'Driver · Route · Hub', icon: Lightbulb },
    ],
  },
  {
    title: 'Act',
    hint: 'Approve, dispatch, alert',
    items: [
      { to: '/act', label: 'Actions & approvals', icon: Zap },
    ],
  },
  {
    title: 'Learn',
    hint: 'Model registry & feedback loop',
    items: [
      { to: '/learn', label: 'Model registry', icon: GraduationCap },
    ],
  },
  {
    title: 'System',
    hint: 'Configuration & database',
    items: [
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

export default function Sidebar() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  useEffect(() => {
    let on = true;
    fetchHealth().then((h) => on && setHealth(h)).catch(() => {});
    const t = setInterval(() => fetchHealth().then((h) => on && setHealth(h)).catch(() => {}), 30_000);
    return () => { on = false; clearInterval(t); };
  }, []);

  const live = !!health && health.status === 'ok';
  const source = health?.data_source ?? '—';
  const host = (health?.lakehouse_url ?? '').replace(/^https?:\/\//, '') || 'connecting…';

  return (
    <aside
      className="w-64 flex flex-col border-r overflow-y-auto"
      style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
    >
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

      <nav className="flex-1 px-3 py-4 space-y-5">
        {sections.map(({ title, hint, items }) => (
          <div key={title}>
            <div
              className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-[0.18em]"
              style={{ color: 'var(--fg-3)' }}
            >
              {title}
            </div>
            {hint && (
              <div className="px-3 mb-2 text-[10px]" style={{ color: 'var(--fg-3)', opacity: 0.7 }}>
                {hint}
              </div>
            )}
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
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span className="flex-1">{label}</span>
                  <ExternalLink className="w-3 h-3 opacity-60" />
                </a>
              ) : (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
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

      <div
        className="px-5 py-4 border-t text-xs sticky bottom-0"
        style={{ background: 'var(--bg-1)', borderColor: 'var(--border)', color: 'var(--fg-3)' }}
      >
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: live ? 'var(--success)' : 'var(--danger)' }} />
          <span className="mono text-[10px]">v0.2.0 · {source}</span>
        </div>
        <div className="mt-1 text-[10px] mono truncate" title={host}>{host}</div>
      </div>
    </aside>
  );
}
