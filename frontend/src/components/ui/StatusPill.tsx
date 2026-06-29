interface StatusPillProps {
  status: string;
}

const map: Record<string, { color: string; bg: string; label?: string }> = {
  live:     { color: 'var(--success)', bg: 'rgba(34,197,94,0.15)' },
  active:   { color: 'var(--success)', bg: 'rgba(34,197,94,0.15)' },
  online:   { color: 'var(--success)', bg: 'rgba(34,197,94,0.15)' },
  ok:       { color: 'var(--success)', bg: 'rgba(34,197,94,0.15)' },
  running:  { color: 'var(--info)',    bg: 'rgba(56,189,248,0.15)' },
  tested:   { color: 'var(--info)',    bg: 'rgba(56,189,248,0.15)' },
  stale:    { color: 'var(--warning)', bg: 'rgba(250,204,21,0.15)' },
  paused:   { color: 'var(--warning)', bg: 'rgba(250,204,21,0.15)' },
  warning:  { color: 'var(--warning)', bg: 'rgba(250,204,21,0.15)' },
  failed:   { color: 'var(--danger)',  bg: 'rgba(239,68,68,0.15)' },
  offline:  { color: 'var(--danger)',  bg: 'rgba(239,68,68,0.15)' },
  critical: { color: 'var(--danger)',  bg: 'rgba(239,68,68,0.15)' },
  info:     { color: 'var(--info)',    bg: 'rgba(56,189,248,0.15)' },
};

export default function StatusPill({ status }: StatusPillProps) {
  const s = map[status.toLowerCase()] ?? { color: 'var(--fg-2)', bg: 'var(--bg-2)' };
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider"
      style={{ background: s.bg, color: s.color }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
      {status}
    </span>
  );
}
