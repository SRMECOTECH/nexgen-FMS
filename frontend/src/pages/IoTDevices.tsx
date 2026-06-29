import { useEffect, useState } from 'react';
import { Cpu, Wifi, Battery, Satellite } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';
import Spinner from '../components/ui/Spinner';
import { fetchDevices, type IoTDeviceStatus } from '../lib/api';

export default function IoTDevices() {
  const [devices, setDevices] = useState<IoTDeviceStatus[]>([]);
  const [counts, setCounts] = useState({ online: 0, stale: 0, offline: 0 });
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetchDevices();
      setDevices(r.devices);
      setCounts({ online: (r as any).online, stale: (r as any).stale, offline: (r as any).offline });
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); const t = setInterval(load, 30_000); return () => clearInterval(t); }, []);
  if (loading && !devices.length) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader title="IoT Devices" subtitle="Per-vehicle GPS device health (ping age, signal, battery)."
        onRefresh={load} refreshing={loading} />

      <div className="grid grid-cols-3 gap-4">
        <SummaryCard label="Online"  value={counts.online}  tone="success" />
        <SummaryCard label="Stale"   value={counts.stale}   tone="warning" />
        <SummaryCard label="Offline" value={counts.offline} tone="danger" />
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider"
                style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-3">Vehicle</th>
              <th className="px-4 py-3">Device</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Last Ping</th>
              <th className="px-4 py-3"><Wifi className="inline w-3.5 h-3.5" /> Signal</th>
              <th className="px-4 py-3"><Satellite className="inline w-3.5 h-3.5" /> Sats</th>
              <th className="px-4 py-3"><Battery className="inline w-3.5 h-3.5" /> Voltage</th>
            </tr>
          </thead>
          <tbody style={{ color: 'var(--fg-2)' }}>
            {devices.map(d => (
              <tr key={d.device_id} style={{ borderBottom: '1px solid var(--border)' }}
                  className="hover:bg-[var(--bg-2)]">
                <td className="px-4 py-2 font-mono" style={{ color: 'var(--fg-1)' }}>{d.vehicle_id}</td>
                <td className="px-4 py-2 font-mono text-xs">{d.device_id}</td>
                <td className="px-4 py-2"><StatusPill status={d.status} /></td>
                <td className="px-4 py-2 text-xs">{Math.round(d.ping_age_sec)}s ago</td>
                <td className="px-4 py-2 font-mono text-xs">{d.signal_strength} dBm</td>
                <td className="px-4 py-2 font-mono text-xs">{d.satellites}</td>
                <td className="px-4 py-2 font-mono text-xs">{d.battery_voltage} V</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: 'success' | 'warning' | 'danger' }) {
  const color = tone === 'success' ? 'var(--success)' : tone === 'warning' ? 'var(--warning)' : 'var(--danger)';
  return (
    <div className="card flex items-center gap-3">
      <div className="p-3 rounded-lg" style={{ background: `${color}1f` }}>
        <Cpu className="w-5 h-5" style={{ color }} />
      </div>
      <div>
        <div className="text-xs uppercase tracking-wider" style={{ color: 'var(--fg-3)' }}>{label}</div>
        <div className="text-2xl font-bold" style={{ color: 'var(--fg-1)' }}>{value}</div>
      </div>
    </div>
  );
}
