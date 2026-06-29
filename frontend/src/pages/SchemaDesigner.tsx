import { useEffect, useState } from 'react';
import { FileSearch } from 'lucide-react';
import PageHeader from '../components/ui/PageHeader';
import Spinner from '../components/ui/Spinner';
import { fetchCatalogTables, type CatalogTable, api } from '../lib/api';

interface SchemaField { position: number; name: string; type: string; required: boolean }

export default function SchemaDesigner() {
  const [tables, setTables] = useState<CatalogTable[]>([]);
  const [schemas, setSchemas] = useState<Record<string, SchemaField[]>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCatalogTables().then(async (r) => {
      setTables(r.tables);
      const results: Record<string, SchemaField[]> = {};
      await Promise.all(r.tables.map(async t => {
        const s = await api.get(`/data/catalog/${t.name}/schema`);
        results[t.name] = s.data.fields;
      }));
      setSchemas(results);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <PageHeader title="Schema Browser" subtitle="Field-level view of every Iceberg table in the telemetry namespace." />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {tables.map(t => {
          const fields = schemas[t.name] ?? [];
          return (
            <div key={t.name} className="card">
              <div className="flex items-center gap-2 mb-3">
                <FileSearch className="w-4 h-4" style={{ color: 'var(--accent)' }} />
                <h3 className="font-mono font-semibold">{t.name}</h3>
                <span className="chip chip-accent ml-auto">{fields.length} fields</span>
              </div>
              <div className="overflow-y-auto max-h-96">
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
                      <th className="text-left py-1.5 pr-2">#</th>
                      <th className="text-left py-1.5 pr-2">Name</th>
                      <th className="text-left py-1.5 pr-2">Type</th>
                      <th className="text-left py-1.5">Req</th>
                    </tr>
                  </thead>
                  <tbody style={{ color: 'var(--fg-2)' }}>
                    {fields.map(f => (
                      <tr key={f.position} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td className="py-1 pr-2 font-mono" style={{ color: 'var(--fg-3)' }}>{f.position}</td>
                        <td className="py-1 pr-2 font-mono">{f.name}</td>
                        <td className="py-1 pr-2" style={{ color: 'var(--accent)' }}>{f.type}</td>
                        <td className="py-1">{f.required ? '●' : '○'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
