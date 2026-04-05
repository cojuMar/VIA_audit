import React, { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, FileText, BarChart2, AlertCircle, Settings } from 'lucide-react';
import ChatInterface from './components/ChatInterface';
import ConversationList from './components/ConversationList';
import ReportGenerator from './components/ReportGenerator';
import ToolsPanel from './components/ToolsPanel';
import StatsPanel from './components/StatsPanel';
import { checkHealth } from './api';

function getTenantId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('tenantId');
  if (fromUrl) {
    localStorage.setItem('via_tenant_id', fromUrl);
    return fromUrl;
  }
  const fromStorage = localStorage.getItem('via_tenant_id');
  if (fromStorage) return fromStorage;
  return 'default';
}

export default function App() {
  const tenantId = getTenantId();
  const qc = useQueryClient();

  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [showReports, setShowReports] = useState(false);
  const [showStats, setShowStats] = useState(false);
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);

  const { data: health, isError: healthError } = useQuery({
    queryKey: ['health', tenantId],
    queryFn: () => checkHealth(tenantId),
    retry: 1,
    staleTime: 60_000,
  });

  const handleConversationCreated = useCallback(
    (id: string) => {
      setSelectedConvId(id);
      void qc.invalidateQueries({ queryKey: ['conversations', tenantId] });
    },
    [tenantId, qc]
  );

  const handleNewConversation = useCallback(() => {
    setSelectedConvId(null);
  }, []);

  const handleToolClick = useCallback((prompt: string) => {
    setPendingPrompt(prompt);
  }, []);

  const noModel = health && !health.model;
  const showBanner = healthError || noModel;

  return (
    <div className="h-screen flex flex-col bg-gray-950 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2.5 bg-gray-900 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-sm">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white leading-none">VIA AI</h1>
            <p className="text-xs text-gray-400 leading-none mt-0.5">Compliance Assistant</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {health?.model && (
            <span className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-800 border border-gray-700 text-xs text-gray-300">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
              {health.model}
            </span>
          )}
          <span className="px-2.5 py-1 rounded-full bg-indigo-600/20 border border-indigo-600/40 text-xs text-indigo-300">
            Tenant: {tenantId}
          </span>
        </div>
      </header>

      {/* API banner */}
      {showBanner && (
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-900/40 border-b border-amber-700/50 text-amber-300 text-xs flex-shrink-0">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>
            {healthError
              ? 'Cannot reach AI Agent Service. Check that ai-agent-service is running on port 3020.'
              : 'No AI model configured. Set the ANTHROPIC_API_KEY environment variable in ai-agent-service.'}
          </span>
          <Settings className="w-3.5 h-3.5 ml-1 opacity-70" />
        </div>
      )}

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar */}
        <aside className="w-72 flex-shrink-0 flex flex-col bg-gray-900 border-r border-gray-700 overflow-hidden">
          <div className="flex-1 overflow-hidden">
            <ConversationList
              tenantId={tenantId}
              selectedId={selectedConvId}
              onSelect={setSelectedConvId}
              onNew={handleNewConversation}
            />
          </div>

          {/* Sidebar action buttons */}
          <div className="flex flex-col gap-1 p-3 border-t border-gray-700 flex-shrink-0">
            <button
              onClick={() => setShowReports(true)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl hover:bg-gray-800 text-gray-300 hover:text-white text-sm transition-colors group"
            >
              <div className="w-7 h-7 rounded-lg bg-gray-800 group-hover:bg-indigo-600/20 flex items-center justify-center transition-colors">
                <FileText className="w-4 h-4 text-indigo-400" />
              </div>
              <span className="font-medium">Reports</span>
            </button>
            <button
              onClick={() => setShowStats(true)}
              className="flex items-center gap-2.5 px-3 py-2 rounded-xl hover:bg-gray-800 text-gray-300 hover:text-white text-sm transition-colors group"
            >
              <div className="w-7 h-7 rounded-lg bg-gray-800 group-hover:bg-indigo-600/20 flex items-center justify-center transition-colors">
                <BarChart2 className="w-4 h-4 text-indigo-400" />
              </div>
              <span className="font-medium">Statistics</span>
            </button>
          </div>
        </aside>

        {/* Chat center */}
        <main className="flex-1 overflow-hidden">
          <ChatInterface
            tenantId={tenantId}
            conversationId={selectedConvId}
            onConversationCreated={handleConversationCreated}
            pendingPrompt={pendingPrompt}
            onPendingPromptConsumed={() => setPendingPrompt(null)}
          />
        </main>

        {/* Right sidebar - Tools */}
        <aside className="flex-shrink-0 overflow-hidden">
          <ToolsPanel tenantId={tenantId} onToolClick={handleToolClick} />
        </aside>
      </div>

      {/* Modals */}
      {showReports && (
        <ReportGenerator
          tenantId={tenantId}
          conversationId={selectedConvId}
          onClose={() => setShowReports(false)}
        />
      )}
      {showStats && (
        <StatsPanel tenantId={tenantId} onClose={() => setShowStats(false)} />
      )}
    </div>
  );
}
