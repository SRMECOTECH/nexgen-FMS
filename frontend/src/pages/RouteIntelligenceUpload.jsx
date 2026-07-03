import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Route as RouteIcon, Clock, Gauge, Truck,
  Layers, ArrowRight, Loader2, MapPin, FileSpreadsheet,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import { riGetUploadTrip, riGetUpload } from '../lib/routeIntel';

export default function RouteIntelligenceUpload() {
  const { uploadId = '' } = useParams();
  const nav = useNavigate();
  const [upload, setUpload] = useState(null);
  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([riGetUpload(Number(uploadId)), riGetUploadTrip(Number(uploadId))])
      .then(([u, t]) => { setUpload(u); setTrip(t); })
      .catch(e => setError(e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  }, [uploadId]);

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Upload" subtitle="Loading…" />
      <div className="card text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
        Loading…
      </div>
    </div>
  );
  if (!trip) return (
    <div className="card text-sm" style={{ color: 'var(--danger)' }}>
      {error ?? 'No trip found for this upload.'}
    </div>
  );

  const segments = trip.segments || [];

  return (
    <div className="space-y-6">
      <button onClick={() => nav('/route-intel')} className="btn-soft text-xs">
        <ArrowLeft className="w-3.5 h-3.5" /> All uploads
      </button>

      <PageHeader
        title={upload?.display_name || upload?.original_name || upload?.filename || `Upload #${uploadId}`}
        subtitle={`${trip.vehicle_id} · ${trip.n_segments} segments · ${trip.distance_km} km · ${new Date(trip.start_ts).toLocaleString()} → ${new Date(trip.end_ts).toLocaleString()}`}
      />

      {/* Trip header card — opens the full dashboard */}
      <motion.button initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
        onClick={() => nav(`/route-intel/trips/${trip.id}`)}
        className="card card-hover w-full text-left ai-glow"
        style={{ borderColor: 'var(--accent)' }}>
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl shrink-0" style={{ background: 'var(--accent-soft)' }}>
            <RouteIcon className="w-6 h-6" style={{ color: 'var(--accent)' }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.15em] mb-1"
              style={{ color: 'var(--accent)' }}>
              <Truck className="w-3 h-3" />
              <span className="mono">{trip.vehicle_id}</span>
              <span style={{ color: 'var(--fg-3)' }}>·</span>
              <span>Trip overview</span>
            </div>
            <div className="text-lg font-bold" style={{ color: 'var(--fg-1)' }}>
              {trip.from_waypoint ?? '—'} → {trip.to_waypoint ?? '—'}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
              <Mini icon={RouteIcon} label="distance" value={`${trip.distance_km} km`} />
              <Mini icon={Clock}    label="duration" value={`${(trip.duration_min / 60).toFixed(1)} h`} />
              <Mini icon={Gauge}    label="avg speed" value={`${trip.avg_speed_kmph} km/h`} />
              <Mini icon={Clock}    label="moving"  value={`${Math.round(trip.moving_min / 60)} h`} />
              <Mini icon={Clock}    label="idle"    value={`${Math.round(trip.stopped_min / 60)} h`} />
            </div>
          </div>
          <div className="flex items-center gap-1 text-xs font-semibold shrink-0"
            style={{ color: 'var(--accent)' }}>
            Open full dashboard <ArrowRight className="w-4 h-4" />
          </div>
        </div>
      </motion.button>

      {/* Segments grid */}
      <div>
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Layers className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          Segments ({segments.length}) — driving blocks between long stops
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {segments.map((s, i) => (
            <motion.button key={s.id}
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              onClick={() => nav(`/route-intel/segments/${s.id}`)}
              className="card card-hover text-left">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <span className="chip chip-completed">#{s.seq}</span>
                </div>
                <div className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
                  {new Date(s.start_ts).toLocaleString()}
                </div>
              </div>
              <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)' }}>
                {s.from_waypoint ?? '—'} → {s.to_waypoint ?? '—'}
              </div>
              <div className="grid grid-cols-3 gap-2 mt-3">
                <Mini icon={RouteIcon} label="dist"  value={`${s.distance_km} km`} />
                <Mini icon={Clock}     label="dur"   value={`${(s.duration_min / 60).toFixed(1)} h`} />
                <Mini icon={Gauge}     label="avg"   value={`${s.avg_speed_kmph} kph`} />
              </div>
              <div className="mt-3 flex items-center justify-between">
                <div className="text-[10px]" style={{ color: 'var(--fg-3)' }}>
                  moving {Math.round(s.moving_min)}m · idle {Math.round(s.stopped_min)}m · {s.n_points.toLocaleString()} pts
                </div>
                {s.analyzed ? <span className="chip chip-running">analyzed</span> : null}
              </div>
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Mini({ icon: Icon, label, value }) {
  return (
    <div className="p-1.5 rounded-lg" style={{ background: 'var(--bg-2)' }}>
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-[0.12em]"
        style={{ color: 'var(--fg-3)' }}>
        {Icon && <Icon className="w-2.5 h-2.5" />} {label}
      </div>
      <div className="text-xs font-bold mono" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
