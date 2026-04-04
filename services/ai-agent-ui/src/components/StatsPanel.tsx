import React from 'react';
import { X, MessageSquare, Wrench, Star, TrendingUp, BarChart2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { getConversationStats } from '../api';

interface Props {
  tenantId: string;
  onClose: () => void;
}

function formatToolName(name: string): string {
  return name
    .replace(/^get_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function StarRating({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          className={`w-4 h-4 ${
            n <= Math.round(rating) ? 'text-yellow-400 fill-yellow-400' : 'text-gray-600'
          }`}
        />
      ))}
      <span className="ml-1.5 text-sm text-gray-300">{rating.toFixed(1)}</span>
    </div>
  );
}

export default function StatsPanel({ tenantId, onClose }: Props) {
  const { data: stats, isLoading, isError } = useQuery({
    queryKey: ['stats', tenantId],
    queryFn: () => getConversationStats(tenantId),
    staleTime: 30_000,
  });

  const maxCount = stats?.most_used_tools?.[0]?.count ?? 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-lg">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-semibold text-white">Usage Statistics</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          {isLoading && (
            <div className="flex items-center justify-center py-10">
              <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {isError && (
            <div className="bg-red-900/40 border border-red-700 text-red-300 rounded-xl px-4 py-3 text-sm text-center">
              Failed to load statistics.
            </div>
          )}

          {stats && (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <MessageSquare className="w-4 h-4 text-indigo-400" />
                    <span className="text-xs text-gray-400 font-medium">Conversations</span>
                  </div>
                  <p className="text-2xl font-bold text-white">
                    {stats.total_conversations.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <MessageSquare className="w-4 h-4 text-green-400" />
                    <span className="text-xs text-gray-400 font-medium">Messages</span>
                  </div>
                  <p className="text-2xl font-bold text-white">
                    {stats.total_messages.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <Wrench className="w-4 h-4 text-orange-400" />
                    <span className="text-xs text-gray-400 font-medium">Tool Calls</span>
                  </div>
                  <p className="text-2xl font-bold text-white">
                    {stats.total_tool_calls.toLocaleString()}
                  </p>
                </div>
                <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <TrendingUp className="w-4 h-4 text-purple-400" />
                    <span className="text-xs text-gray-400 font-medium">Avg Tools/Msg</span>
                  </div>
                  <p className="text-2xl font-bold text-white">
                    {stats.avg_tools_per_message.toFixed(1)}
                  </p>
                </div>
              </div>

              {/* Top tools */}
              {stats.most_used_tools.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-indigo-400" />
                    Top Tools
                  </h3>
                  <div className="space-y-2.5">
                    {stats.most_used_tools.slice(0, 5).map(({ tool_name, count }) => {
                      const pct = Math.round((count / maxCount) * 100);
                      return (
                        <div key={tool_name}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-gray-300">
                              {formatToolName(tool_name)}
                            </span>
                            <span className="text-xs text-gray-500">{count.toLocaleString()}</span>
                          </div>
                          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-indigo-500 rounded-full transition-all"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Feedback */}
              {stats.feedback_avg_rating != null && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-2">
                    <Star className="w-4 h-4 text-yellow-400" />
                    Average Feedback Rating
                  </h3>
                  <StarRating rating={stats.feedback_avg_rating} />
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white text-sm transition-colors border border-gray-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
