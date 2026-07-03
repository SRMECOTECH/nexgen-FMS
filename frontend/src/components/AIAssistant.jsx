import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles, X, Send, Loader2, MessageSquare, ArrowRight,
  Trash2, MapPin, Layers, Truck,
} from 'lucide-react';
import { riAssistantAsk, riAssistantSuggestions } from '../lib/routeIntel';

/**
 * AI Assistant — floating dock pinned across the route-intel section.
 * Right-side slide-out panel. Renders nothing on pages outside /route-intel*.
 * Session-only chat history (cleared on hard reload).
 */
export default function AIAssistant() {
  const { pathname } = useLocation();
  const visible = pathname.startsWith('/route-intel');
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [msgs, setMsgs] = useState([]);  // { kind: 'user' | 'ai', ... }
  const [chips, setChips] = useState([]);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!open || chips.length) return;
    riAssistantSuggestions().then(r => setChips(r.suggestions)).catch(() => {});
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs, busy]);

  // Pull context from the URL (so "summarize this trip" works on a trip page)
  const ctx = (() => {
    const m1 = pathname.match(/\/route-intel\/trips\/(\d+)/);
    const m2 = pathname.match(/\/route-intel\/segments\/(\d+)/);
    if (m1) return { trip_id: Number(m1[1]) };
    if (m2) return { segment_id: Number(m2[1]) };
    return {};
  })();

  const submit = async (text) => {
    const q = (text ?? query).trim();
    if (!q || busy) return;
    setQuery('');
    setMsgs(m => [...m, { kind: 'user', text: q }]);
    setBusy(true);
    try {
      const r = await riAssistantAsk(q, ctx);
      setMsgs(m => [...m, {
        kind: 'ai',
        text: r.answer, intent: r.intent, model: r.model,
        sources: r.sources, followups: r.suggested_followups,
      }]);
    } catch (e) {
      setMsgs(m => [...m, { kind: 'ai', error: e?.response?.data?.detail ?? e?.message ?? 'failed' }]);
    } finally { setBusy(false); }
  };

  if (!visible) return null;

  return (
    <>
      {/* Floating launcher button */}
      {!open && (
        <motion.button
          initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 p-4 rounded-full ai-glow animate-pulse-accent"
          style={{ background: 'var(--accent)' }}
          title="Open AI Assistant"
        >
          <Sparkles className="w-5 h-5" color="#000" />
        </motion.button>
      )}

      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ x: 420, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
            exit={{ x: 420, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 220, damping: 26 }}
            className="fixed top-0 right-0 h-full z-50 flex flex-col"
            style={{
              width: 'min(420px, 100vw)',
              background: 'var(--bg-1)',
              borderLeft: '1px solid var(--border)',
              boxShadow: '-20px 0 60px rgba(0, 0, 0, 0.5)',
            }}
          >
            {/* Header */}
            <div className="px-5 py-4 flex items-center justify-between border-b"
              style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg" style={{ background: 'var(--accent)' }}>
                  <Sparkles className="w-3.5 h-3.5" color="#000" />
                </div>
                <div>
                  <div className="text-sm font-bold" style={{ color: 'var(--fg-1)' }}>
                    AI Assistant
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.15em]"
                    style={{ color: 'var(--accent)' }}>
                    Route Intelligence
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {msgs.length > 0 && (
                  <button onClick={() => setMsgs([])} className="btn-soft text-[11px]"
                    title="Clear chat">
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
                <button onClick={() => setOpen(false)} className="btn-soft text-[11px]"
                  title="Close">
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* Context banner */}
            {(ctx.trip_id || ctx.segment_id) && (
              <div className="px-5 py-2 flex items-center gap-2 text-[11px] border-b"
                style={{ borderColor: 'var(--border)', background: 'var(--accent-soft)', color: 'var(--accent)' }}>
                {ctx.trip_id ? <Truck className="w-3 h-3" /> : <Layers className="w-3 h-3" />}
                <span>Context:</span>
                <span className="mono font-semibold">
                  {ctx.trip_id ? `trip ${ctx.trip_id}` : `segment ${ctx.segment_id}`}
                </span>
              </div>
            )}

            {/* Chat scroll area */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
              {msgs.length === 0 && (
                <EmptyState chips={chips} onPick={(q) => submit(q)} />
              )}

              {msgs.map((m, i) => (
                <Message key={i} m={m} onFollowup={(q) => submit(q)} />
              ))}

              {busy && (
                <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--fg-3)' }}>
                  <Loader2 className="w-3 h-3 animate-spin" style={{ color: 'var(--accent)' }} />
                  thinking…
                </div>
              )}
            </div>

            {/* Input */}
            <div className="px-4 py-3 border-t" style={{ borderColor: 'var(--border)' }}>
              <form onSubmit={(e) => { e.preventDefault(); submit(); }}
                className="input-field">
                <MessageSquare className="w-3.5 h-3.5 shrink-0"
                  style={{ color: 'var(--accent)' }} />
                <input
                  type="text" placeholder="Ask me about your trips…"
                  value={query} onChange={(e) => setQuery(e.target.value)}
                  disabled={busy}
                  className="text-xs"
                />
                <button type="submit" disabled={busy || !query.trim()}
                  className="p-1 rounded"
                  style={{ color: query.trim() ? 'var(--accent)' : 'var(--fg-4)' }}
                  title="Send">
                  <Send className="w-3.5 h-3.5" />
                </button>
              </form>
              <div className="text-[10px] mt-1.5 mono text-center" style={{ color: 'var(--fg-4)' }}>
                Press Enter to send · context auto-detected from URL
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}

// ---------------------------------------------------------------------------
function EmptyState({ chips, onPick }) {
  return (
    <div className="text-center py-8 px-2">
      <div className="w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3 ai-glow"
        style={{ background: 'var(--accent-soft)' }}>
        <Sparkles className="w-5 h-5" style={{ color: 'var(--accent)' }} />
      </div>
      <div className="text-sm font-semibold mb-1" style={{ color: 'var(--fg-1)' }}>
        Ask anything about your trips
      </div>
      <div className="text-xs mb-4" style={{ color: 'var(--fg-3)' }}>
        I read the analyzed data live — costs, idle time, efficiency, segments,
        addresses, weather.
      </div>
      <div className="flex flex-col gap-1.5">
        {chips.map((c, i) => (
          <button key={i} onClick={() => onPick(c.query)}
            className="text-left p-2.5 rounded-lg text-xs hover:translate-x-0.5 transition-transform"
            style={{ background: 'var(--bg-2)', color: 'var(--fg-2)' }}>
            <span className="text-[10px] uppercase tracking-[0.12em] mr-1"
              style={{ color: 'var(--accent)' }}>{c.label}</span>
            <ArrowRight className="inline w-3 h-3 ml-1" style={{ color: 'var(--accent)' }} />
            <div className="text-[11px] mt-0.5" style={{ color: 'var(--fg-3)' }}>"{c.query}"</div>
          </button>
        ))}
      </div>
    </div>
  );
}

function Message({ m, onFollowup }) {
  const nav = useNavigate();
  if (m.kind === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] p-2.5 rounded-lg text-xs"
          style={{ background: 'var(--accent-soft)', color: 'var(--fg-1)' }}>
          {m.text}
        </div>
      </div>
    );
  }
  if (m.error) {
    return (
      <div className="p-2.5 rounded-lg text-xs"
        style={{ background: 'rgba(255, 77, 109, 0.1)', color: 'var(--danger)' }}>
        {m.error}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2">
        <div className="p-1 rounded shrink-0 mt-0.5" style={{ background: 'var(--accent)' }}>
          <Sparkles className="w-2.5 h-2.5" color="#000" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[9px] uppercase tracking-[0.12em] font-semibold"
              style={{ color: 'var(--accent)' }}>{m.intent}</span>
            <span className="text-[9px] mono" style={{ color: 'var(--fg-4)' }}>
              · {m.model}
            </span>
          </div>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--fg-1)' }}>
            {m.text}
          </p>
        </div>
      </div>

      {m.sources?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 ml-7">
          {m.sources.slice(0, 6).map((s, i) => (
            <button key={i}
              onClick={() => nav(
                s.kind === 'trip' ? `/route-intel/trips/${s.id}` :
                s.kind === 'segment' ? `/route-intel/segments/${s.id}` :
                '/route-intel'
              )}
              className="text-[10px] px-1.5 py-0.5 rounded font-semibold flex items-center gap-0.5 hover:scale-105 transition-transform"
              style={{ background: 'var(--bg-2)', color: 'var(--accent)' }}>
              {s.kind === 'trip' ? <Truck className="w-2.5 h-2.5" /> : <MapPin className="w-2.5 h-2.5" />}
              {s.kind} #{s.id}
            </button>
          ))}
          {m.sources.length > 6 && (
            <span className="text-[10px]" style={{ color: 'var(--fg-4)' }}>
              +{m.sources.length - 6} more
            </span>
          )}
        </div>
      )}

      {m.followups?.length > 0 && (
        <div className="flex flex-col gap-1 ml-7 mt-1">
          {m.followups.slice(0, 3).map((q, i) => (
            <button key={i} onClick={() => onFollowup(q)}
              className="text-left text-[11px] p-1.5 rounded flex items-center gap-1.5 hover:translate-x-0.5 transition-transform"
              style={{ background: 'var(--bg-2)', color: 'var(--fg-2)' }}>
              <ArrowRight className="w-2.5 h-2.5 shrink-0" style={{ color: 'var(--accent)' }} />
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
