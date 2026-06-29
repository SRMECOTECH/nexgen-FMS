import { useEffect, useState } from 'react';
import { Database, Columns3, Eye } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { api, fetchCatalogTables, type CatalogTable } from '../lib/api';

interface SchemaField { position: number; name: string; type: string; required: boolean }

export default function DataCatalog() {
  const [tables, setTables] = useState<CatalogTable[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<'schema' | 'sample'>('schema');
  const [schema, setSchema] = useState<SchemaField[]>([]);
  const [sample, setSample] = useState<{ columns: string[]; rows: Record<string, string>[] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCatalogTables().then(r => {
      setTables(r.tables);
      if (r.tables[0]) setSelected(r.tables[0].name);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    if (tab === 'schema') {
      api.get(`/data/catalog/${selected}/schema`).then(r => setSchema(r.data.fields));
    } else {
      api.get(`/data/catalog/${selected}/sample`).then(r => setSample({ columns: r.data.columns, rows: r.data.rows }));
    }
  }, [selected, tab]);

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <PageHeader title="Data Catalog"
        subtitle="Discover Iceberg tables exposed by the neXgen-Lakehouse. Read-only." />

      <div className="grid grid-cols-12 gap-6">
        {/* Tables list */}
        <div className="col-span-12 md:col-span-4 lg:col-span-3 card p-2 h-fit">
          <div className="text-xs uppercase tracking-wider font-semibold px-3 py-2"
               style={{ color: 'var(--fg-3)' }}>
            telemetry · {tables.length}
          </div>
          <div className="space-y-0.5">
            {tables.map(t => (
              <button key={t.name}
                onClick={() => setSelected(t.name)}
                className="w-full text-left flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-all"
                style={{
                  background: selected === t.name ? 'var(--accent-soft)' : 'transparent',
                  color: selected === t.name ? 'var(--accent)' : 'var(--fg-2)',
                  borderLeft: selected === t.name ? '3px solid var(--accent)' : '3px solid transparent',
                }}>
                <Database className="w-3.5 h-3.5" />
                <span className="font-mono text-xs">{t.name}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Detail */}
        <div className="col-span-12 md:col-span-8 lg:col-span-9 space-y-4">
          {selected && (() => {
            const t = tables.find(x => x.name === selected);
            return (
              <>
                <div className="card">
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div>
                      <div className="text-xs" style={{ color: 'var(--fg-3)' }}>telemetry</div>
                      <h2 className="text-lg font-bold font-mono">{t?.name}</h2>
                    </div>
                    <div className="flex gap-4 text-xs">
                      <Stat label="Rows ~" value={t?.rows_estimate.toLocaleString() ?? '-'} />
                      <Stat label="Size" value={`${t?.size_mb} MB`} />
                      <Stat label="Cols" value={String(t?.required_cols)} />
                      <Stat label="Updated" value={t ? new Date(t.last_updated).toLocaleTimeString() : '-'} />
                    </div>
                  </div>

                  <div className="flex gap-1 mt-4 border-b" style={{ borderColor: 'var(--border)' }}>
                    <Tab active={tab === 'schema'} onClick={() => setTab('schema')} icon={Columns3}>Schema</Tab>
                    <Tab active={tab === 'sample'} onClick={() => setTab('sample')} icon={Eye}>Sample</Tab>
                  </div>
                </div>

                {tab === 'schema' && (
                  <div className="card p-0 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-xs uppercase tracking-wider"
                            style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
                          <th className="px-4 py-3">#</th>
                          <th className="px-4 py-3">Field</th>
                          <th className="px-4 py-3">Type</th>
                          <th className="px-4 py-3">Required</th>
                        </tr>
                      </thead>
                      <tbody style={{ color: 'var(--fg-2)' }}>
                        {schema.map(f => (
                          <tr key={f.position} className="hover:bg-[var(--bg-2)]"
                              style={{ borderBottom: '1px solid var(--border)' }}>
                            <td className="px-4 py-2 font-mono text-xs" style={{ color: 'var(--fg-3)' }}>{f.position}</td>
                            <td className="px-4 py-2 font-mono">{f.name}</td>
                            <td className="px-4 py-2"><span className="chip chip-accent">{f.type}</span></td>
                            <td className="px-4 py-2 text-xs">{f.required ? 'yes' : 'no'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {tab === 'sample' && sample && (
                  <div className="card p-0 overflow-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
                          {sample.columns.slice(0, 8).map(c => (
                            <th key={c} className="px-3 py-2 text-left font-mono whitespace-nowrap">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody style={{ color: 'var(--fg-2)' }}>
                        {sample.rows.map((row, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                            {sample.columns.slice(0, 8).map(c => (
                              <td key={c} className="px-3 py-2 font-mono whitespace-nowrap max-w-[180px] truncate">
                                {row[c]}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="px-3 py-2 text-[10px]" style={{ color: 'var(--fg-3)' }}>
                      Showing first 8 of {sample.columns.length} columns · 10 rows
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--fg-3)' }}>{label}</div>
      <div className="font-semibold" style={{ color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}

function Tab({ active, onClick, icon: Icon, children }: { active: boolean; onClick: () => void; icon: typeof Eye; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors"
      style={{
        color: active ? 'var(--accent)' : 'var(--fg-3)',
        borderColor: active ? 'var(--accent)' : 'transparent',
      }}>
      <Icon className="w-4 h-4" />
      {children}
    </button>
  );
}
