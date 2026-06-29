import { useEffect, useState } from 'react';
import { MapPin } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { api } from '../lib/api';

interface Geofence {
  id: string; name: string; kind: string; lat: number; lng: number; radius_m: number;
  active_vehicles: number; entries_today: number; exits_today: number;
}

const kindColor: Record<string, string> = {
  depot: 'var(--accent)', customer: 'var(--info)', fuel: 'var(--warning)', restricted: 'var(--danger)',
};

export default function Geofences() {
  const [items, setItems] = useState<Geofence[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/operations/geofences').then(r => setItems(r.data.geofences)).finally(() => setLoading(false));
  }, []);
  if (loading) return <Spinner />;

  return (
    <div className="space-y-4">
      <PageHeader title="Geofences" subtitle="Authorized zones — depots, customers, fuel stops, restricted areas." />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map(g => (
          <div key={g.id} className="card card-hover">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg" style={{ background: `${kindColor[g.kind]}1f` }}>
                  <MapPin className="w-4 h-4" style={{ color: kindColor[g.kind] }} />
                </div>
                <div>
                  <div className="font-semibold text-sm">{g.name}</div>
                  <div className="text-xs uppercase tracking-wider" style={{ color: kindColor[g.kind] }}>{g.kind}</div>
                </div>
              </div>
              <span className="chip">{g.radius_m} m</span>
            </div>
            <div className="text-xs font-mono mb-3" style={{ color: 'var(--fg-3)' }}>
              {g.lat.toFixed(4)}, {g.lng.toFixed(4)}
            </div>
            <div className="grid grid-cols-3 gap-2 text-center pt-3 border-t"
                 style={{ borderColor: 'var(--border)' }}>
              <Stat label="Active" value={g.active_vehicles} />
              <Stat label="In ↑" value={g.entries_today} />
              <Stat label="Out ↓" value={g.exits_today} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs" style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="font-semibold">{value}</div>
    </div>
  );
}
