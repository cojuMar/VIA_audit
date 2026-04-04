import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Download, Search, Filter } from 'lucide-react';
import { getFindings } from '../api';
import type { Severity, FindingStatus, MonitoringFinding } from '../types';

interface Props {
  tenantId: string;
  findingType?: string;
  title?: string;
}

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info'];
const STATUSES: FindingStatus[] = ['open', 'acknowledged', 'resolved', 'false_positive'];
const PAGE_SIZE = 25;

function severityBadge(s: Severity) {
  const cls = {
    critical: 'bg-red-700 text-white',
    high: 'bg-orange-600 text-white',
    medium: 'bg-yellow-600 text-white',
    low: 'bg-blue-500 text-white',
    info: 'bg-gray-600 text-white',
  }[s];
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${cls}`}>{s}</span>
  );
}

function statusBadge(s: FindingStatus) {
  const cls = {
    open: 'bg-red-900/40 text-red-300 border border-red-800',
    acknowledged: 'bg-yellow-900/40 text-yellow-300 border border-yellow-800',
    resolved: 'bg-green-900/40 text-green-300 border border-green-800',
    false_positive: 'bg-gray-700 text-gray-300 border border-gray-600',
  }[s];
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium capitalize ${cls}`}>
      {s.replace('_', ' ')}
    </span>
  );
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function RiskBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-500">—</span>;
  const pct = Math.min(100, (score / 10) * 100);
  const color = score >= 8 ? 'bg-red-500' : score >= 6 ? 'bg-orange-500' : score >= 4 ? 'bg-yellow-500' : 'bg-blue-500';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-2 rounded bg-gray-700 overflow-hidden">
        <div className={`h-full rounded ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400">{score.toFixed(1)}</span>
    </div>
  );
}

function EvidenceBlock({ evidence }: { evidence: Record<string, unknown> }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
      {Object.entries(evidence).map(([k, v]) => (
        <div key={k} className="bg-gray-800 rounded p-2">
          <p className="text-xs text-gray-500 mb-0.5">{k}</p>
          <p className="text-xs text-gray-200 font-mono break-all">
            {typeof v === 'object' ? JSON.stringify(v) : String(v)}
          </p>
        </div>
      ))}
    </div>
  );
}

export default function FindingsTable({ tenantId, findingType, title }: Props) {
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<FindingStatus | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState(findingType ?? '');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data: findings, isLoading } = useQuery({
    queryKey: ['findings', tenantId],
    queryFn: () => getFindings(tenantId, { limit: 1000 }),
  });

  const filtered = useMemo(() => {
    if (!findings) return [];
    return findings.filter(f => {
      if (severityFilter !== 'all' && f.severity !== severityFilter) return false;
      if (statusFilter !== 'all' && f.status !== statusFilter) return false;
      if (typeFilter && !f.finding_type.includes(typeFilter)) return false;
      if (search) {
        const s = search.toLowerCase();
        return (
          f.title.toLowerCase().includes(s) ||
          (f.entity_name?.toLowerCase().includes(s) ?? false) ||
          (f.entity_id?.toLowerCase().includes(s) ?? false)
        );
      }
      return true;
    });
  }, [findings, severityFilter, statusFilter, typeFilter, search]);

  const allTypes = useMemo(() => {
    if (!findings) return [];
    return [...new Set(findings.map(f => f.finding_type))].sort();
  }, [findings]);

  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const exportCSV = () => {
    const headers = ['id', 'severity', 'title', 'entity_type', 'entity_id', 'entity_name', 'risk_score', 'status', 'finding_type', 'detected_at'];
    const rows = filtered.map(f =>
      headers.map(h => {
        const val = (f as unknown as Record<string, unknown>)[h];
        return `"${String(val ?? '').replace(/"/g, '""')}"`;
      }).join(',')
    );
    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'findings.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">{title ?? 'All Findings'}</h2>
          <p className="text-gray-400 text-sm mt-0.5">
            {isLoading ? 'Loading...' : `${filtered.length} of ${findings?.length ?? 0} findings`}
          </p>
        </div>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg text-sm transition-colors"
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      {/* Filter Bar */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
        {/* Search */}
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search by title or entity..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            className="w-full pl-9 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="flex flex-wrap gap-3">
          {/* Severity chips */}
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => { setSeverityFilter('all'); setPage(0); }}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${severityFilter === 'all' ? 'bg-gray-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
            >
              All Severity
            </button>
            {SEVERITIES.map(s => {
              const cls = {
                critical: severityFilter === s ? 'bg-red-700 text-white' : 'bg-red-900/30 text-red-400 hover:bg-red-800/40',
                high: severityFilter === s ? 'bg-orange-600 text-white' : 'bg-orange-900/30 text-orange-400 hover:bg-orange-800/40',
                medium: severityFilter === s ? 'bg-yellow-600 text-white' : 'bg-yellow-900/30 text-yellow-400 hover:bg-yellow-800/40',
                low: severityFilter === s ? 'bg-blue-600 text-white' : 'bg-blue-900/30 text-blue-400 hover:bg-blue-800/40',
                info: severityFilter === s ? 'bg-gray-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600',
              }[s];
              return (
                <button
                  key={s}
                  onClick={() => { setSeverityFilter(s); setPage(0); }}
                  className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${cls}`}
                >
                  {s}
                </button>
              );
            })}
          </div>

          {/* Status chips */}
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => { setStatusFilter('all'); setPage(0); }}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${statusFilter === 'all' ? 'bg-gray-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
            >
              All Status
            </button>
            {STATUSES.map(s => (
              <button
                key={s}
                onClick={() => { setStatusFilter(s); setPage(0); }}
                className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${statusFilter === s ? 'bg-indigo-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'}`}
              >
                {s.replace('_', ' ')}
              </button>
            ))}
          </div>

          {/* Type dropdown */}
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-gray-400" />
            <select
              value={typeFilter}
              onChange={e => { setTypeFilter(e.target.value); setPage(0); }}
              className="bg-gray-700 border border-gray-600 text-gray-200 text-xs rounded-lg px-2 py-1 focus:outline-none focus:border-indigo-500"
            >
              <option value="">All Types</option>
              {allTypes.map(t => (
                <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-850">
                <th className="text-left px-4 py-3 text-gray-400 font-medium w-8"></th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium w-28">Severity</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">Title</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium">Entity</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium w-32">Risk Score</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium w-28">Detected</th>
                <th className="text-left px-4 py-3 text-gray-400 font-medium w-28">Status</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-gray-500">Loading findings...</td></tr>
              ) : paginated.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-gray-500">No findings match the current filters</td></tr>
              ) : paginated.map(f => (
                <>
                  <tr
                    key={f.id}
                    className="border-b border-gray-700/50 hover:bg-gray-750 cursor-pointer"
                    onClick={() => toggleExpand(f.id)}
                  >
                    <td className="px-4 py-3 text-gray-500">
                      {expanded.has(f.id)
                        ? <ChevronDown size={14} />
                        : <ChevronRight size={14} />
                      }
                    </td>
                    <td className="px-4 py-3">{severityBadge(f.severity)}</td>
                    <td className="px-4 py-3 text-gray-200 font-medium max-w-xs">
                      <p className="line-clamp-2">{f.title}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{f.finding_type.replace(/_/g, ' ')}</p>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">
                      {f.entity_type && <p className="text-gray-500">{f.entity_type}</p>}
                      <p>{f.entity_name ?? f.entity_id ?? '—'}</p>
                    </td>
                    <td className="px-4 py-3"><RiskBar score={f.risk_score} /></td>
                    <td className="px-4 py-3 text-gray-400">{relativeTime(f.detected_at)}</td>
                    <td className="px-4 py-3">{statusBadge(f.status)}</td>
                  </tr>
                  {expanded.has(f.id) && (
                    <tr key={`${f.id}-exp`} className="bg-gray-850 border-b border-gray-700/50">
                      <td colSpan={7} className="px-6 py-4">
                        <div className="space-y-3">
                          <div>
                            <p className="text-xs text-gray-500 mb-1 uppercase tracking-wide">Description</p>
                            <p className="text-sm text-gray-300">{f.description}</p>
                          </div>
                          {Object.keys(f.evidence).length > 0 && (
                            <div>
                              <p className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Evidence</p>
                              <EvidenceBlock evidence={f.evidence} />
                            </div>
                          )}
                          <p className="text-xs text-gray-600">Finding ID: {f.id} | Run ID: {f.run_id}</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-700">
            <p className="text-sm text-gray-400">
              Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
            </p>
            <div className="flex gap-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
                className="px-3 py-1.5 rounded bg-gray-700 text-gray-300 text-sm disabled:opacity-40 hover:bg-gray-600 transition-colors"
              >
                Previous
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const pg = Math.max(0, Math.min(page - 2, totalPages - 5)) + i;
                return (
                  <button
                    key={pg}
                    onClick={() => setPage(pg)}
                    className={`px-3 py-1.5 rounded text-sm transition-colors ${pg === page ? 'bg-indigo-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
                  >
                    {pg + 1}
                  </button>
                );
              })}
              <button
                disabled={page >= totalPages - 1}
                onClick={() => setPage(p => p + 1)}
                className="px-3 py-1.5 rounded bg-gray-700 text-gray-300 text-sm disabled:opacity-40 hover:bg-gray-600 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
