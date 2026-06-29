import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles, RefreshCw, Filter, ArrowRight, Loader2 } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import { riListInsights } from '../lib/api';

const TYPES = [
  { key: '', label: 'All' },
  { key: 'trip_summary', label: 'Trip Summary' },
  { key: 'cost_advice', label: 'Cost Advice' },
  { key: 'route_quality', label: 'Route Quality' },
  { key: 'traffic_callout', label: 'Traffic' },
  { key: 'recommendations_list', label: 'Recommendations' },
  { key: 'comparison_verdict', label: 'Verdicts' },
];

export default function RouteIntelligenceInsights() {
  const nav = useNavigate();
  const [type, setType] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    riListInsights(80, type || undefined)
      .then((r) => setRows(r.insights))
      .finally(() => setLoading(false));
  };
  useEffect(load, [type]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Insights Feed"
        subtitle="Every natural-language paragraph the route-intel pipeline has produced"
      />

      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-3.5 h-3.5" style={{ color: 'var(--fg-3)' }} />
        {TYPES.map((t) => (
          <button key={t.key}
            onClick={() => setType(t.key)}
            className="px-2.5 py-1 rounded text-[11px] font-semibold"
            style={{
              background: type === t.key ? 'var(--accent)' : 'var(--bg-2)',
              color: type === t.key ? '#000' : 'var(--fg-2)',
            }}>{t.label}</button>
        ))}
        <button onClick={load} className="text-xs flex items-center gap-1 ml-auto"
          style={{ color: 'var(--accent)' }}>
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {loading && (
        <div className="card text-xs flex items-center gap-2" style={{ color: 'var(--fg-3)' }}>
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
        </div>
      )}

      {!loading && rows.length === 0 && (
        <div className="card text-sm" style={{ color: 'var(--fg-3)' }}>
          No insights yet — analyze some trips first.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {rows.map((r, i) => (
          <motion.div key={r.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.02 }} className="card card-hover">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
                <div className="text-[10px] uppercase tracking-wider font-semibold"
                  style={{ color: 'var(--accent)' }}>{r.insight_type}</div>
              </div>
              <div className="text-[10px]" style={{ color: 'var(--fg-3)' }}>
                {new Date(r.created_at).toLocaleString()}
              </div>
            </div>
            {r.from_waypoint && (
              <div className="text-xs font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>
                {r.vehicle_id} · #{r.trip_seq} {r.from_waypoint} → {r.to_waypoint}
              </div>
            )}
            <p className="text-xs leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--fg-2)' }}>{r.text}</p>
            <div className="flex items-center justify-between mt-3">
              <span className="text-[10px]" style={{ color: 'var(--fg-3)' }}>
                {r.model}
              </span>
              {r.trip_id && (
                <button onClick={() => nav(`/route-intel/trips/${r.trip_id}`)}
                  className="text-[11px] font-semibold flex items-center gap-1"
                  style={{ color: 'var(--accent)' }}>
                  Open <ArrowRight className="w-3 h-3" />
                </button>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
