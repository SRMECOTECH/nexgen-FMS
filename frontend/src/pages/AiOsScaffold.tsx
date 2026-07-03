import { motion } from 'framer-motion';
import { Sparkles, ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

// ============================================================================
// One reusable scaffold for the AI-OS sections that aren't fully built yet.
// Each section page imports this and supplies its own copy + planned features.
// Keeps the navigation end-to-end navigable today without faking data.
// ============================================================================

export interface AiOsSectionProps {
  /** Sidebar section header, e.g. "Observe". */
  section: string;
  /** Page H1, e.g. "Observe — real-time telemetry". */
  title: string;
  /** Two-sentence promise of what this section will do. */
  promise: string;
  /** Bullet list of upcoming capabilities. */
  upcoming: string[];
  /** ML endpoints (from API_REFERENCE.md) this section will consume. */
  ml_endpoints?: string[];
}

export default function AiOsSection({ section, title, promise, upcoming, ml_endpoints }: AiOsSectionProps) {
  return (
    <div className="space-y-6 max-w-3xl">
      <motion.section
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl p-6 border"
        style={{
          background: 'radial-gradient(900px 160px at 0% 0%, var(--accent-soft), transparent), var(--bg-3)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--accent)' }}>
          {section}
        </div>
        <h1
          className="text-3xl font-bold mb-3"
          style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
        >
          {title}
        </h1>
        <p className="text-base leading-relaxed" style={{ color: 'var(--fg-2)' }}>
          {promise}
        </p>
      </motion.section>

      <section
        className="rounded-2xl p-5 border"
        style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
      >
        <div className="text-[10px] uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--fg-3)' }}>
          Coming next
        </div>
        <ul className="space-y-2">
          {upcoming.map((u, i) => (
            <li key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--fg-2)' }}>
              <Sparkles className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: 'var(--accent)' }} />
              {u}
            </li>
          ))}
        </ul>
      </section>

      {ml_endpoints?.length ? (
        <section
          className="rounded-2xl p-5 border"
          style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}
        >
          <div className="text-[10px] uppercase tracking-[0.18em] mb-3" style={{ color: 'var(--fg-3)' }}>
            Models it consumes (smart-truck subscription API)
          </div>
          <ul className="space-y-1.5">
            {ml_endpoints.map((p) => (
              <li
                key={p}
                className="font-mono text-xs px-2.5 py-1.5 rounded-md inline-flex mr-2 mb-1"
                style={{ background: 'var(--bg-2)', color: 'var(--accent)' }}
              >
                {p}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <Link
        to="/mission-control"
        className="inline-flex items-center gap-1.5 text-sm font-semibold"
        style={{ color: 'var(--accent)' }}
      >
        Back to Mission Control <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    </div>
  );
}
