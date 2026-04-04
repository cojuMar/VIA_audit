import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Search, Sparkles, X, ChevronDown, ChevronUp } from 'lucide-react';
import {
  fetchEntities,
  fetchEntityTypes,
  fetchUniverseCoverage,
  createEntity,
  aiPrioritizeUniverse,
} from '../api';
import type { AuditEntity, AuditEntityType, UniverseCoverage } from '../types';

interface Props {
  tenantId: string;
}

function riskPillClass(score: number) {
  if (score >= 8) return 'bg-red-100 text-red-800';
  if (score >= 6) return 'bg-orange-100 text-orange-800';
  if (score >= 4) return 'bg-yellow-100 text-yellow-800';
  return 'bg-green-100 text-green-800';
}

function riskBand(score: number) {
  if (score >= 8) return 'critical';
  if (score >= 6) return 'high';
  if (score >= 4) return 'medium';
  return 'low';
}

type SortKey = 'name' | 'risk_score' | 'last_audit_date' | 'next_audit_due';
type SortDir = 'asc' | 'desc';

interface AiResult {
  entity_id: string;
  entity_name: string;
  priority_rank: number;
  rationale: string;
  risk_score: number;
}

export default function AuditUniverse({ tenantId: _tenantId }: Props) {
  const qc = useQueryClient();
  const currentYear = new Date().getFullYear();

  // Filters
  const [search, setSearch] = useState('');
  const [selectedType, setSelectedType] = useState('');
  const [minRisk, setMinRisk] = useState(0);
  const [maxRisk, setMaxRisk] = useState(10);
  const [inUniverseOnly, setInUniverseOnly] = useState(false);

  // Sorting
  const [sortKey, setSortKey] = useState<SortKey>('risk_score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerForm, setDrawerForm] = useState({
    name: '',
    description: '',
    entity_type_id: '',
    owner_name: '',
    owner_email: '',
    department: '',
    risk_score: 5,
    audit_frequency_months: 12,
    is_in_universe: true,
    tags: '',
  });

  // AI modal
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiResults, setAiResults] = useState<AiResult[]>([]);

  const { data: entityTypes = [] } = useQuery<AuditEntityType[]>({
    queryKey: ['entity-types'],
    queryFn: fetchEntityTypes,
  });

  const { data: entities = [], isLoading } = useQuery<AuditEntity[]>({
    queryKey: ['entities'],
    queryFn: () => fetchEntities(),
  });

  const { data: coverage } = useQuery<UniverseCoverage>({
    queryKey: ['universe-coverage', currentYear],
    queryFn: () => fetchUniverseCoverage(currentYear),
  });

  const createMutation = useMutation({
    mutationFn: createEntity,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['entities'] });
      setDrawerOpen(false);
      setDrawerForm({
        name: '',
        description: '',
        entity_type_id: '',
        owner_name: '',
        owner_email: '',
        department: '',
        risk_score: 5,
        audit_frequency_months: 12,
        is_in_universe: true,
        tags: '',
      });
    },
  });

  const aiMutation = useMutation({
    mutationFn: () => aiPrioritizeUniverse(20),
    onSuccess: (data: { prioritized: AiResult[] }) => {
      setAiResults(data.prioritized ?? []);
      setAiModalOpen(true);
    },
  });

  const filtered = useMemo(() => {
    let list = [...entities];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((e) => e.name.toLowerCase().includes(q));
    }
    if (selectedType) {
      list = list.filter((e) => e.entity_type_id === selectedType);
    }
    list = list.filter((e) => e.risk_score >= minRisk && e.risk_score <= maxRisk);
    if (inUniverseOnly) {
      list = list.filter((e) => e.is_in_universe);
    }
    list.sort((a, b) => {
      let aVal: string | number = '';
      let bVal: string | number = '';
      if (sortKey === 'name') { aVal = a.name; bVal = b.name; }
      else if (sortKey === 'risk_score') { aVal = a.risk_score; bVal = b.risk_score; }
      else if (sortKey === 'last_audit_date') { aVal = a.last_audit_date ?? ''; bVal = b.last_audit_date ?? ''; }
      else if (sortKey === 'next_audit_due') { aVal = a.next_audit_due ?? ''; bVal = b.next_audit_due ?? ''; }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [entities, search, selectedType, minRisk, maxRisk, inUniverseOnly, sortKey, sortDir]);

  // Risk distribution
  const bandCounts = useMemo(() => ({
    critical: entities.filter((e) => e.risk_score >= 8).length,
    high: entities.filter((e) => e.risk_score >= 6 && e.risk_score < 8).length,
    medium: entities.filter((e) => e.risk_score >= 4 && e.risk_score < 6).length,
    low: entities.filter((e) => e.risk_score < 4).length,
  }), [entities]);
  const maxBandCount = Math.max(...Object.values(bandCounts), 1);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return null;
    return sortDir === 'asc' ? <ChevronUp className="w-3 h-3 inline" /> : <ChevronDown className="w-3 h-3 inline" />;
  }

  const overdueCount = entities.filter(
    (e) => e.next_audit_due && new Date(e.next_audit_due) < new Date()
  ).length;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    createMutation.mutate({
      ...drawerForm,
      tags: drawerForm.tags.split(',').map((t) => t.trim()).filter(Boolean),
    });
  }

  return (
    <div className="space-y-5">
      {/* Coverage stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Entities', value: coverage?.total_entities ?? entities.length },
          { label: 'In Universe', value: entities.filter((e) => e.is_in_universe).length },
          { label: 'Coverage', value: `${(coverage?.coverage_pct ?? 0).toFixed(1)}%` },
          { label: 'Overdue for Audit', value: overdueCount },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm text-center">
            <div className="text-xl font-bold text-gray-900">{s.value}</div>
            <div className="text-xs text-gray-500 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Risk distribution bar */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
        <div className="text-sm font-semibold text-gray-700 mb-3">Risk Distribution</div>
        <div className="space-y-1.5">
          {([
            { label: 'Critical (8–10)', key: 'critical' as const, color: 'bg-red-400' },
            { label: 'High (6–8)', key: 'high' as const, color: 'bg-orange-400' },
            { label: 'Medium (4–6)', key: 'medium' as const, color: 'bg-yellow-400' },
            { label: 'Low (0–4)', key: 'low' as const, color: 'bg-green-400' },
          ] as const).map((band) => (
            <div key={band.key} className="flex items-center gap-2 text-xs">
              <div className="w-28 text-gray-600 shrink-0">{band.label}</div>
              <div className="flex-1 bg-gray-100 rounded h-4 overflow-hidden">
                <div
                  className={`${band.color} h-4 rounded transition-all`}
                  style={{ width: `${(bandCounts[band.key] / maxBandCount) * 100}%` }}
                />
              </div>
              <div className="w-6 text-right text-gray-500">{bandCounts[band.key]}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Filter bar + actions */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm flex flex-wrap gap-3 items-end">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search entities…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 pr-3 py-2 border border-gray-300 rounded-lg text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Entity Type</label>
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="border border-gray-300 rounded-lg text-sm px-2 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="">All Types</option>
            {entityTypes.map((t) => (
              <option key={t.id} value={t.id}>{t.display_name}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Risk Score: {minRisk}–{maxRisk}</label>
          <div className="flex gap-2 items-center">
            <input
              type="range"
              min={0}
              max={10}
              step={0.5}
              value={minRisk}
              onChange={(e) => setMinRisk(Number(e.target.value))}
              className="w-20 accent-indigo-600"
            />
            <span className="text-xs text-gray-400">to</span>
            <input
              type="range"
              min={0}
              max={10}
              step={0.5}
              value={maxRisk}
              onChange={(e) => setMaxRisk(Number(e.target.value))}
              className="w-20 accent-indigo-600"
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={inUniverseOnly}
            onChange={(e) => setInUniverseOnly(e.target.checked)}
            className="accent-indigo-600"
          />
          In Universe Only
        </label>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => aiMutation.mutate()}
            disabled={aiMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors disabled:opacity-60"
          >
            <Sparkles className="w-4 h-4" />
            AI Prioritize
          </button>
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Entity
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th
                className="text-left px-4 py-3 font-semibold text-gray-600 cursor-pointer select-none"
                onClick={() => toggleSort('name')}
              >
                Name <SortIcon k="name" />
              </th>
              <th className="text-left px-4 py-3 font-semibold text-gray-600">Type</th>
              <th className="text-left px-4 py-3 font-semibold text-gray-600">Department</th>
              <th
                className="text-left px-4 py-3 font-semibold text-gray-600 cursor-pointer select-none"
                onClick={() => toggleSort('risk_score')}
              >
                Risk <SortIcon k="risk_score" />
              </th>
              <th
                className="text-left px-4 py-3 font-semibold text-gray-600 cursor-pointer select-none"
                onClick={() => toggleSort('last_audit_date')}
              >
                Last Audit <SortIcon k="last_audit_date" />
              </th>
              <th
                className="text-left px-4 py-3 font-semibold text-gray-600 cursor-pointer select-none"
                onClick={() => toggleSort('next_audit_due')}
              >
                Next Due <SortIcon k="next_audit_due" />
              </th>
              <th className="text-left px-4 py-3 font-semibold text-gray-600">Frequency</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={8} className="text-center py-10 text-gray-400">Loading…</td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-10 text-gray-400">No entities found</td>
              </tr>
            )}
            {filtered.map((entity) => {
              const nextDue = entity.next_audit_due ? new Date(entity.next_audit_due) : null;
              const isOverdue = nextDue && nextDue < new Date();
              return (
                <tr key={entity.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {entity.name}
                    {entity.is_in_universe && (
                      <span className="ml-2 text-xs bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">
                        Universe
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {entity.entity_type ? (
                      <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                        {entity.entity_type.display_name}
                      </span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{entity.department ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${riskPillClass(entity.risk_score)}`}
                    >
                      {entity.risk_score.toFixed(1)} · {riskBand(entity.risk_score)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {entity.last_audit_date
                      ? new Date(entity.last_audit_date).toLocaleDateString()
                      : <span className="text-gray-300">Never</span>}
                  </td>
                  <td className="px-4 py-3">
                    {nextDue ? (
                      <span className={isOverdue ? 'text-red-600 font-medium' : 'text-gray-600'}>
                        {nextDue.toLocaleDateString()}
                        {isOverdue && ' ⚠'}
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    Every {entity.audit_frequency_months}mo
                  </td>
                  <td className="px-4 py-3 text-right">
                    {/* placeholder for future actions */}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Add Entity Drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-30 flex">
          <div
            className="flex-1 bg-black/30"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="w-full max-w-md bg-white shadow-xl flex flex-col overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-800">Add Audit Entity</h2>
              <button onClick={() => setDrawerOpen(false)}>
                <X className="w-5 h-5 text-gray-400 hover:text-gray-700" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="flex-1 p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Name *</label>
                <input
                  required
                  type="text"
                  value={drawerForm.name}
                  onChange={(e) => setDrawerForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  rows={2}
                  value={drawerForm.description}
                  onChange={(e) => setDrawerForm((f) => ({ ...f, description: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Entity Type</label>
                <select
                  value={drawerForm.entity_type_id}
                  onChange={(e) => setDrawerForm((f) => ({ ...f, entity_type_id: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                >
                  <option value="">— Select type —</option>
                  {entityTypes.map((t) => (
                    <option key={t.id} value={t.id}>{t.display_name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Owner Name</label>
                  <input
                    type="text"
                    value={drawerForm.owner_name}
                    onChange={(e) => setDrawerForm((f) => ({ ...f, owner_name: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Owner Email</label>
                  <input
                    type="email"
                    value={drawerForm.owner_email}
                    onChange={(e) => setDrawerForm((f) => ({ ...f, owner_email: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Department</label>
                <input
                  type="text"
                  value={drawerForm.department}
                  onChange={(e) => setDrawerForm((f) => ({ ...f, department: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Risk Score ({drawerForm.risk_score})
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={10}
                    step={0.5}
                    value={drawerForm.risk_score}
                    onChange={(e) => setDrawerForm((f) => ({ ...f, risk_score: Number(e.target.value) }))}
                    className="w-full accent-indigo-600"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Frequency (months)</label>
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={drawerForm.audit_frequency_months}
                    onChange={(e) =>
                      setDrawerForm((f) => ({ ...f, audit_frequency_months: Number(e.target.value) }))
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Tags (comma-separated)
                </label>
                <input
                  type="text"
                  value={drawerForm.tags}
                  onChange={(e) => setDrawerForm((f) => ({ ...f, tags: e.target.value }))}
                  placeholder="sox, gdpr, critical-system"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={drawerForm.is_in_universe}
                  onChange={(e) => setDrawerForm((f) => ({ ...f, is_in_universe: e.target.checked }))}
                  className="accent-indigo-600"
                />
                Include in Audit Universe
              </label>
              {createMutation.isError && (
                <div className="text-red-600 text-xs">
                  Error creating entity. Please try again.
                </div>
              )}
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="flex-1 border border-gray-300 text-gray-600 rounded-lg py-2 text-sm hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg py-2 text-sm transition-colors disabled:opacity-60"
                >
                  {createMutation.isPending ? 'Saving…' : 'Save Entity'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AI Prioritize Modal */}
      {aiModalOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40" onClick={() => setAiModalOpen(false)} />
          <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col m-4">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-800 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-purple-600" />
                AI Universe Prioritization
              </h2>
              <button onClick={() => setAiModalOpen(false)}>
                <X className="w-5 h-5 text-gray-400 hover:text-gray-700" />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 p-5 space-y-3">
              {aiResults.length === 0 ? (
                <div className="text-gray-400 text-sm text-center py-8">No results</div>
              ) : (
                aiResults.map((r) => (
                  <div key={r.entity_id} className="flex gap-3 p-3 rounded-lg border border-gray-100 bg-gray-50">
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-100 text-purple-700 text-sm font-bold flex items-center justify-center">
                      {r.priority_rank}
                    </div>
                    <div>
                      <div className="font-medium text-sm text-gray-800 flex items-center gap-2">
                        {r.entity_name}
                        <span className={`text-xs px-1.5 py-0.5 rounded-full ${riskPillClass(r.risk_score)}`}>
                          {r.risk_score.toFixed(1)}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">{r.rationale}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="px-5 py-3 border-t border-gray-200 flex justify-end">
              <button
                onClick={() => setAiModalOpen(false)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
