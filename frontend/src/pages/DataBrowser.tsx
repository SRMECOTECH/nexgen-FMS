import { useState } from 'react';
import { Play } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import { runQuery } from '../lib/api';

const SAMPLE_QUERIES = [
  'SELECT * FROM telemetry.fact_trips LIMIT 50',
  'SELECT * FROM telemetry.fact_trip_legs LIMIT 50',
  'SELECT * FROM telemetry.gps_telemetry_events LIMIT 100',
  'SELECT * FROM telemetry.gps_events LIMIT 100',
  'SELECT * FROM telemetry.trip_detail LIMIT 100',
  'SELECT * FROM telemetry.trip_header LIMIT 50',
];

export default function DataBrowser() {
  const [sql, setSql] = useState(SAMPLE_QUERIES[0]);
  const [result, setResult] = useState<{ columns: string[]; rows: unknown[][]; error?: string; row_count?: number } | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try { setResult(await runQuery(sql)); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Data Browser" subtitle="Ad-hoc SELECT queries against the lakehouse (via ClickHouse gateway)." />

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-3 card h-fit">
          <div className="text-xs uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--fg-3)' }}>
            Saved snippets
          </div>
          <div className="space-y-1">
            {SAMPLE_QUERIES.map((q, i) => (
              <button key={i} onClick={() => setSql(q)}
                className="w-full text-left text-xs font-mono px-2 py-2 rounded hover:bg-[var(--bg-2)]"
                style={{ color: 'var(--fg-2)' }}>
                {q.replace(/SELECT.*FROM\s+/i, '').replace(/\s+LIMIT.*/i, '')}
              </button>
            ))}
          </div>
        </div>

        <div className="col-span-12 lg:col-span-9 space-y-4">
          <div className="card">
            <textarea
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              rows={5}
              className="w-full font-mono text-sm p-3 rounded outline-none resize-y"
              style={{ background: 'var(--bg-0)', color: 'var(--fg-1)', border: '1px solid var(--border)' }}
              spellCheck={false}
            />
            <div className="flex items-center justify-between mt-3">
              <div className="text-xs" style={{ color: 'var(--fg-3)' }}>
                Only SELECT statements are allowed.
              </div>
              <button onClick={run} disabled={busy}
                className="btn-primary flex items-center gap-2 disabled:opacity-50">
                <Play className="w-4 h-4" />
                {busy ? 'Running...' : 'Run query'}
              </button>
            </div>
          </div>

          {result && (
            <div className="card p-0 overflow-auto">
              {result.error ? (
                <div className="p-4 text-sm" style={{ color: 'var(--danger)' }}>
                  {result.error}
                </div>
              ) : (
                <>
                  <table className="w-full text-xs">
                    <thead>
                      <tr style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
                        {result.columns.slice(0, 12).map(c => (
                          <th key={c} className="px-3 py-2 text-left font-mono whitespace-nowrap">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody style={{ color: 'var(--fg-2)' }}>
                      {result.rows.map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                          {(row as unknown[]).slice(0, 12).map((cell, j) => (
                            <td key={j} className="px-3 py-2 font-mono whitespace-nowrap max-w-[180px] truncate">
                              {String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="px-3 py-2 text-[10px]" style={{ color: 'var(--fg-3)' }}>
                    {result.rows.length} rows shown {result.row_count ? `of ${result.row_count} total` : ''}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
