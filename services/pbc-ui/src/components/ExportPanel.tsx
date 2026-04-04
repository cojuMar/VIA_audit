import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Download, FileText, BookOpen, Sparkles, Loader2, X } from 'lucide-react';
import {
  listPBCLists,
  listWorkpapers,
  exportPBCList,
  exportIssueRegister,
  exportWorkpaper,
  generateAISummary,
} from '../api';
import type { PBCRequestList, Workpaper } from '../types';

interface Props {
  tenantId: string;
  engagementId: string;
}

function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportPanel({ tenantId, engagementId }: Props) {
  const [selectedPBCListId, setSelectedPBCListId] = useState<string>('');
  const [selectedWorkpaperId, setSelectedWorkpaperId] = useState<string>('');
  const [summaryModal, setSummaryModal] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // ── Dropdowns ────────────────────────────────────────────────────────────────

  const { data: pbcLists = [], isLoading: loadingLists } = useQuery<PBCRequestList[]>({
    queryKey: ['pbc-lists', tenantId, engagementId],
    queryFn: () => listPBCLists(tenantId, engagementId),
    enabled: !!tenantId && !!engagementId,
  });

  const { data: workpapers = [], isLoading: loadingWorkpapers } = useQuery<Workpaper[]>({
    queryKey: ['workpapers', tenantId, engagementId],
    queryFn: () => listWorkpapers(tenantId, engagementId),
    enabled: !!tenantId && !!engagementId,
  });

  // ── Mutations ─────────────────────────────────────────────────────────────────

  const exportPBCMutation = useMutation({
    mutationFn: () => exportPBCList(tenantId, selectedPBCListId),
    onSuccess: (data) => {
      downloadJson(data, `pbc-list-${selectedPBCListId}.json`);
    },
  });

  const exportIssuesMutation = useMutation({
    mutationFn: () => exportIssueRegister(tenantId, engagementId),
    onSuccess: (data) => {
      downloadJson(data, `issue-register-${engagementId}.json`);
    },
  });

  const exportWorkpaperMutation = useMutation({
    mutationFn: () => exportWorkpaper(tenantId, selectedWorkpaperId),
    onSuccess: (data) => {
      downloadJson(data, `workpaper-${selectedWorkpaperId}.json`);
    },
  });

  const aiSummaryMutation = useMutation({
    mutationFn: () => generateAISummary(tenantId, engagementId),
    onSuccess: (data) => {
      setSummaryModal(data.summary);
    },
  });

  // ── Copy helper ───────────────────────────────────────────────────────────────

  function handleCopy() {
    if (!summaryModal) return;
    navigator.clipboard.writeText(summaryModal).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <>
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-w-2xl">
        <h2 className="text-lg font-semibold text-white mb-6">Export &amp; Reports</h2>

        <div className="space-y-6">

          {/* 1 — Export PBC List */}
          <div className="flex items-start gap-4">
            <div className="mt-1 p-2 bg-indigo-900/40 rounded-lg">
              <FileText className="h-5 w-5 text-indigo-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200 mb-2">Export PBC List</p>
              <div className="flex gap-2">
                <select
                  value={selectedPBCListId}
                  onChange={(e) => setSelectedPBCListId(e.target.value)}
                  disabled={loadingLists}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
                >
                  <option value="">
                    {loadingLists ? 'Loading…' : pbcLists.length === 0 ? 'No lists found' : 'Select a list…'}
                  </option>
                  {pbcLists.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.list_name}
                    </option>
                  ))}
                </select>
                <button
                  disabled={!selectedPBCListId || exportPBCMutation.isPending}
                  onClick={() => exportPBCMutation.mutate()}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
                >
                  {exportPBCMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Export
                </button>
              </div>
              {exportPBCMutation.isError && (
                <p className="mt-1 text-xs text-red-400">Export failed. Please try again.</p>
              )}
            </div>
          </div>

          <div className="border-t border-gray-800" />

          {/* 2 — Export Issue Register */}
          <div className="flex items-start gap-4">
            <div className="mt-1 p-2 bg-indigo-900/40 rounded-lg">
              <BookOpen className="h-5 w-5 text-indigo-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200 mb-2">Export Issue Register</p>
              <button
                disabled={exportIssuesMutation.isPending}
                onClick={() => exportIssuesMutation.mutate()}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
              >
                {exportIssuesMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Export Issue Register
              </button>
              {exportIssuesMutation.isError && (
                <p className="mt-1 text-xs text-red-400">Export failed. Please try again.</p>
              )}
            </div>
          </div>

          <div className="border-t border-gray-800" />

          {/* 3 — Export Workpaper */}
          <div className="flex items-start gap-4">
            <div className="mt-1 p-2 bg-indigo-900/40 rounded-lg">
              <FileText className="h-5 w-5 text-indigo-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200 mb-2">Export Workpaper</p>
              <div className="flex gap-2">
                <select
                  value={selectedWorkpaperId}
                  onChange={(e) => setSelectedWorkpaperId(e.target.value)}
                  disabled={loadingWorkpapers}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
                >
                  <option value="">
                    {loadingWorkpapers ? 'Loading…' : workpapers.length === 0 ? 'No workpapers found' : 'Select a workpaper…'}
                  </option>
                  {workpapers.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.wp_reference ? `${w.wp_reference} — ` : ''}{w.title}
                    </option>
                  ))}
                </select>
                <button
                  disabled={!selectedWorkpaperId || exportWorkpaperMutation.isPending}
                  onClick={() => exportWorkpaperMutation.mutate()}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
                >
                  {exportWorkpaperMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Export
                </button>
              </div>
              {exportWorkpaperMutation.isError && (
                <p className="mt-1 text-xs text-red-400">Export failed. Please try again.</p>
              )}
            </div>
          </div>

          <div className="border-t border-gray-800" />

          {/* 4 — AI Executive Summary */}
          <div className="flex items-start gap-4">
            <div className="mt-1 p-2 bg-purple-900/40 rounded-lg">
              <Sparkles className="h-5 w-5 text-purple-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-200 mb-1">Generate AI Executive Summary</p>
              <p className="text-xs text-gray-500 mb-2">
                AI-generated summary of engagement findings, issues, and PBC completion status.
              </p>
              <button
                disabled={aiSummaryMutation.isPending}
                onClick={() => aiSummaryMutation.mutate()}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
              >
                {aiSummaryMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Generate Summary
                  </>
                )}
              </button>
              {aiSummaryMutation.isError && (
                <p className="mt-1 text-xs text-red-400">Generation failed. Please try again.</p>
              )}
            </div>
          </div>

        </div>
      </div>

      {/* AI Summary Modal */}
      {summaryModal !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-purple-400" />
                AI Executive Summary
              </h3>
              <button
                onClick={() => setSummaryModal(null)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="px-6 py-4 overflow-y-auto flex-1">
              <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{summaryModal}</p>
            </div>
            <div className="px-6 py-4 border-t border-gray-800 flex justify-end gap-3">
              <button
                onClick={() => setSummaryModal(null)}
                className="px-4 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
              >
                Close
              </button>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm font-medium text-white transition-colors"
              >
                {copied ? 'Copied!' : 'Copy to Clipboard'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
