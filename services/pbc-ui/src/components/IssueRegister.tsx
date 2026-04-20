import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Plus, MessageSquare, Wrench, StickyNote, ArrowRight,
  Paperclip, Upload, X, LayoutList, LayoutGrid, GripVertical,
  AlertTriangle, Calendar, User,
} from 'lucide-react';
import DataTable, { type ColDef } from './DataTable';
import {
  listIssues, getIssue, createIssue, addIssueResponse, updateIssueStatus,
  type IssueCreate, type IssueResponseCreate,
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

function severityBorder(s: IssueSeverity) {
  const map: Record<IssueSeverity, string> = {
    critical: 'border-l-red-500',
    high: 'border-l-orange-400',
    medium: 'border-l-yellow-400',
    low: 'border-l-blue-400',
    informational: 'border-l-gray-300',
  };
  return map[s] ?? 'border-l-gray-300';
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

function statusLabel(s: IssueStatus | string) {
  const map: Record<string, string> = {
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

// ── Kanban column config ──────────────────────────────────────────────────────

interface ColumnDef {
  status: IssueStatus;
  label: string;
  headerColor: string;
  headerText: string;
  dropBg: string;
  dropBorder: string;
  countBg: string;
  countText: string;
}

const COLUMNS: ColumnDef[] = [
  {
    status: 'open',
    label: 'Open',
    headerColor: 'bg-red-500',
    headerText: 'text-white',
    dropBg: 'bg-red-50',
    dropBorder: 'border-red-400',
    countBg: 'bg-red-100',
    countText: 'text-red-700',
  },
  {
    status: 'management_response_pending',
    label: 'Mgmt Response',
    headerColor: 'bg-amber-500',
    headerText: 'text-white',
    dropBg: 'bg-amber-50',
    dropBorder: 'border-amber-400',
    countBg: 'bg-amber-100',
    countText: 'text-amber-700',
  },
  {
    status: 'in_remediation',
    label: 'In Remediation',
    headerColor: 'bg-blue-500',
    headerText: 'text-white',
    dropBg: 'bg-blue-50',
    dropBorder: 'border-blue-400',
    countBg: 'bg-blue-100',
    countText: 'text-blue-700',
  },
  {
    status: 'resolved',
    label: 'Resolved',
    headerColor: 'bg-green-500',
    headerText: 'text-white',
    dropBg: 'bg-green-50',
    dropBorder: 'border-green-400',
    countBg: 'bg-green-100',
    countText: 'text-green-700',
  },
  {
    status: 'closed',
    label: 'Closed',
    headerColor: 'bg-gray-400',
    headerText: 'text-white',
    dropBg: 'bg-gray-50',
    dropBorder: 'border-gray-400',
    countBg: 'bg-gray-100',
    countText: 'text-gray-600',
  },
  {
    status: 'risk_accepted',
    label: 'Risk Accepted',
    headerColor: 'bg-purple-500',
    headerText: 'text-white',
    dropBg: 'bg-purple-50',
    dropBorder: 'border-purple-400',
    countBg: 'bg-purple-100',
    countText: 'text-purple-700',
  },
];

// ── Kanban card ───────────────────────────────────────────────────────────────

interface KanbanCardProps {
  issue: AuditIssue;
  onDragStart: (id: string) => void;
  onClick: (id: string) => void;
  isDragging: boolean;
}

function KanbanCard({ issue, onDragStart, onClick, isDragging }: KanbanCardProps) {
  const isOverdue =
    issue.target_remediation_date &&
    new Date(issue.target_remediation_date) < new Date() &&
    !['resolved', 'closed', 'risk_accepted'].includes(issue.status);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move';
        onDragStart(issue.id);
      }}
      onClick={() => onClick(issue.id)}
      className={`
        group relative bg-white rounded-lg border border-gray-200 border-l-4 ${severityBorder(issue.severity)}
        p-3 cursor-grab active:cursor-grabbing select-none
        shadow-[var(--via-shadow-xs)] hover:shadow-[var(--via-shadow-hover)]
        transition-all duration-150
        ${isDragging ? 'opacity-40 scale-95' : 'opacity-100'}
      `}
    >
      {/* Drag handle hint */}
      <GripVertical className="absolute right-2 top-2 w-3.5 h-3.5 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity" />

      {/* Issue number + severity */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${severityDot(issue.severity)}`} />
        <span className="text-[10px] font-semibold text-gray-400 tracking-wide">
          #{issue.issue_number}
        </span>
        <span className={`badge text-[10px] py-0 ${severityBadge(issue.severity)}`}>
          {issue.severity}
        </span>
      </div>

      {/* Title */}
      <p className="text-sm font-semibold text-gray-800 leading-snug line-clamp-2 pr-4">
        {issue.title}
      </p>

      {/* Finding type */}
      <p className="text-[11px] text-gray-400 mt-0.5">
        {issue.finding_type.replace(/_/g, ' ')}
      </p>

      {/* Footer */}
      <div className="mt-2.5 flex items-center gap-2 flex-wrap">
        {issue.management_owner && (
          <span className="flex items-center gap-1 text-[10px] text-gray-500">
            <User className="w-3 h-3" />
            {issue.management_owner}
          </span>
        )}
        {issue.target_remediation_date && (
          <span className={`flex items-center gap-1 text-[10px] ${isOverdue ? 'text-red-600 font-semibold' : 'text-gray-500'}`}>
            {isOverdue && <AlertTriangle className="w-3 h-3" />}
            {!isOverdue && <Calendar className="w-3 h-3" />}
            {new Date(issue.target_remediation_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          </span>
        )}
        {issue.framework_references?.length > 0 && (
          <span className="text-[10px] text-indigo-500 font-mono">
            {issue.framework_references[0]}
            {issue.framework_references.length > 1 && ` +${issue.framework_references.length - 1}`}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Kanban column ─────────────────────────────────────────────────────────────

interface KanbanColumnProps {
  col: ColumnDef;
  issues: AuditIssue[];
  draggedId: string | null;
  dropTarget: string | null;
  onDragStart: (id: string) => void;
  onDragOver: (status: IssueStatus) => void;
  onDragLeave: () => void;
  onDrop: (status: IssueStatus) => void;
  onCardClick: (id: string) => void;
}

function KanbanColumn({
  col, issues, draggedId, dropTarget,
  onDragStart, onDragOver, onDragLeave, onDrop, onCardClick,
}: KanbanColumnProps) {
  const isDropTarget = dropTarget === col.status;

  return (
    <div className="flex flex-col flex-shrink-0 w-64">
      {/* Column header */}
      <div className={`flex items-center justify-between px-3 py-2 rounded-t-lg ${col.headerColor}`}>
        <span className={`text-xs font-bold tracking-wide ${col.headerText}`}>
          {col.label}
        </span>
        <span className={`text-[11px] font-bold px-1.5 py-0.5 rounded-full ${col.countBg} ${col.countText}`}>
          {issues.length}
        </span>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); onDragOver(col.status); }}
        onDragLeave={onDragLeave}
        onDrop={(e) => { e.preventDefault(); onDrop(col.status); }}
        className={`
          flex-1 rounded-b-lg border-2 p-2 space-y-2 overflow-y-auto transition-colors duration-100
          min-h-[120px]
          ${isDropTarget
            ? `${col.dropBg} ${col.dropBorder} border-dashed`
            : 'bg-gray-50 border-gray-200'}
        `}
      >
        {issues.map((issue) => (
          <KanbanCard
            key={issue.id}
            issue={issue}
            onDragStart={onDragStart}
            onClick={onCardClick}
            isDragging={draggedId === issue.id}
          />
        ))}

        {issues.length === 0 && (
          <div className={`
            flex items-center justify-center h-16 rounded text-xs text-gray-400
            ${isDropTarget ? 'border-2 border-dashed border-current' : ''}
          `}>
            {isDropTarget ? 'Drop here' : 'No issues'}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Kanban board ──────────────────────────────────────────────────────────────

interface KanbanBoardProps {
  tenantId: string;
  engagementId: string;
  issues: AuditIssue[];
  filterSev: FilterSeverity;
  onSelectIssue: (id: string) => void;
}

function KanbanBoard({ tenantId, engagementId, issues, filterSev, onSelectIssue }: KanbanBoardProps) {
  const qc = useQueryClient();
  const draggedIdRef = useRef<string | null>(null);
  const [dropTarget, setDropTarget] = useState<IssueStatus | null>(null);

  const moveMut = useMutation({
    mutationFn: ({ issueId, status }: { issueId: string; status: IssueStatus }) =>
      updateIssueStatus(tenantId, issueId, status),
    onMutate: async ({ issueId, status }) => {
      await qc.cancelQueries({ queryKey: ['issues', tenantId, engagementId] });
      const prev = qc.getQueryData<AuditIssue[]>(['issues', tenantId, engagementId]);
      qc.setQueryData<AuditIssue[]>(['issues', tenantId, engagementId], (old) =>
        (old ?? []).map((i) => (i.id === issueId ? { ...i, status } : i))
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['issues', tenantId, engagementId], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['issues', tenantId, engagementId] });
    },
  });

  function handleDragStart(id: string) {
    draggedIdRef.current = id;
  }

  function handleDrop(targetStatus: IssueStatus) {
    const id = draggedIdRef.current;
    if (!id) return;

    const issue = issues.find((i) => i.id === id);
    if (!issue || issue.status === targetStatus) {
      draggedIdRef.current = null;
      setDropTarget(null);
      return;
    }

    moveMut.mutate({ issueId: id, status: targetStatus });
    draggedIdRef.current = null;
    setDropTarget(null);
  }

  function handleDragLeave() {
    // Small delay prevents flicker when moving between child elements
    setTimeout(() => setDropTarget(null), 50);
  }

  const filtered = filterSev === 'all'
    ? issues
    : issues.filter((i) => i.severity === filterSev);

  const byStatus = COLUMNS.reduce<Record<string, AuditIssue[]>>((acc, col) => {
    acc[col.status] = filtered.filter((i) => i.status === col.status);
    return acc;
  }, {});

  return (
    <div
      className="flex gap-3 overflow-x-auto pb-3"
      style={{ height: 'calc(100vh - 230px)', alignItems: 'flex-start' }}
      onDragEnd={() => { draggedIdRef.current = null; setDropTarget(null); }}
    >
      {COLUMNS.map((col) => (
        <KanbanColumn
          key={col.status}
          col={col}
          issues={byStatus[col.status] ?? []}
          draggedId={draggedIdRef.current}
          dropTarget={dropTarget}
          onDragStart={handleDragStart}
          onDragOver={(s) => setDropTarget(s)}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onCardClick={onSelectIssue}
        />
      ))}
    </div>
  );
}

// ── New Issue Modal ───────────────────────────────────────────────────────────

type FilterStatus = 'all' | 'open' | 'in_remediation' | 'resolved' | 'closed';
type FilterSeverity = 'all' | IssueSeverity;

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

// ── Issue Detail slide-over ───────────────────────────────────────────────────

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
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-lg font-bold text-gray-800">#{issue.issue_number} {issue.title}</span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
            <span className={`badge ${severityBadge(issue.severity)}`}>{issue.severity}</span>
            <span className="badge bg-gray-100 text-gray-700">{issue.finding_type.replace(/_/g, ' ')}</span>
            <span className={`badge ${statusBadge(issue.status)}`}>{statusLabel(issue.status)}</span>
          </div>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {issue.control_reference && (
          <><span className="text-gray-500">Control Ref</span><span className="font-mono text-gray-700">{issue.control_reference}</span></>
        )}
        {issue.management_owner && (
          <><span className="text-gray-500">Owner</span><span className="text-gray-700">{issue.management_owner}</span></>
        )}
        {issue.target_remediation_date && (
          <><span className="text-gray-500">Target Date</span><span className="text-gray-700">{new Date(issue.target_remediation_date).toLocaleDateString()}</span></>
        )}
        {issue.actual_remediation_date && (
          <><span className="text-gray-500">Actual Date</span><span className="text-gray-700">{new Date(issue.actual_remediation_date).toLocaleDateString()}</span></>
        )}
      </div>

      {issue.framework_references?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {issue.framework_references.map((r) => (
            <span key={r} className="badge bg-indigo-100 text-indigo-700">{r}</span>
          ))}
        </div>
      )}

      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Description</p>
        <p className="text-sm text-gray-700 whitespace-pre-wrap">{issue.description}</p>
      </div>

      {issue.root_cause && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Root Cause</p>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{issue.root_cause}</p>
        </div>
      )}

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
                        → {statusLabel(resp.new_status)}
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

type ViewMode = 'list' | 'board';

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

// ── Issue list-view column definitions ────────────────────────────────────────

const SEV_ORDER: Record<IssueSeverity, number> = {
  critical: 0, high: 1, medium: 2, low: 3, informational: 4,
};

const ISSUE_COLS: ColDef<AuditIssue>[] = [
  {
    key: 'number',
    header: '#',
    width: '52px',
    render: (i) => <span className="text-gray-500 tabular-nums text-xs">#{i.issue_number}</span>,
    sortFn: (a, b) => (a.issue_number ?? 0) - (b.issue_number ?? 0),
  },
  {
    key: 'severity',
    header: 'Sev',
    width: '80px',
    render: (i) => (
      <span className={`badge ${severityBadge(i.severity)}`}>
        {i.severity.charAt(0).toUpperCase() + i.severity.slice(1)}
      </span>
    ),
    sortFn: (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  },
  {
    key: 'title',
    header: 'Title',
    render: (i) => (
      <div>
        <p className="font-medium text-gray-800 truncate max-w-xs">{i.title}</p>
        <p className="text-xs text-gray-400 mt-0.5">{i.finding_type.replace(/_/g, ' ')}</p>
      </div>
    ),
    sortFn: (a, b) => a.title.localeCompare(b.title),
  },
  {
    key: 'status',
    header: 'Status',
    width: '140px',
    render: (i) => (
      <span className={`badge ${statusBadge(i.status)}`}>{statusLabel(i.status)}</span>
    ),
    sortFn: (a, b) => a.status.localeCompare(b.status),
  },
  {
    key: 'owner',
    header: 'Owner',
    width: '140px',
    render: (i) => (
      <span className="text-xs text-gray-500 flex items-center gap-1">
        {i.management_owner ? (
          <><User className="w-3 h-3 flex-shrink-0" />{i.management_owner}</>
        ) : '—'}
      </span>
    ),
    sortFn: (a, b) => (a.management_owner ?? '').localeCompare(b.management_owner ?? ''),
  },
  {
    key: 'target_date',
    header: 'Target Date',
    width: '120px',
    render: (i) => {
      if (!i.target_remediation_date) return <span className="text-xs text-gray-400">—</span>;
      const overdue =
        new Date(i.target_remediation_date) < new Date() &&
        !['resolved', 'closed', 'risk_accepted'].includes(i.status);
      return (
        <span className={`text-xs flex items-center gap-1 ${overdue ? 'text-red-600 font-semibold' : 'text-gray-500'}`}>
          <Calendar className="w-3 h-3 flex-shrink-0" />
          {new Date(i.target_remediation_date).toLocaleDateString()}
          {overdue && <AlertTriangle className="w-3 h-3" />}
        </span>
      );
    },
    sortFn: (a, b) => {
      const da = a.target_remediation_date ? new Date(a.target_remediation_date).getTime() : Infinity;
      const db = b.target_remediation_date ? new Date(b.target_remediation_date).getTime() : Infinity;
      return da - db;
    },
  },
];

export default function IssueRegister({ tenantId, engagementId, onBack }: Props) {
  const qc = useQueryClient();
  const [view,         setView]         = useState<ViewMode>('board');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [filterSev,    setFilterSev]    = useState<FilterSeverity>('all');
  const [selectedId,   setSelectedId]   = useState<string | null>(null);
  const [showNew,      setShowNew]      = useState(false);

  const { data: issues = [], isLoading } = useQuery<AuditIssue[]>({
    queryKey: ['issues', tenantId, engagementId],
    queryFn: () => listIssues(tenantId, engagementId),
  });

  const listFiltered = issues.filter((i) => {
    if (filterStatus !== 'all' && i.status !== filterStatus) return false;
    if (filterSev    !== 'all' && i.severity !== filterSev)  return false;
    return true;
  });

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <h1 className="text-xl font-bold text-gray-900 flex-1">Issue Register</h1>

        {/* View toggle */}
        <div className="flex items-center rounded-lg border border-gray-200 overflow-hidden">
          <button
            onClick={() => setView('list')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
              view === 'list'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            <LayoutList className="w-3.5 h-3.5" />
            List
          </button>
          <button
            onClick={() => setView('board')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
              view === 'board'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            Board
          </button>
        </div>

        <button className="btn-primary" onClick={() => setShowNew(true)}>
          <Plus className="w-4 h-4" />
          New Issue
        </button>
      </div>

      {/* Severity filter (shown in both views) */}
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

      {isLoading && (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <p className="text-sm">Loading issues…</p>
        </div>
      )}

      {!isLoading && view === 'board' && (
        <KanbanBoard
          tenantId={tenantId}
          engagementId={engagementId}
          issues={issues}
          filterSev={filterSev}
          onSelectIssue={setSelectedId}
        />
      )}

      {!isLoading && view === 'list' && (
        <>
          {/* Status filter — only in list view */}
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

          <DataTable<AuditIssue>
            cols={ISSUE_COLS}
            rows={listFiltered}
            rowKey={(i) => i.id}
            emptyMessage="No issues match your filters"
            emptySubMessage="Try clearing the severity or status filter."
            searchable
            searchPlaceholder="Search by title, owner, control ref…"
            searchFields={(i) => [
              i.title,
              i.management_owner ?? '',
              i.control_reference ?? '',
              i.finding_type,
              ...(i.framework_references ?? []),
            ]}
            pageSize={20}
            expandRender={(issue) => (
              <IssueDetail
                tenantId={tenantId}
                issueId={issue.id}
                onClose={() => {}}
              />
            )}
            exportFilename="issue-register"
            exportRow={(i) => ({
              '#': i.issue_number ?? '',
              title: i.title,
              severity: i.severity,
              finding_type: i.finding_type,
              status: i.status,
              owner: i.management_owner ?? '',
              control_ref: i.control_reference ?? '',
              target_date: i.target_remediation_date ?? '',
            })}
          />
        </>
      )}

      {/* Issue detail slide-over (board view) */}
      {view === 'board' && selectedId && (
        <div className="fixed inset-0 z-40 flex justify-end" onClick={() => setSelectedId(null)}>
          <div
            className="w-full max-w-lg h-full bg-white shadow-2xl overflow-y-auto p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <IssueDetail
              tenantId={tenantId}
              issueId={selectedId}
              onClose={() => setSelectedId(null)}
            />
          </div>
        </div>
      )}

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
