import PageHeader from '../components/ui/PageHeader';
import { Settings as SettingsIcon } from 'lucide-react';

export default function Configuration() {
  return (
    <div className="space-y-4">
      <PageHeader title="Configuration" subtitle="Runtime settings, lakehouse endpoints, feature flags." />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ConfigGroup title="Lakehouse" rows={[
          ['USE_MOCK_DATA', 'true (mock)'],
          ['LAKEHOUSE_BASE_URL', 'http://98.70.24.178:5173'],
          ['ICEBERG_NAMESPACE', 'telemetry'],
        ]}/>
        <ConfigGroup title="ClickHouse Gateway" rows={[
          ['HOST', '98.70.24.178'],
          ['PORT', '8123'],
          ['DATABASE', 'telemetry'],
          ['USER', '(not set — register consumer)'],
        ]}/>
        <ConfigGroup title="ML" rows={[
          ['MODEL_DIR', 'ml_models/'],
          ['DEFAULT_VERSION_PINNING', 'is_active=true'],
          ['BATCH_SCAN_INTERVAL', 'hourly'],
        ]}/>
        <ConfigGroup title="Frontend" rows={[
          ['VITE_API_URL', 'http://localhost:8000/api/v1'],
          ['Theme', 'Dark + Amber'],
          ['Health-poll interval', '30s'],
        ]}/>
      </div>
    </div>
  );
}

function ConfigGroup({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <SettingsIcon className="w-4 h-4" style={{ color: 'var(--accent)' }} />
        <h3 className="font-semibold">{title}</h3>
      </div>
      <dl className="text-xs space-y-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 py-1.5 border-b"
               style={{ borderColor: 'var(--border)' }}>
            <dt className="font-mono" style={{ color: 'var(--fg-3)' }}>{k}</dt>
            <dd className="font-mono text-right" style={{ color: 'var(--fg-1)' }}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
