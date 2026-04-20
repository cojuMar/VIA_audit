/**
 * DataTable<T> — VIA Sprint 5 Table Standard
 *
 * Generic, typed table component with:
 *   - Click-to-sort column headers with aria-sort + chevron icons
 *   - Sticky thead
 *   - Loading skeleton rows (configurable count)
 *   - Empty state (icon + message)
 *   - Optional client-side search across configurable fields
 *   - Optional pagination
 *   - Optional expandable rows
 *   - Optional CSV export
 *   - Toolbar slot for additional controls
 */

import { useState, useMemo, type ReactNode } from 'react';
import {
  ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight,
  Search, Download, Inbox,
} from 'lucide-react';

// ── Column definition ────────────────────────────────────────────────────────

export interface ColDef<T> {
  /** Unique key used for sort state tracking */
  key: string;
  /** Header label text */
  header: string;
  /** Cell renderer */
  render: (row: T, rowIdx: number) => ReactNode;
  /**
   * If provided the column becomes sortable.
   * Returns negative / zero / positive like Array.prototype.sort.
   */
  sortFn?: (a: T, b: T) => number;
  /** Optional CSS width (e.g. '80px', '12%') */
  width?: string;
  /** Text alignment for th and td */
  align?: 'left' | 'right' | 'center';
}

// ── Props ────────────────────────────────────────────────────────────────────

export interface DataTableProps<T> {
  cols: ColDef<T>[];
  rows: T[];
  /** Must return a stable unique string for each row */
  rowKey: (row: T) => string;

  // Loading state
  loading?: boolean;
  skeletonRows?: number;

  // Empty state
  emptyIcon?: ReactNode;
  emptyMessage?: string;
  emptySubMessage?: string;

  // Search (client-side)
  searchable?: boolean;
  searchPlaceholder?: string;
  /** Return all string fields to match against. If omitted, no matching. */
  searchFields?: (row: T) => string[];

  // Pagination
  pageSize?: number;

  // Expandable rows — renders a sub-row below the main row
  expandRender?: (row: T) => ReactNode;

  // CSV export
  exportFilename?: string;
  /** Map a row to a flat Record for CSV. If omitted export is disabled. */
  exportRow?: (row: T) => Record<string, string | number | boolean | null | undefined>;

  // Extra toolbar nodes (rendered left of search/export)
  toolbar?: ReactNode;

  className?: string;
}

// ── Sort icon ────────────────────────────────────────────────────────────────

function SortIcon({ dir }: { dir: 'asc' | 'desc' | null }) {
  if (dir === 'asc')  return <ChevronUp   className="h-3 w-3 sort-icon" />;
  if (dir === 'desc') return <ChevronDown className="h-3 w-3 sort-icon" />;
  return <ChevronsUpDown className="h-3 w-3 sort-icon" />;
}

// ── CSV export ───────────────────────────────────────────────────────────────

function exportCSV<T>(
  rows: T[],
  exportRow: (r: T) => Record<string, string | number | boolean | null | undefined>,
  filename: string,
) {
  const mapped = rows.map(exportRow);
  if (mapped.length === 0) return;
  const headers = Object.keys(mapped[0]);
  const lines = [
    headers.join(','),
    ...mapped.map(r =>
      headers.map(h => {
        const v = r[h] ?? '';
        const s = String(v);
        return s.includes(',') || s.includes('"') || s.includes('\n')
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      }).join(',')
    ),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── DataTable ────────────────────────────────────────────────────────────────

export default function DataTable<T>({
  cols,
  rows,
  rowKey,
  loading   = false,
  skeletonRows = 5,
  emptyIcon,
  emptyMessage    = 'No records found',
  emptySubMessage = 'Try adjusting your filters or search query.',
  searchable = false,
  searchPlaceholder = 'Search…',
  searchFields,
  pageSize,
  expandRender,
  exportFilename,
  exportRow,
  toolbar,
  className = '',
}: DataTableProps<T>) {
  const [sortKey, setSortKey]   = useState<string | null>(null);
  const [sortDir, setSortDir]   = useState<'asc' | 'desc'>('asc');
  const [query,   setQuery]     = useState('');
  const [page,    setPage]      = useState(1);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggleSort(col: ColDef<T>) {
    if (!col.sortFn) return;
    if (sortKey === col.key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(col.key);
      setSortDir('asc');
    }
    setPage(1);
  }

  function toggleExpand(key: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  // Search filter
  const filtered = useMemo(() => {
    if (!query.trim() || !searchFields) return rows;
    const q = query.toLowerCase();
    return rows.filter(r =>
      searchFields(r).some(f => f?.toLowerCase().includes(q))
    );
  }, [rows, query, searchFields]);

  // Sort
  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    const col = cols.find(c => c.key === sortKey);
    if (!col?.sortFn) return filtered;
    const fn = col.sortFn;
    return [...filtered].sort((a, b) => sortDir === 'asc' ? fn(a, b) : fn(b, a));
  }, [filtered, sortKey, sortDir, cols]);

  // Pagination
  const totalPages = pageSize ? Math.max(1, Math.ceil(sorted.length / pageSize)) : 1;
  const safePage   = Math.min(page, totalPages);
  const visible    = pageSize
    ? sorted.slice((safePage - 1) * pageSize, safePage * pageSize)
    : sorted;

  const hasToolbar = toolbar || searchable || (exportFilename && exportRow);

  return (
    <div className={`flex flex-col ${className}`}>

      {/* Toolbar */}
      {hasToolbar && (
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          {toolbar}

          {searchable && (
            <div className="relative flex-1 min-w-[160px] max-w-[280px]">
              <Search
                className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5"
                style={{ color: 'var(--via-text-3)' }}
              />
              <input
                type="search"
                value={query}
                onChange={e => { setQuery(e.target.value); setPage(1); }}
                placeholder={searchPlaceholder}
                className="form-input pl-8 text-xs py-1.5"
                style={{ height: 32 }}
              />
            </div>
          )}

          {exportFilename && exportRow && (
            <button
              className="btn-secondary text-xs"
              style={{ height: 32 }}
              onClick={() => exportCSV(sorted, exportRow, exportFilename)}
            >
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </button>
          )}
        </div>
      )}

      {/* Table container */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto overflow-y-auto" style={{ maxHeight: 'var(--dt-max-height, none)' }}>
          <table className="via-table">
            <thead>
              <tr>
                {expandRender && <th style={{ width: 32 }} />}
                {cols.map(col => {
                  const isSortable = !!col.sortFn;
                  const isActive   = sortKey === col.key;
                  return (
                    <th
                      key={col.key}
                      className={[
                        isSortable ? 'sortable' : '',
                        isActive   ? 'sort-active' : '',
                      ].filter(Boolean).join(' ')}
                      style={{
                        width: col.width,
                        textAlign: col.align ?? 'left',
                      }}
                      onClick={() => toggleSort(col)}
                      aria-sort={
                        isActive ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'
                      }
                    >
                      {col.header}
                      {isSortable && (
                        <SortIcon dir={isActive ? sortDir : null} />
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>

            <tbody>
              {/* Loading skeleton */}
              {loading && Array.from({ length: skeletonRows }).map((_, ri) => (
                <tr key={`skel-${ri}`}>
                  {expandRender && <td />}
                  {cols.map((col, ci) => (
                    <td key={col.key}>
                      <div
                        className="skeleton-cell"
                        style={{ width: ci === 0 ? '70%' : ci === cols.length - 1 ? '50%' : '80%' }}
                      />
                    </td>
                  ))}
                </tr>
              ))}

              {/* Empty state */}
              {!loading && visible.length === 0 && (
                <tr>
                  <td
                    colSpan={cols.length + (expandRender ? 1 : 0)}
                    style={{ textAlign: 'center', padding: '40px 20px' }}
                  >
                    <div
                      className="flex flex-col items-center gap-2"
                      style={{ color: 'var(--via-text-3)' }}
                    >
                      {emptyIcon ?? <Inbox className="h-8 w-8 opacity-40" />}
                      <p className="text-sm font-medium" style={{ color: 'var(--via-text-2)' }}>
                        {emptyMessage}
                      </p>
                      {emptySubMessage && (
                        <p className="text-xs">{emptySubMessage}</p>
                      )}
                    </div>
                  </td>
                </tr>
              )}

              {/* Data rows */}
              {!loading && visible.map((row, ri) => {
                const key        = rowKey(row);
                const isExpanded = expanded.has(key);
                return [
                  <tr
                    key={key}
                    className={isExpanded ? 'expanded-row' : ''}
                    style={expandRender ? { cursor: 'pointer' } : undefined}
                    onClick={expandRender ? () => toggleExpand(key) : undefined}
                  >
                    {expandRender && (
                      <td style={{ width: 32, paddingRight: 0 }}>
                        {isExpanded
                          ? <ChevronDown className="h-3.5 w-3.5" style={{ color: 'var(--via-text-3)' }} />
                          : <ChevronRight className="h-3.5 w-3.5" style={{ color: 'var(--via-text-3)' }} />
                        }
                      </td>
                    )}
                    {cols.map(col => (
                      <td
                        key={col.key}
                        style={{ textAlign: col.align ?? 'left' }}
                        onClick={expandRender ? e => e.stopPropagation() : undefined}
                      >
                        {col.render(row, ri)}
                      </td>
                    ))}
                  </tr>,

                  isExpanded && expandRender ? (
                    <tr key={`${key}-expand`} className="expand-content">
                      <td
                        colSpan={cols.length + 1}
                        onClick={e => e.stopPropagation()}
                        style={{ padding: '12px 20px' }}
                      >
                        {expandRender(row)}
                      </td>
                    </tr>
                  ) : null,
                ];
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pageSize && !loading && sorted.length > 0 && (
          <div className="via-table-pagination">
            <span>
              {sorted.length === rows.length
                ? `${rows.length} record${rows.length !== 1 ? 's' : ''}`
                : `${sorted.length} of ${rows.length} records`
              }
            </span>
            <div className="flex items-center gap-1">
              <span className="mr-2">
                Page {safePage} of {totalPages}
              </span>
              <button
                className="btn-secondary"
                style={{ padding: '2px 6px', height: 26 }}
                disabled={safePage <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                aria-label="Previous page"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button
                className="btn-secondary"
                style={{ padding: '2px 6px', height: 26 }}
                disabled={safePage >= totalPages}
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                aria-label="Next page"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
