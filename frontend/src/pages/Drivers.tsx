export default function Drivers() {
  return (
    <div className="card">
      <h1 className="text-2xl font-bold">Drivers</h1>
      <p style={{ color: 'var(--fg-3)' }} className="mt-2 text-sm">
        Driver roster + risk scores. Wire to <code>/api/v1/drivers</code> + ML driver-scorer.
      </p>
    </div>
  );
}
