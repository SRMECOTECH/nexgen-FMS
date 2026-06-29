import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Upload, FileSpreadsheet, MapPin, Clock, Route as RouteIcon,
  Sparkles, ArrowRight, RefreshCw, Gauge, Layers, FlaskConical, Truck,
  ExternalLink, Microscope, CheckCircle2, AlertCircle, PlayCircle,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import {
  riListUploads, riUpload, riIngestLocal, riStatus,
  riStreamlitStatus, riStreamlitStart,
  type RIUpload, type RIStreamlitStatus,
} from '../lib/api';

const SAMPLE_PATH = 'data/gpsfinal_20260603.xlsx';

export default function RouteIntelligence() {
  const nav = useNavigate();
  const [uploads, setUploads] = useState<RIUpload[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ ai_backend: string; models_dir: string } | null>(null);
  const [streamlit, setStreamlit] = useState<RIStreamlitStatus | null>(null);
  const [streamlitBusy, setStreamlitBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    Promise.all([riListUploads(50), riStatus(), riStreamlitStatus()])
      .then(([u, s, sl]) => { setUploads(u.uploads); setStatus(s); setStreamlit(sl); setError(null); })
      .catch((e) => setError(e?.message ?? 'failed'))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  // Poll Streamlit health every 8s while the page is open so the button
  // flips to "open" as soon as the supervisor binds the port.
  useEffect(() => {
    const t = setInterval(() => {
      riStreamlitStatus().then(setStreamlit).catch(() => {});
    }, 8000);
    return () => clearInterval(t);
  }, []);

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

  const handleUpload = async (file: File) => {
    setBusy(true); setError(null);
    try {
      const r = await riUpload(file);
      load();
      // jump straight to the upload's trip list
      nav(`/route-intel/uploads/${r.upload_id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'upload failed');
    } finally { setBusy(false); }
  };

  const handleSample = async () => {
    setBusy(true); setError(null);
    try {
      const r = await riIngestLocal(SAMPLE_PATH);
      load();
      nav(`/route-intel/uploads/${r.upload_id}`);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'ingest failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Route Intelligence"
        subtitle="Upload GPS Excel · auto-detect trips · cost + efficiency + AI insights"
      />

      {/* Hero: Detailed Analysis of GPS Data — opens the Streamlit deep-dive */}
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="card relative overflow-hidden cursor-pointer"
        onClick={openStreamlit}
        style={{
          background: 'linear-gradient(135deg, var(--accent-soft) 0%, transparent 100%)',
          borderColor: 'var(--accent)',
        }}>
        <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl pointer-events-none"
          style={{ background: 'var(--accent)', opacity: 0.22 }} />
        <div className="flex items-center gap-4">
          <div className="p-3 rounded-xl shrink-0" style={{ background: 'var(--accent)' }}>
            <Microscope className="w-7 h-7" color="#000" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-wider mb-1"
              style={{ color: 'var(--accent)' }}>Deep dive</div>
            <div className="text-xl font-bold" style={{ color: 'var(--fg-1)' }}>
              Detailed Analysis of GPS Data
            </div>
            <div className="text-xs mt-1" style={{ color: 'var(--fg-2)' }}>
              The complete Plotly + folium analyzer — multi-route comparison maps, waypoint network diagrams,
              POI + geocoding + weather overlays, executive cost summary, AI journey planner.
              Reads your vendor <code>gpsfinal_*.xlsx</code> natively.
            </div>
            <div className="text-[11px] mt-2 flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
              {streamlit?.running
                ? <><CheckCircle2 className="w-3 h-3" style={{ color: 'var(--success)' }} /> Running on {streamlit.configured_url}</>
                : streamlit
                  ? <><AlertCircle className="w-3 h-3" style={{ color: 'var(--warning)' }} /> Background service starting…</>
                  : <>Checking…</>}
              {streamlit?.managed_pid !== null && streamlit?.managed_pid !== undefined && (
                <span style={{ color: 'var(--fg-3)' }}>· pid {streamlit.managed_pid}</span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <button
              onClick={(e) => { e.stopPropagation(); openStreamlit(); }}
              className="px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-1.5"
              style={{ background: 'var(--accent)', color: '#000' }}>
              <ExternalLink className="w-4 h-4" />
              {streamlit?.running ? 'Open deep analyzer' : 'Launch & open'}
            </button>
            {!streamlit?.running && (
              <button
                onClick={(e) => { e.stopPropagation(); startStreamlit(); }}
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

      {/* Upload zone */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          className={`card lg:col-span-2 relative border-2 border-dashed transition-colors`}
          style={{
            borderColor: drag ? 'var(--accent)' : 'var(--border)',
            background: drag ? 'var(--accent-soft)' : 'var(--bg-1)',
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
              Drop a gps Excel here
            </div>
            <div className="text-xs mb-4" style={{ color: 'var(--fg-3)' }}>
              .xlsx with <code>s_asset_id, dt_message, i_lat, i_long</code> columns. Multi-sheet OK.
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={busy}
                onClick={() => fileInput.current?.click()}
                className="px-4 py-2 rounded-lg text-sm font-semibold"
                style={{ background: 'var(--accent)', color: '#000', opacity: busy ? 0.6 : 1 }}>
                {busy ? 'Working…' : 'Choose file'}
              </button>
              <button
                disabled={busy}
                onClick={handleSample}
                className="px-4 py-2 rounded-lg text-sm font-semibold border"
                style={{ borderColor: 'var(--border)', color: 'var(--fg-2)', opacity: busy ? 0.6 : 1 }}>
                <FlaskConical className="inline w-4 h-4 -mt-0.5 mr-1" />
                Load sample (gpsfinal_20260603.xlsx)
              </button>
            </div>
            <input
              ref={fileInput} type="file" accept=".xlsx,.xls" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); }}
            />
            {error && <div className="mt-3 text-xs" style={{ color: 'var(--danger)' }}>{error}</div>}
          </div>
        </motion.div>

        {/* AI backend status card */}
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }} className="card">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <div className="text-sm font-semibold">AI Insights Backend</div>
          </div>
          <div className="text-2xl font-bold mb-1" style={{ color: 'var(--fg-1)' }}>
            {status?.ai_backend ?? '—'}
          </div>
          <div className="text-[11px] mb-3" style={{ color: 'var(--fg-3)' }}>
            Drop a <code>.gguf</code> file in <br />
            <code className="break-all">{status?.models_dir}</code> <br />
            and restart the backend to upgrade from rule-based templates.
          </div>
          <div className="text-[10px] uppercase tracking-wider"
            style={{ color: 'var(--fg-3)' }}>What you get</div>
          <ul className="text-xs mt-1 space-y-1" style={{ color: 'var(--fg-2)' }}>
            <li>• Cost model (fuel + driver + idle waste)</li>
            <li>• Route efficiency vs straight-line</li>
            <li>• Speed-zone + traffic loss + backtracking</li>
            <li>• Waypoint sequence + per-window aggregates</li>
            <li>• Natural-language summary &amp; recommendations</li>
          </ul>
        </motion.div>
      </div>

      {/* Past uploads */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Layers className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            Recent uploads
          </h3>
          <button onClick={load} className="text-xs flex items-center gap-1"
            style={{ color: 'var(--accent)' }}>
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
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs uppercase tracking-wider"
                    style={{ color: 'var(--fg-3)' }}>{u.vehicle_id}</div>
                  <div className="text-sm font-semibold truncate"
                    style={{ color: 'var(--fg-1)' }}>{u.original_name || u.filename}</div>
                </div>
                <FileSpreadsheet className="w-5 h-5 shrink-0" style={{ color: 'var(--accent)' }} />
              </div>
              <div className="grid grid-cols-3 gap-2 mt-3 text-[11px]">
                <Stat label="trips" value={String(u.trip_count)} />
                <Stat label="rows" value={u.n_rows.toLocaleString()} />
                <Stat label="distance" value={`${Math.round(u.total_distance_km)} km`} />
              </div>
              <div className="text-[10px] mt-2 flex items-center gap-1.5"
                style={{ color: 'var(--fg-3)' }}>
                <Clock className="w-3 h-3" />
                {new Date(u.first_ts).toLocaleString()} → {new Date(u.last_ts).toLocaleString()}
              </div>
              <div className="mt-2 text-[11px] inline-flex items-center gap-1 font-semibold"
                style={{ color: 'var(--accent)' }}>
                Open <ArrowRight className="w-3 h-3" />
              </div>
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-1.5 rounded" style={{ background: 'var(--bg-2)' }}>
      <div className="text-[9px] uppercase tracking-wider"
        style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="text-xs font-bold" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}
