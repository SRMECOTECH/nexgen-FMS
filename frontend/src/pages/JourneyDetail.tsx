import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Route, Clock, MapPin, Gauge, Timer, RefreshCw, Navigation } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import LeafletMap from '../components/ui/LeafletMap';
import {
  fetchGpsJourneys, fetchGpsTrackRange,
  type Journey, type GpsTrackPoint,
} from '../lib/api';
import { metaFor, fmtDur, fmtTime, Coords } from './HaltsRests';

export default function JourneyDetail() {
  const { vehicle = '', trip = '' } = useParams();
  const nav = useNavigate();
  const [journey, setJourney] = useState<Journey | null>(null);
  const [track, setTrack] = useState<GpsTrackPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setErrorMsg(null);
    fetchGpsJourneys(vehicle)
      .then(async (r) => {
        const j = r.journeys.find(x => String(x.trip) === String(trip)) ?? null;
        if (cancelled) return;
        setJourney(j);
        if (j) {
          const t = await fetchGpsTrackRange(vehicle, 15, j.start, j.end).catch(() => null);
          if (!cancelled && t) setTrack(t.points);
        }
      })
      .catch(e => !cancelled && setErrorMsg('Could not load this journey (' + (e?.message ?? 'error') + ')'))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [vehicle, trip]);

  const back = () => nav(-1);

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Journey" subtitle="Loading route & halts…" />
      <div className="card flex items-center gap-2 text-xs" style={{ color: 'var(--fg-2)' }}>
        <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} /> Loading…
      </div>
    </div>
  );

  if (!journey) return (
    <div className="space-y-4">
      <button onClick={back} className="flex items-center gap-2 text-sm" style={{ color: 'var(--accent)' }}>
        <ArrowLeft className="w-4 h-4" /> Back
      </button>
      <div className="card text-sm" style={{ color: 'var(--fg-3)' }}>
        {errorMsg ?? `Journey #${trip} not found for ${vehicle}.`}
      </div>
    </div>
  );

  const stops = journey.halts.map(h => ({ lat: h.lat, lng: h.lng, minutes: h.minutes, near: h.where }));

  return (
    <div className="space-y-6">
      <button onClick={back} className="flex items-center gap-2 text-sm" style={{ color: 'var(--accent)' }}>
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <PageHeader
        title={`${journey.from_place} → ${journey.to_place}`}
        subtitle={`${vehicle} · Journey #${journey.trip} · ${fmtTime(journey.start)}`} />

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Kpi icon={Route} label="Distance" value={`${journey.distance_km} km`} />
        <Kpi icon={Clock} label="Duration" value={fmtDur(journey.duration_min)} />
        <Kpi icon={Gauge} label="Avg / max" value={`${journey.avg_speed} / ${journey.max_speed}`} sub="km/h" />
        <Kpi icon={Timer} label="Halts" value={String(journey.halt_count)} sub={`${fmtDur(journey.halt_minutes)} stopped`} />
        <Kpi icon={Navigation} label="Moving" value={`${journey.moving_pct}%`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Map */}
        <div className="card lg:col-span-2">
          <h3 className="font-semibold mb-2 flex items-center gap-2">
            <MapPin className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Route
          </h3>
          <p className="text-xs mb-3" style={{ color: 'var(--fg-3)' }}>
            {track.length.toLocaleString()} merged points (15-min windows) · red markers = halts
          </p>
          <LeafletMap points={track} stops={stops} height={460} />
        </div>

        {/* Halt timeline */}
        <div className="card">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <Timer className="w-4 h-4" style={{ color: 'var(--accent)' }} /> Halts on this journey
          </h3>
          <div className="space-y-2 max-h-[460px] overflow-y-auto">
            {journey.halts.length === 0 && (
              <div className="text-xs" style={{ color: 'var(--fg-3)' }}>No halts recorded within this journey.</div>
            )}
            {journey.halts.map((h, i) => {
              const { icon: Icon, color } = metaFor(h.reason);
              return (
                <motion.div key={i} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2, delay: i * 0.03 }}
                  className="p-2.5 rounded-lg" style={{ background: 'var(--bg-2)', borderLeft: `3px solid ${color}` }}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium" style={{ color }}>
                      <Icon className="w-3.5 h-3.5" />{h.reason}
                    </span>
                    <span className="text-sm font-semibold" style={{ color: 'var(--fg-1)' }}>{fmtDur(h.minutes)}</span>
                  </div>
                  <div className="mt-1.5 text-xs leading-snug" style={{ color: 'var(--fg-2)' }}>📍 {h.where}</div>
                  <div className="mt-0.5 text-[10px]"><Coords lat={h.lat} lng={h.lng} /></div>
                  {h.poi && (
                    <div className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]"
                      style={{ background: `${color}1f`, color }}>
                      OSM match · {h.poi.category}{h.poi.distance_m != null ? ` · ~${h.poi.distance_m} m` : ''}
                    </div>
                  )}
                  <div className="mt-1 text-[10px]" style={{ color: 'var(--fg-3)' }}>{fmtTime(h.arrive)}</div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon: Icon, label, value, sub }: { icon: any; label: string; value: string; sub?: string }) {
  return (
    <div className="card card-hover flex items-center gap-3">
      <div className="p-2.5 rounded-lg" style={{ background: 'var(--accent-soft)', boxShadow: '0 0 18px -6px var(--accent-glow)' }}>
        <Icon className="w-5 h-5" style={{ color: 'var(--accent)' }} />
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--fg-3)' }}>{label}</div>
        <div className="text-lg font-bold truncate" style={{ color: 'var(--fg-1)' }}>{value}</div>
        {sub && <div className="text-[10px] truncate" style={{ color: 'var(--fg-3)' }}>{sub}</div>}
      </div>
    </div>
  );
}
