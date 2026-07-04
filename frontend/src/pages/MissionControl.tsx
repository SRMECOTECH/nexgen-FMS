import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, Compass, Sparkles, TrendingUp, TrendingDown, Minus,
  ShieldCheck, AlertTriangle, Activity, X, ChevronRight,
  Wand2, RefreshCw, Loader2,
} from 'lucide-react';
import {
  aiMissionControl, aiCards, aiExplain, riListInsights,
  type MissionControlSummary, type AiCard,
} from '../lib/api';

// ============================================================================
// Mission Control — the landing page of the AI-OS.
//
// Layout (top → bottom):
//   1. Greeting card     — AI narrative ("Good morning. AI analysed N…")
//   2. AI Cards row      — Fleet Stability · ETA Confidence · Risk Index · AI Confidence
//                          each click opens the Why? drawer
//   3. Live signals row  — the supporting numbers behind the narrative
//
// Every number on this page is sourced from /api/v1/ai/* which in turn
// composes /api/v1/ml/* (proxied to smart-truck). Nothing is faked client-side.
// ============================================================================

const riskColor: Record<MissionControlSummary['operational_risk'], string> = {
  LOW:    'var(--success)',
  MEDIUM: 'var(--warning)',
  HIGH:   'var(--danger)',
};

const trendIcon = { up: TrendingUp, down: TrendingDown, flat: Minus } as const;
const trendColor = { up: 'var(--success)', down: 'var(--danger)', flat: 'var(--fg-3)' };

export default function MissionControl() {
  const [summary, setSummary]   = useState<MissionControlSummary | null>(null);
  const [cards, setCards]       = useState<AiCard[] | null>(null);
  const [openCard, setOpenCard] = useState<AiCard | null>(null);
  const [explain, setExplain]   = useState<any>(null);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [s, c] = await Promise.all([aiMissionControl(), aiCards()]);
        if (!live) return;
        setSummary(s);
        setCards(c.cards);
      } catch (e: any) {
        if (!live) return;
        setError(e?.response?.data?.detail ?? e?.message ?? 'Failed to reach AI composer');
      }
    })();
    return () => { live = false; };
  }, []);

  async function onOpen(card: AiCard) {
    setOpenCard(card); setExplain(null);
    try { setExplain(await aiExplain(card.id)); }
    catch (e: any) { setExplain({ error: e?.message ?? 'failed' }); }
  }

  return (
    <div className="space-y-6">
      {/* ============================================================== */}
      {/* 1) Greeting & narrative                                         */}
      {/* ============================================================== */}
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="rounded-2xl p-6 border"
        style={{
          background:
            'radial-gradient(1200px 200px at 0% 0%, var(--accent-soft), transparent), var(--bg-3)',
          borderColor: 'var(--border)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--accent)' }}>
          <Compass className="w-4 h-4" />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">Mission Control</span>
        </div>

        {error ? (
          <ErrorBanner message={error} />
        ) : !summary ? (
          <SkeletonNarrative />
        ) : (
          <>
            <h1
              className="text-3xl font-bold mb-2"
              style={{ fontFamily: 'var(--font-display)', color: 'var(--fg-1)' }}
            >
              {summary.greeting}
            </h1>
            <div className="flex items-center gap-3 mb-4">
              <RiskPill risk={summary.operational_risk} />
              <span className="text-xs mono" style={{ color: 'var(--fg-3)' }}>
                generated {new Date(summary.generated_at).toLocaleTimeString()}
              </span>
            </div>

            <div className="grid md:grid-cols-2 gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.15em] mb-2" style={{ color: 'var(--fg-3)' }}>
                  AI detected
                </div>
                <ul className="space-y-1.5">
                  {summary.bullets.length === 0 && (
                    <li className="text-sm" style={{ color: 'var(--fg-3)' }}>
                      No significant events in the last 24h.
                    </li>
                  )}
                  {summary.bullets.map((b, i) => (
                    <motion.li
                      key={i}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.1 + i * 0.05 }}
                      className="text-sm flex items-start gap-2"
                      style={{ color: 'var(--fg-2)' }}
                    >
                      <Sparkles className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
                      {b}
                    </motion.li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-[0.15em] mb-2" style={{ color: 'var(--fg-3)' }}>
                  Model status
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {Object.entries(summary.sources).map(([name, status]) => {
                    const dot =
                      status === 'ok'    ? 'var(--success)' :
                      status === 'dummy' ? 'var(--warning)' :
                                           'var(--fg-4)';
                    return (
                      <div
                        key={name}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs"
                        style={{ background: 'var(--bg-2)', color: 'var(--fg-2)' }}
                        title={status === 'dummy' ? 'Model slow/unavailable — showing placeholder data' : status}
                      >
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: dot }} />
                        <span className="capitalize">{name.replace(/_/g, ' ')}</span>
                        {status === 'dummy' && (
                          <span
                            className="ml-auto text-[9px] uppercase tracking-wider"
                            style={{ color: 'var(--warning)' }}
                          >demo</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </>
        )}
      </motion.section>

      {/* ============================================================== */}
      {/* 2) AI Cards                                                     */}
      {/* ============================================================== */}
      <section>
        <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--fg-3)' }}>
          <Brain className="w-4 h-4" />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">AI Cards · click for evidence</span>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {!cards
            ? Array.from({ length: 4 }).map((_, i) => <CardSkeleton key={i} />)
            : cards.map((c, idx) => <Card key={c.id} card={c} delay={idx * 0.05} onClick={() => onOpen(c)} />)}
        </div>
      </section>

      {/* ============================================================== */}
      {/* 3) Live signals — supporting numbers behind the narrative       */}
      {/* ============================================================== */}
      {summary && (
        <section
          className="rounded-2xl p-5 border"
          style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center gap-2 mb-3" style={{ color: 'var(--fg-3)' }}>
            <Activity className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">Live signals</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <Signal label="Drivers scanned"    value={summary.signals.drivers_scanned} />
            <Signal label="At-risk drivers"    value={summary.signals.drivers_at_risk} accent="danger" />
            <Signal label="Avg driver score"   value={summary.signals.fleet_avg_driver_score} suffix=" / 100" />
            <Signal label="Fatigued"           value={summary.signals.fatigued_drivers} accent="warning" />
            <Signal label="Anomaly flagged"    value={summary.signals.anomaly_events_flagged} accent="prediction" />
            <Signal label="Trips forecast 7d"  value={summary.signals.upcoming_trips_forecast} />
          </div>
        </section>
      )}

      {/* ============================================================== */}
      {/* 4) Latest AI insights — generated on demand, straight from the  */}
      {/*    ri_ai_insights table (Gemini via LangChain, or templates).   */}
      {/* ============================================================== */}
      <InsightsFeed />

      {/* ============================================================== */}
      {/* Why? drawer                                                     */}
      {/* ============================================================== */}
      <AnimatePresence>
        {openCard && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex justify-end"
            style={{ background: 'rgba(0,0,0,0.45)' }}
            onClick={() => setOpenCard(null)}
          >
            <motion.aside
              initial={{ x: 420 }} animate={{ x: 0 }} exit={{ x: 420 }}
              transition={{ type: 'spring', damping: 26, stiffness: 220 }}
              className="w-[420px] h-full overflow-y-auto p-6 border-l"
              style={{ background: 'var(--bg-4)', borderColor: 'var(--border)' }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--accent)' }}>
                    Why?
                  </div>
                  <h2 className="text-xl font-bold" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
                    {openCard.title}
                  </h2>
                </div>
                <button
                  onClick={() => setOpenCard(null)}
                  className="p-1 rounded-md hover:bg-[var(--bg-2)]"
                  style={{ color: 'var(--fg-2)' }}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {!explain ? <CardSkeleton inDrawer /> : (
                <pre
                  className="text-xs p-3 rounded-lg overflow-auto"
                  style={{ background: 'var(--bg-2)', color: 'var(--fg-2)', fontFamily: 'var(--font-mono)' }}
                >{JSON.stringify(explain, null, 2)}</pre>
              )}
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ----------------------------------------------------------------------------
// sub-components
// ----------------------------------------------------------------------------

function RiskPill({ risk }: { risk: MissionControlSummary['operational_risk'] }) {
  const Icon = risk === 'HIGH' ? AlertTriangle : risk === 'LOW' ? ShieldCheck : Activity;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wide"
      style={{ background: 'var(--bg-2)', color: riskColor[risk], border: `1px solid ${riskColor[risk]}` }}
    >
      <Icon className="w-3 h-3" />
      Risk · {risk}
    </span>
  );
}

function Card({ card, delay, onClick }: { card: AiCard; delay: number; onClick: () => void }) {
  const Icon = trendIcon[card.trend];
  return (
    <motion.button
      onClick={onClick}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.35 }}
      whileHover={{ y: -2 }}
      className="text-left rounded-2xl p-5 border transition-shadow"
      style={{
        background: 'var(--bg-3)',
        borderColor: 'var(--border)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] uppercase tracking-[0.15em]" style={{ color: 'var(--fg-3)' }}>
          {card.title}
        </span>
        <Icon className="w-3.5 h-3.5" style={{ color: trendColor[card.trend] }} />
      </div>
      <div
        className="text-3xl font-bold mb-1"
        style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
      >
        {card.value_pct.toFixed(1)}<span className="text-base" style={{ color: 'var(--fg-3)' }}>%</span>
      </div>
      <div className="text-xs mb-2" style={{ color: 'var(--fg-3)' }}>
        Confidence {card.confidence_pct}%
      </div>
      <div className="text-[11px] leading-snug" style={{ color: 'var(--fg-2)' }}>
        {card.blurb}
      </div>
      <div
        className="mt-3 flex items-center gap-1 text-[11px] font-semibold"
        style={{ color: 'var(--accent)' }}
      >
        Why? <ChevronRight className="w-3 h-3" />
      </div>
    </motion.button>
  );
}

function Signal({
  label, value, suffix, accent,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  accent?: 'danger' | 'warning' | 'prediction';
}) {
  const color =
    accent === 'danger' ? 'var(--danger)' :
    accent === 'warning' ? 'var(--warning)' :
    accent === 'prediction' ? 'var(--prediction)' :
    'var(--fg-1)';
  return (
    <div className="rounded-lg p-3" style={{ background: 'var(--bg-2)' }}>
      <div className="text-[10px] uppercase tracking-[0.15em] mb-1" style={{ color: 'var(--fg-3)' }}>
        {label}
      </div>
      <div className="text-xl font-bold mono" style={{ color }}>
        {value ?? '—'}{value != null && suffix ? suffix : ''}
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg p-4 text-sm flex items-start gap-2"
      style={{ background: 'rgba(255,77,109,0.08)', border: '1px solid var(--danger)', color: 'var(--fg-1)' }}
    >
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: 'var(--danger)' }} />
      <div>
        <div className="font-semibold mb-1">AI composer is offline.</div>
        <div className="text-xs" style={{ color: 'var(--fg-2)' }}>{message}</div>
        <div className="text-[11px] mt-2" style={{ color: 'var(--fg-3)' }}>
          Most likely the smart-truck ml_service is not running on <code className="mono">localhost:8001</code>,
          or <code className="mono">ML_API_KEY</code> in <code className="mono">.env</code> is not a valid
          subscription key. See <code className="mono">docs/API_REFERENCE.md</code>.
        </div>
      </div>
    </div>
  );
}

function SkeletonNarrative() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-7 w-2/3 rounded" style={{ background: 'var(--bg-2)' }} />
      <div className="h-4 w-1/3 rounded" style={{ background: 'var(--bg-2)' }} />
      <div className="h-3 w-full rounded mt-4" style={{ background: 'var(--bg-2)' }} />
      <div className="h-3 w-5/6 rounded" style={{ background: 'var(--bg-2)' }} />
    </div>
  );
}

function CardSkeleton({ inDrawer = false }: { inDrawer?: boolean }) {
  return (
    <div
      className={`rounded-2xl p-5 border animate-pulse ${inDrawer ? '' : ''}`}
      style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
    >
      <div className="h-3 w-1/2 rounded mb-3" style={{ background: 'var(--bg-2)' }} />
      <div className="h-8 w-1/3 rounded mb-2" style={{ background: 'var(--bg-2)' }} />
      <div className="h-3 w-full rounded" style={{ background: 'var(--bg-2)' }} />
    </div>
  );
}

// ============================================================================
// Latest AI insights feed — the newest rows from ri_ai_insights, shown right
// on Mission Control so the "AI gives you something" is visible on landing.
// Rows written by Gemini get a glowing badge; template fallbacks are grey.
// Generation stays on-demand: open a trip → "Regenerate AI" adds rows here.
// ============================================================================
interface FeedRow {
  id: number; insight_type: string; text: string; model: string;
  created_at: string; trip_id: number | null;
  from_waypoint: string | null; to_waypoint: string | null;
  vehicle_id: string | null;
}

const TYPE_LABEL: Record<string, string> = {
  trip_summary: 'Trip summary',
  cost_advice: 'Cost advice',
  route_quality: 'Route quality',
  traffic_callout: 'Traffic',
  recommendations_list: 'Recommendations',
  comparison_verdict: 'Comparison',
};

function InsightsFeed() {
  const [rows, setRows]       = useState<FeedRow[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const d = await riListInsights(8);
      setRows(d.insights ?? []);
    } catch { setRows([]); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <section
      className="rounded-2xl p-5 border"
      style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
          <Wand2 className="w-4 h-4" style={{ color: 'var(--accent)' }} />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">
            Latest AI insights · generated on demand
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-semibold border transition-all hover:bg-[var(--bg-2)]"
            style={{ borderColor: 'var(--border)', color: 'var(--fg-2)' }}
          >
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            Refresh
          </button>
          <Link
            to="/route-intel/insights"
            className="flex items-center gap-1 text-[11px] font-semibold"
            style={{ color: 'var(--accent)' }}
          >
            Full feed <ChevronRight className="w-3 h-3" />
          </Link>
        </div>
      </div>

      {!rows ? (
        <div className="h-16 rounded-lg animate-pulse" style={{ background: 'var(--bg-2)' }} />
      ) : rows.length === 0 ? (
        <div className="text-sm py-4 text-center" style={{ color: 'var(--fg-3)' }}>
          No AI insights yet — open a trip in <Link to="/route-intel" style={{ color: 'var(--accent)' }}>Route
          Intelligence</Link> and click <b>Regenerate AI</b>.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {rows.map((r) => {
            const isLlm = (r.model || '').startsWith('gemini') && !(r.model || '').includes('rule-fallback');
            const tripLabel = r.from_waypoint || r.to_waypoint
              ? `${r.from_waypoint ?? '—'} → ${r.to_waypoint ?? '—'}`
              : r.vehicle_id ?? '';
            return (
              <Link
                key={r.id}
                to={r.trip_id ? `/route-intel/trips/${r.trip_id}` : '/route-intel/insights'}
                className="rounded-xl p-4 border block transition-all hover:border-[var(--accent)]"
                style={{ background: 'var(--bg-2)', borderColor: 'var(--border)' }}
              >
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider"
                    style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
                  >
                    {TYPE_LABEL[r.insight_type] ?? r.insight_type}
                  </span>
                  {tripLabel && (
                    <span className="text-[11px] mono truncate" style={{ color: 'var(--fg-3)' }}>{tripLabel}</span>
                  )}
                  <span
                    className="ml-auto flex items-center gap-1 text-[10px] font-semibold"
                    style={{ color: isLlm ? 'var(--success)' : 'var(--fg-4)' }}
                    title={r.model}
                  >
                    <Sparkles className="w-3 h-3" />
                    {isLlm ? 'Gemini AI' : 'template'}
                  </span>
                </div>
                <p
                  className="text-xs leading-relaxed"
                  style={{
                    color: 'var(--fg-2)',
                    display: '-webkit-box', WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical', overflow: 'hidden',
                  }}
                >
                  {r.text}
                </p>
                <div className="text-[10px] mono mt-2" style={{ color: 'var(--fg-4)' }}>
                  {new Date(r.created_at).toLocaleString()}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
