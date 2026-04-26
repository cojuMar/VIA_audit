/**
 * DataTable — lifted out of pbc-ui's table component.
 *
 * Generic over the row shape. Each column declares a `key` (for React),
 * a `header` label, and a `cell` accessor. Optional `sortKey` enables
 * ascending/descending sort with `aria-sort` set on the header so screen
 * readers announce the current sort.
 */
import { type ReactNode, useMemo, useState } from 'react';

export interface Column<Row> {
  key: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  /** If provided, header is clickable and toggles sort. */
  sortKey?: (row: Row) => string | number | Date | null | undefined;
  /** Optional aria-label override for the header (useful when `header` is an icon). */
  ariaLabel?: string;
}

export interface DataTableProps<Row> {
  rows: Row[];
  columns: Column<Row>[];
  rowKey: (row: Row) => string;
  emptyState?: ReactNode;
  caption?: string;
}

type SortDir = 'asc' | 'desc';

export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  emptyState = 'No data',
  caption,
}: DataTableProps<Row>) {
  const [sortIdx, setSortIdx] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const sorted = useMemo(() => {
    if (sortIdx === null) return rows;
    const col = columns[sortIdx];
    if (!col?.sortKey) return rows;
    const accessor = col.sortKey;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, columns, sortIdx, sortDir]);

  const onHeaderClick = (idx: number) => {
    const col = columns[idx];
    if (!col.sortKey) return;
    if (sortIdx === idx) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortIdx(idx);
      setSortDir('asc');
    }
  };

  if (rows.length === 0) {
    return <div role="status">{emptyState}</div>;
  }

  return (
    <table
      style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}
    >
      {caption && <caption style={{ textAlign: 'left', padding: 8 }}>{caption}</caption>}
      <thead>
        <tr>
          {columns.map((col, idx) => {
            const isSorted = sortIdx === idx;
            const ariaSort: 'none' | 'ascending' | 'descending' = !col.sortKey
              ? 'none'
              : isSorted
                ? sortDir === 'asc'
                  ? 'ascending'
                  : 'descending'
                : 'none';
            return (
              <th
                key={col.key}
                scope="col"
                aria-sort={ariaSort}
                aria-label={col.ariaLabel}
                onClick={() => onHeaderClick(idx)}
                style={{
                  textAlign: 'left',
                  padding: '8px 12px',
                  borderBottom: '1px solid #e5e7eb',
                  cursor: col.sortKey ? 'pointer' : 'default',
                  userSelect: 'none',
                }}
              >
                {col.header}
                {isSorted && (sortDir === 'asc' ? ' ▲' : ' ▼')}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((col) => (
              <td
                key={col.key}
                style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9' }}
              >
                {col.cell(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
