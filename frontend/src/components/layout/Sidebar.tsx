import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Truck, Users, MapPin, Sparkles, Activity, Map as MapIcon,
  Bell, Workflow, Database, Table2, Cable, Cpu, FileSearch, ScrollText, LifeBuoy,
  Settings, GitBranch, Power, ShieldCheck, Brain, Route, Satellite, BedDouble, Building2,
  Wand2, FileSpreadsheet, Microscope, ExternalLink,
} from 'lucide-react';
import { fetchHealth, type HealthStatus } from '../../lib/api';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  external?: boolean;   // opens in a new tab via window.open
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const sections: NavSection[] = [
  {
    title: 'Overview',
    items: [
      { to: '/',           label: 'Dashboard',  icon: LayoutDashboard },
      { to: '/map',        label: 'Live Map',   icon: MapIcon },
      { to: '/monitoring', label: 'Monitoring', icon: Activity },
    ],
  },
  {
    title: 'Operations',
    items: [
      { to: '/trips',     label: 'Trips',      icon: MapPin },
      { to: '/partners',  label: 'Partners',   icon: Building2 },
      { to: '/vehicles',  label: 'Vehicles',   icon: Truck },
      { to: '/drivers',   label: 'Drivers',    icon: Users },
      { to: '/alerts',    label: 'Alerts',     icon: Bell },
      { to: '/geofences', label: 'Geofences',  icon: MapIcon },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { to: '/ml',           label: 'ML Insights',     icon: Sparkles },
      { to: '/gps',          label: 'GPS Feed',        icon: Satellite },
      { to: '/halts',        label: 'Halts & Rests',   icon: BedDouble },
      { to: '/analytics/behaviour', label: 'Behavioural Patterns', icon: Brain },
      { to: '/analytics/lanes',     label: 'Lane Volume', icon: Route },
      { to: '/ml/pipelines', label: 'Pipelines',       icon: Workflow },
      { to: '/ml/models',    label: 'Model Registry',  icon: GitBranch },
    ],
  },
  {
    title: 'Route Intelligence',
    items: [
      { to: '/route-intel',           label: 'Upload & Trips',                  icon: FileSpreadsheet },
      { to: '/route-intel/insights',  label: 'AI Insights Feed',                icon: Wand2 },
      { to: 'http://127.0.0.1:8501',  label: 'Detailed Analysis of GPS Data',   icon: Microscope, external: true },
    ],
  },
  {
    title: 'Data',
    items: [
      { to: '/data/catalog',  label: 'Data Catalog',  icon: Database },
      { to: '/data/browser',  label: 'Data Browser',  icon: Table2 },
      { to: '/data/schema',   label: 'Schema',        icon: FileSearch },
      { to: '/data/quality',  label: 'Data Quality',  icon: ShieldCheck },
      { to: '/data/connectors', label: 'Connectors',  icon: Cable },
      { to: '/data/devices',  label: 'IoT Devices',   icon: Cpu },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/system/diagnostics', label: 'Diagnostics', icon: LifeBuoy },
      { to: '/system/logs',        label: 'Logs',        icon: ScrollText },
      { to: '/system/recovery',    label: 'Recovery',    icon: Power },
      { to: '/system/config',      label: 'Configuration', icon: Settings },
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
          className="w-9 h-9 rounded-lg flex items-center justify-center animate-pulse-amber"
          style={{ background: 'var(--accent)' }}
        >
          <Activity className="w-5 h-5" color="#000" />
        </div>
        <div>
          <div className="text-sm font-bold tracking-wide" style={{ color: 'var(--fg-1)' }}>
            ne<span style={{ color: 'var(--accent)' }}>X</span>gen-FMS
          </div>
          <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--accent)' }}>
            Fleet Intelligence
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-5">
        {sections.map(({ title, items }) => (
          <div key={title}>
            <div
              className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: 'var(--fg-3)' }}
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
          <span>v0.1.0 · {source}</span>
        </div>
        <div className="mt-1 truncate" title={host}>warehouse @ {host}</div>
      </div>
    </aside>
  );
}
