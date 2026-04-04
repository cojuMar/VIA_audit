import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, CheckCircle } from 'lucide-react';
import { fetchCategories, fetchAppetites, upsertAppetite, fetchRisks } from '../api';
import type { RiskAppetite, AppetiteLevel } from '../types';

interface Props {
  tenantId: string;
}

const APPETITE_LEVELS: AppetiteLevel[] = ['zero', 'low', 'moderate', 'high', 'very_high'];

const appetiteColor = (level: AppetiteLevel): string => {
  switch (level) {
    case 'zero':
    case 'low':
      return 'text-green-700 bg-green-50 ring-green-600/20';
    case 'moderate':
      return 'text-yellow-700 bg-yellow-50 ring-yellow-600/20';
    case 'high':
    case 'very_high':
      return 'text-red-700 bg-red-50 ring-red-600/20';
  }
};

const appetiteLabel: Record<AppetiteLevel, string> = {
  zero: 'Zero',
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  very_high: 'Very High',
};

function cellScoreBg(score: number, maxAcceptable: number): string {
  if (score > maxAcceptable) return 'bg-red-400 opacity-80';
  if (score >= 20) return 'bg-red-200';
  if (score >= 15) return 'bg-orange-200';
  if (score >= 9) return 'bg-yellow-200';
  return 'bg-green-200';
}

interface RowState {
  category_id: string;
  category_name: string;
  appetite_level: AppetiteLevel;
  max_acceptable_score: number;
  description: string;
  approved_by: string;
}

export default function AppetiteConfig({ tenantId }: Props) {
  const qc = useQueryClient();
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const [savedRows, setSavedRows] = useState<Set<string>>(new Set());

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', tenantId],
    queryFn: fetchCategories,
  });

  const { data: appetites = [] } = useQuery({
    queryKey: ['appetites', tenantId],
    queryFn: fetchAppetites,
  });

  const { data: risks = [] } = useQuery({
    queryKey: ['risks', tenantId],
    queryFn: () => fetchRisks(),
  });

  // Initialise row state when data loads
  useEffect(() => {
    const initialRows: Record<string, RowState> = {};
    for (const cat of categories) {
      const existing = appetites.find((a) => a.category_id === cat.id);
      initialRows[cat.id] = {
        category_id: cat.id,
        category_name: cat.display_name,
        appetite_level: existing?.appetite_level ?? 'low',
        max_acceptable_score: existing?.max_acceptable_score ?? 9,
        description: existing?.description ?? '',
        approved_by: existing?.approved_by ?? '',
      };
    }
    setRows(initialRows);
  }, [categories, appetites]);

  const saveMut = useMutation({
    mutationFn: (payload: Partial<RiskAppetite>) => upsertAppetite(payload),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['appetites'] });
      setSavedRows((prev) => new Set(prev).add(variables.category_id!));
      setTimeout(
        () =>
          setSavedRows((prev) => {
            const next = new Set(prev);
            next.delete(variables.category_id!);
            return next;
          }),
        2000
      );
    },
  });

  function updateRow(categoryId: string, field: keyof RowState, value: string | number | AppetiteLevel) {
    setRows((prev) => ({
      ...prev,
      [categoryId]: { ...prev[categoryId], [field]: value },
    }));
  }

  function getRisksAboveAppetite(categoryId: string, maxScore: number) {
    return risks.filter(
      (r) =>
        r.category_id === categoryId &&
        r.residual_score !== null &&
        r.residual_score > maxScore
    ).length;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Risk Appetite Configuration</h1>
      </div>

      {/* Appetite vs Portfolio Summary */}
      <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">Appetite vs Portfolio</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {Object.values(rows).map((row) => {
            const count = getRisksAboveAppetite(row.category_id, row.max_acceptable_score);
            return (
              <div key={row.category_id} className="rounded-lg border border-gray-200 p-3 text-center">
                <p className="text-xs font-medium text-gray-500 truncate">{row.category_name}</p>
                <p className={`mt-1 text-2xl font-bold ${count > 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {count}
                </p>
                <p className="text-xs text-gray-400">above appetite</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Category Rows */}
      <div className="space-y-4">
        {Object.values(rows).map((row) => {
          const saved = savedRows.has(row.category_id);
          return (
            <div key={row.category_id} className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-semibold text-gray-900">{row.category_name}</h3>
                <button
                  onClick={() =>
                    saveMut.mutate({
                      category_id: row.category_id,
                      category_name: row.category_name,
                      appetite_level: row.appetite_level,
                      max_acceptable_score: row.max_acceptable_score,
                      description: row.description || null,
                      approved_by: row.approved_by || null,
                      effective_date: new Date().toISOString().slice(0, 10),
                    })
                  }
                  disabled={saveMut.isPending}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    saved
                      ? 'bg-green-50 text-green-700 ring-1 ring-green-600/20'
                      : 'bg-indigo-600 text-white hover:bg-indigo-700'
                  }`}
                >
                  {saved ? (
                    <>
                      <CheckCircle className="h-4 w-4" /> Saved
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4" /> Save Appetite Statement
                    </>
                  )}
                </button>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {/* Appetite Level */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Appetite Level</label>
                  <select
                    value={row.appetite_level}
                    onChange={(e) =>
                      updateRow(row.category_id, 'appetite_level', e.target.value as AppetiteLevel)
                    }
                    className={`w-full rounded-lg border px-3 py-2 text-sm font-medium ring-1 ${appetiteColor(row.appetite_level)} border-transparent`}
                  >
                    {APPETITE_LEVELS.map((level) => (
                      <option key={level} value={level}>
                        {appetiteLabel[level]}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Max Score Slider */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Max Acceptable Score: <strong>{row.max_acceptable_score}</strong>
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={25}
                    value={row.max_acceptable_score}
                    onChange={(e) =>
                      updateRow(row.category_id, 'max_acceptable_score', Number(e.target.value))
                    }
                    className="w-full accent-indigo-600"
                  />
                  <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                    <span>1</span>
                    <span>25</span>
                  </div>
                </div>

                {/* Approved By */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Approved By</label>
                  <input
                    value={row.approved_by}
                    onChange={(e) => updateRow(row.category_id, 'approved_by', e.target.value)}
                    placeholder="Name or role"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                </div>

                {/* Risks Above */}
                <div className="flex flex-col items-center justify-center rounded-lg border border-gray-100 bg-gray-50 p-3">
                  <span className={`text-3xl font-bold ${getRisksAboveAppetite(row.category_id, row.max_acceptable_score) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {getRisksAboveAppetite(row.category_id, row.max_acceptable_score)}
                  </span>
                  <span className="text-xs text-gray-500">risks above appetite</span>
                </div>
              </div>

              {/* Description */}
              <div className="mt-4">
                <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                <textarea
                  value={row.description}
                  onChange={(e) => updateRow(row.category_id, 'description', e.target.value)}
                  rows={2}
                  placeholder="Describe the risk appetite statement for this category…"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Appetite Matrix Visual */}
      <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">Appetite Matrix</h2>
        <p className="mb-4 text-xs text-gray-500">
          Cells shaded with a red overlay indicate scores that exceed a category's appetite threshold.
          Select a category to highlight its boundary.
        </p>
        <div className="space-y-6">
          {Object.values(rows).slice(0, 4).map((row) => (
            <div key={row.category_id}>
              <p className="text-xs font-semibold text-gray-600 mb-2">
                {row.category_name} — threshold: {row.max_acceptable_score}
              </p>
              <div
                className="grid gap-0.5"
                style={{ gridTemplateColumns: 'repeat(5, 1fr)', gridTemplateRows: 'repeat(5, 28px)' }}
              >
                {[5, 4, 3, 2, 1].map((impact) =>
                  [1, 2, 3, 4, 5].map((likelihood) => {
                    const score = likelihood * impact;
                    return (
                      <div
                        key={`${impact}-${likelihood}`}
                        className={`flex items-center justify-center rounded text-[10px] font-mono ${cellScoreBg(score, row.max_acceptable_score)}`}
                      >
                        {score}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
