import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronRight, X } from 'lucide-react';

// ============================================================================
// FeatureCatalog — a grid of "feature cards" + a slide-in drawer that shows
// the full chart / table / map for the clicked feature.
//
// Used by trip-level and segment-level Route Intelligence pages to replace the
// old single long-scroll layout. Same component, different feature lists.
//
// `features` shape:
//   [{
//      id:          unique key
//      icon:        lucide-react component
//      title:       "Cost Breakdown"
//      description: one cool sentence, like a tooltip on a Tesla setting
//      preview?:    optional small ReactNode shown on the card (a chip, kpi, sparkline)
//      status?:     'live' | 'demo' | 'unavailable' — colours the corner dot
//      accent?:     css var for icon background, defaults to var(--accent)
//      detail:      ReactNode rendered inside the drawer
//      onOpen?:     function called when drawer opens (use to lazy-fetch data)
//   }]
// ============================================================================

const statusColor = {
  live:        'var(--success)',
  demo:        'var(--warning)',
  unavailable: 'var(--fg-4)',
};

export default function FeatureCatalog({ features, columns = 'auto' }) {
  const [openId, setOpenId] = useState(null);
  const open = features.find((f) => f.id === openId) || null;

  useEffect(() => {
    if (!open || !open.onOpen) return;
    open.onOpen();
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (e.key === 'Escape') setOpenId(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  const gridCls =
    columns === 2 ? 'sm:grid-cols-2'
    : columns === 3 ? 'sm:grid-cols-2 lg:grid-cols-3'
    : 'sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4';

  return (
    <>
      <div className={`grid grid-cols-1 ${gridCls} gap-3`}>
        {features.map((f, i) => (
          <FeatureCard key={f.id} f={f} index={i} onClick={() => setOpenId(f.id)} />
        ))}
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex justify-end"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={() => setOpenId(null)}
          >
            <motion.aside
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 28, stiffness: 240 }}
              className="h-full w-full md:w-[78vw] lg:w-[68vw] xl:w-[60vw] overflow-y-auto border-l"
              style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
              onClick={(e) => e.stopPropagation()}
            >
              <DrawerHeader f={open} onClose={() => setOpenId(null)} />
              <div className="p-6 space-y-4">
                {open.detail}
              </div>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

function FeatureCard({ f, index, onClick }) {
  const Icon = f.icon;
  return (
    <motion.button
      onClick={onClick}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.3 }}
      whileHover={{ y: -2 }}
      className="text-left rounded-2xl p-4 border h-full flex flex-col"
      style={{
        background: 'var(--bg-3)',
        borderColor: 'var(--border)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div className="flex items-start gap-3 mb-2">
        <div
          className="p-2 rounded-lg shrink-0"
          style={{ background: f.accent ?? 'var(--accent-soft)', color: f.accent ? '#000' : 'var(--accent)' }}
        >
          {Icon && <Icon className="w-4 h-4" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <h3
              className="text-sm font-semibold leading-tight truncate"
              style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
            >
              {f.title}
            </h3>
            {f.status && (
              <span
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: statusColor[f.status] }}
                title={f.status === 'live' ? 'live data' : f.status === 'demo' ? 'demo / placeholder' : 'not available'}
              />
            )}
          </div>
        </div>
      </div>

      <p
        className="text-[11px] leading-relaxed mb-3 flex-1"
        style={{ color: 'var(--fg-2)' }}
      >
        {f.description}
      </p>

      {f.preview && (
        <div className="mb-3">{f.preview}</div>
      )}

      <div
        className="flex items-center gap-1 text-[11px] font-semibold mt-auto"
        style={{ color: 'var(--accent)' }}
      >
        Open detailed view <ChevronRight className="w-3 h-3" />
      </div>
    </motion.button>
  );
}

// ---------------------------------------------------------------------------
// Drawer header
// ---------------------------------------------------------------------------

function DrawerHeader({ f, onClose }) {
  const Icon = f.icon;
  return (
    <div
      className="sticky top-0 z-10 px-6 py-4 border-b flex items-start justify-between gap-4"
      style={{ background: 'var(--bg-1)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-start gap-3 min-w-0">
        <div
          className="p-2 rounded-lg shrink-0"
          style={{ background: f.accent ?? 'var(--accent-soft)', color: f.accent ? '#000' : 'var(--accent)' }}
        >
          {Icon && <Icon className="w-4 h-4" />}
        </div>
        <div className="min-w-0">
          <h2
            className="text-xl font-bold leading-tight truncate"
            style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}
          >
            {f.title}
          </h2>
          <p className="text-xs mt-0.5" style={{ color: 'var(--fg-3)' }}>{f.description}</p>
        </div>
      </div>
      <button
        onClick={onClose}
        className="p-1.5 rounded-md hover:bg-[var(--bg-2)] shrink-0"
        style={{ color: 'var(--fg-2)' }}
        aria-label="Close drawer"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
