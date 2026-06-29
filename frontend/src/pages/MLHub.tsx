import { Sparkles, Gauge, AlertTriangle, ShieldAlert, Fuel, Clock, Route, Activity } from 'lucide-react';

const models = [
  { name: 'Dynamic ETA',          desc: 'XGBoost regressor predicting remaining trip time',     icon: Clock,         tier: 1 },
  { name: 'Delay Risk',           desc: 'Pre-departure classifier — will this trip be late?',   icon: AlertTriangle, tier: 1 },
  { name: 'Driver Risk Score',    desc: '0-100 weekly score per driver',                        icon: Gauge,         tier: 1 },
  { name: 'Telemetry Anomaly',    desc: 'IsolationForest on raw GPS stream',                    icon: Activity,      tier: 1 },
  { name: 'Fuel Pilferage',       desc: 'Unexplained fuel drops vs odometer movement',          icon: Fuel,          tier: 2 },
  { name: 'Detention Predictor',  desc: 'Expected wait time at next consignee',                 icon: ShieldAlert,   tier: 2 },
  { name: 'Route Deviation',      desc: 'Distance from canonical lane path',                    icon: Route,         tier: 2 },
  { name: 'Lane Discovery',       desc: 'DBSCAN clustering on origin-dest pairs',               icon: Sparkles,      tier: 3 },
];

export default function MLHub() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">ML Insights</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--fg-3)' }}>
          Models defined in the planning doc — implementation status will appear here as each lands.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {models.map(({ name, desc, icon: Icon, tier }) => (
          <div key={name} className="card card-hover animate-fade-in-up">
            <div className="flex items-start gap-3">
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: 'var(--accent-soft)' }}
              >
                <Icon className="w-5 h-5" style={{ color: 'var(--accent)' }} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold">{name}</h3>
                  <span className="chip chip-accent">Tier {tier}</span>
                </div>
                <p className="text-xs mt-1.5" style={{ color: 'var(--fg-3)' }}>{desc}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
