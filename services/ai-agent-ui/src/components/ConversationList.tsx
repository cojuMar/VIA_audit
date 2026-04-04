import React, { useState } from 'react';
import { MessageSquare, Plus, Trash2, Edit3, Check, X } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listConversations, archiveConversation, updateConversationTitle } from '../api';
import type { Conversation } from '../types';

interface Props {
  tenantId: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function ConversationList({ tenantId, selectedId, onSelect, onNew }: Props) {
  const qc = useQueryClient();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ['conversations', tenantId],
    queryFn: () => listConversations(tenantId),
    refetchInterval: 30_000,
  });

  const archiveMutation = useMutation({
    mutationFn: (convId: string) => archiveConversation(tenantId, convId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['conversations', tenantId] });
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ convId, title }: { convId: string; title: string }) =>
      updateConversationTitle(tenantId, convId, title),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['conversations', tenantId] });
      setEditingId(null);
    },
  });

  const activeConversations = conversations.filter((c) => c.status === 'active');
  const totalMessages = activeConversations.reduce((sum, c) => sum + c.message_count, 0);

  const startEdit = (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const commitEdit = (convId: string) => {
    if (editTitle.trim()) {
      renameMutation.mutate({ convId, title: editTitle.trim() });
    } else {
      setEditingId(null);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-900 border-r border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-indigo-400" />
          <span className="text-sm font-semibold text-gray-100">Conversations</span>
        </div>
        <button
          onClick={onNew}
          title="New conversation"
          className="w-7 h-7 rounded-lg flex items-center justify-center bg-gray-800 hover:bg-indigo-600 text-gray-400 hover:text-white transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-1">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!isLoading && activeConversations.length === 0 && (
          <div className="text-center py-8 px-4">
            <MessageSquare className="w-8 h-8 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-500 text-xs">No conversations yet</p>
            <button
              onClick={onNew}
              className="mt-2 text-indigo-400 hover:text-indigo-300 text-xs underline"
            >
              Start one
            </button>
          </div>
        )}

        {activeConversations.map((conv) => (
          <div
            key={conv.id}
            className={`group relative flex items-start gap-2 px-3 py-2.5 cursor-pointer transition-colors ${
              selectedId === conv.id
                ? 'bg-indigo-700/40 border-l-2 border-indigo-500'
                : 'border-l-2 border-transparent hover:bg-gray-800'
            }`}
            onClick={() => onSelect(conv.id)}
            onMouseEnter={() => setHoveredId(conv.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            <div className="flex-1 min-w-0">
              {editingId === conv.id ? (
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <input
                    autoFocus
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitEdit(conv.id);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    className="flex-1 bg-gray-700 border border-indigo-500 rounded px-1.5 py-0.5 text-xs text-gray-100 outline-none"
                  />
                  <button
                    onClick={() => commitEdit(conv.id)}
                    className="text-green-400 hover:text-green-300"
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setEditingId(null)}
                    className="text-gray-500 hover:text-gray-400"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ) : (
                <p
                  className={`text-xs font-medium truncate ${
                    selectedId === conv.id ? 'text-white' : 'text-gray-200'
                  }`}
                >
                  {conv.title || 'New conversation'}
                </p>
              )}
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-xs text-gray-500">{relativeTime(conv.updated_at)}</span>
                <span className="text-gray-600">·</span>
                <span className="text-xs text-gray-500">{conv.message_count} msgs</span>
              </div>
            </div>

            {/* Action buttons on hover */}
            {hoveredId === conv.id && editingId !== conv.id && (
              <div
                className="flex items-center gap-1 flex-shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={(e) => startEdit(conv, e)}
                  className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-700 text-gray-500 hover:text-gray-300 transition-colors"
                  title="Rename"
                >
                  <Edit3 className="w-3 h-3" />
                </button>
                <button
                  onClick={() => archiveMutation.mutate(conv.id)}
                  className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-900/40 text-gray-500 hover:text-red-400 transition-colors"
                  title="Archive"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer stats */}
      <div className="px-4 py-3 border-t border-gray-700 bg-gray-900">
        <p className="text-xs text-gray-500">
          {activeConversations.length} conversation{activeConversations.length !== 1 ? 's' : ''} •{' '}
          {totalMessages} message{totalMessages !== 1 ? 's' : ''}
        </p>
      </div>
    </div>
  );
}
