import { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Database } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { fetchDataQuality, type DataQuality, type ColumnHealth } from '../lib/api';

const statusColor: Record<string, string> = {
  ok:      'var(--success)',
  partial: 'var(--info)',
  zero:    'var(--warning)',
  sparse:  'var(--warning)',
  missing: 'var(--danger)',
};

const verdictBadge: Record<string, { color: string; bg: string }> = {
  'READY':                  { color: 'var(--success)', bg: 'rgba(34,197,94,0.15)' },
  'MOSTLY READY':           { color: 'var(--info)',    bg: 'rgba(56,189,248,0.15)' },
  'DEGRADED (zeros)':       { color: 'var(--warning)', bg: 'rgba(250,204,21,0.15)' },
  'BLOCKED — sparse':       { color: 'var(--warning)', bg: 'rgba(250,204,21,0.15)' },
  'BLOCKED — missing column':{ color: 'var(--danger)',  bg: 'rgba(239,68,68,0.15)' },
};

export default function DataQuality() {
  const [data, setData] = useState<DataQuality | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setData(await fetchDataQuality()); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  if (loading && !data) return <Spinner />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <PageHeader title="Data Quality" subtitle="What's actually populated in the lakehouse — and which models that blocks."
        onRefresh={load} refreshing={loading} />

      {/* Feature readiness — the punchline */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--fg-2)' }}>
          Feature Readiness
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.feature_readiness.map(f => {
            const badge = verdictBadge[f.verdict] ?? { color: 'var(--fg-2)', bg: 'var(--bg-2)' };
            const isReady = f.verdict === 'READY' || f.verdict === 'MOSTLY READY';
            return (
              <div key={f.feature} className="card flex items-start gap-3">
                {isReady
                  ? <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0" style={{ color: 'var(--success)' }} />
                  : <XCircle className="w-5 h-5 mt-0.5 shrink-0" style={{ color: 'var(--danger)' }} />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold text-sm">{f.feature}</div>
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
                          style={{ color: badge.color, background: badge.bg }}>{f.verdict}</span>
                  </div>
                  {!isReady && f.blocking_columns.length > 0 && (
                    <div className="text-xs mt-1" style={{ color: 'var(--fg-3)' }}>
                      blocked by: {f.blocking_columns.map(c => (
                        <code key={c} className="font-mono mx-1" style={{ color: 'var(--danger)' }}>{c}</code>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Per-table summary */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--fg-2)' }}>
          Per-table column health
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.tables_summary.map(t => {
            const totalNonOk = t.total - t.ok;
            return (
              <div key={t.table} className="card">
                <div className="flex items-center gap-2 mb-3">
                  <Database className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                  <h3 className="font-mono font-semibold">{t.table}</h3>
                  <span className="chip ml-auto">{t.total} cols</span>
                </div>
                <BarRow label="OK"      count={t.ok}      total={t.total} color="var(--success)" />
                <BarRow label="Partial" count={t.partial} total={t.total} color="var(--info)" />
                <BarRow label="Zero"    count={t.zero}    total={t.total} color="var(--warning)" />
                <BarRow label="Sparse"  count={t.sparse}  total={t.total} color="var(--warning)" />
                <BarRow label="Missing" count={t.missing} total={t.total} color="var(--danger)" />
                <div className="mt-2 text-xs" style={{ color: 'var(--fg-3)' }}>
                  {totalNonOk > 0
                    ? `${totalNonOk}/${t.total} columns have data-quality issues`
                    : 'All columns populated'}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Column-level grid */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--fg-2)' }}>
          Column-level detail
        </h2>
        {(['fact_trips','fact_trip_legs','gps_telemetry_events','gps_events'] as const).map(tbl => {
          const cols = data.columns.filter(c => c.table === tbl);
          if (!cols.length) return null;
          return (
            <div key={tbl} className="mb-4">
              <div className="font-mono text-xs font-semibold mb-2" style={{ color: 'var(--accent)' }}>{tbl}</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-1.5">
                {cols.map(c => <ColumnChip key={c.column} c={c} />)}
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}

function BarRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-xs mb-1.5">
      <div className="w-16" style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="flex-1 h-2 rounded overflow-hidden" style={{ background: 'var(--bg-2)' }}>
        <div className="h-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="w-10 text-right font-mono">{count}</div>
    </div>
  );
}

function ColumnChip({ c }: { c: ColumnHealth }) {
  const color = statusColor[c.status];
  return (
    <div
      title={`${c.column} — ${c.status} (${c.null_pct}% null${c.all_zero ? ', all zero' : ''})`}
      className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-mono truncate"
      style={{ background: 'var(--bg-2)', border: `1px solid ${color}40` }}
    >
      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
      <span className="truncate" style={{ color: 'var(--fg-2)' }}>{c.column}</span>
    </div>
  );
}
