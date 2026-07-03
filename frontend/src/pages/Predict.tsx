import AiOsSection from './AiOsScaffold';

export default function Predict() {
  return (
    <AiOsSection
      section="Predict"
      title="Predict — what will happen next"
      promise={
        'ETA, SLA-risk and 7-day demand forecasting, each with confidence, contributing '
        + 'factors and "what-if" controls. Always shown with its evidence — no black box.'
      }
      upcoming={[
        'ETA workbench — pick origin / destination / driver / vehicle and see prediction + factors',
        'SLA risk bucket per booked trip with the contributing-factor breakdown',
        '7-day demand & trip-count forecast, per-route and fleet-wide',
        'Client-level forecast for enterprise tier customers',
      ]}
      ml_endpoints={[
        '/ml/predict/eta (basic)',
        '/ml/predict/sla (pro)',
        '/ml/forecast/demand (basic)',
        '/ml/forecast/trips (basic)',
        '/ml/clients/forecast (enterprise)',
      ]}
    />
  );
}
