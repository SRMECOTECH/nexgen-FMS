import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Upload, FileSpreadsheet, ArrowRight, RefreshCw, Layers,
  Microscope, ExternalLink, Sparkles, CheckCircle2, AlertCircle,
  PlayCircle, FlaskConical, Truck, MapPin, Activity,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import {
  riListUploads, riUpload, riIngestLocal, riStatus,
  riStreamlitStatus, riStreamlitStart,
} from '../lib/routeIntel';

const SAMPLE_PATH = 'data/gpsfinal_20260603.xlsx';

export default function RouteIntelligence() {
  const nav = useNavigate();
  const [uploads, setUploads] = useState([]);
  const [status, setStatus] = useState(null);
  const [streamlit, setStreamlit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [streamlitBusy, setStreamlitBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState(null);
  const fileInput = useRef(null);

  const load = () => {
    setLoading(true);
    Promise.all([riListUploads(50), riStatus(), riStreamlitStatus()])
      .then(([u, s, sl]) => { setUploads(u.uploads); setStatus(s); setStreamlit(sl); setError(null); })
      .catch(e => setError(e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  useEffect(() => {
    const t = setInterval(() => riStreamlitStatus().then(setStreamlit).catch(() => {}), 8000);
    return () => clearInterval(t);
  }, []);

  const handleUpload = async (file) => {
    setBusy(true); setError(null);
    try {
      const r = await riUpload(file);
      load();
      nav(`/route-intel/uploads/${r.upload_id}`);
    } catch (e) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'upload failed');
    } finally { setBusy(false); }
  };

  const handleSample = async () => {
    setBusy(true); setError(null);
    try {
      const r = await riIngestLocal(SAMPLE_PATH);
      load();
      nav(`/route-intel/uploads/${r.upload_id}`);
    } catch (e) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'ingest failed');
    } finally { setBusy(false); }
  };

  const startStreamlit = async () => {
    setStreamlitBusy(true);
    try { setStreamlit(await riStreamlitStart()); }
    finally { setStreamlitBusy(false); }
  };

  const openStreamlit = () => {
    if (streamlit?.running) {
      window.open(streamlit.configured_url, '_blank', 'noopener,noreferrer');
    } else {
      startStreamlit().then(() => {
        setTimeout(() => {
          window.open(streamlit?.configured_url ?? 'http://127.0.0.1:8501', '_blank', 'noopener,noreferrer');
        }, 1500);
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Route Intelligence"
        subtitle="Upload GPS Excel · auto-detect segments · AI-driven cost, efficiency, weather, POI overlays"
      />

      {/* Deep-dive launcher */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="card ai-glow cursor-pointer"
        onClick={openStreamlit}
        style={{ borderColor: 'var(--accent)' }}
      >
        <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl pointer-events-none"
          style={{ background: 'var(--accent)', opacity: 0.18 }} />
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl shrink-0 animate-pulse-accent" style={{ background: 'var(--accent)' }}>
            <Microscope className="w-7 h-7" color="#000" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-[0.15em] mb-1"
              style={{ color: 'var(--accent)' }}>Deep Analysis</div>
            <div className="text-xl font-bold" style={{ color: 'var(--fg-1)' }}>
              Detailed Analysis of GPS Data
            </div>
            <div className="text-xs mt-1" style={{ color: 'var(--fg-2)' }}>
              Full Plotly + folium toolkit — multi-route maps, waypoint network diagrams,
              POI overlays, weather, AI journey planner. Reads <code className="mono">gpsfinal_*.xlsx</code> natively.
            </div>
            <div className="text-[11px] mt-2 flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
              {streamlit?.running
                ? <><CheckCircle2 className="w-3 h-3" style={{ color: 'var(--success)' }} /> Running · {streamlit.configured_url}</>
                : streamlit
                  ? <><AlertCircle className="w-3 h-3" style={{ color: 'var(--warning)' }} /> Service starting…</>
                  : <>Checking…</>}
              {streamlit?.managed_pid && (
                <span className="mono">· pid {streamlit.managed_pid}</span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <button onClick={(e) => { e.stopPropagation(); openStreamlit(); }}
              className="btn-primary flex items-center gap-1.5">
              <ExternalLink className="w-4 h-4" />
              {streamlit?.running ? 'Open' : 'Launch & open'}
            </button>
            {!streamlit?.running && (
              <button onClick={(e) => { e.stopPropagation(); startStreamlit(); }}
                disabled={streamlitBusy}
                className="text-[11px] flex items-center gap-1"
                style={{ color: 'var(--fg-3)', opacity: streamlitBusy ? 0.5 : 1 }}>
                <PlayCircle className="w-3 h-3" />
                {streamlitBusy ? 'starting…' : 'start service'}
              </button>
            )}
          </div>
        </div>
      </motion.div>

      {/* Upload zone + backend status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="card lg:col-span-2 border-2 border-dashed transition-colors"
          style={{
            borderColor: drag ? 'var(--accent)' : 'var(--border)',
            background: drag ? 'var(--accent-soft)' : undefined,
          }}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault(); setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) handleUpload(f);
          }}
        >
          <div className="flex flex-col items-center text-center py-8">
            <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-3"
              style={{ background: 'var(--accent-soft)' }}>
              <Upload className="w-7 h-7" style={{ color: 'var(--accent)' }} />
            </div>
            <div className="text-lg font-bold mb-1" style={{ color: 'var(--fg-1)' }}>
              Drop a GPS Excel here
            </div>
            <div className="text-xs mb-1" style={{ color: 'var(--fg-3)' }}>
              <span className="mono">.xlsx</span> with <span className="mono">s_asset_id, dt_message, i_lat, i_long</span>. Multi-sheet OK.
            </div>
            <div className="text-[11px] mb-4" style={{ color: 'var(--fg-3)' }}>
              One Excel = one trip; long stops within are segments of that trip.
            </div>
            <div className="flex items-center gap-2">
              <button disabled={busy} onClick={() => fileInput.current?.click()} className="btn-primary">
                {busy ? 'Working…' : 'Choose file'}
              </button>
              <button disabled={busy} onClick={handleSample} className="btn-ghost flex items-center gap-1.5">
                <FlaskConical className="w-4 h-4" />
                Load sample
              </button>
            </div>
            <input ref={fileInput} type="file" accept=".xlsx,.xls" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); }} />
            {error && <div className="mt-3 text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }} className="card">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <div className="text-sm font-semibold">AI Backend</div>
          </div>
          <div className="text-2xl font-bold mb-1 mono" style={{ color: 'var(--fg-1)' }}>
            {status?.ai_backend ?? '—'}
          </div>
          <div className="text-[11px] mb-3" style={{ color: 'var(--fg-3)' }}>
            Drop a <code className="mono">.gguf</code> into<br />
            <code className="mono break-all">{status?.models_dir}</code><br />
            and restart to upgrade from rule-based.
          </div>
          <div className="text-[10px] uppercase tracking-[0.15em] mb-1.5"
            style={{ color: 'var(--fg-3)' }}>Pipeline</div>
          <ul className="text-xs space-y-1.5" style={{ color: 'var(--fg-2)' }}>
            <li className="flex items-start gap-1.5">
              <span className="mt-1 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--accent)' }} />
              Cost model (fuel + driver + idle)
            </li>
            <li className="flex items-start gap-1.5">
              <span className="mt-1 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--accent)' }} />
              Route efficiency + backtracking
            </li>
            <li className="flex items-start gap-1.5">
              <span className="mt-1 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--accent)' }} />
              Speed zones + traffic loss
            </li>
            <li className="flex items-start gap-1.5">
              <span className="mt-1 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--accent)' }} />
              Weather · POI · geocoding overlays
            </li>
            <li className="flex items-start gap-1.5">
              <span className="mt-1 w-1 h-1 rounded-full shrink-0" style={{ background: 'var(--genai)' }} />
              Natural-language insights
            </li>
          </ul>
        </motion.div>
      </div>

      {/* Recent uploads */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Layers className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            Recent uploads
          </h3>
          <button onClick={load} className="btn-soft text-xs">
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
        {loading && (
          <div className="card text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
            <RefreshCw className="w-3.5 h-3.5 animate-spin" style={{ color: 'var(--accent)' }} />
            Loading…
          </div>
        )}
        {!loading && uploads.length === 0 && (
          <div className="card text-sm" style={{ color: 'var(--fg-3)' }}>
            No uploads yet. Drop a file above or load the sample.
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {uploads.map((u, i) => (
            <motion.button
              key={u.id}
              initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              onClick={() => nav(`/route-intel/uploads/${u.id}`)}
              className="card card-hover text-left"
            >
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] mb-0.5"
                    style={{ color: 'var(--accent)' }}>
                    <Truck className="w-3 h-3" />
                    <span className="mono">{u.vehicle_id}</span>
                  </div>
                  <div className="text-sm font-semibold truncate"
                    style={{ color: 'var(--fg-1)' }}>{u.display_name || u.original_name || u.filename}</div>
                </div>
                <FileSpreadsheet className="w-5 h-5 shrink-0" style={{ color: 'var(--accent)' }} />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="segments" value={u.n_segments ?? u.trip_count ?? '—'} />
                <Stat label="rows" value={u.n_rows.toLocaleString()} />
                <Stat label="distance" value={`${Math.round(u.total_distance_km)} km`} />
              </div>
              <div className="text-[10px] mt-2.5 mono" style={{ color: 'var(--fg-3)' }}>
                {new Date(u.first_ts).toLocaleDateString()} → {new Date(u.last_ts).toLocaleDateString()}
              </div>
              <div className="mt-2.5 text-[11px] inline-flex items-center gap-1 font-semibold"
                style={{ color: 'var(--accent)' }}>
                Open trip <ArrowRight className="w-3 h-3" />
              </div>
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="p-1.5 rounded-lg" style={{ background: 'var(--bg-2)' }}>
      <div className="text-[9px] uppercase tracking-[0.12em]"
        style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-sm font-bold mono" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
