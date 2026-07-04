import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  ScrollText, RefreshCw, Loader2, Search, Play, Pause,
  ChevronDown, ChevronRight, AlertTriangle,
} from 'lucide-react';
import { fetchLogs, type LogEntry, type LogsResponse } from '../lib/api';

// ============================================================================
// System → Logs — REAL backend logs, live in the browser.
//
// Every line the backend logs (startup, DB bootstrap, per-request traces,
// unhandled exceptions with full tracebacks) lands in an in-memory ring
// buffer server-side; this page polls it so any issue is visible and
// diagnosable without opening a terminal.
// ============================================================================

const LEVELS = ['ALL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'] as const;
type LevelFilter = typeof LEVELS[number];

const LEVEL_COLOR: Record<string, string> = {
  DEBUG:    'var(--fg-4)',
  INFO:     'var(--accent)',
  WARNING:  'var(--warning)',
  ERROR:    'var(--danger)',
  CRITICAL: 'var(--danger)',
};

function LogRow({ r }: { r: LogEntry }) {
  const [open, setOpen] = useState(false);
  const color = LEVEL_COLOR[r.level] ?? 'var(--fg-3)';
  const isErr = r.level === 'ERROR' || r.level === 'CRITICAL';
  return (
    <div
      className="border-b last:border-b-0 text-xs"
      style={{
        borderColor: 'var(--border)',
        background: isErr ? 'color-mix(in srgb, var(--danger) 6%, transparent)' : 'transparent',
      }}
    >
      <div
        className={`flex items-start gap-3 px-3 py-1.5 ${r.exc ? 'cursor-pointer' : ''}`}
        onClick={() => r.exc && setOpen(o => !o)}
      >
        <span className="mono shrink-0 pt-px" style={{ color: 'var(--fg-4)' }}>
          {r.ts.slice(11, 23)}
        </span>
        <span className="mono shrink-0 w-16 font-semibold pt-px" style={{ color }}>
          {r.level}
        </span>
        <span className="mono shrink-0 max-w-44 truncate pt-px" title={r.service} style={{ color: 'var(--fg-3)' }}>
          {r.service}
        </span>
        <span className="mono flex-1 break-all" style={{ color: isErr ? 'var(--fg-1)' : 'var(--fg-2)' }}>
          {r.message}
        </span>
        {r.exc && (
          <span className="shrink-0 pt-px" style={{ color: 'var(--danger)' }}>
            {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </span>
        )}
      </div>
      {open && r.exc && (
        <pre
          className="mx-3 mb-2 p-3 rounded-lg overflow-x-auto text-[11px] leading-snug"
          style={{ background: 'var(--bg-1)', color: 'var(--danger)', border: '1px solid var(--border)' }}
        >
          {r.exc}
        </pre>
      )}
    </div>
  );
}

export default function Logs() {
  const [data, setData]       = useState<LogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [level, setLevel]     = useState<LevelFilter>('ALL');
  const [search, setSearch]   = useState('');
  const [live, setLive]       = useState(true);

  // filters live in refs so the poll timer always reads the latest values
  const filtersRef = useRef({ level, search });
  filtersRef.current = { level, search };

  const load = useCallback(() => {
    const f = filtersRef.current;
    fetchLogs({
      limit: 400,
      level: f.level === 'ALL' ? undefined : f.level,
      search: f.search.trim() || undefined,
    })
      .then(d => { setData(d); setError(null); })
      .catch(e => setError(e?.message ?? 'backend unreachable'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setLoading(true); load(); }, [load, level]);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [live, load]);

  const counts = data?.counts;
  const errCount = (counts?.ERROR ?? 0) + (counts?.CRITICAL ?? 0);

  return (
    <div className="space-y-6">
      {/* ===== Hero =================================================== */}
      <motion.section
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl p-6 border"
        style={{
          background: 'radial-gradient(900px 160px at 0% 0%, var(--accent-soft), transparent), var(--bg-3)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--accent)' }}>
          <ScrollText className="w-4 h-4" />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">System</span>
        </div>
        <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
          Backend logs
        </h1>
        <p className="text-sm leading-relaxed max-w-3xl" style={{ color: 'var(--fg-2)' }}>
          Live feed of everything the backend logs — startup, database bootstrap, every API
          request, and full error tracebacks. If something breaks, the reason is on this page.
          {data && (
            <span className="mono text-xs ml-2" style={{ color: 'var(--fg-3)' }}>
              · {data.buffered} lines buffered
            </span>
          )}
        </p>
      </motion.section>

      {error && (
        <div className="rounded-xl border p-4 text-sm flex items-center gap-2"
             style={{ borderColor: 'var(--danger)', color: 'var(--danger)', background: 'var(--bg-3)' }}>
          <AlertTriangle className="w-4 h-4 shrink-0" />
          Could not reach the backend ({error}) — is it running? Check the terminal it was started from.
        </div>
      )}

      {/* ===== Toolbar ================================================ */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          {LEVELS.map(l => {
            const active = level === l;
            const badge =
              l === 'ERROR' ? errCount :
              l === 'WARNING' ? counts?.WARNING ?? 0 :
              l === 'INFO' ? counts?.INFO ?? 0 :
              l === 'DEBUG' ? counts?.DEBUG ?? 0 : null;
            return (
              <button
                key={l}
                onClick={() => setLevel(l)}
                className="px-3 py-1.5 text-xs font-semibold transition-all"
                style={{
                  background: active ? 'var(--accent)' : 'var(--bg-3)',
                  color: active ? '#000' : l === 'ERROR' && errCount ? 'var(--danger)' : 'var(--fg-2)',
                }}
              >
                {l}{badge !== null && badge > 0 ? ` (${badge})` : ''}
              </button>
            );
          })}
        </div>

        <div className="relative flex-1 min-w-52">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--fg-3)' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
            placeholder="Filter by text — service, message, traceback… (Enter)"
            className="w-full rounded-lg pl-9 pr-3 py-2 text-xs mono outline-none"
            style={{ background: 'var(--bg-1)', border: '1px solid var(--border)', color: 'var(--fg-1)' }}
            spellCheck={false}
          />
        </div>

        <button
          onClick={() => setLive(v => !v)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold border transition-all"
          style={{
            borderColor: live ? 'var(--success)' : 'var(--border)',
            color: live ? 'var(--success)' : 'var(--fg-2)',
          }}
        >
          {live ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
          {live ? 'Live (4s)' : 'Paused'}
        </button>
        <button
          onClick={() => { setLoading(true); load(); }}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold border transition-all hover:bg-[var(--bg-2)]"
          style={{ borderColor: 'var(--border)', color: 'var(--fg-2)' }}
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Refresh
        </button>
      </div>

      {/* ===== Log table ============================================== */}
      <section className="rounded-2xl border overflow-hidden" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
        <div className="max-h-[62vh] overflow-y-auto">
          {data?.logs.length
            ? data.logs.map(r => <LogRow key={r.id} r={r} />)
            : (
              <div className="p-6 text-sm text-center" style={{ color: 'var(--fg-3)' }}>
                {loading ? 'Loading…' : 'No log lines match the current filter.'}
              </div>
            )}
        </div>
      </section>

      <p className="text-[11px]" style={{ color: 'var(--fg-3)' }}>
        Rows with a chevron carry a full Python traceback — click to expand. The buffer holds the
        most recent 3000 lines in backend memory; restarting the backend clears it.
      </p>
    </div>
  );
}
