import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Zap } from 'lucide-react';
import { aiLiveThinking } from '../lib/api';

// ============================================================================
// Live AI Thinking — a streaming view of what each agent is doing.
// Today it polls /ai/live-thinking (a synthetic tick stream). When the real
// agent loop ships, this page swaps to an SSE/websocket of the same shape.
// ============================================================================

interface Tick { t: string; agent: string; msg: string }

export default function LiveThinking() {
  const [ticks, setTicks] = useState<Tick[]>([]);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const r = await aiLiveThinking();
        if (!live) return;
        setTicks((prev) => [...r.ticks, ...prev].slice(0, 40));
      } catch { /* keep the page rendered even when backend is down */ }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => { live = false; clearInterval(id); };
  }, []);

  return (
    <div className="space-y-6 max-w-3xl">
      <section
        className="rounded-2xl p-6 border"
        style={{
          background: 'radial-gradient(900px 160px at 0% 0%, var(--accent-soft), transparent), var(--bg-3)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--accent)' }}>
          <Zap className="w-4 h-4" />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">Live AI Thinking</span>
        </div>
        <h1
          className="text-3xl font-bold mb-2"
          style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
        >
          What the agents are doing right now
        </h1>
        <p className="text-sm" style={{ color: 'var(--fg-2)' }}>
          Streamed reasoning from the AI agents — ETA Intelligence, Driver Coach, Maintenance, Route Intelligence.
          Polled every 5 seconds; swaps to an event stream when the agent loop ships.
        </p>
      </section>

      <section className="rounded-2xl border" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
        <ul className="divide-y" style={{ borderColor: 'var(--border-soft)' }}>
          <AnimatePresence initial={false}>
            {ticks.length === 0 && (
              <li className="px-5 py-6 text-sm" style={{ color: 'var(--fg-3)' }}>
                Waiting for the first tick…
              </li>
            )}
            {ticks.map((tk, i) => (
              <motion.li
                key={`${tk.t}-${i}`}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="px-5 py-3 flex items-start gap-3"
              >
                <div className="mono text-[10px] pt-0.5 w-20 shrink-0" style={{ color: 'var(--fg-3)' }}>
                  {new Date(tk.t).toLocaleTimeString()}
                </div>
                <div
                  className="text-[10px] uppercase tracking-[0.15em] px-1.5 py-0.5 rounded shrink-0"
                  style={{ background: 'var(--bg-2)', color: 'var(--accent)' }}
                >
                  {tk.agent}
                </div>
                <div className="text-sm" style={{ color: 'var(--fg-2)' }}>{tk.msg}</div>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      </section>
    </div>
  );
}
