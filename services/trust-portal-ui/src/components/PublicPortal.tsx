import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ShieldOff } from 'lucide-react';
import { getPortalPublic } from '../api';
import type { ComplianceBadge } from '../types';
import DocumentLibrary from './DocumentLibrary';
import SecurityChatbot from './SecurityChatbot';
import QuestionnaireDeflector from './QuestionnaireDeflector';

interface Props {
  slug: string;
}

type Tab = 'documents' | 'chat' | 'deflection';

const BADGE_COLORS: Record<ComplianceBadge['color'], string> = {
  green: 'bg-green-100 text-green-700 border-green-200',
  amber: 'bg-amber-100 text-amber-700 border-amber-200',
  red: 'bg-red-100 text-red-700 border-red-200',
};

function InitialsAvatar({ name, color }: { name: string; color: string }) {
  const initials = name
    .split(' ')
    .slice(0, 2)
    .map(w => w[0])
    .join('')
    .toUpperCase();
  return (
    <div
      className="w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg shrink-0"
      style={{ backgroundColor: color }}
    >
      {initials}
    </div>
  );
}

export default function PublicPortal({ slug }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('documents');

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['portal', slug],
    queryFn: () => getPortalPublic(slug),
    retry: 1,
  });

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <span className="inline-block w-10 h-10 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  // Unavailable state
  const isUnavailable =
    isError ||
    !data ||
    !data.config.portal_enabled ||
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (error as any)?.response?.status === 404;

  if (isUnavailable) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4 text-center gap-4">
        <ShieldOff size={48} className="text-gray-300" />
        <h1 className="text-xl font-semibold text-gray-700">This portal is not available</h1>
        <p className="text-sm text-gray-400 max-w-sm">
          The trust portal you are looking for is not available or has been disabled.
          Please contact the organization directly for security documentation.
        </p>
      </div>
    );
  }

  const { config, badges } = data;
  const primaryColor = config.primary_color || '#2563eb';

  const tabs: Array<{ id: Tab; label: string; disabled?: boolean }> = [
    { id: 'documents', label: 'Documents' },
    { id: 'chat', label: 'Chat', disabled: !config.chatbot_enabled },
    { id: 'deflection', label: 'Questionnaire Response' },
  ];

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-5 flex items-center gap-4">
          {config.logo_url ? (
            <img
              src={config.logo_url}
              alt={config.company_name}
              className="w-12 h-12 rounded-xl object-contain border border-gray-100"
            />
          ) : (
            <InitialsAvatar name={config.company_name} color={primaryColor} />
          )}
          <div>
            <h1
              className="text-xl font-bold leading-tight"
              style={{ color: primaryColor }}
            >
              {config.company_name}
            </h1>
            {config.tagline && (
              <p className="text-sm text-gray-500 mt-0.5">{config.tagline}</p>
            )}
          </div>
        </div>

        {/* Compliance Badges Strip */}
        {config.show_compliance_scores && badges.length > 0 && (
          <div className="border-t border-gray-100 bg-gray-50">
            <div className="max-w-5xl mx-auto px-4 py-3 flex flex-wrap gap-2">
              {badges.map(badge => (
                <div
                  key={badge.slug}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${BADGE_COLORS[badge.color]}`}
                >
                  <span>{badge.framework_name}</span>
                  <span className="font-bold">{badge.score_pct}%</span>
                  <span className="opacity-70">{badge.badge_text}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="max-w-5xl mx-auto px-4">
          <nav className="flex gap-0 -mb-px">
            {tabs.map(tab => {
              if (tab.disabled) return null;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                    isActive
                      ? 'border-current text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                  style={isActive ? { borderColor: primaryColor, color: primaryColor } : undefined}
                >
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-8">
        {activeTab === 'documents' && (
          <DocumentLibrary
            slug={slug}
            ndaVersion={config.nda_version}
            requireNda={config.require_nda}
          />
        )}
        {activeTab === 'chat' && config.chatbot_enabled && (
          <div className="max-w-2xl">
            <SecurityChatbot slug={slug} welcomeMessage={config.chatbot_welcome_message} />
          </div>
        )}
        {activeTab === 'deflection' && (
          <div>
            <div className="mb-6">
              <h2 className="text-base font-semibold text-gray-900">Questionnaire Response</h2>
              <p className="text-sm text-gray-500 mt-1">
                Submit your security questionnaire and our AI will map each question to our
                existing evidence and documentation.
              </p>
            </div>
            <QuestionnaireDeflector slug={slug} />
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white py-4">
        <p className="text-center text-xs text-gray-400">Powered by VIA</p>
      </footer>
    </div>
  );
}
