import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Plus,
  MessageSquare,
  Wrench,
  StickyNote,
  ArrowRight,
  Paperclip,
  Upload,
  X,
} from 'lucide-react';
import {
  listIssues,
  getIssue,
  createIssue,
  addIssueResponse,
  type IssueCreate,
  type IssueResponseCreate,
} from '../api';
import type { AuditIssue, IssueStatus, IssueSeverity } from '../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function severityDot(s: IssueSeverity) {
  const map: Record<IssueSeverity, string> = {
    critical: 'bg-red-600',
    high: 'bg-orange-500',
    medium: 'bg-yellow-400',
    low: 'bg-blue-400',
    informational: 'bg-gray-400',
  };
  return map[s] ?? 'bg-gray-300';
}

function severityBadge(s: IssueSeverity) {
  const map: Record<IssueSeverity, string> = {
    critical: 'bg-red-100 text-red-800',
    high: 'bg-orange-100 text-orange-700',
    medium: 'bg-yellow-100 text-yellow-700',
    low: 'bg-blue-100 text-blue-700',
    informational: 'bg-gray-100 text-gray-600',
  };
  return map[s] ?? 'bg-gray-100 text-gray-600';
}

function statusBadge(s: IssueStatus) {
  const map: Record<IssueStatus, string> = {
    open: 'bg-red-100 text-red-700',
    management_response_pending: 'bg-yellow-100 text-yellow-700',
    in_remediation: 'bg-blue-100 text-blue-700',
    resolved: 'bg-green-100 text-green-700',
    closed: 'bg-gray-100 text-gray-500',
    risk_accepted: 'bg-purple-100 text-purple-700',
  };
  return map[s] ?? 'bg-gray-100 text-gray-600';
}

function statusLabel(s: IssueStatus) {
  const map: Record<IssueStatus, string> = {
    open: 'Open',
    management_response_pending: 'Mgmt Response',
    in_remediation: 'In Remediation',
    resolved: 'Resolved',
    closed: 'Closed',
    risk_accepted: 'Risk Accepted',
  };
  return map[s] ?? s;
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

const RESPONSE_ICONS: Record<string, React.ElementType> = {
  management: MessageSquare,
  remediation: Wrench,
  auditor_note: StickyNote,
  status_change: ArrowRight,
  evidence: Paperclip,
};

function ResponseIcon({ type }: { type: string }) {
  const Icon = RESPONSE_ICONS[type] ?? MessageSquare;
  return <Icon className="w-4 h-4 text-gray-500" />;
}

type FilterStatus = 'all' | 'open' | 'in_remediation' | 'resolved' | 'closed';
type FilterSeverity = 'all' | IssueSeverity;

// ── New Issue Modal ───────────────────────────────────────────────────────────

interface NewIssueModalProps {
  tenantId: string;
  engagementId: string;
  onClose: () => void;
  onDone: () => void;
}

function NewIssueModal({ tenantId, engagementId, onClose, onDone }: NewIssueModalProps) {
  const [form, setForm] = useState<IssueCreate>({
    title: '',
    description: '',
    finding_type: 'control_deficiency',
    severity: 'medium',
    control_reference: null,
    framework_references: [],
    root_cause: null,
    management_owner: null,
    target_remediation_date: null,
  });
  const [fwTag, setFwTag] = useState('');

  const mut = useMutation({
    mutationFn: () => createIssue(tenantId, engagementId, form),
    onSuccess: onDone,
  });

  function set(k: keyof IssueCreate, v: unknown) {
    setForm((f) => ({ ...f, [k]: v || null }));
  }

  function addTag() {
    if (fwTag.trim()) {
      setForm((f) => ({ ...f, framework_references: [...(f.framework_references ?? []), fwTag.trim()] }));
      setFwTag('');
    }
  }

  function removeTag(i: number) {
    setForm((f) => ({ ...f, framework_references: (f.framework_references ?? []).filter((_, idx) => idx !== i) }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">New Issue</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-gray-400" /></button>
        </div>
        <div>
          <label className="form-label">Title *</label>
          <input className="form-input" value={form.title} onChange={(e) => set('title', e.target.value)} />
        </div>
        <div>
          <label className="form-label">Description *</label>
          <textarea className="form-input" rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Finding Type</label>
            <select className="form-input" value={form.finding_type} onChange={(e) => set('finding_type', e.target.value)}>
              {['control_deficiency', 'material_weakness', 'significant_deficiency', 'observation', 'recommendation'].map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Severity</label>
            <select className="form-input" value={form.severity} onChange={(e) => set('severity', e.target.value)}>
              {['critical', 'high', 'medium', 'low', 'informational'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Control Reference</label>
            <input className="form-input" onChange={(e) => set('control_reference', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Management Owner</label>
            <input className="form-input" onChange={(e) => set('management_owner', e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="form-label">Target Remediation Date</label>
            <input type="date" className="form-input" onChange={(e) => set('target_remediation_date', e.target.value)} />
          </div>
        </div>
        <div>
          <label className="form-label">Root Cause</label>
          <textarea className="form-input" rows={2} onChange={(e) => set('root_cause', e.target.value)} />
        </div>
        <div>
          <label className="form-label">Framework References</label>
          <div className="flex gap-2 mb-2">
            <input
              className="form-input flex-1"
              placeholder="e.g. SOC2-CC6.1"
              value={fwTag}
              onChange={(e) => setFwTag(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
            />
            <button className="btn-secondary" onClick={addTag}>Add</button>
          </div>
          <div className="flex flex-wrap gap-1">
            {form.framework_references?.map((ref, i) => (
              <span key={i} className="badge bg-indigo-100 text-indigo-700 flex items-center gap-1">
                {ref}
                <button onClick={() => removeTag(i)}><X className="w-3 h-3" /></button>
              </span>
            ))}
          </div>
        </div>
        {mut.isError && <p className="text-sm text-red-600">Failed to create issue.</p>}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={!form.title || !form.description || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? 'Creating…' : 'Create Issue'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Issue Detail ──────────────────────────────────────────────────────────────

interface IssueDetailProps {
  tenantId: string;
  issueId: string;
  onClose: () => void;
}

function IssueDetail({ tenantId, issueId, onClose }: IssueDetailProps) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [respForm, setRespForm] = useState<IssueResponseCreate>({
    response_type: 'management',
    response_text: '',
    submitted_by: '',
    new_status: null,
    file: null,
  });

  const { data: issue } = useQuery<AuditIssue>({
    queryKey: ['issue', tenantId, issueId],
    queryFn: () => getIssue(tenantId, issueId),
  });

  const respMut = useMutation({
    mutationFn: () => addIssueResponse(tenantId, issueId, respForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issue', tenantId, issueId] });
      qc.invalidateQueries({ queryKey: ['issues', tenantId] });
      setRespForm((f) => ({ ...f, response_text: '', submitted_by: '', new_status: null, file: null }));
    },
  });

  if (!issue) return <div className="p-6 text-gray-400">Loading…</div>;

  return (
    <div className="space-y-5 p-1">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-start gap-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-lg font-bold text-gray-800">#{issue.issue_number} {issue.title}</span>
              <span className={`badge ${severityBadge(issue.severity)}`}>{issue.severity}</span>
              <span className="badge bg-gray-100 text-gray-700">{issue.finding_type.replace(/_/g, ' ')}</span>
              <span className={`badge ${statusBadge(issue.status)}`}>{statusLabel(issue.status)}</span>
            </div>
          </div>
        </div>

        {/* Metadata grid */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          {issue.control_reference && (
            <>
              <span className="text-gray-500">Control Ref</span>
              <span className="font-mono text-gray-700">{issue.control_reference}</span>
            </>
          )}
          {issue.management_owner && (
            <>
              <span className="text-gray-500">Owner</span>
              <span className="text-gray-700">{issue.management_owner}</span>
            </>
          )}
          {issue.target_remediation_date && (
            <>
              <span className="text-gray-500">Target Date</span>
              <span className="text-gray-700">{new Date(issue.target_remediation_date).toLocaleDateString()}</span>
            </>
          )}
          {issue.actual_remediation_date && (
            <>
              <span className="text-gray-500">Actual Date</span>
              <span className="text-gray-700">{new Date(issue.actual_remediation_date).toLocaleDateString()}</span>
            </>
          )}
        </div>

        {issue.framework_references?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {issue.framework_references.map((r) => (
              <span key={r} className="badge bg-indigo-100 text-indigo-700">{r}</span>
            ))}
          </div>
        )}
      </div>

      {/* Description */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Description</p>
        <p className="text-sm text-gray-700 whitespace-pre-wrap">{issue.description}</p>
      </div>

      {/* Root Cause */}
      {issue.root_cause && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Root Cause</p>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{issue.root_cause}</p>
        </div>
      )}

      {/* Response timeline */}
      {issue.responses && issue.responses.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Response Timeline</p>
          <div className="space-y-3">
            {issue.responses.map((resp) => (
              <div key={resp.id} className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <ResponseIcon type={resp.response_type} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-800">{resp.submitted_by}</span>
                    <span className="text-xs text-gray-400">{relTime(resp.responded_at)}</span>
                    <span className="text-xs text-gray-400">·</span>
                    <span className="text-xs text-gray-500">{resp.response_type.replace(/_/g, ' ')}</span>
                    {resp.new_status && (
                      <span className={`badge ${statusBadge(resp.new_status as IssueStatus)}`}>
                        → {statusLabel(resp.new_status as IssueStatus)}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mt-0.5 whitespace-pre-wrap">{resp.response_text}</p>
                  {resp.file_name && (
                    <div className="flex items-center gap-1 text-xs text-blue-600 mt-1">
                      <Paperclip className="w-3 h-3" />
                      <span className="underline cursor-pointer">{resp.file_name}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add Response form */}
      <div className="border-t border-gray-200 pt-4 space-y-3">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Add Response</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Response Type</label>
            <select
              className="form-input"
              value={respForm.response_type}
              onChange={(e) => setRespForm((f) => ({ ...f, response_type: e.target.value }))}
            >
              {['management', 'remediation', 'auditor_note', 'status_change', 'evidence'].map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">New Status (optional)</label>
            <select
              className="form-input"
              value={respForm.new_status ?? ''}
              onChange={(e) => setRespForm((f) => ({ ...f, new_status: e.target.value || null }))}
            >
              <option value="">— no change —</option>
              {['open', 'management_response_pending', 'in_remediation', 'resolved', 'closed', 'risk_accepted'].map((s) => (
                <option key={s} value={s}>{statusLabel(s as IssueStatus)}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="form-label">Response Text *</label>
          <textarea
            className="form-input"
            rows={3}
            value={respForm.response_text}
            onChange={(e) => setRespForm((f) => ({ ...f, response_text: e.target.value }))}
          />
        </div>
        <div>
          <label className="form-label">Submitted By *</label>
          <input
            className="form-input"
            value={respForm.submitted_by}
            onChange={(e) => setRespForm((f) => ({ ...f, submitted_by: e.target.value }))}
          />
        </div>
        <div>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={(e) => setRespForm((f) => ({ ...f, file: e.target.files?.[0] ?? null }))}
          />
          <button className="btn-secondary w-full" onClick={() => fileRef.current?.click()}>
            <Upload className="w-4 h-4" />
            {respForm.file ? respForm.file.name : 'Attach file (optional)'}
          </button>
        </div>
        {respMut.isError && <p className="text-sm text-red-600">Failed to submit response.</p>}
        <button
          className="btn-primary w-full"
          disabled={!respForm.response_text || !respForm.submitted_by || respMut.isPending}
          onClick={() => respMut.mutate()}
        >
          {respMut.isPending ? 'Submitting…' : 'Submit Response'}
        </button>
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface Props {
  tenantId: string;
  engagementId: string;
  onBack: () => void;
}

const FILTER_STATUS: { key: FilterStatus; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'open', label: 'Open' },
  { key: 'in_remediation', label: 'In Remediation' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'closed', label: 'Closed' },
];

const FILTER_SEV: { key: FilterSeverity; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
];

export default function IssueRegister({ tenantId, engagementId, onBack }: Props) {
  const qc = useQueryClient();
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [filterSev, setFilterSev] = useState<FilterSeverity>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  const { data: issues = [], isLoading } = useQuery<AuditIssue[]>({
    queryKey: ['issues', tenantId, engagementId],
    queryFn: () => listIssues(tenantId, engagementId),
  });

  const filtered = issues.filter((i) => {
    if (filterStatus !== 'all' && i.status !== filterStatus) return false;
    if (filterSev !== 'all' && i.severity !== filterSev) return false;
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <h1 className="text-xl font-bold text-gray-900 flex-1">Issue Register</h1>
      </div>

      <div className="flex gap-4 h-[calc(100vh-220px)]">
        {/* Left panel */}
        <div className="w-1/3 flex flex-col gap-3">
          {/* Filter chips */}
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1">
              {FILTER_STATUS.map((f) => (
                <button
                  key={f.key}
                  className={`badge cursor-pointer ${filterStatus === f.key ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                  onClick={() => setFilterStatus(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              {FILTER_SEV.map((f) => (
                <button
                  key={f.key}
                  className={`badge cursor-pointer ${filterSev === f.key ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                  onClick={() => setFilterSev(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Issue list */}
          <div className="flex-1 overflow-y-auto card divide-y divide-gray-100">
            {isLoading && <p className="p-4 text-sm text-gray-400">Loading…</p>}
            {!isLoading && filtered.length === 0 && (
              <p className="p-4 text-sm text-gray-400">No issues match filters.</p>
            )}
            {filtered.map((issue) => (
              <button
                key={issue.id}
                className={`w-full text-left px-3 py-2.5 hover:bg-gray-50 transition-colors ${selectedId === issue.id ? 'bg-blue-50' : ''}`}
                onClick={() => setSelectedId(issue.id)}
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${severityDot(issue.severity)}`} />
                  <span className="text-sm font-medium text-gray-800 truncate">
                    #{issue.issue_number} {issue.title}
                  </span>
                </div>
                <div className="flex items-center gap-1 mt-0.5 pl-4">
                  <span className={`badge ${statusBadge(issue.status)}`}>{statusLabel(issue.status)}</span>
                </div>
              </button>
            ))}
          </div>

          <button className="btn-primary w-full" onClick={() => setShowNew(true)}>
            <Plus className="w-4 h-4" />
            New Issue
          </button>
        </div>

        {/* Right panel */}
        <div className="flex-1 card overflow-y-auto p-5">
          {selectedId ? (
            <IssueDetail
              tenantId={tenantId}
              issueId={selectedId}
              onClose={() => setSelectedId(null)}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              <p>Select an issue to view details</p>
            </div>
          )}
        </div>
      </div>

      {showNew && (
        <NewIssueModal
          tenantId={tenantId}
          engagementId={engagementId}
          onClose={() => setShowNew(false)}
          onDone={() => {
            setShowNew(false);
            qc.invalidateQueries({ queryKey: ['issues', tenantId, engagementId] });
          }}
        />
      )}
    </div>
  );
}
