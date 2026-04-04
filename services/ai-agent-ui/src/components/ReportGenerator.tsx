import React, { useState } from 'react';
import {
  X,
  FileText,
  AlertTriangle,
  Shield,
  Activity,
  GraduationCap,
  CheckCircle,
  Loader2,
  Copy,
  Printer,
  ChevronDown,
} from 'lucide-react';
import { useMutation } from '@tanstack/react-query';
import { marked } from 'marked';
import { generateReport } from '../api';
import type { ReportRequest, Report } from '../types';

interface Props {
  tenantId: string;
  conversationId: string | null;
  onClose: () => void;
}

const REPORT_TYPES = [
  {
    id: 'compliance_summary',
    label: 'Compliance Summary',
    icon: FileText,
    desc: 'Overall compliance posture',
  },
  {
    id: 'gap_analysis',
    label: 'Gap Analysis',
    icon: AlertTriangle,
    desc: 'Missing controls & gaps',
  },
  {
    id: 'vendor_risk',
    label: 'Vendor Risk Report',
    icon: Shield,
    desc: 'Third-party risk assessment',
  },
  {
    id: 'monitoring_findings',
    label: 'Monitoring Findings',
    icon: Activity,
    desc: 'Recent monitoring alerts',
  },
  {
    id: 'training_status',
    label: 'Training Status',
    icon: GraduationCap,
    desc: 'Staff training compliance',
  },
  {
    id: 'audit_readiness',
    label: 'Audit Readiness',
    icon: CheckCircle,
    desc: 'Audit preparation status',
  },
] as const;

type ReportTypeId = typeof REPORT_TYPES[number]['id'];

export default function ReportGenerator({ tenantId, conversationId, onClose }: Props) {
  const [selectedType, setSelectedType] = useState<ReportTypeId | null>(null);
  const [title, setTitle] = useState('');
  const [request, setRequest] = useState('');
  const [report, setReport] = useState<Report | null>(null);
  const [copied, setCopied] = useState(false);

  const mutation = useMutation({
    mutationFn: (req: ReportRequest) => generateReport(tenantId, req),
    onSuccess: (data) => setReport(data),
  });

  const handleGenerate = () => {
    if (!selectedType || !request.trim()) return;
    mutation.mutate({
      report_type: selectedType,
      title: title.trim() || null,
      natural_language_request: request.trim(),
      conversation_id: conversationId,
    });
  };

  const handleCopy = async () => {
    if (!report) return;
    await navigator.clipboard.writeText(report.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => window.print();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 flex-shrink-0">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-semibold text-white">Generate Report</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {!report ? (
            <div className="px-6 py-5 space-y-5">
              {/* Report type selection */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Report Type <span className="text-red-400">*</span>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {REPORT_TYPES.map(({ id, label, icon: Icon, desc }) => (
                    <button
                      key={id}
                      onClick={() => setSelectedType(id)}
                      className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all ${
                        selectedType === id
                          ? 'border-indigo-500 bg-indigo-600/20 text-white'
                          : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-600 hover:bg-gray-750'
                      }`}
                    >
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          selectedType === id ? 'bg-indigo-600' : 'bg-gray-700'
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                      </div>
                      <div>
                        <p className="text-xs font-medium">{label}</p>
                        <p className="text-xs text-gray-500">{desc}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Title */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  Title <span className="text-gray-500 text-xs">(optional)</span>
                </label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Auto-generated if blank"
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none focus:border-indigo-500 transition-colors"
                />
              </div>

              {/* Natural language request */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  What do you want in this report? <span className="text-red-400">*</span>
                </label>
                <textarea
                  value={request}
                  onChange={(e) => setRequest(e.target.value)}
                  placeholder="Describe what you want in this report..."
                  rows={4}
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none focus:border-indigo-500 transition-colors resize-none"
                />
              </div>

              {mutation.isError && (
                <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-xl px-4 py-2 text-sm">
                  Failed to generate report. Please try again.
                </div>
              )}
            </div>
          ) : (
            <div className="px-6 py-5">
              {/* Report header */}
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-base font-semibold text-white">{report.title}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Generated in {report.generation_time_ms}ms • {report.model_used}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 no-print">
                  <button
                    onClick={() => void handleCopy()}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs transition-colors border border-gray-700"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    {copied ? 'Copied!' : 'Copy Markdown'}
                  </button>
                  <button
                    onClick={handlePrint}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-xs transition-colors border border-gray-700"
                  >
                    <Printer className="w-3.5 h-3.5" />
                    Print
                  </button>
                </div>
              </div>

              {/* Report content */}
              <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 print-area">
                <div
                  className="prose-dark text-sm"
                  dangerouslySetInnerHTML={{ __html: marked.parse(report.content) as string }}
                />
              </div>

              {/* Generate another */}
              <button
                onClick={() => {
                  setReport(null);
                  mutation.reset();
                }}
                className="mt-4 flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 text-sm transition-colors"
              >
                <ChevronDown className="w-4 h-4 rotate-90" />
                Generate another report
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-700 flex-shrink-0 no-print">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-sm transition-colors border border-gray-700"
          >
            Close
          </button>
          {!report && (
            <button
              onClick={handleGenerate}
              disabled={!selectedType || !request.trim() || mutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <FileText className="w-4 h-4" />
                  Generate Report
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
