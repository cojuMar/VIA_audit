import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Plus,
  Upload,
  Bell,
  ChevronDown,
  ChevronRight,
  Check,
  Download,
  X,
} from 'lucide-react';
import {
  listPBCLists,
  listPBCRequests,
  createPBCList,
  createPBCRequest,
  bulkCreatePBCRequests,
  fulfillPBCRequest,
  updatePBCRequestStatus,
  exportPBCList,
  type PBCListCreate,
  type PBCRequestCreate,
  type FulfillmentCreate,
} from '../api';
import type { PBCRequestList, PBCRequest, PBCRequestStatus } from '../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusBadge(s: PBCRequestStatus) {
  const map: Record<PBCRequestStatus, string> = {
    open: 'bg-gray-100 text-gray-700',
    in_progress: 'bg-blue-100 text-blue-700',
    fulfilled: 'bg-green-100 text-green-700',
    not_applicable: 'bg-purple-100 text-purple-700',
    overdue: 'bg-red-100 text-red-700',
  };
  return map[s] ?? 'bg-gray-100 text-gray-600';
}

function priorityBadge(p: 'high' | 'medium' | 'low') {
  const map = { high: 'bg-red-100 text-red-700', medium: 'bg-yellow-100 text-yellow-700', low: 'bg-gray-100 text-gray-600' };
  return map[p];
}

function priorityLetter(p: 'high' | 'medium' | 'low') {
  return p[0].toUpperCase();
}

function relDate(d: string | null) {
  if (!d) return '—';
  const diff = Math.ceil((new Date(d).getTime() - Date.now()) / 86_400_000);
  if (diff < 0) return `${Math.abs(diff)}d overdue`;
  if (diff === 0) return 'today';
  return `in ${diff}d`;
}

// ── Fulfill Modal ─────────────────────────────────────────────────────────────

interface FulfillModalProps {
  tenantId: string;
  request: PBCRequest;
  onClose: () => void;
  onDone: () => void;
}

function FulfillModal({ tenantId, request, onClose, onDone }: FulfillModalProps) {
  const [form, setForm] = useState<FulfillmentCreate>({
    submitted_by: '',
    response_text: '',
    submission_notes: '',
    file: null,
  });
  const fileRef = useRef<HTMLInputElement>(null);
  const mut = useMutation({
    mutationFn: () => fulfillPBCRequest(tenantId, request.id, form),
    onSuccess: onDone,
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Fulfill Request #{request.request_number}</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-gray-400" /></button>
        </div>
        <p className="text-sm text-gray-600">{request.title}</p>
        <div>
          <label className="form-label">Submitted By *</label>
          <input
            className="form-input"
            value={form.submitted_by}
            onChange={(e) => setForm((f) => ({ ...f, submitted_by: e.target.value }))}
          />
        </div>
        <div>
          <label className="form-label">Response Text</label>
          <textarea
            className="form-input"
            rows={4}
            value={form.response_text ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, response_text: e.target.value }))}
          />
        </div>
        <div>
          <label className="form-label">Attach File</label>
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={(e) => setForm((f) => ({ ...f, file: e.target.files?.[0] ?? null }))}
          />
          <button className="btn-secondary w-full" onClick={() => fileRef.current?.click()}>
            <Upload className="w-4 h-4" />
            {form.file ? form.file.name : 'Choose file…'}
          </button>
        </div>
        <div>
          <label className="form-label">Submission Notes</label>
          <input
            className="form-input"
            value={form.submission_notes ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, submission_notes: e.target.value }))}
          />
        </div>
        {mut.isError && <p className="text-sm text-red-600">Failed to submit fulfillment.</p>}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            disabled={!form.submitted_by || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? 'Submitting…' : 'Submit'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Bulk Import Modal ─────────────────────────────────────────────────────────

interface BulkImportModalProps {
  tenantId: string;
  listId: string;
  onClose: () => void;
  onDone: () => void;
}

function BulkImportModal({ tenantId, listId, onClose, onDone }: BulkImportModalProps) {
  const [raw, setRaw] = useState('');
  const [error, setError] = useState('');

  const mut = useMutation({
    mutationFn: (reqs: PBCRequestCreate[]) => bulkCreatePBCRequests(tenantId, listId, reqs),
    onSuccess: onDone,
  });

  function parse() {
    setError('');
    try {
      // Try JSON first
      const parsed = JSON.parse(raw) as PBCRequestCreate[];
      if (!Array.isArray(parsed)) throw new Error('Must be an array');
      mut.mutate(parsed);
    } catch {
      // Try CSV: title,description,category,priority
      try {
        const lines = raw.trim().split('\n').filter(Boolean);
        const headers = lines[0].split(',');
        const reqs: PBCRequestCreate[] = lines.slice(1).map((line) => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => { obj[h.trim()] = (vals[i] ?? '').trim(); });
          return {
            title: obj.title || '',
            description: obj.description || '',
            category: obj.category || null,
            priority: (obj.priority as PBCRequestCreate['priority']) || 'medium',
          };
        });
        mut.mutate(reqs);
      } catch {
        setError('Invalid JSON or CSV format.');
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Bulk Import Requests</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-gray-400" /></button>
        </div>
        <p className="text-xs text-gray-500">
          Paste a JSON array of request objects, or CSV with headers: title, description, category, priority
        </p>
        <textarea
          className="form-input font-mono text-xs"
          rows={12}
          placeholder='[{"title":"...", "description":"...", "priority":"high"}]'
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        {mut.isError && <p className="text-sm text-red-600">Failed to import.</p>}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={!raw.trim() || mut.isPending} onClick={parse}>
            {mut.isPending ? 'Importing…' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Add Request Modal ─────────────────────────────────────────────────────────

interface AddRequestModalProps {
  tenantId: string;
  listId: string;
  onClose: () => void;
  onDone: () => void;
}

function AddRequestModal({ tenantId, listId, onClose, onDone }: AddRequestModalProps) {
  const [form, setForm] = useState<PBCRequestCreate>({
    title: '',
    description: '',
    category: null,
    priority: 'medium',
    assigned_to: null,
    due_date: null,
    framework_control_ref: null,
  });

  const mut = useMutation({
    mutationFn: () => createPBCRequest(tenantId, listId, form),
    onSuccess: onDone,
  });

  function set(k: keyof PBCRequestCreate, v: unknown) {
    setForm((f) => ({ ...f, [k]: v || null }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Add Request</h2>
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
            <label className="form-label">Category</label>
            <input className="form-input" onChange={(e) => set('category', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Priority</label>
            <select className="form-input" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div>
            <label className="form-label">Assigned To</label>
            <input className="form-input" onChange={(e) => set('assigned_to', e.target.value)} />
          </div>
          <div>
            <label className="form-label">Due Date</label>
            <input type="date" className="form-input" onChange={(e) => set('due_date', e.target.value)} />
          </div>
        </div>
        <div>
          <label className="form-label">Framework Control Ref</label>
          <input className="form-input" onChange={(e) => set('framework_control_ref', e.target.value)} />
        </div>
        {mut.isError && <p className="text-sm text-red-600">Failed to create request.</p>}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={!form.title || !form.description || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? 'Adding…' : 'Add Request'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Request Row ───────────────────────────────────────────────────────────────

interface RequestRowProps {
  req: PBCRequest;
  tenantId: string;
  onFulfill: (req: PBCRequest) => void;
  listId: string;
}

function RequestRow({ req, tenantId, onFulfill, listId }: RequestRowProps) {
  const [expanded, setExpanded] = useState(false);
  const qc = useQueryClient();

  const naMut = useMutation({
    mutationFn: () => updatePBCRequestStatus(tenantId, req.id, 'not_applicable'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pbc-requests', listId] }),
  });

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 text-sm text-gray-500 w-10">{req.request_number}</td>
        <td className="px-3 py-2 w-10">
          <span className={`badge ${priorityBadge(req.priority)}`}>{priorityLetter(req.priority)}</span>
        </td>
        <td className="px-3 py-2 text-sm font-medium text-gray-800">{req.title}</td>
        <td className="px-3 py-2 text-xs text-gray-500">{req.category ?? '—'}</td>
        <td className="px-3 py-2 text-xs text-gray-500">{req.assigned_to ?? '—'}</td>
        <td className="px-3 py-2 text-xs text-gray-500">{relDate(req.due_date)}</td>
        <td className="px-3 py-2">
          <span className={`badge ${statusBadge(req.status)}`}>{req.status.replace('_', ' ')}</span>
        </td>
        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
          <div className="flex gap-1">
            {req.status !== 'fulfilled' && req.status !== 'not_applicable' && (
              <button
                className="btn-primary text-xs py-0.5"
                onClick={() => onFulfill(req)}
              >
                <Check className="w-3 h-3" />
                Fulfill
              </button>
            )}
            {req.status !== 'not_applicable' && req.status !== 'fulfilled' && (
              <button
                className="btn-secondary text-xs py-0.5"
                disabled={naMut.isPending}
                onClick={() => naMut.mutate()}
              >
                N/A
              </button>
            )}
          </div>
        </td>
        <td className="px-3 py-2 w-6">
          {expanded ? <ChevronDown className="w-3 h-3 text-gray-400" /> : <ChevronRight className="w-3 h-3 text-gray-400" />}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-blue-50">
          <td colSpan={9} className="px-6 py-3 text-sm space-y-2">
            <p className="text-gray-700">{req.description}</p>
            {req.framework_control_ref && (
              <p className="text-xs text-gray-500">Control ref: <span className="font-mono">{req.framework_control_ref}</span></p>
            )}
            {req.fulfillments && req.fulfillments.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Fulfillment History</p>
                {req.fulfillments.map((f) => (
                  <div key={f.id} className="flex items-start gap-2 text-xs text-gray-600 border-l-2 border-green-300 pl-2">
                    <span className="font-medium">{f.submitted_by}</span>
                    <span className="text-gray-400">{new Date(f.submitted_at).toLocaleString()}</span>
                    {f.response_text && <span>{f.response_text}</span>}
                    {f.file_name && (
                      <span className="text-blue-600 underline">{f.file_name}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ── New List Modal ────────────────────────────────────────────────────────────

interface NewListModalProps {
  tenantId: string;
  engagementId: string;
  onClose: () => void;
  onDone: () => void;
}

function NewListModal({ tenantId, engagementId, onClose, onDone }: NewListModalProps) {
  const [form, setForm] = useState<PBCListCreate>({ list_name: '', description: null, due_date: null });
  const mut = useMutation({
    mutationFn: () => createPBCList(tenantId, engagementId, form),
    onSuccess: onDone,
  });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-sm p-6 space-y-4">
        <h2 className="text-lg font-semibold">New PBC List</h2>
        <div>
          <label className="form-label">List Name *</label>
          <input className="form-input" value={form.list_name} onChange={(e) => setForm((f) => ({ ...f, list_name: e.target.value }))} />
        </div>
        <div>
          <label className="form-label">Description</label>
          <textarea className="form-input" rows={2} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))} />
        </div>
        <div>
          <label className="form-label">Due Date</label>
          <input type="date" className="form-input" onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value || null }))} />
        </div>
        {mut.isError && <p className="text-sm text-red-600">Failed to create list.</p>}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={!form.list_name || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Per-List View ─────────────────────────────────────────────────────────────

interface ListViewProps {
  tenantId: string;
  list: PBCRequestList;
}

function ListView({ tenantId, list }: ListViewProps) {
  const qc = useQueryClient();
  const [fulfillTarget, setFulfillTarget] = useState<PBCRequest | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showBulk, setShowBulk] = useState(false);

  const { data: requests = [], isLoading } = useQuery<PBCRequest[]>({
    queryKey: ['pbc-requests', list.id],
    queryFn: () => listPBCRequests(tenantId, list.id),
  });

  const total = requests.length;
  const fulfilled = requests.filter((r) => r.status === 'fulfilled').length;
  const open = requests.filter((r) => r.status === 'open').length;
  const inProg = requests.filter((r) => r.status === 'in_progress').length;
  const na = requests.filter((r) => r.status === 'not_applicable').length;
  const overdue = requests.filter((r) => r.status === 'overdue').length;
  const pct = total > 0 ? Math.round((fulfilled / total) * 100) : 0;

  function handleExport() {
    exportPBCList(tenantId, list.id).then((data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pbc-list-${list.list_name}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  const invalidate = () => qc.invalidateQueries({ queryKey: ['pbc-requests', list.id] });

  return (
    <div className="space-y-4">
      {/* Progress summary */}
      <div className="card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-2xl font-bold text-blue-600">{pct}%</span>
            <span className="text-sm text-gray-500 ml-2">complete ({fulfilled}/{total})</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              { label: 'Open', count: open, cls: 'bg-gray-100 text-gray-700' },
              { label: 'In Progress', count: inProg, cls: 'bg-blue-100 text-blue-700' },
              { label: 'Fulfilled', count: fulfilled, cls: 'bg-green-100 text-green-700' },
              { label: 'N/A', count: na, cls: 'bg-purple-100 text-purple-700' },
              { label: 'Overdue', count: overdue, cls: 'bg-red-100 text-red-700' },
            ].map((s) => (
              <span key={s.label} className={`badge ${s.cls}`}>{s.label}: {s.count}</span>
            ))}
          </div>
        </div>
        <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden flex">
          {total > 0 && (
            <>
              <div className="bg-green-500 h-full" style={{ width: `${(fulfilled / total) * 100}%` }} />
              <div className="bg-blue-400 h-full" style={{ width: `${(inProg / total) * 100}%` }} />
              <div className="bg-red-400 h-full" style={{ width: `${(overdue / total) * 100}%` }} />
            </>
          )}
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2">
        <button className="btn-primary" onClick={() => setShowAdd(true)}>
          <Plus className="w-4 h-4" />
          Add Request
        </button>
        <button className="btn-secondary" onClick={() => setShowBulk(true)}>
          <Upload className="w-4 h-4" />
          Bulk Import
        </button>
        <button className="btn-secondary">
          <Bell className="w-4 h-4" />
          Send Reminder
        </button>
        <div className="flex-1" />
        <button className="btn-secondary" onClick={handleExport}>
          <Download className="w-4 h-4" />
          Export JSON
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <p className="text-gray-500 text-sm">Loading requests…</p>
      ) : requests.length === 0 ? (
        <div className="card p-8 text-center text-gray-400">
          <p>No requests in this list. Add some to get started.</p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['#', 'Pri', 'Title', 'Category', 'Assigned To', 'Due', 'Status', 'Actions', ''].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {requests.map((req) => (
                <RequestRow
                  key={req.id}
                  req={req}
                  tenantId={tenantId}
                  onFulfill={setFulfillTarget}
                  listId={list.id}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {fulfillTarget && (
        <FulfillModal
          tenantId={tenantId}
          request={fulfillTarget}
          onClose={() => setFulfillTarget(null)}
          onDone={() => { setFulfillTarget(null); invalidate(); }}
        />
      )}
      {showAdd && (
        <AddRequestModal
          tenantId={tenantId}
          listId={list.id}
          onClose={() => setShowAdd(false)}
          onDone={() => { setShowAdd(false); invalidate(); }}
        />
      )}
      {showBulk && (
        <BulkImportModal
          tenantId={tenantId}
          listId={list.id}
          onClose={() => setShowBulk(false)}
          onDone={() => { setShowBulk(false); invalidate(); }}
        />
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface Props {
  tenantId: string;
  engagementId: string;
  onBack: () => void;
}

export default function PBCRequestListView({ tenantId, engagementId, onBack }: Props) {
  const qc = useQueryClient();
  const [activeListId, setActiveListId] = useState<string | null>(null);
  const [showNewList, setShowNewList] = useState(false);

  const { data: lists = [], isLoading } = useQuery<PBCRequestList[]>({
    queryKey: ['pbc-lists', tenantId, engagementId],
    queryFn: () => listPBCLists(tenantId, engagementId),
  });

  const activeList = lists.find((l) => l.id === activeListId) ?? lists[0] ?? null;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <h1 className="text-xl font-bold text-gray-900 flex-1">PBC Request Manager</h1>
      </div>

      {/* List tabs */}
      <div className="flex items-center gap-2 border-b border-gray-200 pb-0">
        {isLoading && <span className="text-sm text-gray-400">Loading lists…</span>}
        {lists.map((list) => (
          <button
            key={list.id}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              (activeListId ?? lists[0]?.id) === list.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => setActiveListId(list.id)}
          >
            {list.list_name}
          </button>
        ))}
        <button
          className="ml-2 btn-secondary text-xs"
          onClick={() => setShowNewList(true)}
        >
          <Plus className="w-3 h-3" />
          New List
        </button>
      </div>

      {/* Per-list view */}
      {activeList ? (
        <ListView tenantId={tenantId} list={activeList} />
      ) : (
        !isLoading && (
          <div className="card p-12 text-center text-gray-400">
            <p>No PBC lists yet. Create one to get started.</p>
          </div>
        )
      )}

      {showNewList && (
        <NewListModal
          tenantId={tenantId}
          engagementId={engagementId}
          onClose={() => setShowNewList(false)}
          onDone={() => {
            setShowNewList(false);
            qc.invalidateQueries({ queryKey: ['pbc-lists', tenantId, engagementId] });
          }}
        />
      )}
    </div>
  );
}
