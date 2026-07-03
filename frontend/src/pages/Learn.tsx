import AiOsSection from './AiOsScaffold';

export default function Learn() {
  return (
    <AiOsSection
      section="Learn"
      title="Learn — the feedback loop"
      promise={
        'Model registry, retraining schedules, and the closed-loop grading of AI suggestions '
        + 'against human decisions. The page where the system gets smarter, on schedule.'
      }
      upcoming={[
        'Model registry table — version, training date, MAE / AUC, "Compare"',
        'Retraining schedules per tier (daily / weekly / monthly)',
        'Drift dashboard — feature distributions vs training-time baseline',
        'Suggestion ledger — what AI said vs what humans did',
      ]}
      ml_endpoints={[
        '/ml/models (basic)',
        '/ml/models/comparison (basic)',
        '/ml/training/readiness (enterprise)',
        '/ml/train-tier/{tier} (enterprise)',
      ]}
    />
  );
}
