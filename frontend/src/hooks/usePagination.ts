import { useMemo, useState, useEffect } from 'react';

export interface Pagination<T> {
  page: number;
  pageSize: number;
  pageCount: number;
  total: number;
  start: number;          // 1-based index of first row on this page
  end: number;            // 1-based index of last row on this page
  pageItems: T[];         // the slice to render
  setPage: (p: number) => void;
  setPageSize: (n: number) => void;
  next: () => void;
  prev: () => void;
}

/**
 * Client-side pagination over an in-memory array. Re-clamps to a valid page
 * whenever the data shrinks (e.g. after a search filter) so you never land on
 * an empty page.
 */
export function usePagination<T>(items: T[], initialPageSize = 12): Pagination<T> {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);

  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  // keep the current page valid when data / pageSize changes
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [pageCount, page]);

  const pageItems = useMemo(() => {
    const from = (page - 1) * pageSize;
    return items.slice(from, from + pageSize);
  }, [items, page, pageSize]);

  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);

  return {
    page, pageSize, pageCount, total, start, end, pageItems,
    setPage: (p) => setPage(Math.min(Math.max(1, p), pageCount)),
    setPageSize: (n) => { setPageSize(n); setPage(1); },
    next: () => setPage((p) => Math.min(p + 1, pageCount)),
    prev: () => setPage((p) => Math.max(p - 1, 1)),
  };
}
