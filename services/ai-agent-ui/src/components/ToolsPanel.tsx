import React, { useState } from 'react';
import {
  Wrench,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  ChevronUp,
  BarChart2,
  ShieldCheck,
  Users,
  ClipboardList,
  BookOpen,
  Plug,
  Activity,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { listTools } from '../api';
import type { AgentTool } from '../types';

interface Props {
  tenantId: string;
  onToolClick?: (prompt: string) => void;
}

interface ToolGroup {
  label: string;
  icon: React.ElementType;
  color: string;
  tools: AgentTool[];
}

const TOOL_CATEGORY_MAP: Record<string, string> = {
  get_compliance_scores: 'Compliance',
  get_compliance_gaps: 'Compliance',
  generate_compliance_report: 'Compliance',
  get_vendor_risk_summary: 'Vendors',
  get_monitoring_findings: 'Monitoring',
  get_sod_violations: 'Monitoring',
  get_cloud_config_issues: 'Monitoring',
  get_training_compliance: 'People',
  get_policy_compliance: 'People',
  get_background_check_status: 'People',
  get_org_compliance_score: 'People',
  get_open_pbc_requests: 'Audit',
  get_audit_issues: 'Audit',
  search_knowledge_base: 'Knowledge',
  get_integration_status: 'Integrations',
};

const TOOL_PROMPT_MAP: Record<string, string> = {
  get_compliance_scores: 'What are the current compliance scores across all frameworks?',
  get_compliance_gaps: 'Show me all compliance gaps and missing controls.',
  generate_compliance_report: 'Generate a full compliance summary report.',
  get_vendor_risk_summary: 'Which vendors are at high risk and why?',
  get_monitoring_findings: 'What are the latest monitoring findings and alerts?',
  get_sod_violations: 'Are there any segregation of duties violations?',
  get_cloud_config_issues: 'Show me all cloud configuration issues.',
  get_training_compliance: 'What is the current training compliance status?',
  get_policy_compliance: 'Are there any policy compliance issues?',
  get_background_check_status: 'What is the background check status for all staff?',
  get_org_compliance_score: 'What is the overall organizational compliance score?',
  get_open_pbc_requests: 'What PBC requests are currently open?',
  get_audit_issues: 'What are the most common audit issues?',
  search_knowledge_base: 'Search the knowledge base for compliance best practices.',
  get_integration_status: 'What is the status of all integrations?',
};

const CATEGORY_META: Record<string, { icon: React.ElementType; color: string }> = {
  Compliance: { icon: BarChart2, color: 'text-indigo-400' },
  Vendors: { icon: ShieldCheck, color: 'text-yellow-400' },
  Monitoring: { icon: Activity, color: 'text-red-400' },
  People: { icon: Users, color: 'text-green-400' },
  Audit: { icon: ClipboardList, color: 'text-orange-400' },
  Knowledge: { icon: BookOpen, color: 'text-purple-400' },
  Integrations: { icon: Plug, color: 'text-cyan-400' },
};

function formatToolName(name: string): string {
  return name
    .replace(/^get_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ToolsPanel({ tenantId, onToolClick }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(
    new Set(Object.keys(CATEGORY_META))
  );

  const { data: tools = [], isLoading } = useQuery({
    queryKey: ['tools', tenantId],
    queryFn: () => listTools(tenantId),
    staleTime: 60_000,
  });

  // Group tools by category
  const grouped: Record<string, ToolGroup> = {};
  tools.forEach((tool) => {
    const cat = TOOL_CATEGORY_MAP[tool.name] ?? 'Other';
    if (!grouped[cat]) {
      const meta = CATEGORY_META[cat] ?? { icon: Wrench, color: 'text-gray-400' };
      grouped[cat] = { label: cat, icon: meta.icon, color: meta.color, tools: [] };
    }
    grouped[cat].tools.push(tool);
  });

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const handleToolClick = (toolName: string) => {
    const prompt = TOOL_PROMPT_MAP[toolName] ?? `Use the ${formatToolName(toolName)} tool.`;
    onToolClick?.(prompt);
  };

  if (collapsed) {
    return (
      <div className="flex flex-col items-center bg-gray-900 border-l border-gray-700 w-10 py-3 gap-4">
        <button
          onClick={() => setCollapsed(false)}
          className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          title="Show tools"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div
          className="text-gray-500 text-xs font-medium"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          Tools
        </div>
        <Wrench className="w-4 h-4 text-gray-600 mt-auto mb-2" />
      </div>
    );
  }

  return (
    <div className="flex flex-col bg-gray-900 border-l border-gray-700 w-64">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Wrench className="w-4 h-4 text-indigo-400" />
          <span className="text-sm font-semibold text-gray-100">Agent Tools</span>
          {tools.length > 0 && (
            <span className="text-xs bg-indigo-600/30 text-indigo-300 px-1.5 py-0.5 rounded-full">
              {tools.length}
            </span>
          )}
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          title="Collapse"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Tool groups */}
      <div className="flex-1 overflow-y-auto py-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!isLoading && Object.entries(grouped).map(([cat, group]) => {
          const Icon = group.icon;
          const isExpanded = expandedCategories.has(cat);
          return (
            <div key={cat} className="mb-1">
              <button
                onClick={() => toggleCategory(cat)}
                className="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-gray-800 transition-colors group"
              >
                <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${group.color}`} />
                <span className="flex-1 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                  {group.label}
                </span>
                <span className="text-xs text-gray-600">{group.tools.length}</span>
                {isExpanded ? (
                  <ChevronUp className="w-3 h-3 text-gray-600" />
                ) : (
                  <ChevronDown className="w-3 h-3 text-gray-600" />
                )}
              </button>

              {isExpanded && (
                <div className="px-2 pb-1 space-y-0.5">
                  {group.tools.map((tool) => (
                    <button
                      key={tool.name}
                      onClick={() => handleToolClick(tool.name)}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors group"
                      title={tool.description}
                    >
                      <p className="text-xs font-medium text-gray-300 group-hover:text-white transition-colors">
                        {formatToolName(tool.name)}
                      </p>
                      <p className="text-xs text-gray-600 group-hover:text-gray-500 transition-colors truncate mt-0.5">
                        {tool.description}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {!isLoading && tools.length === 0 && (
          <div className="text-center py-8 px-4">
            <Wrench className="w-8 h-8 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-500 text-xs">No tools available</p>
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-4 py-3 border-t border-gray-700">
        <p className="text-xs text-gray-600">Click a tool to insert a suggested prompt</p>
      </div>
    </div>
  );
}
