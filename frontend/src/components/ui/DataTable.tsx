/**
 * A sortable table with client-side or server-side pagination. Scrolls horizontally
 * on small screens instead of squashing columns.
 */
import React, { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Button } from './Button';
import { EmptyState, SkeletonRows } from './feedback';

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  render: (row: T) => React.ReactNode;
  /** Enables sorting on this column. */
  sortValue?: (row: T) => string | number | null | undefined;
  className?: string;
  align?: 'left' | 'right';
}

interface ServerPagination {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  empty?: React.ReactNode;
  onRowClick?: (row: T) => void;
  /** Client-side page size (ignored with server pagination). */
  pageSize?: number;
  pagination?: ServerPagination;
  initialSort?: { key: string; dir: 'asc' | 'desc' };
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  empty,
  onRowClick,
  pageSize = 25,
  pagination,
  initialSort,
  className,
}: DataTableProps<T>) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [clientPage, setClientPage] = useState(1);

  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sort?.key);
    if (!sort || !column?.sortValue) return rows;
    const value = column.sortValue;
    return [...rows].sort((a, b) => {
      const va = value(a);
      const vb = value(b);
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      const cmp = va < vb ? -1 : 1;
      return sort.dir === 'asc' ? cmp : -cmp;
    });
  }, [rows, sort, columns]);

  const page = pagination ? pagination.page : clientPage;
  const size = pagination ? pagination.pageSize : pageSize;
  const total = pagination ? pagination.total : sorted.length;
  const pages = Math.max(1, Math.ceil(total / size));
  const visible = pagination ? sorted : sorted.slice((page - 1) * size, page * size);
  const goTo = (p: number) => (pagination ? pagination.onPageChange(p) : setClientPage(p));

  const toggleSort = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));

  if (loading) return <SkeletonRows rows={6} className="p-4" />;
  if (!rows.length) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;

  return (
    <div className={className}>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-card-border text-xs uppercase tracking-wider text-muted-foreground">
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className={cn('px-4 py-3 font-medium whitespace-nowrap', c.align === 'right' && 'text-right', c.className)}
                  aria-sort={sort?.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(c.key)}
                      className="inline-flex items-center gap-1 hover:text-foreground cursor-pointer"
                    >
                      {c.header}
                      {sort?.key === c.key &&
                        (sort.dir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-card-border">
            {visible.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === 'Enter') onRowClick(row);
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                className={cn('transition-colors', onRowClick && 'cursor-pointer hover:bg-white/[0.02] focus:bg-white/[0.03] focus:outline-none')}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cn('px-4 py-3 align-top', c.align === 'right' && 'text-right', c.className)}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-between gap-2 border-t border-card-border px-4 py-3 text-sm text-muted-foreground">
          <span>
            {(page - 1) * size + 1}–{Math.min(page * size, total)} of {total}
          </span>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" onClick={() => goTo(page - 1)} disabled={page <= 1} aria-label="Previous page">
              <ChevronLeft size={16} />
            </Button>
            <Button variant="ghost" size="icon" onClick={() => goTo(page + 1)} disabled={page >= pages} aria-label="Next page">
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
