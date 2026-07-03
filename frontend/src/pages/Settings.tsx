import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Settings as SettingsIcon, Database, RefreshCw, Loader2, CheckCircle2,
  XCircle, AlertTriangle, Save, Eye, EyeOff, Hammer,
} from 'lucide-react';
import {
  fetchAppConfig, saveAppConfig, fetchDbStatus, initDb,
  type AppConfig, type DbStatus, type DbInitResult,
} from '../lib/api';

// ============================================================================
// Settings — the single place where a fresh clone becomes a working install.
//
//   1. Database card — is the warehouse reachable? which tables exist?
//      One button creates the database + every table (idempotent).
//   2. Configuration — every .env tunable, grouped exactly like the file,
//      editable and written back to .env (values apply live; port/URL keys
//      flag that a restart is needed).
// ============================================================================

function Pill({ ok, textOk, textBad }: { ok: boolean; textOk: string; textBad: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold"
      style={{
        color: ok ? 'var(--success)' : 'var(--danger)',
        background: ok ? 'color-mix(in srgb, var(--success) 12%, transparent)'
                       : 'color-mix(in srgb, var(--danger) 12%, transparent)',
      }}
    >
      {ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
      {ok ? textOk : textBad}
    </span>
  );
}

export default function Settings() {
  const [config, setConfig]   = useState<AppConfig | null>(null);
  const [edits, setEdits]     = useState<Record<string, string>>({});
  const [reveal, setReveal]   = useState<Record<string, boolean>>({});
  const [saving, setSaving]   = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [db, setDb]               = useState<DbStatus | null>(null);
  const [dbLoading, setDbLoading] = useState(true);
  const [initing, setIniting]     = useState(false);
  const [initResult, setInitResult] = useState<DbInitResult | null>(null);
  const [error, setError]         = useState<string | null>(null);

  const loadConfig = () => {
    fetchAppConfig().then(setConfig).catch(e => setError(e?.message ?? 'failed to load config'));
  };
  const loadDb = () => {
    setDbLoading(true);
    fetchDbStatus().then(setDb).catch(e => setError(e?.message ?? 'failed to load DB status'))
      .finally(() => setDbLoading(false));
  };
  useEffect(() => { loadConfig(); loadDb(); }, []);

  const dirty = useMemo(() => {
    if (!config) return {};
    const out: Record<string, string> = {};
    for (const sec of config.sections) {
      for (const k of sec.keys) {
        if (k.key in edits && edits[k.key] !== k.value) out[k.key] = edits[k.key];
      }
    }
    return out;
  }, [config, edits]);
  const dirtyCount = Object.keys(dirty).length;

  const onSave = async () => {
    if (!dirtyCount) return;
    setSaving(true); setSaveMsg(null);
    try {
      const res = await saveAppConfig(dirty);
      const restartNote = res.needs_restart.length
        ? ` Restart the backend/frontend for: ${res.needs_restart.join(', ')}.`
        : ' Changes are live.';
      setSaveMsg({ ok: true, text: `Saved ${res.saved.length} setting(s) to .env.${restartNote}` });
      setEdits({});
      loadConfig();
      loadDb();
    } catch (e: any) {
      setSaveMsg({ ok: false, text: e?.response?.data?.detail ?? e?.message ?? 'save failed' });
    } finally {
      setSaving(false);
    }
  };

  const onInit = async () => {
    setIniting(true); setInitResult(null);
    try {
      const res = await initDb();
      setInitResult(res);
      loadDb();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? 'init failed');
    } finally {
      setIniting(false);
    }
  };

  const inputStyle = {
    background: 'var(--bg-1)',
    border: '1px solid var(--border)',
    color: 'var(--fg-1)',
  } as const;

  return (
    <div className="space-y-6">
      {/* ===== Hero =================================================== */}
      <motion.section
        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-2xl p-6 border"
        style={{
          background: 'radial-gradient(900px 160px at 0% 0%, var(--accent-soft), transparent), var(--bg-3)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="flex items-center gap-2 mb-2" style={{ color: 'var(--accent)' }}>
          <SettingsIcon className="w-4 h-4" />
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold">System</span>
        </div>
        <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--fg-1)', fontFamily: 'var(--font-display)' }}>
          Settings
        </h1>
        <p className="text-sm leading-relaxed max-w-3xl" style={{ color: 'var(--fg-2)' }}>
          Everything a fresh install needs: point the app at your database, click
          <b> Initialize database</b>, and tune any behaviour — all values are written
          back to <span className="mono">.env</span> so they survive restarts.
        </p>
      </motion.section>

      {error && (
        <div className="rounded-xl border p-4 text-sm flex items-center gap-2"
             style={{ borderColor: 'var(--danger)', color: 'var(--danger)', background: 'var(--bg-3)' }}>
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {/* ===== Database card ========================================== */}
      <section className="rounded-2xl border p-6" style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <h2 className="text-lg font-bold" style={{ color: 'var(--fg-1)' }}>Database</h2>
            {db && <Pill ok={db.reachable} textOk="connected" textBad={db.configured ? 'unreachable' : 'not configured'} />}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadDb} disabled={dbLoading}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold border transition-all hover:bg-[var(--bg-2)]"
              style={{ borderColor: 'var(--border)', color: 'var(--fg-2)' }}
            >
              {dbLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              Refresh
            </button>
            <button
              onClick={onInit} disabled={initing}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all"
              style={{ background: 'var(--accent)', color: '#000' }}
            >
              {initing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Hammer className="w-3.5 h-3.5" />}
              Initialize database (create schema + tables)
            </button>
          </div>
        </div>

        {db && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="text-sm space-y-1.5" style={{ color: 'var(--fg-2)' }}>
              <div><span style={{ color: 'var(--fg-3)' }}>URL:</span> <span className="mono text-xs">{db.url_masked || '—'}</span></div>
              <div><span style={{ color: 'var(--fg-3)' }}>Engine:</span> {db.dialect ?? '—'} · <span style={{ color: 'var(--fg-3)' }}>Database:</span> {db.database ?? '—'}</div>
              {db.error && <div style={{ color: 'var(--danger)' }} className="text-xs mono">{db.error}</div>}
              <div className="text-xs pt-1" style={{ color: 'var(--fg-3)' }}>
                On a fresh clone: set the Warehouse database URL below, save, then click Initialize.
                The MySQL database and every table are created automatically (safe to re-run).
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] font-semibold mb-2" style={{ color: 'var(--fg-3)' }}>
                Tables ({db.tables.length})
              </div>
              <div className="max-h-48 overflow-y-auto rounded-lg border" style={{ borderColor: 'var(--border)' }}>
                {db.tables.length === 0 && (
                  <div className="p-3 text-xs" style={{ color: 'var(--fg-3)' }}>
                    No tables yet — click "Initialize database".
                  </div>
                )}
                {db.tables.map(t => (
                  <div key={t.name} className="flex justify-between px-3 py-1.5 text-xs border-b last:border-b-0"
                       style={{ borderColor: 'var(--border)', color: 'var(--fg-2)' }}>
                    <span className="mono">{t.name}</span>
                    <span className="mono" style={{ color: 'var(--fg-3)' }}>{t.rows ?? '—'} rows</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {initResult && (
          <div className="mt-4 rounded-lg border p-3 text-xs space-y-1"
               style={{ borderColor: 'var(--border)', background: 'var(--bg-1)' }}>
            <div className="font-semibold" style={{ color: initResult.ok ? 'var(--success)' : 'var(--warning)' }}>
              {initResult.ok ? 'Bootstrap complete — warehouse ready.' : 'Bootstrap finished with issues:'}
            </div>
            {Object.entries(initResult.steps).map(([step, s]) => (
              <div key={step} className="flex items-center gap-2 mono" style={{ color: s.ok ? 'var(--fg-2)' : 'var(--danger)' }}>
                {s.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {step}{s.error ? ` — ${s.error}` : ''}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ===== Configuration sections ================================= */}
      {config?.sections.map(sec => (
        <section key={sec.section} className="rounded-2xl border p-6"
                 style={{ background: 'var(--bg-3)', borderColor: 'var(--border)' }}>
          <h2 className="text-base font-bold mb-0.5" style={{ color: 'var(--fg-1)' }}>{sec.section}</h2>
          <p className="text-xs mb-4" style={{ color: 'var(--fg-3)' }}>{sec.hint}</p>
          <div className="grid gap-4 md:grid-cols-2">
            {sec.keys.map(k => {
              const value = k.key in edits ? edits[k.key] : k.value;
              const changed = k.key in dirty;
              return (
                <div key={k.key}>
                  <label className="flex items-center gap-2 text-xs font-semibold mb-1" style={{ color: 'var(--fg-2)' }}>
                    {k.label}
                    <span className="mono text-[10px]" style={{ color: 'var(--fg-4)' }}>{k.key}</span>
                    {k.restart && (
                      <span className="text-[10px] px-1.5 rounded"
                            style={{ color: 'var(--warning)', background: 'color-mix(in srgb, var(--warning) 12%, transparent)' }}>
                        restart
                      </span>
                    )}
                    {changed && <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent)' }} />}
                  </label>
                  <div className="relative">
                    {k.kind === 'bool' ? (
                      <select
                        value={(value || 'false').toLowerCase()}
                        onChange={e => setEdits(p => ({ ...p, [k.key]: e.target.value }))}
                        className="w-full rounded-lg px-3 py-2 text-sm mono outline-none"
                        style={inputStyle}
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : (
                      <input
                        type={k.secret && !reveal[k.key] ? 'password' : 'text'}
                        value={value}
                        onChange={e => setEdits(p => ({ ...p, [k.key]: e.target.value }))}
                        className="w-full rounded-lg px-3 py-2 text-sm mono outline-none"
                        style={{ ...inputStyle, paddingRight: k.secret ? '2.5rem' : undefined }}
                        spellCheck={false}
                      />
                    )}
                    {k.secret && (
                      <button
                        type="button"
                        onClick={() => setReveal(p => ({ ...p, [k.key]: !p[k.key] }))}
                        className="absolute right-2 top-1/2 -translate-y-1/2"
                        style={{ color: 'var(--fg-3)' }}
                        aria-label={reveal[k.key] ? 'Hide value' : 'Show value'}
                      >
                        {reveal[k.key] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] mt-1 leading-snug" style={{ color: 'var(--fg-3)' }}>{k.description}</p>
                </div>
              );
            })}
          </div>
        </section>
      ))}

      {/* ===== Sticky save bar ======================================== */}
      {config && (
        <div className="sticky bottom-4 flex items-center justify-between gap-3 rounded-2xl border p-4"
             style={{ background: 'var(--bg-1)', borderColor: dirtyCount ? 'var(--accent)' : 'var(--border)' }}>
          <div className="text-xs" style={{ color: 'var(--fg-2)' }}>
            {saveMsg
              ? <span style={{ color: saveMsg.ok ? 'var(--success)' : 'var(--danger)' }}>{saveMsg.text}</span>
              : dirtyCount
                ? `${dirtyCount} unsaved change(s) → written to ${config.env_file}`
                : <>All values live in <span className="mono">.env</span> — edits here are saved back to that file.</>}
          </div>
          <button
            onClick={onSave} disabled={!dirtyCount || saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#000' }}
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save changes
          </button>
        </div>
      )}
    </div>
  );
}
