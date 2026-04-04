import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Settings,
  FileText,
  Activity,
  Shield,
  MessageSquare,
  Upload,
  Trash2,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  Check,
  ExternalLink,
} from 'lucide-react';
import {
  getAdminConfig,
  upsertAdminConfig,
  getAdminDocuments,
  uploadDocument,
  deleteDocument,
  getAccessLogs,
  getAccessStats,
  getNDAList,
  getNDAStats,
  getDeflections,
} from '../api';
import type {
  PortalConfig,
  PortalDocument,
  AccessLogEvent,
  AccessLogStats,
  NDAAcceptance,
  DeflectionResult,
} from '../types';

interface Props {
  tenantId: string;
}

type AdminTab = 'config' | 'documents' | 'logs' | 'ndas' | 'deflections';

// ── Utility ──────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ── Toggle ────────────────────────────────────────────────────────────────────

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-blue-600' : 'bg-gray-200'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
}

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-5 py-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

// ── Tab 1: Configuration ──────────────────────────────────────────────────────

const FRAMEWORK_OPTIONS = [
  'soc2', 'iso27001', 'pci_dss', 'hipaa', 'gdpr', 'nist_csf', 'cis_controls', 'fedramp',
];

function ConfigTab({ tenantId }: { tenantId: string }) {
  const qc = useQueryClient();
  const { data: config, isLoading } = useQuery({
    queryKey: ['admin', 'config', tenantId],
    queryFn: () => getAdminConfig(tenantId),
  });

  const [form, setForm] = useState<Partial<PortalConfig>>({});
  const [saved, setSaved] = useState(false);

  React.useEffect(() => {
    if (config) setForm(config);
  }, [config]);

  const mutation = useMutation({
    mutationFn: (data: Partial<PortalConfig>) => upsertAdminConfig(tenantId, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin', 'config', tenantId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const set = <K extends keyof PortalConfig>(key: K, value: PortalConfig[K]) =>
    setForm(prev => ({ ...prev, [key]: value }));

  const toggleFramework = (fw: string) => {
    const current = form.allowed_frameworks ?? [];
    set('allowed_frameworks', current.includes(fw) ? current.filter(f => f !== fw) : [...current, fw]);
  };

  const slugValid = !form.slug || /^[a-z0-9-]+$/.test(form.slug);

  if (isLoading) return <div className="py-10 text-center text-gray-400">Loading...</div>;

  return (
    <div className="max-w-2xl space-y-8">
      {/* Portal Status */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Portal Status</h3>
        <div className="space-y-3">
          {([
            ['portal_enabled', 'Portal Enabled', 'Make this portal publicly accessible'],
            ['require_nda', 'Require NDA', 'Require visitors to sign NDA before downloading documents'],
            ['show_compliance_scores', 'Show Compliance Scores', 'Display framework scores on the public portal'],
            ['chatbot_enabled', 'Enable Chatbot', 'Show the AI security chatbot on the public portal'],
          ] as Array<[keyof PortalConfig, string, string]>).map(([key, label, desc]) => (
            <div key={key} className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium text-gray-700">{label}</p>
                <p className="text-xs text-gray-400">{desc}</p>
              </div>
              <Toggle
                checked={!!(form[key])}
                onChange={v => set(key, v as PortalConfig[typeof key])}
              />
            </div>
          ))}
        </div>
      </section>

      {/* Branding */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Branding</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">Slug</label>
            <input
              type="text"
              value={form.slug ?? ''}
              onChange={e => set('slug', e.target.value)}
              placeholder="my-company"
              className={`w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                !slugValid ? 'border-red-400' : 'border-gray-300'
              }`}
            />
            {!slugValid && <p className="text-xs text-red-500 mt-1">Only lowercase letters, numbers, and hyphens.</p>}
            {form.slug && (
              <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
                <ExternalLink size={10} />
                https://portal.example.com/portal/{form.slug}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Company Name</label>
            <input
              type="text"
              value={form.company_name ?? ''}
              onChange={e => set('company_name', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Tagline</label>
            <input
              type="text"
              value={form.tagline ?? ''}
              onChange={e => set('tagline', e.target.value || null as unknown as string)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Logo URL</label>
            <input
              type="url"
              value={form.logo_url ?? ''}
              onChange={e => set('logo_url', e.target.value || null as unknown as string)}
              placeholder="https://..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Primary Color</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={form.primary_color ?? '#2563eb'}
                onChange={e => set('primary_color', e.target.value)}
                className="h-9 w-12 cursor-pointer rounded border border-gray-300 p-0.5"
              />
              <input
                type="text"
                value={form.primary_color ?? '#2563eb'}
                onChange={e => set('primary_color', e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Chatbot */}
      {form.chatbot_enabled && (
        <section>
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Chatbot</h3>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Welcome Message</label>
            <textarea
              value={form.chatbot_welcome_message ?? ''}
              onChange={e => set('chatbot_welcome_message', e.target.value || null as unknown as string)}
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              placeholder="Hello! I can answer questions about our security posture..."
            />
          </div>
        </section>
      )}

      {/* Frameworks */}
      <section>
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Allowed Frameworks</h3>
        <div className="flex flex-wrap gap-2">
          {FRAMEWORK_OPTIONS.map(fw => {
            const selected = (form.allowed_frameworks ?? []).includes(fw);
            return (
              <button
                key={fw}
                type="button"
                onClick={() => toggleFramework(fw)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                  selected
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                }`}
              >
                {selected && <Check size={11} />}
                {fw.toUpperCase().replace(/_/g, ' ')}
              </button>
            );
          })}
        </div>
      </section>

      {/* Save */}
      <button
        onClick={() => mutation.mutate(form)}
        disabled={mutation.isPending || !slugValid}
        className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {mutation.isPending && (
          <span className="inline-block w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
        )}
        {saved ? <><Check size={14} /> Saved!</> : 'Save Configuration'}
      </button>
    </div>
  );
}

// ── Tab 2: Documents ──────────────────────────────────────────────────────────

const DOC_TYPES = [
  { value: 'soc2_report', label: 'SOC 2 Report' },
  { value: 'iso_cert', label: 'ISO Certificate' },
  { value: 'pentest', label: 'Pen Test' },
  { value: 'security_overview', label: 'Security Overview' },
  { value: 'other', label: 'Other' },
];

function DocumentsTab({ tenantId }: { tenantId: string }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadForm, setUploadForm] = useState({
    display_name: '',
    document_type: 'soc2_report',
    description: '',
    requires_nda: false,
    valid_until: '',
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: docs, isLoading } = useQuery({
    queryKey: ['admin', 'documents', tenantId],
    queryFn: () => getAdminDocuments(tenantId),
  });

  const uploadMutation = useMutation({
    mutationFn: (fd: FormData) => uploadDocument(tenantId, fd),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin', 'documents', tenantId] });
      setSelectedFile(null);
      setUploadForm({ display_name: '', document_type: 'soc2_report', description: '', requires_nda: false, valid_until: '' });
      setUploadError(null);
    },
    onError: () => setUploadError('Upload failed. Please try again.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (docId: string) => deleteDocument(tenantId, docId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['admin', 'documents', tenantId] }),
  });

  const handleFile = (file: File) => {
    setSelectedFile(file);
    if (!uploadForm.display_name) {
      setUploadForm(prev => ({ ...prev, display_name: file.name.replace(/\.[^.]+$/, '') }));
    }
  };

  const handleUpload = () => {
    if (!selectedFile) { setUploadError('Please select a file.'); return; }
    if (!uploadForm.display_name) { setUploadError('Please enter a document name.'); return; }
    const fd = new FormData();
    fd.append('file', selectedFile);
    Object.entries(uploadForm).forEach(([k, v]) => fd.append(k, String(v)));
    uploadMutation.mutate(fd);
  };

  const DOC_TYPE_LABELS: Record<string, string> = Object.fromEntries(DOC_TYPES.map(t => [t.value, t.label]));

  return (
    <div className="space-y-8">
      {/* Upload Area */}
      <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-5">
        <h3 className="text-sm font-semibold text-gray-900">Upload Document</h3>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
          }}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-300 hover:bg-gray-50'
          }`}
        >
          <Upload size={24} className="mx-auto mb-2 text-gray-400" />
          <p className="text-sm text-gray-600">
            {selectedFile ? (
              <span className="text-blue-600 font-medium">{selectedFile.name} ({formatBytes(selectedFile.size)})</span>
            ) : (
              <>Drag & drop or <span className="text-blue-600">browse</span> — PDF, DOCX, PNG</>
            )}
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.png"
            className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
        </div>

        {/* Upload form fields */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Display Name</label>
            <input
              type="text"
              value={uploadForm.display_name}
              onChange={e => setUploadForm(p => ({ ...p, display_name: e.target.value }))}
              placeholder="SOC 2 Type II Report 2025"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Document Type</label>
            <select
              value={uploadForm.document_type}
              onChange={e => setUploadForm(p => ({ ...p, document_type: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {DOC_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <input
              type="text"
              value={uploadForm.description}
              onChange={e => setUploadForm(p => ({ ...p, description: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Valid Until</label>
            <input
              type="date"
              value={uploadForm.valid_until}
              onChange={e => setUploadForm(p => ({ ...p, valid_until: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex items-center gap-3 pt-5">
            <Toggle
              checked={uploadForm.requires_nda}
              onChange={v => setUploadForm(p => ({ ...p, requires_nda: v }))}
            />
            <label className="text-sm text-gray-600">Requires NDA</label>
          </div>
        </div>

        {uploadError && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {uploadError}
          </p>
        )}

        <button
          onClick={handleUpload}
          disabled={uploadMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {uploadMutation.isPending && (
            <span className="inline-block w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          )}
          <Upload size={14} /> Upload Document
        </button>
      </div>

      {/* Document Table */}
      {isLoading ? (
        <div className="text-center py-8 text-gray-400">Loading...</div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Name', 'Type', 'NDA Required', 'Visible', 'Valid Until', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {(docs ?? []).map((doc: PortalDocument) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-800">{doc.display_name}</p>
                    {doc.file_size_bytes && (
                      <p className="text-xs text-gray-400">{formatBytes(doc.file_size_bytes)}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${doc.requires_nda ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-500'}`}>
                      {doc.requires_nda ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${doc.is_visible ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {doc.is_visible ? 'Visible' : 'Hidden'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {doc.valid_until
                      ? new Date(doc.valid_until).toLocaleDateString()
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors" title={doc.is_visible ? 'Hide' : 'Show'}>
                        {doc.is_visible ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                      <button
                        onClick={() => {
                          if (confirm('Delete this document?')) deleteMutation.mutate(doc.id);
                        }}
                        className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(docs ?? []).length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-gray-400 text-sm">
                    No documents uploaded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Tab 3: Access Logs ────────────────────────────────────────────────────────

const EVENT_FILTER_CHIPS = [
  { label: 'All', value: '' },
  { label: 'Page Views', value: 'page_view' },
  { label: 'Downloads', value: 'document_download' },
  { label: 'Chatbot', value: 'chatbot_message' },
  { label: 'NDAs', value: 'nda_signed' },
  { label: 'Deflections', value: 'deflection_submitted' },
];

function LogsTab({ tenantId }: { tenantId: string }) {
  const [eventFilter, setEventFilter] = useState('');

  const { data: stats } = useQuery<AccessLogStats>({
    queryKey: ['admin', 'logs', 'stats', tenantId],
    queryFn: () => getAccessStats(tenantId),
  });

  const { data: logs, isLoading } = useQuery<AccessLogEvent[]>({
    queryKey: ['admin', 'logs', tenantId, eventFilter],
    queryFn: () => getAccessLogs(tenantId, 100, eventFilter || undefined),
  });

  const STAT_CARDS = [
    ['Total Views', stats?.total_views ?? 0],
    ['Unique Visitors', stats?.unique_visitors ?? 0],
    ['Downloads', stats?.document_downloads ?? 0],
    ['Chatbot Messages', stats?.chatbot_messages ?? 0],
    ['NDAs Signed', stats?.ndas_signed ?? 0],
    ['Last 30 Days', stats?.last_30_days ?? 0],
  ] as Array<[string, number]>;

  return (
    <div className="space-y-6">
      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {STAT_CARDS.map(([label, value]) => (
          <StatCard key={label} label={label} value={value} />
        ))}
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        {EVENT_FILTER_CHIPS.map(chip => (
          <button
            key={chip.value}
            onClick={() => setEventFilter(chip.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
              eventFilter === chip.value
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Log table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {['Time', 'Event', 'Visitor Email', 'Company', 'Details'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-gray-400">Loading...</td>
              </tr>
            ) : (logs ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-gray-400">No log events found.</td>
              </tr>
            ) : (
              (logs ?? []).map((ev: AccessLogEvent) => (
                <tr key={ev.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">{timeAgo(ev.occurred_at)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-medium px-2 py-0.5 bg-gray-100 rounded-full text-gray-600">
                      {ev.event_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{ev.visitor_email ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-600">{ev.visitor_company ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span
                      title={JSON.stringify(ev.metadata, null, 2)}
                      className="cursor-help text-xs text-gray-400 underline decoration-dotted"
                    >
                      {Object.keys(ev.metadata).length > 0 ? 'hover to view' : '—'}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Tab 4: NDA Acceptances ────────────────────────────────────────────────────

interface NDARecord extends NDAAcceptance {
  ip_address?: string;
  signed_at?: string;
}

function NDATab({ tenantId }: { tenantId: string }) {
  const { data: ndas, isLoading } = useQuery<NDARecord[]>({
    queryKey: ['admin', 'ndas', tenantId],
    queryFn: () => getNDAList(tenantId) as Promise<NDARecord[]>,
  });

  const { data: stats } = useQuery<{ total: number; last_7_days: number; unique_companies: number }>({
    queryKey: ['admin', 'ndas', 'stats', tenantId],
    queryFn: () => getNDAStats(tenantId),
  });

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard label="Total Accepted" value={stats?.total ?? 0} />
        <StatCard label="Last 7 Days" value={stats?.last_7_days ?? 0} />
        <StatCard label="Unique Companies" value={stats?.unique_companies ?? 0} />
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {['Name', 'Email', 'Company', 'IP Address', 'Signed At'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-400">Loading...</td></tr>
            ) : (ndas ?? []).length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-gray-400">No NDA acceptances yet.</td></tr>
            ) : (
              (ndas ?? []).map((nda, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">{nda.signatory_name}</td>
                  <td className="px-4 py-3 text-gray-600">{nda.signatory_email}</td>
                  <td className="px-4 py-3 text-gray-600">{nda.signatory_company ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{nda.ip_address ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {nda.signed_at ? timeAgo(nda.signed_at) : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Tab 5: Questionnaire Deflections ─────────────────────────────────────────

function DeflectionsTab({ tenantId }: { tenantId: string }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: deflections, isLoading } = useQuery<DeflectionResult[]>({
    queryKey: ['admin', 'deflections', tenantId],
    queryFn: () => getDeflections(tenantId),
  });

  const STATUS_STYLES: Record<string, string> = {
    completed: 'bg-green-100 text-green-700',
    pending: 'bg-yellow-100 text-yellow-700',
    processing: 'bg-blue-100 text-blue-700',
    failed: 'bg-red-100 text-red-700',
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            {['ID', 'Questions', 'Status', ''].map(h => (
              <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {isLoading ? (
            <tr><td colSpan={4} className="px-4 py-10 text-center text-gray-400">Loading...</td></tr>
          ) : (deflections ?? []).length === 0 ? (
            <tr><td colSpan={4} className="px-4 py-10 text-center text-gray-400">No deflections yet.</td></tr>
          ) : (
            (deflections ?? []).map((d: DeflectionResult) => (
              <React.Fragment key={d.id}>
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">{d.id.slice(0, 8)}…</td>
                  <td className="px-4 py-3 text-gray-700">{d.deflection_mappings.length}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[d.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {d.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {d.deflection_mappings.length > 0 && (
                      <button
                        onClick={() => setExpanded(expanded === d.id ? null : d.id)}
                        className="text-xs text-blue-500 hover:underline flex items-center gap-1"
                      >
                        {expanded === d.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                        {expanded === d.id ? 'Collapse' : 'Expand'}
                      </button>
                    )}
                  </td>
                </tr>
                {expanded === d.id && d.deflection_mappings.length > 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 pb-4 bg-gray-50">
                      <div className="space-y-2 mt-2">
                        {d.deflection_mappings.map((m, i) => (
                          <div key={i} className="border border-gray-200 rounded-lg p-3 bg-white">
                            <p className="text-xs font-semibold text-gray-800 mb-1">{m.question}</p>
                            <p className="text-xs text-gray-600">{m.ai_response}</p>
                            {m.rag_evidence.length > 0 && (
                              <div className="mt-2 space-y-1">
                                {m.rag_evidence.map((ev, j) => (
                                  <div key={j} className="text-xs bg-gray-50 rounded px-2 py-1 text-gray-500">
                                    <span className="font-medium">{ev.title}</span>: {ev.snippet}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Admin Shell ──────────────────────────────────────────────────────────

export default function TrustPortalAdmin({ tenantId }: Props) {
  const [activeTab, setActiveTab] = useState<AdminTab>('config');

  const tabs: Array<{ id: AdminTab; label: string; icon: React.ReactNode }> = [
    { id: 'config', label: 'Configuration', icon: <Settings size={16} /> },
    { id: 'documents', label: 'Documents', icon: <FileText size={16} /> },
    { id: 'logs', label: 'Access Logs', icon: <Activity size={16} /> },
    { id: 'ndas', label: 'NDA Acceptances', icon: <Shield size={16} /> },
    { id: 'deflections', label: 'Deflections', icon: <MessageSquare size={16} /> },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900">Trust Portal Admin</h1>
            <p className="text-xs text-gray-400 font-mono">Tenant: {tenantId}</p>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-8 flex gap-6">
        {/* Sidebar nav */}
        <aside className="w-48 shrink-0">
          <nav className="space-y-1">
            {tabs.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <main className="flex-1 min-w-0">
          <h2 className="text-base font-semibold text-gray-900 mb-6">
            {tabs.find(t => t.id === activeTab)?.label}
          </h2>
          {activeTab === 'config' && <ConfigTab tenantId={tenantId} />}
          {activeTab === 'documents' && <DocumentsTab tenantId={tenantId} />}
          {activeTab === 'logs' && <LogsTab tenantId={tenantId} />}
          {activeTab === 'ndas' && <NDATab tenantId={tenantId} />}
          {activeTab === 'deflections' && <DeflectionsTab tenantId={tenantId} />}
        </main>
      </div>
    </div>
  );
}
