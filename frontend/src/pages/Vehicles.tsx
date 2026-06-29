export default function Vehicles() {
  return (
    <div className="card">
      <h1 className="text-2xl font-bold">Vehicles</h1>
      <p style={{ color: 'var(--fg-3)' }} className="mt-2 text-sm">
        Vehicle inventory + live status. Wire to <code>/api/v1/vehicles</code> once the backend route is added.
      </p>
    </div>
  );
}
