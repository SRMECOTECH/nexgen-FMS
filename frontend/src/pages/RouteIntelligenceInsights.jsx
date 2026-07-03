import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles, RefreshCw, Filter, ArrowRight, Loader2, AlertCircle, Upload,
  Calendar, X, Search, ChevronDown, ChevronUp, Wand2, Coins, Activity, Wind,
  Truck, Layers3, List as ListIcon, Layers, AlertTriangle, IndianRupee,
} from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import { riListInsights } from '../lib/routeIntel';
import RecommendationsPanel from './RecommendationsPanel';

// ============================================================================
// AI Insights Feed — redesigned for signal-over-noise.
//
// The pipeline writes 5 paragraphs per analysis run, and trips often get
// re-analysed several times, so a chronological dump is unreadable. The new
// layout is:
//
//   1. Hero stats        — total insights, unique trips, HIGH-priority count,
//                          estimated monthly savings, model in use
//   2. Critical actions  — collapsible. HIGH/MEDIUM recommendations across all
//                          trips, de-duped and sorted by ₹/month
//   3. Toolbar           — search · type pills (multi) · priority pills (multi)
//                          · date range · sort · grouped/flat view toggle
//   4. Main feed         — default: ONE CARD PER ANALYSIS RUN (trip + timestamp
//                          bucket), with tabs for each of the 5 insight types.
//                          Alt: flat chronological list with improved cards.
// ============================================================================

// ---- type registry: icon + label + accent colour ---------------------------
const TYPE_META = {
  trip_summary:         { label: 'Trip Summary',     icon: Truck,          color: 'var(--accent)' },
  cost_advice:          { label: 'Cost Advice',      icon: Coins,          color: 'var(--prediction)' },
  route_quality:        { label: 'Route Quality',    icon: Wand2,          color: 'var(--accent-2)' },
  traffic_callout:      { label: 'Traffic',          icon: Wind,           color: 'var(--warning)' },
  recommendations_list: { label: 'Recommendations',  icon: Sparkles,       color: 'var(--success)' },
  comparison_verdict:   { label: 'Verdicts',         icon: Activity,       color: 'var(--genai)' },
};
const TYPE_KEYS = Object.keys(TYPE_META);

// ---- date-range presets ----------------------------------------------------
const RANGE_PRESETS = [
  { key: 'all',   label: 'All time', days: null },
  { key: 'today', label: 'Today',    days: 0 },
  { key: '7d',    label: 'Last 7d',  days: 7 },
  { key: '30d',   label: 'Last 30d', days: 30 },
];
const isoDay = (d) => d.toISOString().slice(0, 10);
function presetRange(key) {
  const today = new Date();
  if (key === 'today') return { from: isoDay(today), to: isoDay(today) };
  if (key === '7d')    { const f = new Date(today); f.setDate(f.getDate() - 7);  return { from: isoDay(f), to: isoDay(today) }; }
  if (key === '30d')   { const f = new Date(today); f.setDate(f.getDate() - 30); return { from: isoDay(f), to: isoDay(today) }; }
  return { from: '', to: '' };
}

// ---- sort options ---------------------------------------------------------
const SORTS = [
  { key: 'newest',   label: 'Newest first' },
  { key: 'oldest',   label: 'Oldest first' },
  { key: 'savings',  label: 'Highest savings' },
  { key: 'priority', label: 'Critical first' },
];

// ---- parse "• [HIGH] Idle Time Reduction: ... ≈ ₹60,332/month." -----------
function parseRecommendations(text) {
  if (!text) return [];
  return text.split('\n')
    .map(l => l.trim())
    .filter(l => l.startsWith('•'))
    .map(l => {
      const m = l.match(/\[(HIGH|MEDIUM|LOW)\]/i);
      const priority = (m?.[1] || 'MEDIUM').toUpperCase();
      const sav = l.match(/₹([\d,]+)\s*\/?\s*month/i);
      const monthly = sav ? Number(sav[1].replace(/,/g, '')) : 0;
      const cat = l.match(/\]\s*([^:]+):/);
      const category = cat ? cat[1].trim() : '—';
      const cleaned = l.replace(/^•\s*/, '').replace(/\s*≈.*$/, '').trim();
      return { priority, monthly_savings_inr: monthly, category, text: cleaned, raw: l };
    });
}

// ---- group flat rows into "analysis runs" -------------------------------
// Prefer run_id so a segment run and a parent-trip run created at the same
// minute don't accidentally collide. Older rows without run_id fall back to
// (trip_id + minute).
function groupIntoRuns(rows) {
  const map = new Map();
  for (const r of rows) {
    const minute = (r.created_at || '').slice(0, 16);
    const key = r.run_id ? `run-${r.run_id}` : `${r.trip_id ?? 'x'}-${minute}`;
    if (!map.has(key)) {
      const isSegment = r.scope === 'segment';
      map.set(key, {
        key,
        run_id:        r.run_id,
        trip_id:       r.trip_id,
        vehicle_id:    r.vehicle_id,
        scope:         isSegment ? 'segment' : 'trip',
        // ACTUAL scope of this run (segment route if segment-scoped, full trip otherwise):
        from_waypoint: isSegment ? r.segment_from : r.from_waypoint,
        to_waypoint:   isSegment ? r.segment_to   : r.to_waypoint,
        // Parent trip context — shown as the "part of …" tag on segment cards:
        parent_trip_from: r.from_waypoint,
        parent_trip_to:   r.to_waypoint,
        segment_seq:      r.segment_seq ?? null,
        segment_distance: r.segment_distance_km ?? null,
        trip_distance:    r.distance_km ?? null,
        created_at: r.created_at,
        model: r.model,
        insights: {},
        max_priority: null,
        total_monthly_savings: 0,
      });
    }
    const run = map.get(key);
    run.insights[r.insight_type] = r;
    if (r.insight_type === 'recommendations_list') {
      const recs = parseRecommendations(r.text);
      const sum = recs.reduce((a, x) => a + x.monthly_savings_inr, 0);
      run.total_monthly_savings = Math.max(run.total_monthly_savings, sum);
      const rank = { HIGH: 3, MEDIUM: 2, LOW: 1 };
      const top = recs.reduce((a, x) => (rank[x.priority] > rank[a ?? 'LOW']) ? x.priority : a, null);
      if (top) run.max_priority = top;
    }
  }
  return Array.from(map.values());
}

const priorityRank = { HIGH: 3, MEDIUM: 2, LOW: 1 };

// ============================================================================
export default function RouteIntelligenceInsights() {
  const nav = useNavigate();

  // ---- filters ------------------------------------------------------------
  const [search, setSearch]       = useState('');
  const [types, setTypes]         = useState([]);          // multi-select; [] = all
  const [priorities, setPrios]    = useState([]);          // multi-select; [] = all
  const [rangeKey, setRangeKey]   = useState('all');
  const [dateFrom, setDateFrom]   = useState('');
  const [dateTo, setDateTo]       = useState('');
  const [sortKey, setSortKey]     = useState('newest');
  const [view, setView]           = useState('grouped');   // grouped | flat
  const [dedupe, setDedupe]         = useState(true);      // server-side semantic de-dup

  // ---- data ---------------------------------------------------------------
  const [rows, setRows]     = useState([]);
  const [meta, setMeta]     = useState({ dedupe_available: false, embedding_model: null, raw_count: 0, deduped_count: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  const load = () => {
    setLoading(true); setError(null);
    // backend supports a single type filter; we apply multi-select client-side.
    riListInsights(200, undefined, dateFrom || undefined, dateTo || undefined, dedupe)
      .then(r => {
        setRows(r.insights);
        setMeta({
          dedupe_available: !!r.dedupe_available,
          embedding_model:  r.embedding_model || null,
          raw_count:        r.raw_count ?? r.insights.length,
          deduped_count:    r.deduped_count ?? r.insights.length,
        });
      })
      .catch(e => setError(e?.response?.data?.detail ?? e?.message ?? 'failed to load'))
      .finally(() => setLoading(false));
  };
  useEffect(load, [dateFrom, dateTo, dedupe]);

  const applyPreset = (key) => {
    setRangeKey(key);
    const r = presetRange(key);
    setDateFrom(r.from); setDateTo(r.to);
  };

  // ---- runs (always computed; filters apply on top) -----------------------
  const allRuns = useMemo(() => groupIntoRuns(rows), [rows]);

  // ---- hero stats ---------------------------------------------------------
  const stats = useMemo(() => {
    const totalSavings = allRuns.reduce((a, r) => a + r.total_monthly_savings, 0);
    const critical = allRuns.filter(r => r.max_priority === 'HIGH').length;
    const models = new Set(rows.map(r => r.model).filter(Boolean));
    return {
      insights: rows.length,
      runs: allRuns.length,
      trips: new Set(allRuns.map(r => r.trip_id).filter(Boolean)).size,
      critical,
      monthly_savings: totalSavings,
      models: [...models],
    };
  }, [rows, allRuns]);

  // ---- filtered + sorted feed --------------------------------------------
  const filteredRuns = useMemo(() => {
    const q = search.trim().toLowerCase();
    let out = allRuns.filter(run => {
      // type filter — show run if it has at least one of the selected types
      if (types.length && !types.some(t => run.insights[t])) return false;
      // priority filter — only meaningful for runs that have recs
      if (priorities.length) {
        if (!run.max_priority || !priorities.includes(run.max_priority)) return false;
      }
      // search
      if (q) {
        const bag = [
          run.vehicle_id, run.from_waypoint, run.to_waypoint,
          ...Object.values(run.insights).map(i => i?.text || ''),
        ].join(' ').toLowerCase();
        if (!bag.includes(q)) return false;
      }
      return true;
    });

    const cmp = {
      newest:   (a, b) => (b.created_at || '').localeCompare(a.created_at || ''),
      oldest:   (a, b) => (a.created_at || '').localeCompare(b.created_at || ''),
      savings:  (a, b) => b.total_monthly_savings - a.total_monthly_savings,
      priority: (a, b) => (priorityRank[b.max_priority] || 0) - (priorityRank[a.max_priority] || 0)
                       || (b.total_monthly_savings - a.total_monthly_savings),
    }[sortKey];
    out = [...out].sort(cmp);
    return out;
  }, [allRuns, types, priorities, search, sortKey]);

  // flat (filtered) rows = rows whose parent run survived + type matches
  const filteredFlatRows = useMemo(() => {
    const keep = new Set(filteredRuns.map(r => r.key));
    const q = search.trim().toLowerCase();
    return rows
      .filter(r => {
        const k = `${r.trip_id ?? 'x'}-${(r.created_at || '').slice(0, 16)}`;
        if (!keep.has(k)) return false;
        if (types.length && !types.includes(r.insight_type)) return false;
        if (q) {
          const bag = [r.vehicle_id, r.from_waypoint, r.to_waypoint, r.text, r.insight_type].join(' ').toLowerCase();
          if (!bag.includes(q)) return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sortKey === 'oldest') return (a.created_at || '').localeCompare(b.created_at || '');
        return (b.created_at || '').localeCompare(a.created_at || '');
      });
  }, [rows, filteredRuns, types, search, sortKey]);

  const toggle = (val, list, setList) =>
    setList(list.includes(val) ? list.filter(x => x !== val) : [...list, val]);

  // -------------------------------------------------------------------------
  return (
    <div className="space-y-6">
      <PageHeader title="AI Insights Feed"
        subtitle="Every natural-language paragraph the route-intel pipeline has produced — grouped, ranked, searchable" />

      {/* ===== About this page (compact, one-liner) ====================== */}
      <div
        className="rounded-xl px-4 py-3 text-[12px] leading-relaxed flex items-start gap-2"
        style={{
          background: 'linear-gradient(90deg, var(--accent-soft), transparent)',
          border: '1px solid var(--border)',
          color: 'var(--fg-2)',
        }}
      >
        <Sparkles className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
        <div>
          <span style={{ color: 'var(--fg-1)' }}>What you're looking at:</span>{' '}
          a fleet-wide rollup of every AI paragraph (cost advice, route quality, traffic notes, recommendations) ever written about your trips.
          One trip can produce several cards — one per <b>analysis run</b> (whole-trip or per-segment). The <span className="mono">Whole trip</span> / <span className="mono">Segment #N</span> chip on each card tells you the scope.
        </div>
      </div>

      {/* ===== Stats strip ================================================ */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatTile icon={Sparkles}      label="Insights"          value={stats.insights}                accent="var(--accent)" />
        <StatTile icon={Layers3}       label="Analysis runs"     value={stats.runs}                    accent="var(--accent-2)" />
        <StatTile icon={Truck}         label="Unique trips"      value={stats.trips}                   accent="var(--genai)" />
        <StatTile icon={AlertTriangle} label="Critical (HIGH)"   value={stats.critical}                accent="var(--danger)" />
        <StatTile icon={IndianRupee}   label="Potential ₹/mo"    value={`₹${stats.monthly_savings.toLocaleString('en-IN')}`} accent="var(--success)" big />
      </div>

      {/* ===== Critical action items (headline → routes → detailed report) ===== */}
      <RecommendationsPanel />

      {/* ===== Toolbar =================================================== */}
      <div className="card space-y-3" style={{ padding: '14px 16px' }}>
        {/* row 1: search + view toggle + sort + refresh */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-[220px] max-w-[420px]">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--fg-3)' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search vehicle, route, or text…"
              className="w-full pl-8 pr-3 py-1.5 rounded-md text-xs"
              style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)' }}
            />
            {search && (
              <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2" title="Clear">
                <X className="w-3 h-3" style={{ color: 'var(--fg-3)' }} />
              </button>
            )}
          </div>

          <div className="flex items-center gap-1 ml-auto">
            <select
              value={sortKey} onChange={(e) => setSortKey(e.target.value)}
              className="text-[11px] px-2 py-1.5 rounded mono"
              style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)', colorScheme: 'dark' }}
            >
              {SORTS.map(s => <option key={s.key} value={s.key}>Sort: {s.label}</option>)}
            </select>

            <div className="flex items-center rounded border" style={{ borderColor: 'var(--border)' }}>
              <ViewBtn active={view === 'grouped'} onClick={() => setView('grouped')} icon={Layers}>By run</ViewBtn>
              <ViewBtn active={view === 'flat'}    onClick={() => setView('flat')}    icon={ListIcon}>Flat</ViewBtn>
            </div>

            <button
              onClick={() => setDedupe(d => !d)}
              disabled={!meta.dedupe_available && !dedupe}
              className="btn-soft text-xs flex items-center gap-1"
              title={meta.dedupe_available
                ? `Semantic de-dup via ${meta.embedding_model ?? 'embeddings'} (collapses near-duplicate paragraphs)`
                : 'Embeddings model not installed — run scripts/download-models.ps1'}
              style={{
                background: dedupe && meta.dedupe_available ? 'var(--accent-soft)' : 'var(--bg-2)',
                color:      dedupe && meta.dedupe_available ? 'var(--accent)' : 'var(--fg-3)',
                opacity:    !meta.dedupe_available ? 0.55 : 1,
              }}
            >
              <Layers3 className="w-3 h-3" />
              {dedupe ? 'Dedupe ON' : 'Dedupe OFF'}
              {!meta.dedupe_available && <span className="text-[9px] ml-1">(no model)</span>}
            </button>
            <button onClick={load} className="btn-soft text-xs">
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
          </div>
        </div>

        {/* row 2: type pills (multi) */}
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="w-3.5 h-3.5" style={{ color: 'var(--fg-3)' }} />
          <span className="text-[10px] uppercase tracking-[0.12em] mr-1" style={{ color: 'var(--fg-3)' }}>Type</span>
          <PillToggle active={types.length === 0} onClick={() => setTypes([])} label="All" />
          {TYPE_KEYS.map(k => (
            <PillToggle key={k} active={types.includes(k)} onClick={() => toggle(k, types, setTypes)}
              label={TYPE_META[k].label} color={TYPE_META[k].color} />
          ))}
        </div>

        {/* row 3: priority pills (multi) + date range */}
        <div className="flex items-center gap-2 flex-wrap">
          <AlertTriangle className="w-3.5 h-3.5" style={{ color: 'var(--fg-3)' }} />
          <span className="text-[10px] uppercase tracking-[0.12em] mr-1" style={{ color: 'var(--fg-3)' }}>Priority</span>
          <PillToggle active={priorities.length === 0} onClick={() => setPrios([])} label="Any" />
          <PillToggle active={priorities.includes('HIGH')}   onClick={() => toggle('HIGH', priorities, setPrios)}   label="HIGH"   color="var(--danger)" />
          <PillToggle active={priorities.includes('MEDIUM')} onClick={() => toggle('MEDIUM', priorities, setPrios)} label="MEDIUM" color="var(--warning)" />
          <PillToggle active={priorities.includes('LOW')}    onClick={() => toggle('LOW', priorities, setPrios)}    label="LOW"    color="var(--fg-3)" />

          <span className="w-px h-4 mx-2" style={{ background: 'var(--border)' }} />

          <Calendar className="w-3.5 h-3.5" style={{ color: 'var(--fg-3)' }} />
          <span className="text-[10px] uppercase tracking-[0.12em] mr-1" style={{ color: 'var(--fg-3)' }}>Date</span>
          {RANGE_PRESETS.map(r => (
            <PillToggle key={r.key} active={rangeKey === r.key} onClick={() => applyPreset(r.key)} label={r.label} />
          ))}
          <input type="date" value={dateFrom}
            onChange={(e) => { setDateFrom(e.target.value); setRangeKey('custom'); }}
            className="text-[11px] px-2 py-1 rounded mono"
            style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)', colorScheme: 'dark' }} />
          <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>→</span>
          <input type="date" value={dateTo}
            onChange={(e) => { setDateTo(e.target.value); setRangeKey('custom'); }}
            className="text-[11px] px-2 py-1 rounded mono"
            style={{ background: 'var(--bg-2)', color: 'var(--fg-1)', border: '1px solid var(--border)', colorScheme: 'dark' }} />
          {(dateFrom || dateTo) && (
            <button onClick={() => applyPreset('all')} className="btn-soft text-[11px]" title="Clear dates">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        <div className="text-[11px] flex items-center gap-2 pt-1" style={{ color: 'var(--fg-3)' }}>
          Showing <span className="mono" style={{ color: 'var(--accent)' }}>
            {view === 'grouped' ? `${filteredRuns.length} run${filteredRuns.length === 1 ? '' : 's'}`
                                 : `${filteredFlatRows.length} insight${filteredFlatRows.length === 1 ? '' : 's'}`}
          </span>
          {stats.models.length > 0 && (
            <>
              · model{stats.models.length > 1 ? 's' : ''}:{' '}
              {stats.models.map(m => (
                <span key={m} className="mono px-1.5 py-0.5 rounded"
                  style={{ background: 'var(--bg-2)', color: 'var(--fg-2)' }}>{m}</span>
              ))}
            </>
          )}
          {dedupe && meta.dedupe_available && meta.raw_count > meta.deduped_count && (
            <span className="ml-auto" style={{ color: 'var(--accent)' }}>
              · de-duped <span className="mono">{meta.raw_count} → {meta.deduped_count}</span>
              {meta.embedding_model && <span className="mono ml-1" style={{ color: 'var(--fg-3)' }}>via {meta.embedding_model}</span>}
            </span>
          )}
          {!meta.dedupe_available && (
            <span className="ml-auto text-[10px]" style={{ color: 'var(--fg-3)' }}>
              Tip: run <span className="mono">scripts/download-models.ps1</span> to enable semantic de-dup.
            </span>
          )}
        </div>
      </div>

      {/* ===== States ==================================================== */}
      {loading && (
        <div className="card text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading insights…
        </div>
      )}
      {error && (
        <div className="card flex items-start gap-2 text-sm" style={{ color: 'var(--danger)' }}>
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">Backend error</div>
            <div className="text-xs mt-1 mono" style={{ color: 'var(--fg-3)' }}>{error}</div>
            <button onClick={load} className="btn-soft text-xs mt-2">
              <RefreshCw className="w-3 h-3" /> Retry
            </button>
          </div>
        </div>
      )}
      {!loading && !error && rows.length === 0 && (
        <div className="card text-center py-8" style={{ color: 'var(--fg-3)' }}>
          <div className="w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3"
            style={{ background: 'var(--accent-soft)' }}>
            <Upload className="w-5 h-5" style={{ color: 'var(--accent)' }} />
          </div>
          <div className="text-sm font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>No insights yet</div>
          <div className="text-xs mb-3">Upload an Excel and analyse a trip — insights appear here automatically.</div>
          <button onClick={() => nav('/route-intel')} className="btn-primary text-xs">Go to upload</button>
        </div>
      )}

      {/* ===== Main feed ================================================ */}
      {view === 'grouped' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredRuns.map((run, i) => (
            <RunCard key={run.key} run={run} index={i} onOpen={() => run.trip_id && nav(`/route-intel/trips/${run.trip_id}`)} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredFlatRows.map((r, i) => (
            <FlatInsightCard key={r.id} r={r} index={i} onOpen={() => r.trip_id && nav(`/route-intel/trips/${r.trip_id}`)} />
          ))}
        </div>
      )}

      {!loading && !error
        && (view === 'grouped' ? filteredRuns.length === 0 : filteredFlatRows.length === 0)
        && rows.length > 0 && (
        <div className="card text-center py-6 text-xs" style={{ color: 'var(--fg-3)' }}>
          No matches for the current filters.
          <button onClick={() => { setSearch(''); setTypes([]); setPrios([]); applyPreset('all'); }}
            className="btn-soft text-[11px] ml-2">
            <X className="w-3 h-3" /> Clear filters
          </button>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Sub-components
// ============================================================================

function StatTile({ icon: Icon, label, value, accent, big }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-xl p-3 border"
      style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-md" style={{ background: 'var(--bg-2)' }}>
          <Icon className="w-3.5 h-3.5" style={{ color: accent }} />
        </div>
        <div className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--fg-3)' }}>{label}</div>
      </div>
      <div
        className={`mt-2 font-bold mono ${big ? 'text-xl' : 'text-2xl'}`}
        style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
      >
        {value}
      </div>
    </motion.div>
  );
}

function PillToggle({ active, onClick, label, color }) {
  return (
    <button
      onClick={onClick}
      className="text-[11px] px-2.5 py-1 rounded-full transition-all"
      style={{
        background: active ? (color || 'var(--accent)') : 'var(--bg-2)',
        color:      active ? '#000' : 'var(--fg-2)',
        border:     `1px solid ${active ? (color || 'var(--accent)') : 'var(--border)'}`,
        fontWeight: active ? 600 : 500,
      }}
    >
      {label}
    </button>
  );
}

function ViewBtn({ active, onClick, icon: Icon, children }) {
  return (
    <button
      onClick={onClick}
      className="text-[11px] px-2 py-1.5 flex items-center gap-1"
      style={{
        background: active ? 'var(--accent-soft)' : 'transparent',
        color:      active ? 'var(--accent)' : 'var(--fg-2)',
        fontWeight: active ? 600 : 500,
      }}
    >
      <Icon className="w-3 h-3" /> {children}
    </button>
  );
}

function CollapsibleSection({ open, onToggle, title, subtitle, icon: Icon, accent, children }) {
  return (
    <section className="rounded-2xl border" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
      <button
        onClick={onToggle}
        className="w-full px-5 py-3 flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ background: 'var(--bg-2)' }}>
            <Icon className="w-4 h-4" style={{ color: accent }} />
          </div>
          <div>
            <div className="text-sm font-semibold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
              {title}
            </div>
            <div className="text-[11px]" style={{ color: 'var(--fg-3)' }}>{subtitle}</div>
          </div>
        </div>
        {open ? <ChevronUp className="w-4 h-4" style={{ color: 'var(--fg-3)' }} />
              : <ChevronDown className="w-4 h-4" style={{ color: 'var(--fg-3)' }} />}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function RunCard({ run, index, onOpen }) {
  const presentTypes = TYPE_KEYS.filter(k => run.insights[k]);
  const [activeTab, setActiveTab] = useState(presentTypes[0] || null);
  const active = activeTab && run.insights[activeTab];
  const ts = run.created_at ? new Date(run.created_at) : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02 }}
      className="card card-hover flex flex-col"
      style={{
        borderLeft: run.max_priority === 'HIGH'   ? '3px solid var(--danger)'
                  : run.max_priority === 'MEDIUM' ? '3px solid var(--warning)'
                  : '3px solid transparent',
      }}
    >
      {/* header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          {/* Scope chip + km — tells you at a glance whether this card is the
              whole trip or just one segment. */}
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded"
              style={{
                background: run.scope === 'segment' ? 'var(--accent-soft)' : 'var(--bg-2)',
                color:      run.scope === 'segment' ? 'var(--accent)'      : 'var(--fg-2)',
              }}
              title={run.scope === 'segment'
                ? `Segment #${run.segment_seq ?? '?'} of the parent trip`
                : 'Whole-trip analysis run'}
            >
              {run.scope === 'segment'
                ? `Segment ${run.segment_seq ? `#${run.segment_seq}` : ''}`
                : 'Whole trip'}
            </span>
            {(run.scope === 'segment' ? run.segment_distance : run.trip_distance) && (
              <span className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
                {(run.scope === 'segment' ? run.segment_distance : run.trip_distance).toFixed(1)} km
              </span>
            )}
          </div>
          {/* PRIMARY label: the actual scope of this run (segment route or trip route). */}
          <div className="text-xs font-bold truncate" style={{ color: 'var(--fg-1)' }}>
            <span className="mono mr-1">{run.vehicle_id}</span>
            <span>{run.from_waypoint || '—'} → {run.to_waypoint || '—'}</span>
          </div>
          {/* When segment-scoped, surface the parent trip context underneath. */}
          {run.scope === 'segment' && (run.parent_trip_from || run.parent_trip_to) && (
            <div className="text-[10px] mt-0.5 truncate" style={{ color: 'var(--fg-3)' }}>
              part of <span style={{ color: 'var(--fg-2)' }}>{run.parent_trip_from} → {run.parent_trip_to}</span>
            </div>
          )}
          <div className="text-[10px] mono mt-0.5" style={{ color: 'var(--fg-3)' }}>
            {ts ? ts.toLocaleString() : ''} · model: <span style={{ color: 'var(--fg-2)' }}>{run.model}</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {run.max_priority && (
            <span className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded"
              style={{
                background: run.max_priority === 'HIGH' ? 'var(--danger)' : 'var(--warning)',
                color: '#000',
              }}>
              {run.max_priority}
            </span>
          )}
          {run.total_monthly_savings > 0 && (
            <span className="text-[10px] mono font-bold" style={{ color: 'var(--success)' }}>
              ₹{run.total_monthly_savings.toLocaleString('en-IN')}/mo
            </span>
          )}
        </div>
      </div>

      {/* tabs */}
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        {presentTypes.map(k => {
          const meta = TYPE_META[k];
          const TabIcon = meta.icon;
          const on = activeTab === k;
          return (
            <button
              key={k} onClick={() => setActiveTab(k)}
              className="text-[10px] px-2 py-1 rounded flex items-center gap-1 transition-all"
              style={{
                background: on ? meta.color : 'var(--bg-2)',
                color:      on ? '#000' : 'var(--fg-2)',
                fontWeight: on ? 700 : 500,
              }}
              title={meta.label}
            >
              <TabIcon className="w-3 h-3" /> {meta.label}
            </button>
          );
        })}
      </div>

      {/* body */}
      <div className="flex-1">
        {active ? (
          <p className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--fg-2)' }}>
            {active.text}
          </p>
        ) : (
          <div className="text-[11px]" style={{ color: 'var(--fg-3)' }}>No insight selected.</div>
        )}
      </div>

      {/* footer */}
      <div className="flex items-center justify-end mt-3">
        {run.trip_id && (
          <button onClick={onOpen} className="text-[11px] font-semibold flex items-center gap-1"
            style={{ color: 'var(--accent)' }}>
            Open trip <ArrowRight className="w-3 h-3" />
          </button>
        )}
      </div>
    </motion.div>
  );
}

function FlatInsightCard({ r, index, onOpen }) {
  const meta = TYPE_META[r.insight_type] || { label: r.insight_type, icon: Sparkles, color: 'var(--accent)' };
  const TypeIcon = meta.icon;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.015 }}
      className="card card-hover"
      style={{ borderLeft: `3px solid ${meta.color}` }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <TypeIcon className="w-3.5 h-3.5" style={{ color: meta.color }} />
          <div className="text-[10px] uppercase tracking-[0.15em] font-semibold" style={{ color: meta.color }}>
            {meta.label}
          </div>
        </div>
        <div className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>
          {new Date(r.created_at).toLocaleString()}
        </div>
      </div>
      {r.from_waypoint && (
        <div className="text-xs font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>
          <span className="mono">{r.vehicle_id}</span> · {r.from_waypoint} → {r.to_waypoint}
        </div>
      )}
      <p className="text-xs leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--fg-2)' }}>
        {r.text}
      </p>
      <div className="flex items-center justify-between mt-3">
        <span className="text-[10px] mono" style={{ color: 'var(--fg-3)' }}>{r.model}</span>
        {r.trip_id && (
          <button onClick={onOpen} className="text-[11px] font-semibold flex items-center gap-1"
            style={{ color: 'var(--accent)' }}>
            Open <ArrowRight className="w-3 h-3" />
          </button>
        )}
      </div>
    </motion.div>
  );
}
