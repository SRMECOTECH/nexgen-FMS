import AiOsSection from './AiOsScaffold';

export default function Recommend() {
  return (
    <AiOsSection
      section="Recommend"
      title="Recommend — what you should do about it"
      promise={
        'Concrete next actions, ranked. "Assign Rakesh K. instead of Suresh — 12% higher on-time '
        + 'rate on this lane." Every recommendation carries reason, confidence and an alternative.'
      }
      upcoming={[
        'Driver recommender for a planned trip (top-N drivers with route experience)',
        'Best historical route (with hour / day-of-week) for a given lane',
        'Hub-rank changes — "Delhi NCR moved up 1 slot this week, here\'s why"',
        '"Approve" button that hands the choice back to the human',
      ]}
      ml_endpoints={[
        '/ml/recommend/drivers (pro)',
        '/ml/optimize/route (pro)',
        '/ml/optimize/hubs (pro)',
      ]}
    />
  );
}
