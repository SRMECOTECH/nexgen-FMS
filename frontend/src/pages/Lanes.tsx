import { useEffect, useState } from 'react';
import { Route } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { fetchLanes } from '../lib/api';

interface Lane { origin: string; destination: string; trips: number; transporters: number }

export default function Lanes() {
  const [lanes, setLanes] = useState<Lane[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLanes().then(r => setLanes(r.lanes)).finally(() => setLoading(false));
  }, []);
  if (loading) return <Spinner />;

  const total = lanes.reduce((s, l) => s + l.trips, 0);

  return (
    <div className="space-y-4">
      <PageHeader title="Lane Volume" subtitle="Discovered origin → destination pairs by trip count." />
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider"
                style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-3 w-10">#</th>
              <th className="px-4 py-3">Origin</th>
              <th className="px-4 py-3">Destination</th>
              <th className="px-4 py-3">Trips</th>
              <th className="px-4 py-3">Share</th>
              <th className="px-4 py-3">Transporters</th>
            </tr>
          </thead>
          <tbody style={{ color: 'var(--fg-2)' }}>
            {lanes.map((l, i) => {
              const pct = total ? (l.trips / total) * 100 : 0;
              return (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }} className="hover:bg-[var(--bg-2)]">
                  <td className="px-4 py-3 text-xs">{i + 1}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Route className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
                      {l.origin}
                    </div>
                  </td>
                  <td className="px-4 py-3">{l.destination}</td>
                  <td className="px-4 py-3 font-semibold" style={{ color: 'var(--accent)' }}>{l.trips}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 rounded overflow-hidden" style={{ background: 'var(--bg-2)' }}>
                        <div className="h-full" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
                      </div>
                      <span className="text-xs">{pct.toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">{l.transporters}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
