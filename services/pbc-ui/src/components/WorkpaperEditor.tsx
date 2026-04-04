import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Plus,
  Check,
  Circle,
  ChevronRight,
  X,
  Trash2,
} from 'lucide-react';
import {
  listWorkpapers,
  getWorkpaper,
  createWorkpaper,
  updateWorkpaperStatus,
  updateWorkpaperSection,
  listTemplates,
  type WorkpaperCreate,
} from '../api';
import type {
  Workpaper,
  WorkpaperSection,
  WorkpaperTemplate,
  WorkpaperStatus,
  WorkpaperField,
} from '../types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function wpStatusBadge(s: WorkpaperStatus) {
  const map: Record<WorkpaperStatus, string> = {
    draft: 'bg-gray-100 text-gray-600',
    in_review: 'bg-yellow-100 text-yellow-700',
    reviewed: 'bg-blue-100 text-blue-700',
    final: 'bg-green-100 text-green-700',
    superseded: 'bg-red-100 text-red-500',
  };
  return map[s] ?? 'bg-gray-100 text-gray-600';
}

function completionPct(wp: Workpaper) {
  if (!wp.sections || wp.sections.length === 0) return 0;
  return Math.round((wp.sections.filter((s) => s.is_complete).length / wp.sections.length) * 100);
}

// ── Risk Table Field ──────────────────────────────────────────────────────────

interface RiskRow {
  risk: string;
  likelihood: string;
  impact: string;
  rating: string;
  mitigation: string;
}

function RiskTable({ value, onChange }: { value: RiskRow[]; onChange: (rows: RiskRow[]) => void }) {
  function addRow() {
    onChange([...value, { risk: '', likelihood: 'medium', impact: 'medium', rating: 'medium', mitigation: '' }]);
  }
  function removeRow(i: number) {
    onChange(value.filter((_, idx) => idx !== i));
  }
  function updateRow(i: number, k: keyof RiskRow, v: string) {
    onChange(value.map((r, idx) => idx === i ? { ...r, [k]: v } : r));
  }

  const LEVELS = ['low', 'medium', 'high', 'critical'];

  return (
    <div className="space-y-2">
      <table className="w-full text-xs border border-gray-200 rounded">
        <thead className="bg-gray-50">
          <tr>
            {['Risk', 'Likelihood', 'Impact', 'Rating', 'Mitigation', ''].map((h) => (
              <th key={h} className="px-2 py-1 text-left font-medium text-gray-500">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {value.map((row, i) => (
            <tr key={i} className="border-t border-gray-100">
              <td className="px-1 py-1">
                <input
                  className="form-input text-xs py-0.5"
                  value={row.risk}
                  onChange={(e) => updateRow(i, 'risk', e.target.value)}
                />
              </td>
              {(['likelihood', 'impact', 'rating'] as const).map((k) => (
                <td key={k} className="px-1 py-1">
                  <select className="form-input text-xs py-0.5" value={row[k]} onChange={(e) => updateRow(i, k, e.target.value)}>
                    {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </td>
              ))}
              <td className="px-1 py-1">
                <input
                  className="form-input text-xs py-0.5"
                  value={row.mitigation}
                  onChange={(e) => updateRow(i, 'mitigation', e.target.value)}
                />
              </td>
              <td className="px-1 py-1">
                <button onClick={() => removeRow(i)} className="text-red-400 hover:text-red-600">
                  <Trash2 className="w-3 h-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="btn-secondary text-xs" onClick={addRow}>
        <Plus className="w-3 h-3" />
        Add Row
      </button>
    </div>
  );
}

// ── Field Renderer ────────────────────────────────────────────────────────────

function FieldRenderer({
  field,
  value,
  onChange,
}: {
  field: WorkpaperField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (field.type === 'risk_table') {
    return (
      <RiskTable
        value={(value as RiskRow[]) ?? []}
        onChange={onChange}
      />
    );
  }
  if (field.type === 'textarea') {
    return (
      <textarea
        className="form-input"
        rows={4}
        value={(value as string) ?? ''}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (field.type === 'select') {
    return (
      <select
        className="form-input"
        value={(value as string) ?? ''}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select…</option>
        {field.options?.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  return (
    <input
      type={field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}
      className="form-input"
      value={(value as string) ?? ''}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// ── Section Card ──────────────────────────────────────────────────────────────

interface SectionCardProps {
  tenantId: string;
  wpId: string;
  section: WorkpaperSection;
  fields: WorkpaperField[];
  onSaved: () => void;
}

function SectionCard({ tenantId, wpId, section, fields, onSaved }: SectionCardProps) {
  const qc = useQueryClient();
  const [content, setContent] = useState<Record<string, unknown>>(section.content ?? {});
  const [complete, setComplete] = useState(section.is_complete);

  const mut = useMutation({
    mutationFn: () =>
      updateWorkpaperSection(tenantId, wpId, section.id, { content, is_complete: complete }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workpaper', tenantId, wpId] });
      onSaved();
    },
  });

  function setField(key: string, val: unknown) {
    setContent((c) => ({ ...c, [key]: val }));
  }

  return (
    <div id={`section-${section.id}`} className="card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">{section.title}</h3>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={complete}
            onChange={(e) => setComplete(e.target.checked)}
            className="rounded"
          />
          <span className="text-sm text-gray-600">Mark Complete</span>
        </label>
      </div>
      {fields.length > 0 ? (
        <div className="space-y-3">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="form-label">{f.label}</label>
              <FieldRenderer
                field={f}
                value={content[f.key]}
                onChange={(v) => setField(f.key, v)}
              />
            </div>
          ))}
        </div>
      ) : (
        <div>
          <label className="form-label">Notes</label>
          <textarea
            className="form-input"
            rows={4}
            value={(content['notes'] as string) ?? ''}
            onChange={(e) => setField('notes', e.target.value)}
          />
        </div>
      )}
      {mut.isError && <p className="text-sm text-red-600">Failed to save section.</p>}
      <div className="flex justify-end">
        <button className="btn-primary" disabled={mut.isPending} onClick={() => mut.mutate()}>
          {mut.isPending ? 'Saving…' : 'Save Section'}
        </button>
      </div>
    </div>
  );
}

// ── Template Picker Modal ─────────────────────────────────────────────────────

interface TemplatePickerProps {
  tenantId: string;
  engagementId: string;
  onClose: () => void;
  onDone: (wp: Workpaper) => void;
}

function TemplatePickerModal({ tenantId, engagementId, onClose, onDone }: TemplatePickerProps) {
  const [step, setStep] = useState<'pick' | 'details'>('pick');
  const [selectedTemplate, setSelectedTemplate] = useState<WorkpaperTemplate | null>(null);
  const [form, setForm] = useState<WorkpaperCreate>({
    title: '',
    template_id: null,
    wp_reference: null,
    workpaper_type: 'standard',
    preparer: null,
    reviewer: null,
  });

  const { data: templates = [] } = useQuery<WorkpaperTemplate[]>({
    queryKey: ['templates', tenantId],
    queryFn: () => listTemplates(tenantId),
  });

  const mut = useMutation({
    mutationFn: () => createWorkpaper(tenantId, engagementId, form),
    onSuccess: onDone,
  });

  function pickTemplate(t: WorkpaperTemplate | null) {
    setSelectedTemplate(t);
    setForm((f) => ({
      ...f,
      template_id: t?.id ?? null,
      title: t?.title ?? '',
      workpaper_type: t?.template_type ?? 'standard',
    }));
    setStep('details');
  }

  function set(k: keyof WorkpaperCreate, v: unknown) {
    setForm((f) => ({ ...f, [k]: v || null }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="card w-full max-w-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {step === 'pick' ? 'Choose Template' : 'Workpaper Details'}
          </h2>
          <button onClick={onClose}><X className="w-4 h-4 text-gray-400" /></button>
        </div>

        {step === 'pick' && (
          <div className="space-y-3">
            {/* Blank option */}
            <button
              className="card p-4 w-full text-left hover:bg-gray-50 transition-colors border-2 border-dashed border-gray-300"
              onClick={() => pickTemplate(null)}
            >
              <p className="font-medium text-gray-700">Blank Workpaper</p>
              <p className="text-xs text-gray-400">Start from scratch with no pre-defined sections</p>
            </button>
            {templates.map((t) => (
              <button
                key={t.id}
                className="card p-4 w-full text-left hover:bg-blue-50 transition-colors"
                onClick={() => pickTemplate(t)}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-medium text-gray-800">{t.title}</p>
                    {t.description && <p className="text-xs text-gray-500 mt-0.5">{t.description}</p>}
                  </div>
                  <span className="badge bg-indigo-100 text-indigo-700 ml-2 flex-shrink-0">{t.template_type}</span>
                </div>
                {t.framework_references?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {t.framework_references.map((r) => (
                      <span key={r} className="badge bg-gray-100 text-gray-600">{r}</span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}

        {step === 'details' && (
          <div className="space-y-3">
            {selectedTemplate && (
              <p className="text-sm text-gray-500">Template: <span className="font-medium">{selectedTemplate.title}</span></p>
            )}
            <div>
              <label className="form-label">Title *</label>
              <input className="form-input" value={form.title} onChange={(e) => set('title', e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="form-label">WP Reference</label>
                <input className="form-input" placeholder="WP-001" onChange={(e) => set('wp_reference', e.target.value)} />
              </div>
              <div>
                <label className="form-label">Type</label>
                <select className="form-input" value={form.workpaper_type ?? 'standard'} onChange={(e) => set('workpaper_type', e.target.value)}>
                  {['standard', 'lead_schedule', 'supporting', 'memo', 'risk_assessment'].map((t) => (
                    <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="form-label">Preparer</label>
                <input className="form-input" onChange={(e) => set('preparer', e.target.value)} />
              </div>
              <div>
                <label className="form-label">Reviewer</label>
                <input className="form-input" onChange={(e) => set('reviewer', e.target.value)} />
              </div>
            </div>
            {mut.isError && <p className="text-sm text-red-600">Failed to create workpaper.</p>}
            <div className="flex justify-between">
              <button className="btn-secondary" onClick={() => setStep('pick')}>Back</button>
              <div className="flex gap-2">
                <button className="btn-secondary" onClick={onClose}>Cancel</button>
                <button className="btn-primary" disabled={!form.title || mut.isPending} onClick={() => mut.mutate()}>
                  {mut.isPending ? 'Creating…' : 'Create Workpaper'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Workpaper List ────────────────────────────────────────────────────────────

interface WPListProps {
  tenantId: string;
  engagementId: string;
  onOpen: (wp: Workpaper) => void;
}

function WorkpaperList({ tenantId, engagementId, onOpen }: WPListProps) {
  const qc = useQueryClient();
  const [showPicker, setShowPicker] = useState(false);

  const { data: workpapers = [], isLoading } = useQuery<Workpaper[]>({
    queryKey: ['workpapers', tenantId, engagementId],
    queryFn: () => listWorkpapers(tenantId, engagementId),
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateWorkpaperStatus(tenantId, id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['workpapers', tenantId, engagementId] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Workpapers</h2>
        <button className="btn-primary" onClick={() => setShowPicker(true)}>
          <Plus className="w-4 h-4" />
          New Workpaper
        </button>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading workpapers…</p>}

      {!isLoading && workpapers.length === 0 && (
        <div className="card p-10 text-center text-gray-400">
          <p>No workpapers yet. Create one to get started.</p>
        </div>
      )}

      {workpapers.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['WP Ref', 'Title', 'Type', 'Preparer', 'Status', 'Completion', 'Actions'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {workpapers.map((wp) => {
                const pct = completionPct(wp);
                return (
                  <tr key={wp.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-mono text-xs text-gray-500">{wp.wp_reference ?? '—'}</td>
                    <td className="px-3 py-2 font-medium text-gray-800">{wp.title}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{wp.workpaper_type.replace(/_/g, ' ')}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{wp.preparer ?? '—'}</td>
                    <td className="px-3 py-2">
                      <span className={`badge ${wpStatusBadge(wp.status)}`}>{wp.status.replace(/_/g, ' ')}</span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                          <div className="bg-blue-500 h-full" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs text-gray-500">{pct}%</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        <button className="btn-secondary text-xs py-0.5" onClick={() => onOpen(wp)}>
                          Open
                        </button>
                        {wp.status === 'draft' && (
                          <button
                            className="btn-secondary text-xs py-0.5"
                            disabled={statusMut.isPending}
                            onClick={() => statusMut.mutate({ id: wp.id, status: 'in_review' })}
                          >
                            Submit for Review
                          </button>
                        )}
                        {wp.status === 'reviewed' && (
                          <button
                            className="btn-primary text-xs py-0.5"
                            disabled={statusMut.isPending}
                            onClick={() => statusMut.mutate({ id: wp.id, status: 'final' })}
                          >
                            Finalize
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showPicker && (
        <TemplatePickerModal
          tenantId={tenantId}
          engagementId={engagementId}
          onClose={() => setShowPicker(false)}
          onDone={(wp) => {
            setShowPicker(false);
            qc.invalidateQueries({ queryKey: ['workpapers', tenantId, engagementId] });
            onOpen(wp);
          }}
        />
      )}
    </div>
  );
}

// ── Workpaper Editor View ─────────────────────────────────────────────────────

interface EditorViewProps {
  tenantId: string;
  wp: Workpaper;
  onBack: () => void;
  engagementId: string;
}

function EditorView({ tenantId, wp: initialWp, onBack, engagementId }: EditorViewProps) {
  const qc = useQueryClient();
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);

  const { data: wp } = useQuery<Workpaper>({
    queryKey: ['workpaper', tenantId, initialWp.id],
    queryFn: () => getWorkpaper(tenantId, initialWp.id),
    initialData: initialWp,
  });

  const { data: templates = [] } = useQuery<WorkpaperTemplate[]>({
    queryKey: ['templates', tenantId],
    queryFn: () => listTemplates(tenantId),
  });

  const statusMut = useMutation({
    mutationFn: (status: string) => updateWorkpaperStatus(tenantId, wp!.id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workpaper', tenantId, wp!.id] });
      qc.invalidateQueries({ queryKey: ['workpapers', tenantId, engagementId] });
    },
  });

  if (!wp) return null;

  const sections = wp.sections ?? [];
  const totalSections = sections.length;
  const completeSections = sections.filter((s) => s.is_complete).length;
  const pct = totalSections > 0 ? Math.round((completeSections / totalSections) * 100) : 0;

  // Find fields for a section
  const template = templates.find((t) => t.id === wp.template_id);
  function fieldsForSection(sec: WorkpaperSection): WorkpaperField[] {
    return template?.sections.find((ts) => ts.section_key === sec.section_key)?.fields ?? [];
  }

  function scrollTo(secId: string) {
    setActiveSectionId(secId);
    document.getElementById(`section-${secId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <div className="space-y-4">
      {/* Breadcrumb + Header */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <button className="hover:text-gray-700" onClick={onBack}>Workpapers</button>
        <ChevronRight className="w-3 h-3" />
        <span className="text-gray-800 font-medium">{wp.title}</span>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        {wp.wp_reference && <span className="font-mono text-sm text-gray-500">{wp.wp_reference}</span>}
        <h2 className="text-lg font-bold text-gray-900">{wp.title}</h2>
        <span className={`badge ${wpStatusBadge(wp.status)}`}>{wp.status.replace(/_/g, ' ')}</span>
        {wp.preparer && <span className="text-sm text-gray-500">Preparer: {wp.preparer}</span>}
        <div className="flex-1" />
        {wp.status === 'draft' && (
          <button className="btn-secondary" disabled={statusMut.isPending} onClick={() => statusMut.mutate('in_review')}>
            Submit for Review
          </button>
        )}
        {wp.status === 'reviewed' && (
          <button className="btn-primary" disabled={statusMut.isPending} onClick={() => statusMut.mutate('final')}>
            Finalize
          </button>
        )}
      </div>

      {/* Completion bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{completeSections} of {totalSections} sections complete</span>
          <span>{pct}%</span>
        </div>
        <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
          <div className="bg-blue-500 h-full transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Review notes */}
      {wp.status === 'in_review' && wp.review_notes && (
        <div className="card p-4 border-l-4 border-yellow-400 bg-yellow-50">
          <p className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-1">Reviewer Notes</p>
          <p className="text-sm text-yellow-800 whitespace-pre-wrap">{wp.review_notes}</p>
        </div>
      )}

      {/* Layout: sidebar + sections */}
      {sections.length > 0 ? (
        <div className="flex gap-4">
          {/* Section sidebar */}
          <div className="w-1/4 flex-shrink-0">
            <div className="card divide-y divide-gray-100 sticky top-4">
              {sections
                .slice()
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((sec) => (
                  <button
                    key={sec.id}
                    className={`w-full text-left px-3 py-2.5 flex items-center gap-2 hover:bg-gray-50 transition-colors ${activeSectionId === sec.id ? 'bg-blue-50' : ''}`}
                    onClick={() => scrollTo(sec.id)}
                  >
                    {sec.is_complete ? (
                      <Check className="w-4 h-4 text-green-500 flex-shrink-0" />
                    ) : (
                      <Circle className="w-4 h-4 text-gray-300 flex-shrink-0" />
                    )}
                    <span className="text-sm text-gray-700 truncate">{sec.title}</span>
                  </button>
                ))}
            </div>
          </div>

          {/* Sections editor */}
          <div className="flex-1 space-y-4">
            {sections
              .slice()
              .sort((a, b) => a.sort_order - b.sort_order)
              .map((sec) => (
                <SectionCard
                  key={sec.id}
                  tenantId={tenantId}
                  wpId={wp.id}
                  section={sec}
                  fields={fieldsForSection(sec)}
                  onSaved={() => {}}
                />
              ))}
          </div>
        </div>
      ) : (
        <div className="card p-8 text-center text-gray-400">
          <p>No sections defined. Sections are created automatically from the template.</p>
        </div>
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

export default function WorkpaperEditor({ tenantId, engagementId, onBack }: Props) {
  const [openWp, setOpenWp] = useState<Workpaper | null>(null);

  if (openWp) {
    return (
      <EditorView
        tenantId={tenantId}
        wp={openWp}
        engagementId={engagementId}
        onBack={() => setOpenWp(null)}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button className="btn-secondary" onClick={onBack}>
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <h1 className="text-xl font-bold text-gray-900 flex-1">Workpapers</h1>
      </div>
      <WorkpaperList tenantId={tenantId} engagementId={engagementId} onOpen={setOpenWp} />
    </div>
  );
}
