import PageHeader from '../components/ui/PageHeader';
import { Map as MapIcon } from 'lucide-react';

export default function LiveMap() {
  return (
    <div className="space-y-4">
      <PageHeader title="Live Map" subtitle="Real-time vehicle positions on the network." />
      <div className="card flex items-center justify-center h-[500px]">
        <div className="text-center">
          <MapIcon className="w-16 h-16 mx-auto mb-3" style={{ color: 'var(--accent)' }} />
          <h3 className="text-lg font-semibold">Map view coming next</h3>
          <p className="text-sm mt-1 max-w-md" style={{ color: 'var(--fg-3)' }}>
            Will render Leaflet (OpenStreetMap) markers from <code>gps_telemetry_events</code> filtered
            to <code>vehicle_id</code> in active trips. Heatmap and clustering toggles planned.
          </p>
        </div>
      </div>
    </div>
  );
}
