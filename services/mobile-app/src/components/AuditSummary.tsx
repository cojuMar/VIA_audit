import { useState, useEffect } from 'react';
import {
  ChevronLeft,
  AlertTriangle,
  Camera,
  Loader2,
  Sparkles,
  X,
  Copy,
  Check,
  BarChart3,
  Image,
  ListChecks,
} from 'lucide-react';
import { fetchAuditSummary, aiGenerateFindingsReport, aiPrioritizeFindings } from '../api';
import { getAudit, getResponsesForAudit, getPhotosForAudit } from '../offline/db';
import { useOnlineStatus } from '../offline/sync';
import type { AuditSummary as AuditSummaryType, FieldAudit, ResponsePayload } from '../types';

interface AuditSummaryProps {
  tenantId: string;
  auditId: string;
  onBack: () => void;
}

const SEV_COLORS: Record<string, string> = {
  critical: 'finding-critical',
  high: 'finding-high',
  medium: 'finding-medium',
  low: 'finding-low',
};

const RISK_RING: Record<string, string> = {
  low: 'stroke-green-500',
  medium: 'stroke-yellow-500',
  high: 'stroke-orange-500',
  critical: 'stroke-red-500',
};

const RISK_TEXT: Record<string, string> = {
  low: 'text-green-600',
  medium: 'text-yellow-600',
  high: 'text-orange-600',
  critical: 'text-red-600',
};

function ScoreGauge({ score, riskLevel }: { score: number; riskLevel?: string }) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const ringClass = riskLevel ? RISK_RING[riskLevel] ?? 'stroke-blue-500' : 'stroke-blue-500';
  const textClass = riskLevel ? RISK_TEXT[riskLevel] ?? 'text-blue-600' : 'text-blue-600';

  return (
    <div className="flex flex-col items-center justify-center py-6">
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 128 128">
          <circle
            cx="64" cy="64" r={radius}
            stroke="#e5e7eb" strokeWidth="10" fill="none"
          />
          <circle
            cx="64" cy="64" r={radius}
            className={ringClass}
            strokeWidth="10" fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 0.6s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold ${textClass}`}>{Math.round(score)}%</span>
          {riskLevel && (
            <span className={`text-xs font-semibold uppercase capitalize ${textClass}`}>
              {riskLevel}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function MarkdownModal({
  title,
  content,
  onClose,
}: {
  title: string;
  content: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-end">
      <div className="bg-white rounded-t-2xl w-full max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h3 className="font-bold text-gray-900">{title}</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="tap-target px-2 text-gray-500 flex items-center gap-1 text-sm"
            >
              {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button onClick={onClose} className="tap-target p-1">
              <X size={20} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <pre className="whitespace-pre-wrap text-sm text-gray-700 font-sans leading-relaxed">
            {content}
          </pre>
        </div>
      </div>
    </div>
  );
}

export default function AuditSummary({ tenantId: _tenantId, auditId, onBack }: AuditSummaryProps) {
  const isOnline = useOnlineStatus();
  const [summary, setSummary] = useState<AuditSummaryType | null>(null);
  const [localAudit, setLocalAudit] = useState<FieldAudit | null>(null);
  const [localResponses, setLocalResponses] = useState<ResponsePayload[]>([]);
  const [localPhotos, setLocalPhotos] = useState<{ sync_id: string; data_url: string; caption?: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [aiReport, setAiReport] = useState<string | null>(null);
  const [aiPriorities, setAiPriorities] = useState<string | null>(null);
  const [showModal, setShowModal] = useState<'report' | 'priorities' | null>(null);
  const [aiLoading, setAiLoading] = useState<'report' | 'priorities' | null>(null);
  const [expandedPhoto, setExpandedPhoto] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'overview' | 'findings' | 'photos'>('overview');

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        // Always load local data first
        const [audit, responses, photos] = await Promise.all([
          getAudit(auditId),
          getResponsesForAudit(auditId),
          getPhotosForAudit(auditId),
        ]);
        setLocalAudit(audit ?? null);
        setLocalResponses(responses);
        setLocalPhotos(photos);

        // Try server for richer summary
        if (isOnline) {
          try {
            const serverSummary = await fetchAuditSummary(auditId);
            setSummary(serverSummary);
          } catch {
            // Fall back to local
          }
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [auditId, isOnline]);

  const handleAiReport = async () => {
    if (!isOnline) return;
    setAiLoading('report');
    try {
      const result = await aiGenerateFindingsReport(auditId);
      setAiReport(result.report ?? result.content ?? JSON.stringify(result, null, 2));
      setShowModal('report');
    } catch (err) {
      setAiReport('Failed to generate report. Please try again.');
      setShowModal('report');
    } finally {
      setAiLoading(null);
    }
  };

  const handleAiPriorities = async () => {
    if (!isOnline) return;
    setAiLoading('priorities');
    try {
      const result = await aiPrioritizeFindings(auditId);
      setAiPriorities(result.priorities ?? result.content ?? JSON.stringify(result, null, 2));
      setShowModal('priorities');
    } catch (err) {
      setAiPriorities('Failed to prioritize findings. Please try again.');
      setShowModal('priorities');
    } finally {
      setAiLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <Loader2 size={40} className="animate-spin text-blue-600" />
      </div>
    );
  }

  const audit = summary?.audit ?? localAudit;
  if (!audit) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6">
        <p className="text-gray-500">Audit not found.</p>
        <button onClick={onBack} className="btn-secondary mt-4 w-full max-w-xs">Back</button>
      </div>
    );
  }

  const findings = summary
    ? summary.section_scores // use server data
    : null;
  const findingResponses = localResponses.filter((r) => r.is_finding);
  const findingsBySeverity = summary?.findings_by_severity ?? buildFindingsBySev(findingResponses);
  const sectionScores = summary?.section_scores ?? [];

  return (
    <div className="min-h-screen bg-gray-50 pb-safe">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-4 flex items-center gap-3">
        <button onClick={onBack} className="tap-target p-1 -ml-1">
          <ChevronLeft size={24} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-bold text-gray-900 truncate">{audit.location_name}</h1>
          <p className="text-sm text-gray-500 capitalize">
            {audit.status.replace('_', ' ')} ·{' '}
            {new Date(audit.started_at).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </p>
        </div>
      </header>

      {/* Section tabs */}
      <div className="bg-white border-b border-gray-200 flex">
        {[
          { key: 'overview', label: 'Overview', icon: <BarChart3 size={14} /> },
          { key: 'findings', label: `Findings (${findingResponses.length})`, icon: <AlertTriangle size={14} /> },
          { key: 'photos', label: `Photos (${localPhotos.length})`, icon: <Image size={14} /> },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveSection(tab.key as typeof activeSection)}
            className={`flex-1 tap-target flex items-center justify-center gap-1.5 text-xs font-medium border-b-2 transition-colors ${
              activeSection === tab.key
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-4 space-y-4">
        {/* ── OVERVIEW ── */}
        {activeSection === 'overview' && (
          <>
            {/* Score gauge */}
            {audit.overall_score != null && (
              <div className="card">
                <ScoreGauge score={audit.overall_score} riskLevel={audit.risk_level ?? undefined} />
                <div className="grid grid-cols-3 gap-3 text-center border-t border-gray-100 pt-4">
                  <div>
                    <p className="text-2xl font-bold text-gray-900">{summary?.response_count ?? localResponses.length}</p>
                    <p className="text-xs text-gray-500">Questions</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-orange-600">
                      {summary?.finding_count ?? findingResponses.length}
                    </p>
                    <p className="text-xs text-gray-500">Findings</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-gray-900">{localPhotos.length}</p>
                    <p className="text-xs text-gray-500">Photos</p>
                  </div>
                </div>
              </div>
            )}

            {/* Findings by severity */}
            {Object.keys(findingsBySeverity).length > 0 && (
              <div className="card space-y-2">
                <h2 className="font-semibold text-gray-900">Findings by Severity</h2>
                {(['critical', 'high', 'medium', 'low'] as const).map((sev) => {
                  const count = findingsBySeverity[sev] ?? 0;
                  if (!count) return null;
                  return (
                    <div key={sev} className="flex items-center gap-3">
                      <span
                        className={`w-20 text-xs font-semibold capitalize px-2 py-0.5 rounded text-center ${SEV_COLORS[sev]}`}
                      >
                        {sev}
                      </span>
                      <div className="flex-1 bg-gray-100 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${SEV_BAR_COLORS[sev]}`}
                          style={{
                            width: `${Math.min(100, (count / Math.max(1, findingResponses.length)) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-sm font-bold text-gray-700 w-6 text-right">{count}</span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Section scores */}
            {sectionScores.length > 0 && (
              <div className="card space-y-3">
                <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                  <ListChecks size={16} />
                  Section Scores
                </h2>
                {sectionScores.map((s) => (
                  <div key={s.section_name}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-700 truncate flex-1 pr-2">{s.section_name}</span>
                      <span className="font-semibold text-gray-900 flex-shrink-0">
                        {Math.round(s.score_pct)}%
                      </span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${scoreBarColor(s.score_pct)}`}
                        style={{ width: `${s.score_pct}%`, transition: 'width 0.4s ease' }}
                      />
                    </div>
                    {s.finding_count > 0 && (
                      <p className="text-xs text-orange-600 mt-0.5">{s.finding_count} finding(s)</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* AI Actions */}
            {isOnline && (
              <div className="space-y-2">
                <button
                  onClick={handleAiReport}
                  disabled={aiLoading === 'report'}
                  className="btn-primary w-full gap-2"
                >
                  {aiLoading === 'report' ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  Generate AI Report
                </button>
                <button
                  onClick={handleAiPriorities}
                  disabled={aiLoading === 'priorities'}
                  className="btn-secondary w-full gap-2"
                >
                  {aiLoading === 'priorities' ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  AI Prioritize Findings
                </button>
              </div>
            )}

            <div className="text-center text-xs text-gray-400 py-2">
              Full report available in the desktop portal
            </div>
          </>
        )}

        {/* ── FINDINGS ── */}
        {activeSection === 'findings' && (
          <>
            {findingResponses.length === 0 ? (
              <div className="card text-center py-10">
                <AlertTriangle size={32} className="mx-auto mb-2 text-gray-300" />
                <p className="text-gray-500 font-medium">No findings recorded</p>
              </div>
            ) : (
              <div className="space-y-3">
                {(['critical', 'high', 'medium', 'low'] as const).map((sev) => {
                  const sevFindings = findingResponses.filter(
                    (r) => (r.finding_severity ?? 'medium') === sev
                  );
                  if (!sevFindings.length) return null;
                  return (
                    <div key={sev}>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2 flex items-center gap-1">
                        <span className={`w-2 h-2 rounded-full ${SEV_DOT[sev]}`} />
                        {sev} ({sevFindings.length})
                      </p>
                      {sevFindings.map((finding) => (
                        <div key={finding.sync_id} className={`${SEV_COLORS[sev]} rounded-xl p-4 mb-2 space-y-1`}>
                          <p className="font-semibold text-sm">
                            {finding.response_value ?? (finding.boolean_response != null ? String(finding.boolean_response) : 'Finding')}
                          </p>
                          {finding.comment && (
                            <p className="text-xs opacity-80">{finding.comment}</p>
                          )}
                          {(finding.photo_references?.length ?? 0) > 0 && (
                            <div className="flex items-center gap-1 text-xs opacity-70 mt-1">
                              <Camera size={12} />
                              {finding.photo_references.length} photo(s)
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ── PHOTOS ── */}
        {activeSection === 'photos' && (
          <>
            {localPhotos.length === 0 ? (
              <div className="card text-center py-10">
                <Camera size={32} className="mx-auto mb-2 text-gray-300" />
                <p className="text-gray-500 font-medium">No photos captured</p>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {localPhotos.map((photo) => (
                  <button
                    key={photo.sync_id}
                    onClick={() => setExpandedPhoto(photo.data_url)}
                    className="aspect-square overflow-hidden rounded-lg border border-gray-200"
                  >
                    <img
                      src={photo.data_url}
                      alt={photo.caption ?? 'Audit photo'}
                      className="w-full h-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Expanded photo modal */}
      {expandedPhoto && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4"
          onClick={() => setExpandedPhoto(null)}
        >
          <img
            src={expandedPhoto}
            alt="Full size"
            className="max-w-full max-h-full object-contain rounded-lg"
          />
          <button
            onClick={() => setExpandedPhoto(null)}
            className="absolute top-4 right-4 bg-white/20 rounded-full p-2"
          >
            <X size={24} className="text-white" />
          </button>
        </div>
      )}

      {/* AI report modal */}
      {showModal === 'report' && aiReport && (
        <MarkdownModal
          title="AI Findings Report"
          content={aiReport}
          onClose={() => setShowModal(null)}
        />
      )}
      {showModal === 'priorities' && aiPriorities && (
        <MarkdownModal
          title="Prioritized Findings"
          content={aiPriorities}
          onClose={() => setShowModal(null)}
        />
      )}

      {/* Suppress unused variable warning */}
      {findings && null}
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function buildFindingsBySev(responses: ResponsePayload[]): Record<string, number> {
  const result: Record<string, number> = {};
  for (const r of responses) {
    const sev = r.finding_severity ?? 'medium';
    result[sev] = (result[sev] ?? 0) + 1;
  }
  return result;
}

function scoreBarColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-yellow-500';
  if (score >= 40) return 'bg-orange-500';
  return 'bg-red-500';
}

const SEV_BAR_COLORS: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-400',
  low: 'bg-blue-400',
};

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-400',
  low: 'bg-blue-400',
};
