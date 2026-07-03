import AiOsSection from './AiOsScaffold';

export default function Understand() {
  return (
    <AiOsSection
      section="Understand"
      title="Understand — structure & insight derived from raw signal"
      promise={
        'AI-derived lanes, hubs, driver behavioural profiles, route fingerprints. ' +
        'Route Intelligence (in the sidebar above) is the first surface here; '
        + 'Digital Twin per vehicle and Knowledge Graph join later.'
      }
      upcoming={[
        'Digital Twin: per-vehicle AI profile with identity, behaviour, memory, prediction, history',
        'Knowledge Graph: vehicles ↔ drivers ↔ trips ↔ customers ↔ routes — click anything, everything expands',
        'Driver Behaviour Profile — uses /ml/drivers/{id}/score & /fatigue',
        'Hub discovery — /ml/optimize/hubs',
      ]}
      ml_endpoints={[
        '/ml/drivers/scores (basic)',
        '/ml/drivers/{driver_id}/score (basic)',
        '/ml/drivers/fatigue (pro)',
        '/ml/optimize/hubs (pro)',
      ]}
    />
  );
}
