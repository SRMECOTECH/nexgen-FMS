import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft, Route as RouteIcon, Clock, Gauge, Truck, MapPin,
  CheckCircle2, Loader2, FileSpreadsheet, Layers, GitCompare,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import { riGetUpload, riCompare, type RITrip, type RIUpload } from '../lib/api';

export default function RouteIntelligenceUpload() {
  const { uploadId = '' } = useParams();
  const nav = useNavigate();
  const [upload, setUpload] = useState<(RIUpload & { trips: RITrip[] }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    riGetUpload(Number(uploadId))
      .then((u) => setUpload(u))
      .catch((e) => setError(e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  }, [uploadId]);

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else if (next.size < 6) next.add(id);
    setSelected(next);
  };

  const startCompare = async () => {
    if (selected.size < 2) return;
    setComparing(true);
    try {
      const cmp = await riCompare([...selected]);
      nav(`/route-intel/compare/${cmp.id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'compare failed');
    } finally {
      setComparing(false);
    }
  };

  if (loading) return (
    <div className="space-y-4">
      <PageHeader title="Upload" subtitle="Loading trips…" />
      <div className="card text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
      </div>
    </div>
  );

  if (!upload) return (
    <div className="card text-sm" style={{ color: 'var(--danger)' }}>
      {error ?? 'Upload not found.'}
    </div>
  );

  return (
    <div className="space-y-6">
      <button onClick={() => nav('/route-intel')} className="flex items-center gap-2 text-sm"
        style={{ color: 'var(--accent)' }}>
        <ArrowLeft className="w-4 h-4" /> All uploads
      </button>

      <PageHeader
        title={upload.original_name || upload.filename}
        subtitle={`${upload.vehicle_id} · ${upload.n_rows.toLocaleString()} rows · ${Math.round(upload.total_distance_km)} km · ${new Date(upload.first_ts).toLocaleDateString()} → ${new Date(upload.last_ts).toLocaleDateString()}`}
      />

      {/* compare toolbar */}
      {selected.size > 0 && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
          className="card flex items-center justify-between gap-3"
          style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
          <div className="flex items-center gap-2 text-sm">
            <GitCompare className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <span style={{ color: 'var(--fg-1)' }}>
              {selected.size} trip{selected.size > 1 ? 's' : ''} selected
            </span>
            <span style={{ color: 'var(--fg-3)' }}>(2-6 to compare)</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setSelected(new Set())}
              className="text-xs" style={{ color: 'var(--fg-3)' }}>Clear</button>
            <button
              disabled={selected.size < 2 || comparing}
              onClick={startCompare}
              className="px-3 py-1.5 rounded text-xs font-semibold"
              style={{ background: 'var(--accent)', color: '#000',
                       opacity: selected.size < 2 || comparing ? 0.6 : 1 }}>
              {comparing ? 'Comparing…' : 'Compare →'}
            </button>
          </div>
        </motion.div>
      )}

      {/* trip cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {upload.trips.map((t, i) => {
          const sel = selected.has(t.id);
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              className="card card-hover relative"
              style={{
                outline: sel ? `2px solid var(--accent)` : 'none',
                outlineOffset: 1,
              }}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wider"
                    style={{ color: 'var(--fg-3)' }}>Trip #{t.seq}</div>
                  <div className="text-sm font-semibold truncate"
                    style={{ color: 'var(--fg-1)' }}>
                    {t.from_waypoint ?? '—'} → {t.to_waypoint ?? '—'}
                  </div>
                </div>
                <label className="inline-flex items-center gap-1.5 text-[10px] cursor-pointer">
                  <input type="checkbox" checked={sel} onChange={() => toggle(t.id)}
                    style={{ accentColor: 'var(--accent)' }} />
                  <span style={{ color: 'var(--fg-3)' }}>compare</span>
                </label>
              </div>

              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <Mini label="distance" value={`${t.distance_km} km`} icon={RouteIcon} />
                <Mini label="duration" value={`${(t.duration_min / 60).toFixed(1)} h`} icon={Clock} />
                <Mini label="avg speed" value={`${t.avg_speed_kmph} km/h`} icon={Gauge} />
              </div>

              <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]"
                style={{ color: 'var(--fg-3)' }}>
                <div>moving {Math.round(t.moving_min)}m</div>
                <div>idle {Math.round(t.stopped_min)}m</div>
                <div>{t.n_points.toLocaleString()} pts</div>
              </div>

              <div className="text-[10px] mt-2" style={{ color: 'var(--fg-3)' }}>
                {new Date(t.start_ts).toLocaleString()}
              </div>

              <div className="mt-3 flex items-center justify-between">
                {t.analyzed
                  ? <span className="inline-flex items-center gap-1 text-[10px]"
                      style={{ color: 'var(--success)' }}>
                      <CheckCircle2 className="w-3 h-3" /> analyzed
                    </span>
                  : <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>
                      not analyzed
                    </span>}
                <button
                  onClick={() => nav(`/route-intel/trips/${t.id}`)}
                  className="text-xs font-semibold"
                  style={{ color: 'var(--accent)' }}>
                  Open →
                </button>
              </div>
            </motion.div>
          );
        })}
      </div>

      {error && (
        <div className="card text-xs" style={{ color: 'var(--danger)' }}>{error}</div>
      )}
    </div>
  );
}

function Mini({ label, value, icon: Icon }: { label: string; value: string; icon: any }) {
  return (
    <div className="p-1.5 rounded" style={{ background: 'var(--bg-2)' }}>
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider"
        style={{ color: 'var(--fg-3)' }}>
        <Icon className="w-2.5 h-2.5" /> {label}
      </div>
      <div className="text-xs font-bold" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
