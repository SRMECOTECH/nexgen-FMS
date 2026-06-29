import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Pagination as PaginationState } from '../../hooks/usePagination';

interface PaginationProps {
  state: PaginationState<any>;
  label?: string;                 // e.g. "trips", "trucks"
  pageSizeOptions?: number[];
}

/** Build a compact page list with ellipses: 1 … 4 5 [6] 7 8 … 20 */
function pageWindow(page: number, pageCount: number): (number | '…')[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1);
  const out: (number | '…')[] = [1];
  const lo = Math.max(2, page - 1);
  const hi = Math.min(pageCount - 1, page + 1);
  if (lo > 2) out.push('…');
  for (let p = lo; p <= hi; p++) out.push(p);
  if (hi < pageCount - 1) out.push('…');
  out.push(pageCount);
  return out;
}

export default function Pagination({ state, label = 'rows', pageSizeOptions = [12, 24, 50, 100] }: PaginationProps) {
  const { page, pageCount, total, start, end, setPage, setPageSize, next, prev, pageSize } = state;
  if (total === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 mt-1 text-xs"
      style={{ borderTop: '1px solid var(--border)', color: 'var(--fg-3)' }}>
      <div className="flex items-center gap-2">
        <span>
          Showing <span className="tabular" style={{ color: 'var(--fg-1)' }}>{start}</span>–
          <span className="tabular" style={{ color: 'var(--fg-1)' }}>{end}</span> of{' '}
          <span className="tabular" style={{ color: 'var(--fg-1)' }}>{total.toLocaleString()}</span> {label}
        </span>
        <select
          value={pageSize}
          onChange={(e) => setPageSize(Number(e.target.value))}
          className="ml-1 rounded-md px-1.5 py-1 outline-none cursor-pointer"
          style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', color: 'var(--fg-2)' }}
        >
          {pageSizeOptions.map((n) => <option key={n} value={n}>{n} / page</option>)}
        </select>
      </div>

      <div className="flex items-center gap-1">
        <button onClick={prev} disabled={page === 1} className="pg-btn" aria-label="Previous page">
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        {pageWindow(page, pageCount).map((p, i) =>
          p === '…'
            ? <span key={`e${i}`} className="px-1.5 select-none">…</span>
            : <button key={p} onClick={() => setPage(p)} className="pg-btn tabular"
                style={p === page
                  ? { background: 'var(--accent)', color: '#001016', borderColor: 'var(--accent)', fontWeight: 700 }
                  : undefined}>
                {p}
              </button>,
        )}
        <button onClick={next} disabled={page === pageCount} className="pg-btn" aria-label="Next page">
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* button styling kept local so the component is drop-in anywhere */}
      <style>{`
        .pg-btn {
          min-width: 28px; height: 28px;
          display: inline-flex; align-items: center; justify-content: center;
          padding: 0 0.4rem; border-radius: 7px;
          border: 1px solid var(--border); background: var(--bg-2); color: var(--fg-2);
          transition: color .15s, border-color .15s, background .15s;
        }
        .pg-btn:hover:not(:disabled) { color: var(--accent); border-color: var(--accent); }
        .pg-btn:disabled { opacity: .4; cursor: not-allowed; }
      `}</style>
    </div>
  );
}
