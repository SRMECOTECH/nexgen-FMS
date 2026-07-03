import AiOsSection from './AiOsScaffold';

export default function Act() {
  return (
    <AiOsSection
      section="Act"
      title="Act — approvals, dispatch, alerts"
      promise={
        'The human-in-the-loop pane. AI recommends — you approve, override, or dismiss. '
        + 'Every action is logged so the Learn loop can grade the AI on what you trusted.'
      }
      upcoming={[
        'Approval queue: each card shows recommendation, evidence, "Approve / Modify / Dismiss"',
        'Bulk-dispatch from a forecasted demand spike',
        'Alert routing rules (which agents notify whom, on which channel)',
        'Audit log — what AI suggested vs what the human chose',
      ]}
    />
  );
}
