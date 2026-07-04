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
              <Emphasis text={summary.greeting} />
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

              {!explain ? <CardSkeleton inDrawer /> : <ExplainView explain={explain} />}
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

/** Render the tiny `**bold**` markdown the composer uses in its headline as
 *  real emphasis instead of literal asterisks. */
function Emphasis({ text }: { text: string }) {
  const parts = (text ?? '').split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1
          ? <span key={i} style={{ color: 'var(--accent)' }}>{p}</span>
          : <span key={i}>{p}</span>,
      )}
    </>
  );
}

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
        <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.15em]" style={{ color: 'var(--fg-3)' }}>
          {card.title}
          {card.live === false && (
            <span
              className="text-[9px] normal-case tracking-normal px-1.5 py-0.5 rounded-full font-semibold"
              style={{ background: 'var(--bg-2)', color: 'var(--warning)' }}
              title="Model offline — placeholder value, not a live reading"
            >demo</span>
          )}
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

/** Human-readable rendering of an /ai/explain payload — narrative first,
 *  then weighted contributors, then supporting evidence. No raw JSON. */
function ExplainView({ explain }: { explain: any }) {
  if (explain?.error) {
    return (
      <div className="text-xs rounded-lg p-3" style={{ background: 'var(--bg-2)', color: 'var(--danger)' }}>
        Could not load the explanation: {String(explain.error)}
      </div>
    );
  }
  const contributors: any[] = Array.isArray(explain?.contributors) ? explain.contributors : [];
  const anomalies: any[] = Array.isArray(explain?.top_anomalies) ? explain.top_anomalies : [];
  const riskDrivers: any[] = Array.isArray(explain?.top_risk_drivers) ? explain.top_risk_drivers : [];

  return (
    <div className="space-y-5">
      {explain?.narrative && (
        <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-2)' }}>{explain.narrative}</p>
      )}

      {contributors.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] mb-2" style={{ color: 'var(--fg-3)' }}>
            Contributing signals
          </div>
          <div className="space-y-2">
            {contributors.map((c, i) => (
              <div key={i} className="rounded-lg p-3" style={{ background: 'var(--bg-2)' }}>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span style={{ color: 'var(--fg-1)' }}>{c.name}</span>
                  <span className="mono" style={{ color: 'var(--fg-2)' }}>{String(c.value ?? '—')}</span>
                </div>
                <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--bg-3)' }}>
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${Math.round((c.weight ?? 0) * 100)}%`, background: 'var(--accent)' }}
                  />
                </div>
                <div className="text-[10px] mt-1" style={{ color: 'var(--fg-3)' }}>
                  weight {Math.round((c.weight ?? 0) * 100)}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {anomalies.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] mb-2" style={{ color: 'var(--fg-3)' }}>
            Top anomalies
          </div>
          <div className="space-y-1.5">
            {anomalies.map((a, i) => (
              <div key={i} className="flex items-start justify-between gap-2 text-xs p-2 rounded-lg"
                style={{ background: 'var(--bg-2)' }}>
                <div>
                  <span className="mono" style={{ color: 'var(--fg-1)' }}>trip {a.trip_id}</span>
                  <div className="text-[11px]" style={{ color: 'var(--fg-2)' }}>{a.reason}</div>
                </div>
                {a.score != null && (
                  <span className="mono text-[11px] shrink-0" style={{ color: 'var(--warning)' }}>
                    {Number(a.score).toFixed(2)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {riskDrivers.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] mb-2" style={{ color: 'var(--fg-3)' }}>
            Highest-risk drivers
          </div>
          <div className="space-y-1.5">
            {riskDrivers.map((d, i) => (
              <div key={i} className="flex items-center justify-between text-xs p-2 rounded-lg"
                style={{ background: 'var(--bg-2)' }}>
                <span style={{ color: 'var(--fg-1)' }}>{d.driver_name ?? `Driver ${d.driver_id}`}</span>
                <span className="mono" style={{ color: 'var(--danger)' }}>
                  {d.composite_score != null ? Number(d.composite_score).toFixed(2) : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!explain?.narrative && contributors.length === 0 && anomalies.length === 0 && riskDrivers.length === 0 && (
        <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
          No detailed evidence available for this card right now — the supporting
          model may be offline.
        </div>
      )}
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

function modelBadge(model: string | null): string {
  const m = (model || '').toLowerCase();
  if (m.startsWith('gemini'))    return 'Gemini AI';
  if (m.startsWith('llama-cpp')) return 'Local LLM';
  return model || 'AI';
}

function InsightsFeed() {
  const [rows, setRows]       = useState<FeedRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [openRow, setOpenRow] = useState<FeedRow | null>(null);

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
            Latest AI insights
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
            const tripLabel = r.from_waypoint || r.to_waypoint
              ? `${r.from_waypoint ?? '—'} → ${r.to_waypoint ?? '—'}`
              : r.vehicle_id ?? '';
            return (
              <button
                key={r.id}
                onClick={() => setOpenRow(r)}
                className="text-left rounded-xl p-4 border block w-full transition-all hover:border-[var(--accent)]"
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
                    style={{ color: 'var(--success)' }}
                    title={r.model}
                  >
                    <Sparkles className="w-3 h-3" />
                    {modelBadge(r.model)}
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
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] mono" style={{ color: 'var(--fg-4)' }}>
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  <span className="flex items-center gap-1 text-[11px] font-semibold" style={{ color: 'var(--accent)' }}>
                    Details <ChevronRight className="w-3 h-3" />
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <InsightModal row={openRow} onClose={() => setOpenRow(null)} />
    </section>
  );
}

/** Full-detail card shown when an insight is clicked — the complete paragraph
 *  plus its context (route, vehicle, model, timestamp) and a jump to the trip. */
function InsightModal({ row, onClose }: { row: FeedRow | null; onClose: () => void }) {
  useEffect(() => {
    if (!row) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [row, onClose]);

  return (
    <AnimatePresence>
      {row && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.55)' }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: 'spring', damping: 26, stiffness: 260 }}
            className="w-full max-w-xl rounded-2xl border overflow-hidden"
            style={{ background: 'var(--bg-4)', borderColor: 'var(--border)', boxShadow: 'var(--shadow-card)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* header */}
            <div className="px-6 pt-5 pb-4 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span
                      className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider"
                      style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
                    >
                      {TYPE_LABEL[row.insight_type] ?? row.insight_type}
                    </span>
                    <span
                      className="flex items-center gap-1 text-[10px] font-semibold"
                      style={{ color: 'var(--success)' }}
                      title={row.model}
                    >
                      <Sparkles className="w-3 h-3" /> {modelBadge(row.model)}
                    </span>
                  </div>
                  <h3
                    className="text-lg font-bold leading-tight"
                    style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
                  >
                    {row.from_waypoint || row.to_waypoint
                      ? `${row.from_waypoint ?? '—'} → ${row.to_waypoint ?? '—'}`
                      : (TYPE_LABEL[row.insight_type] ?? 'AI insight')}
                  </h3>
                </div>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-md hover:bg-[var(--bg-2)] shrink-0"
                  style={{ color: 'var(--fg-2)' }}
                  aria-label="Close"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* body */}
            <div className="px-6 py-5 max-h-[50vh] overflow-y-auto">
              <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--fg-1)' }}>
                {row.text}
              </p>
            </div>

            {/* meta + actions */}
            <div className="px-6 py-4 border-t flex items-center justify-between gap-3 flex-wrap"
              style={{ borderColor: 'var(--border)', background: 'var(--bg-3)' }}>
              <div className="text-[11px] mono space-x-3" style={{ color: 'var(--fg-3)' }}>
                {row.vehicle_id && <span>{row.vehicle_id}</span>}
                <span>{new Date(row.created_at).toLocaleString()}</span>
                <span title="generation model">{row.model}</span>
              </div>
              {row.trip_id && (
                <Link
                  to={`/route-intel/trips/${row.trip_id}`}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-md text-[11px] font-semibold"
                  style={{ background: 'var(--accent)', color: '#000' }}
                >
                  Open trip <ChevronRight className="w-3 h-3" />
                </Link>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
