import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Building2, Warehouse, Truck, Search, RefreshCw, ChevronRight, MapPin, Boxes } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import {
  fetchTripParties, fetchTripsDb, type PartyDim, type PartyRow, type Trip,
} from '../lib/api';
import { TripModal, statusChip, fmtD } from './Trips';

const TABS: { dim: PartyDim; label: string; icon: any }[] = [
  { dim: 'consignor', label: 'Consignors', icon: Building2 },
  { dim: 'consignee', label: 'Consignees', icon: Warehouse },
  { dim: 'transporter', label: 'Transporters', icon: Truck },
];

export default function Partners() {
  const [dim, setDim] = useState<PartyDim>('consignor');
  const [parties, setParties] = useState<PartyRow[]>([]);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [tripsBusy, setTripsBusy] = useState(false);
  const [openTrip, setOpenTrip] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true); setSelected(null); setTrips([]);
    fetchTripParties(dim)
      .then(r => { setParties(r.parties); if (r.parties[0]) selectParty(r.parties[0].name); })
      .finally(() => setLoading(false));
  }, [dim]);

  function selectParty(name: string) {
    setSelected(name); setTripsBusy(true);
    fetchTripsDb({ [dim]: name, limit: 1000 } as any)
      .then(r => setTrips(r.trips)).finally(() => setTripsBusy(false));
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? parties.filter(p => (p.name ?? '').toLowerCase().includes(q)) : parties;
  }, [parties, search]);

  return (
    <div className="space-y-6">
      <PageHeader title="Partners" subtitle="Consignors, consignees and transporters — trip volume, fleet and lanes per party, from MySQL." />

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {TABS.map(t => {
          const active = dim === t.dim;
          return (
            <button key={t.dim} onClick={() => setDim(t.dim)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium lift"
              style={{
                background: active ? 'var(--accent-soft)' : 'var(--bg-2)',
                color: active ? 'var(--accent)' : 'var(--fg-2)',
                border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
              }}>
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-2)' }}>
          <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} /> Loading…
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Party list */}
          <div className="card lg:col-span-2">
            <div className="flex items-center gap-2 mb-3">
              <h3 className="font-semibold capitalize">{dim}s</h3>
              <span className="chip">{filtered.length}</span>
              <div className="ml-auto relative">
                <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--fg-3)' }} />
                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…"
                  className="pl-8 pr-3 py-1.5 rounded-md text-xs w-40 outline-none"
                  style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-1)' }} />
              </div>
            </div>
            <div className="space-y-1.5 max-h-[560px] overflow-y-auto">
              {filtered.map(p => {
                const active = selected === p.name;
                return (
                  <button key={p.name} onClick={() => selectParty(p.name)}
                    className="w-full text-left p-2.5 rounded-lg lift"
                    style={{ background: active ? 'var(--accent-soft)' : 'var(--bg-2)', border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}` }}>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium truncate flex-1" style={{ color: active ? 'var(--accent)' : 'var(--fg-1)' }}>{p.name}</span>
                      <span className="text-xs font-mono shrink-0" style={{ color: 'var(--accent)' }}>{p.trips}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[10px]" style={{ color: 'var(--fg-3)' }}>
                      <span><Truck className="inline w-3 h-3" /> {p.assets}</span>
                      <span><MapPin className="inline w-3 h-3" /> {p.lanes} lanes</span>
                      <span>{p.open_trips} open</span>
                    </div>
                  </button>
                );
              })}
              {filtered.length === 0 && <div className="text-xs py-4 text-center" style={{ color: 'var(--fg-3)' }}>No matches.</div>}
            </div>
          </div>

          {/* Selected party trips */}
          <div className="card lg:col-span-3">
            <div className="flex items-center gap-2 mb-3">
              <Boxes className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              <h3 className="font-semibold truncate">{selected ?? 'Select a party'}</h3>
              <span className="chip ml-auto">{trips.length} trips</span>
            </div>
            {tripsBusy ? (
              <div className="text-xs flex items-center gap-2 py-6 justify-center" style={{ color: 'var(--fg-3)' }}>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading trips…
              </div>
            ) : (
              <div className="overflow-x-auto" style={{ maxHeight: 520 }}>
                <table className="w-full text-xs">
                  <thead className="sticky top-0" style={{ background: 'var(--bg-1)' }}>
                    <tr style={{ color: 'var(--fg-3)' }}>
                      <th className="text-left py-2 pl-2">Trip #</th><th className="text-left">Asset</th>
                      <th className="text-left">Status</th><th className="text-left">Lane</th>
                      <th className="text-left">Start</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {trips.map(t => (
                      <tr key={t.trip_no} onClick={() => setOpenTrip(t.trip_no)} className="lift cursor-pointer" style={{ borderTop: '1px solid var(--border)' }}>
                        <td className="py-2 pl-2 font-mono font-semibold" style={{ color: 'var(--accent)' }}>{t.trip_no}</td>
                        <td className="font-mono" style={{ color: 'var(--fg-1)' }}>{t.asset_id}</td>
                        <td><span className={`chip ${statusChip(t.status)}`}>{t.status_label}</span></td>
                        <td style={{ color: 'var(--fg-2)' }}>{t.org_node} <span style={{ color: 'var(--fg-3)' }}>→</span> {t.dest_node}</td>
                        <td className="whitespace-nowrap" style={{ color: 'var(--fg-3)' }}>{fmtD(t.start_ts)}</td>
                        <td><ChevronRight className="w-4 h-4" style={{ color: 'var(--fg-3)' }} /></td>
                      </tr>
                    ))}
                    {trips.length === 0 && <tr><td colSpan={6} className="py-6 text-center" style={{ color: 'var(--fg-3)' }}>No trips.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      <AnimatePresence>
        {openTrip != null && <TripModal tripNo={openTrip} onClose={() => setOpenTrip(null)} />}
      </AnimatePresence>
    </div>
  );
}
