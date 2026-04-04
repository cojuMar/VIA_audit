import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText, Sparkles, Plus, X, Loader2, Send,
  Package, AlertCircle, BarChart2, CheckSquare,
} from 'lucide-react';
import {
  fetchPackages, fetchPackage, createPackage, buildESGPackage,
  buildAuditCommitteePackage, aiBoardPackSummary,
} from '../api';
import type { BoardPackage, PackageItem } from '../types';

interface Props { tenantId: string }

function packageTypeColor(type: string) {
  switch (type) {
    case 'board_pack': return 'bg-indigo-100 text-indigo-700 border-indigo-200';
    case 'esg_report': return 'bg-green-100 text-green-700 border-green-200';
    case 'audit_report': return 'bg-orange-100 text-orange-700 border-orange-200';
    default: return 'bg-gray-100 text-gray-700 border-gray-200';
  }
}

function packageStatusColor(status: string) {
  switch (status) {
    case 'approved': return 'bg-green-100 text-green-700';
    case 'distributed': return 'bg-blue-100 text-blue-700';
    case 'draft': return 'bg-gray-100 text-gray-600';
    case 'under_review': return 'bg-yellow-100 text-yellow-700';
    default: return 'bg-gray-100 text-gray-600';
  }
}

function contentTypeIcon(type: string) {
  switch (type) {
    case 'esg_scorecard': return <BarChart2 className="w-4 h-4 text-green-600" />;
    case 'metrics_table': return <FileText className="w-4 h-4 text-blue-600" />;
    case 'risk_heatmap': return <AlertCircle className="w-4 h-4 text-orange-600" />;
    case 'audit_findings': return <CheckSquare className="w-4 h-4 text-purple-600" />;
    default: return <FileText className="w-4 h-4 text-gray-500" />;
  }
}

function ContentRenderer({ item }: { item: PackageItem }) {
  const { content_type, content_data } = item;

  if (content_type === 'esg_scorecard') {
    const e = content_data.environmental as { coverage_pct?: number } | undefined;
    const s = content_data.social as { coverage_pct?: number } | undefined;
    const g = content_data.governance as { coverage_pct?: number } | undefined;
    return (
      <div className="flex gap-2 mt-2 flex-wrap">
        {e && <span className="esg-e text-xs px-2 py-1 rounded-full font-medium">E: {Math.round(e.coverage_pct ?? 0)}%</span>}
        {s && <span className="esg-s text-xs px-2 py-1 rounded-full font-medium">S: {Math.round(s.coverage_pct ?? 0)}%</span>}
        {g && <span className="esg-g text-xs px-2 py-1 rounded-full font-medium">G: {Math.round(g.coverage_pct ?? 0)}%</span>}
      </div>
    );
  }

  if (content_type === 'metrics_table') {
    const rows = content_data.rows as Array<Record<string, unknown>> | undefined;
    if (!rows || rows.length === 0) return <p className="text-xs text-gray-400 mt-1">No data</p>;
    const keys = Object.keys(rows[0]);
    return (
      <div className="mt-2 overflow-x-auto">
        <table className="text-xs w-full">
          <thead>
            <tr>{keys.map((k) => <th key={k} className="text-left py-1 px-2 bg-gray-100 text-gray-500 font-medium">{k}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, 5).map((row, i) => (
              <tr key={i} className="border-b border-gray-100">
                {keys.map((k) => <td key={k} className="py-1 px-2 text-gray-700">{String(row[k] ?? '')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (content_type === 'risk_heatmap') {
    const risks = content_data.top_risks as Array<{ name?: string; risk_level?: string }> | undefined;
    if (!risks || risks.length === 0) return <p className="text-xs text-gray-400 mt-1">No risks</p>;
    const levelColor = (l?: string) => {
      if (l === 'critical') return 'bg-red-100 text-red-700';
      if (l === 'high') return 'bg-orange-100 text-orange-700';
      if (l === 'medium') return 'bg-yellow-100 text-yellow-700';
      return 'bg-green-100 text-green-700';
    };
    return (
      <div className="mt-2 space-y-1">
        {risks.slice(0, 5).map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${levelColor(r.risk_level)}`}>{r.risk_level ?? 'low'}</span>
            <span className="text-xs text-gray-700">{r.name ?? 'Unknown risk'}</span>
          </div>
        ))}
      </div>
    );
  }

  if (content_type === 'audit_findings') {
    const counts = content_data.severity_counts as Record<string, number> | undefined;
    if (!counts) return <p className="text-xs text-gray-400 mt-1">No findings data</p>;
    return (
      <div className="flex gap-2 mt-2 flex-wrap">
        {Object.entries(counts).map(([sev, count]) => (
          <span key={sev} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">
            {sev}: <strong>{count}</strong>
          </span>
        ))}
      </div>
    );
  }

  // text / default
  const text = content_data.text ?? content_data.content ?? content_data.body;
  if (text) return <p className="text-xs text-gray-600 mt-2 whitespace-pre-wrap">{String(text).slice(0, 300)}{String(text).length > 300 ? '…' : ''}</p>;
  return null;
}

interface PackageDetailProps {
  packageId: string;
  onClose: () => void;
}
function PackageDetail({ packageId, onClose }: PackageDetailProps) {
  const queryClient = useQueryClient();
  const [generatingSummary, setGeneratingSummary] = useState(false);

  const { data: pkg, isLoading } = useQuery<BoardPackage>({
    queryKey: ['package', packageId],
    queryFn: () => fetchPackage(packageId),
  });

  const handleGenerateSummary = async () => {
    setGeneratingSummary(true);
    try {
      await aiBoardPackSummary(packageId);
      void queryClient.invalidateQueries({ queryKey: ['package', packageId] });
    } finally {
      setGeneratingSummary(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-end justify-end z-50">
      <div className="bg-white h-full w-full max-w-2xl shadow-2xl overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Package className="w-5 h-5 text-indigo-600" />
            <h3 className="text-lg font-semibold">Package Details</h3>
          </div>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>

        {isLoading ? (
          <div className="p-6 flex items-center justify-center text-gray-400"><Loader2 className="w-6 h-6 animate-spin mr-2" />Loading…</div>
        ) : !pkg ? (
          <div className="p-6 text-gray-400">Package not found.</div>
        ) : (
          <div className="p-6 space-y-5">
            {/* Header */}
            <div>
              <div className="flex items-start justify-between gap-3">
                <h4 className="text-xl font-bold text-gray-900">{pkg.title}</h4>
                <span className={`text-xs px-2 py-1 rounded-full font-medium shrink-0 ${packageStatusColor(pkg.status)}`}>{pkg.status}</span>
              </div>
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <span className={`text-xs px-2 py-0.5 rounded border font-medium ${packageTypeColor(pkg.package_type)}`}>{pkg.package_type.replace(/_/g, ' ')}</span>
                {pkg.reporting_period && <span className="text-xs text-gray-500">Period: {pkg.reporting_period}</span>}
                {pkg.prepared_by && <span className="text-xs text-gray-500">Prepared by: {pkg.prepared_by}</span>}
                <span className="text-xs text-gray-400">{new Date(pkg.created_at).toLocaleDateString()}</span>
              </div>
            </div>

            {/* Executive Summary */}
            {(pkg.executive_summary || pkg.ai_generated_summary) ? (
              <div className="bg-gray-50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  {pkg.ai_generated_summary ? <Sparkles className="w-4 h-4 text-purple-600" /> : <FileText className="w-4 h-4 text-gray-600" />}
                  <p className="text-sm font-semibold text-gray-700">
                    {pkg.ai_generated_summary ? 'AI-Generated Summary' : 'Executive Summary'}
                  </p>
                </div>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{pkg.ai_generated_summary ?? pkg.executive_summary}</p>
              </div>
            ) : (
              <div className="border border-dashed border-gray-300 rounded-xl p-4 text-center">
                <p className="text-sm text-gray-400 mb-2">No executive summary yet</p>
                <button
                  onClick={handleGenerateSummary}
                  disabled={generatingSummary}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 mx-auto"
                >
                  {generatingSummary ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  {generatingSummary ? 'Generating…' : 'Generate AI Summary'}
                </button>
              </div>
            )}

            {/* Package Items */}
            {pkg.items && pkg.items.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-3">{pkg.items.length} Sections</p>
                <div className="space-y-3">
                  {[...pkg.items].sort((a, b) => a.sequence_number - b.sequence_number).map((item) => (
                    <div key={item.id} className={`border rounded-lg p-4 ${item.is_confidential ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'}`}>
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 flex items-center justify-center bg-indigo-100 text-indigo-700 text-xs font-bold rounded-full">
                            {item.sequence_number}
                          </span>
                          {contentTypeIcon(item.content_type)}
                          <span className="text-sm font-semibold text-gray-800">{item.section_title}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{item.content_type}</span>
                          {item.is_confidential && (
                            <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">Confidential</span>
                          )}
                        </div>
                      </div>
                      {item.source_service && (
                        <p className="text-xs text-gray-400 mb-1">Source: {item.source_service}</p>
                      )}
                      <ContentRenderer item={item} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Distribute */}
            <div className="flex justify-end pt-2">
              <button className="flex items-center gap-2 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">
                <Send className="w-4 h-4" />Distribute Package
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface CreatePackageModalProps {
  onClose: () => void;
  onSubmit: (data: object) => void;
  submitting: boolean;
}
function CreatePackageModal({ onClose, onSubmit, submitting }: CreatePackageModalProps) {
  const [title, setTitle] = useState('');
  const [packageType, setPackageType] = useState('board_pack');
  const [reportingPeriod, setReportingPeriod] = useState('');
  const [preparedBy, setPreparedBy] = useState('');
  const [executiveSummary, setExecutiveSummary] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      title,
      package_type: packageType,
      reporting_period: reportingPeriod || undefined,
      prepared_by: preparedBy || undefined,
      executive_summary: executiveSummary || undefined,
      recipient_list: [],
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Create Package</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select
                value={packageType}
                onChange={(e) => setPackageType(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {['board_pack', 'esg_report', 'audit_report', 'committee_pack'].map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reporting Period</label>
              <input
                type="text"
                value={reportingPeriod}
                onChange={(e) => setReportingPeriod(e.target.value)}
                placeholder="e.g. 2025-Q4"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Prepared By</label>
            <input
              type="text"
              value={preparedBy}
              onChange={(e) => setPreparedBy(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Executive Summary</label>
            <textarea
              value={executiveSummary}
              onChange={(e) => setExecutiveSummary(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={submitting} className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {submitting ? 'Creating…' : 'Create Package'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface BuildPromptModalProps {
  type: 'esg' | 'audit';
  onClose: () => void;
  onBuild: (period: string) => void;
  building: boolean;
}
function BuildPromptModal({ type, onClose, onBuild, building }: BuildPromptModalProps) {
  const [period, setPeriod] = useState('');
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">
            Build {type === 'esg' ? 'ESG Package' : 'Audit Committee Pack'}
          </h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reporting Period</label>
            <input
              type="text"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="e.g. 2025 or 2025-Q4"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button
              onClick={() => period && onBuild(period)}
              disabled={!period || building}
              className={`flex items-center gap-2 px-4 py-2 text-sm text-white rounded-lg disabled:opacity-50 ${type === 'esg' ? 'bg-green-600 hover:bg-green-700' : 'bg-orange-600 hover:bg-orange-700'}`}
            >
              {building ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {building ? 'Building…' : 'Build'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function BoardPackages({ tenantId: _tenantId }: Props) {
  const queryClient = useQueryClient();
  const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [buildPrompt, setBuildPrompt] = useState<'esg' | 'audit' | null>(null);
  const [buildingType, setBuildingType] = useState<'esg' | 'audit' | null>(null);

  const { data: packagesRaw, isLoading } = useQuery<BoardPackage[]>({
    queryKey: ['packages'],
    queryFn: () => fetchPackages({ limit: 50 }),
    retry: 1,
  });
  const packages = packagesRaw ?? [];

  const createMutation = useMutation({
    mutationFn: createPackage,
    onSuccess: () => {
      setShowCreateModal(false);
      void queryClient.invalidateQueries({ queryKey: ['packages'] });
    },
  });

  const handleBuild = async (type: 'esg' | 'audit', period: string) => {
    setBuildingType(type);
    setBuildPrompt(null);
    try {
      if (type === 'esg') {
        await buildESGPackage({ reporting_period: period });
      } else {
        await buildAuditCommitteePackage({ reporting_period: period });
      }
      void queryClient.invalidateQueries({ queryKey: ['packages'] });
    } finally {
      setBuildingType(null);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Board Packages</h2>
          <p className="text-sm text-gray-500 mt-0.5">Manage board packs, ESG reports, and audit committee materials</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setBuildPrompt('esg')}
            disabled={buildingType === 'esg'}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            {buildingType === 'esg' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            {buildingType === 'esg' ? 'Building…' : 'Build ESG Package'}
          </button>
          <button
            onClick={() => setBuildPrompt('audit')}
            disabled={buildingType === 'audit'}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50"
          >
            {buildingType === 'audit' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            {buildingType === 'audit' ? 'Building…' : 'Build Audit Committee Pack'}
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            <Plus className="w-4 h-4" />Create Manual
          </button>
        </div>
      </div>

      {/* Package List */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-400 flex items-center justify-center gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />Loading packages…
        </div>
      ) : packages.length === 0 ? (
        <div className="metric-card text-center py-12">
          <Package className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400">No packages yet. Build one using the buttons above.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {packages.map((pkg) => (
            <button
              key={pkg.id}
              onClick={() => setSelectedPackageId(pkg.id)}
              className="text-left metric-card hover:shadow-md transition-shadow group"
            >
              <div className="flex items-start justify-between mb-2">
                <span className={`text-xs px-2 py-0.5 rounded border font-medium ${packageTypeColor(pkg.package_type)}`}>
                  {pkg.package_type.replace(/_/g, ' ')}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${packageStatusColor(pkg.status)}`}>{pkg.status}</span>
              </div>
              <h4 className="text-sm font-semibold text-gray-800 group-hover:text-indigo-700 transition-colors line-clamp-2">{pkg.title}</h4>
              {pkg.reporting_period && (
                <p className="text-xs text-gray-500 mt-1">Period: {pkg.reporting_period}</p>
              )}
              <div className="flex items-center justify-between mt-3">
                <div className="flex items-center gap-2">
                  {pkg.prepared_by && <span className="text-xs text-gray-400 truncate max-w-24">{pkg.prepared_by}</span>}
                  {pkg.item_count !== undefined && (
                    <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{pkg.item_count} sections</span>
                  )}
                </div>
                <span className="text-xs text-gray-400">{new Date(pkg.created_at).toLocaleDateString()}</span>
              </div>
              {(pkg.ai_generated_summary ?? pkg.executive_summary) && (
                <div className="flex items-center gap-1 mt-2">
                  <Sparkles className="w-3 h-3 text-purple-400" />
                  <p className="text-xs text-gray-500 truncate">{(pkg.ai_generated_summary ?? pkg.executive_summary ?? '').slice(0, 60)}…</p>
                </div>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Modals */}
      {selectedPackageId && (
        <PackageDetail
          packageId={selectedPackageId}
          onClose={() => setSelectedPackageId(null)}
        />
      )}
      {showCreateModal && (
        <CreatePackageModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          submitting={createMutation.isPending}
        />
      )}
      {buildPrompt && (
        <BuildPromptModal
          type={buildPrompt}
          onClose={() => setBuildPrompt(null)}
          onBuild={(period) => handleBuild(buildPrompt, period)}
          building={buildingType === buildPrompt}
        />
      )}
    </div>
  );
}
