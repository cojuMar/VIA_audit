import {
  useState, useEffect, useRef, useCallback, type ReactNode, type KeyboardEvent,
} from 'react';
import {
  Search, X, Calendar, AlertCircle, BarChart2, FileText,
  ClipboardList, Users, ArrowUpRight, Loader2, Command,
} from 'lucide-react';
import type { AuthUser } from '../contexts/AuthContext';
import { moduleUrl } from '../data/moduleUrl';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SearchResult {
  type: string;
  id: string;
  title: string;
  subtitle: string;
  meta: string;
  module_port: number;
  module_id: string;
}

// ── Type metadata ─────────────────────────────────────────────────────────────

interface TypeMeta {
  label: string;
  icon: ReactNode;
  color: string;        // CSS color value
  bgColor: string;
}

const TYPE_META: Record<string, TypeMeta> = {
  engagement: {
    label: 'Engagement',
    icon: <Calendar className="h-3.5 w-3.5" />,
    color: 'var(--status-info)',
    bgColor: 'color-mix(in srgb, var(--status-info) 12%, transparent)',
  },
  issue: {
    label: 'Issue',
    icon: <AlertCircle className="h-3.5 w-3.5" />,
    color: 'var(--status-danger)',
    bgColor: 'color-mix(in srgb, var(--status-danger) 12%, transparent)',
  },
  risk: {
    label: 'Risk',
    icon: <BarChart2 className="h-3.5 w-3.5" />,
    color: 'var(--status-warning)',
    bgColor: 'color-mix(in srgb, var(--status-warning) 12%, transparent)',
  },
  workpaper: {
    label: 'Workpaper',
    icon: <FileText className="h-3.5 w-3.5" />,
    color: 'var(--brand)',
    bgColor: 'var(--brand-subtle)',
  },
  pbc_request: {
    label: 'PBC Request',
    icon: <ClipboardList className="h-3.5 w-3.5" />,
    color: 'var(--status-success)',
    bgColor: 'color-mix(in srgb, var(--status-success) 12%, transparent)',
  },
  user: {
    label: 'User',
    icon: <Users className="h-3.5 w-3.5" />,
    color: 'color-mix(in srgb, var(--brand) 70%, var(--status-info))',
    bgColor: 'color-mix(in srgb, var(--brand) 10%, transparent)',
  },
};

function getTypeMeta(type: string): TypeMeta {
  return TYPE_META[type] ?? {
    label: type,
    icon: <Search className="h-3.5 w-3.5" />,
    color: 'var(--ink-muted)',
    bgColor: 'var(--surface-raised)',
  };
}

// ── Text highlight ────────────────────────────────────────────────────────────

function HighlightedText({ text, query }: { text: string; query: string }) {
  if (!query.trim() || !text) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark
        style={{
          backgroundColor: 'color-mix(in srgb, var(--brand) 25%, transparent)',
          color: 'inherit',
          borderRadius: '2px',
          padding: '0 1px',
        }}
      >
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

// ── Result row ────────────────────────────────────────────────────────────────

interface ResultRowProps {
  result: SearchResult;
  query: string;
  isFocused: boolean;
  onMouseEnter: () => void;
  onClick: () => void;
}

function ResultRow({ result, query, isFocused, onMouseEnter, onClick }: ResultRowProps) {
  const meta = getTypeMeta(result.type);

  return (
    <button
      onMouseEnter={onMouseEnter}
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors"
      style={{
        backgroundColor: isFocused ? 'var(--brand-subtle)' : 'transparent',
        borderLeft: isFocused ? '2px solid var(--brand)' : '2px solid transparent',
      }}
    >
      {/* Type icon */}
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
        style={{ backgroundColor: meta.bgColor, color: meta.color }}
      >
        {meta.icon}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--ink-primary)' }}>
          <HighlightedText text={result.title} query={query} />
        </p>
        {result.subtitle && (
          <p className="text-[11px] truncate mt-0.5" style={{ color: 'var(--ink-muted)' }}>
            {result.subtitle}
          </p>
        )}
      </div>

      {/* Right side: meta + icon */}
      <div className="flex items-center gap-2 shrink-0">
        {result.meta && (
          <span
            className="hidden sm:inline text-[10px] font-medium px-1.5 py-0.5 rounded capitalize"
            style={{ backgroundColor: meta.bgColor, color: meta.color }}
          >
            {result.meta}
          </span>
        )}
        {result.module_port > 0 && (
          <ArrowUpRight
            className="h-3.5 w-3.5 opacity-40"
            style={{ color: 'var(--ink-muted)' }}
          />
        )}
      </div>
    </button>
  );
}

// ── Type section header ───────────────────────────────────────────────────────

function SectionHeader({ type, count }: { type: string; count: number }) {
  const meta = getTypeMeta(type);
  return (
    <div
      className="flex items-center gap-2 px-4 py-1.5"
      style={{ borderBottom: '1px solid var(--line)' }}
    >
      <span style={{ color: meta.color }}>{meta.icon}</span>
      <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--ink-muted)' }}>
        {meta.label}s
      </span>
      <span
        className="text-[10px] font-semibold px-1.5 rounded-full"
        style={{ backgroundColor: meta.bgColor, color: meta.color }}
      >
        {count}
      </span>
    </div>
  );
}

// ── Empty / idle states ───────────────────────────────────────────────────────

function EmptyState({ query, loading }: { query: string; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-10 gap-2" style={{ color: 'var(--ink-muted)' }}>
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm">Searching…</span>
      </div>
    );
  }

  if (query.length >= 2) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center px-4">
        <Search className="h-8 w-8 mb-3" style={{ color: 'var(--ink-muted)' }} />
        <p className="text-sm font-medium" style={{ color: 'var(--ink-secondary)' }}>
          No results for "{query}"
        </p>
        <p className="text-[11px] mt-1" style={{ color: 'var(--ink-muted)' }}>
          Try different keywords or check spelling
        </p>
      </div>
    );
  }

  return (
    <div className="px-4 py-6 space-y-3">
      <p className="text-[11px] font-bold uppercase tracking-widest" style={{ color: 'var(--ink-muted)' }}>
        Search across
      </p>
      <div className="flex flex-wrap gap-2">
        {Object.entries(TYPE_META).map(([key, m]) => (
          <span
            key={key}
            className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium"
            style={{ backgroundColor: m.bgColor, color: m.color }}
          >
            {m.icon}
            {m.label}s
          </span>
        ))}
      </div>
      <p className="text-[11px] mt-2" style={{ color: 'var(--ink-muted)' }}>
        Type at least 2 characters to search
      </p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onClose: () => void;
  user: AuthUser;
}

const RESULT_TYPES = ['engagement', 'issue', 'risk', 'workpaper', 'pbc_request', 'user'] as const;

export default function GlobalSearch({ open, onClose, user }: Props) {
  const inputRef                = useRef<HTMLInputElement>(null);
  const listRef                 = useRef<HTMLDivElement>(null);
  const [query,   setQuery]     = useState('');
  const [results, setResults]   = useState<SearchResult[]>([]);
  const [loading, setLoading]   = useState(false);
  const [focused, setFocused]   = useState(-1);

  // Auto-focus input when opened; clear on close
  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setFocused(-1);
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!open) return;
    if (query.length < 2) { setResults([]); setLoading(false); return; }

    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await fetch('/auth/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, tenant_id: user.tenant_id, limit: 6 }),
        });
        if (res.ok) {
          const data = await res.json();
          setResults(data.results ?? []);
          setFocused(-1);
        }
      } catch (err) {
        // Surface — never swallow. Toast wiring lands once @via/ui-kit's
        // ToasterProvider is mounted at the hub-ui root (Sprint 27).
        console.warn('[GlobalSearch] search failed:', err);
      }
      finally { setLoading(false); }
    }, 300);

    return () => clearTimeout(t);
  }, [query, open, user.tenant_id]);

  // Navigate to result
  const openResult = useCallback((result: SearchResult) => {
    if (result.module_port > 0) {
      window.open(
        moduleUrl({ id: result.module_id, port: result.module_port }),
        '_blank',
        'noopener',
      );
    }
    onClose();
  }, [onClose]);

  // Keyboard navigation
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') { onClose(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocused(f => Math.min(f + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocused(f => Math.max(f - 1, -1));
    } else if (e.key === 'Enter' && focused >= 0 && results[focused]) {
      openResult(results[focused]);
    }
  }

  // Scroll focused item into view
  useEffect(() => {
    if (focused < 0 || !listRef.current) return;
    const el = listRef.current.querySelector(`[data-idx="${focused}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [focused]);

  if (!open) return null;

  // Group results by type in canonical order
  const grouped = RESULT_TYPES.reduce<Record<string, SearchResult[]>>((acc, t) => {
    acc[t] = results.filter(r => r.type === t);
    return acc;
  }, {} as Record<string, SearchResult[]>);

  // Flat ordered list for keyboard navigation
  const flat: SearchResult[] = RESULT_TYPES.flatMap(t => grouped[t]);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60]"
        style={{ backgroundColor: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(2px)' }}
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className="fixed z-[61] left-1/2 top-[12vh] -translate-x-1/2 w-full"
        style={{ maxWidth: '600px', padding: '0 16px' }}
        role="dialog"
        aria-label="Global search"
        aria-modal="true"
      >
        <div
          className="overflow-hidden rounded-2xl"
          style={{
            backgroundColor: 'var(--surface-overlay)',
            border: '1px solid var(--line-focus)',
            boxShadow: '0 24px 64px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.2)',
          }}
        >
          {/* Search input */}
          <div
            className="flex items-center gap-3 px-4"
            style={{ borderBottom: '1px solid var(--line)' }}
          >
            <Search className="h-4 w-4 shrink-0" style={{ color: 'var(--ink-muted)' }} />
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search engagements, issues, risks, workpapers…"
              className="flex-1 bg-transparent py-4 text-sm outline-none"
              style={{ color: 'var(--ink-primary)' }}
              autoComplete="off"
              spellCheck={false}
            />
            <div className="flex items-center gap-2 shrink-0">
              {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: 'var(--ink-muted)' }} />}
              {query && (
                <button
                  onClick={() => { setQuery(''); setResults([]); inputRef.current?.focus(); }}
                  className="flex h-5 w-5 items-center justify-center rounded transition-colors"
                  style={{ color: 'var(--ink-muted)' }}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
              <kbd
                className="hidden sm:flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium"
                style={{
                  backgroundColor: 'var(--surface-raised)',
                  color: 'var(--ink-muted)',
                  border: '1px solid var(--line)',
                }}
              >
                <Command className="h-2.5 w-2.5" />
                K
              </kbd>
            </div>
          </div>

          {/* Results area */}
          <div
            ref={listRef}
            style={{ maxHeight: '420px', overflowY: 'auto' }}
          >
            {flat.length === 0 ? (
              <EmptyState query={query} loading={loading && query.length >= 2} />
            ) : (
              <>
                {RESULT_TYPES.map(type => {
                  const group = grouped[type];
                  if (!group || group.length === 0) return null;
                  return (
                    <div key={type}>
                      <SectionHeader type={type} count={group.length} />
                      {group.map(result => {
                        const idx = flat.indexOf(result);
                        return (
                          <div key={result.id} data-idx={idx}>
                            <ResultRow
                              result={result}
                              query={query}
                              isFocused={focused === idx}
                              onMouseEnter={() => setFocused(idx)}
                              onClick={() => openResult(result)}
                            />
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </>
            )}
          </div>

          {/* Footer */}
          <div
            className="flex items-center justify-between px-4 py-2"
            style={{ borderTop: '1px solid var(--line)' }}
          >
            <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--ink-muted)' }}>
              <span className="flex items-center gap-1">
                <kbd className="rounded px-1 py-0.5 font-mono" style={{ backgroundColor: 'var(--surface-raised)', border: '1px solid var(--line)' }}>↑↓</kbd>
                Navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded px-1 py-0.5 font-mono" style={{ backgroundColor: 'var(--surface-raised)', border: '1px solid var(--line)' }}>↵</kbd>
                Open
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded px-1 py-0.5 font-mono" style={{ backgroundColor: 'var(--surface-raised)', border: '1px solid var(--line)' }}>Esc</kbd>
                Close
              </span>
            </div>
            {flat.length > 0 && (
              <p className="text-[10px]" style={{ color: 'var(--ink-muted)' }}>
                {flat.length} result{flat.length !== 1 ? 's' : ''}
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
