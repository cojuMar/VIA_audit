import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Bot, Send, ThumbsUp, ThumbsDown, Wrench, ChevronDown, ChevronUp } from 'lucide-react';
import { marked } from 'marked';
import type { Message, ChatResponse } from '../types';
import { sendMessage, getConversation, submitFeedback } from '../api';

marked.setOptions({ breaks: true, gfm: true });

interface Props {
  tenantId: string;
  conversationId: string | null;
  onConversationCreated: (id: string) => void;
  pendingPrompt?: string | null;
  onPendingPromptConsumed?: () => void;
}

const SUGGESTED_PROMPTS = [
  'What is my overall compliance score?',
  'Show me critical monitoring findings',
  'Which vendors are at high risk?',
  'Are there any overdue training assignments?',
  'Generate a compliance summary report',
  'What are the most common audit issues?',
];

function formatToolName(name: string): string {
  return name
    .replace(/^get_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

interface FeedbackState {
  [messageId: string]: {
    open: boolean;
    rating: number;
    type: string;
    submitted: boolean;
  };
}

interface ToolsCollapseState {
  [messageId: string]: boolean;
}

export default function ChatInterface({
  tenantId,
  conversationId,
  onConversationCreated,
  pendingPrompt,
  onPendingPromptConsumed,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [currentConvId, setCurrentConvId] = useState<string | null>(conversationId);
  const [feedback, setFeedback] = useState<FeedbackState>({});
  const [toolsCollapsed, setToolsCollapsed] = useState<ToolsCollapseState>({});
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Sync conversationId prop → load history when switching conversations
  useEffect(() => {
    if (conversationId !== currentConvId) {
      setCurrentConvId(conversationId);
      setMessages([]);
      if (conversationId) {
        getConversation(tenantId, conversationId)
          .then(({ messages: msgs }) => {
            setMessages(msgs.filter((m) => m.role !== 'tool_result'));
          })
          .catch(() => {});
      }
    }
  }, [conversationId, tenantId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Consume pending prompt from ToolsPanel
  useEffect(() => {
    if (pendingPrompt) {
      setInput(pendingPrompt);
      textareaRef.current?.focus();
      onPendingPromptConsumed?.();
    }
  }, [pendingPrompt, onPendingPromptConsumed]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const autoResize = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const maxH = 5 * 24 + 32;
    ta.style.height = Math.min(ta.scrollHeight, maxH) + 'px';
  };

  const handleSend = useCallback(
    async (text?: string) => {
      const msg = (text ?? input).trim();
      if (!msg || isLoading) return;

      setInput('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      setError(null);

      const optimisticUser: Message = {
        id: `tmp-${Date.now()}`,
        conversation_id: currentConvId ?? '',
        role: 'user',
        content: msg,
        tool_calls: [],
        input_tokens: null,
        output_tokens: null,
        latency_ms: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticUser]);
      setIsLoading(true);

      try {
        const resp: ChatResponse = await sendMessage(tenantId, msg, currentConvId);
        const convId = resp.conversation_id;
        if (!currentConvId) {
          setCurrentConvId(convId);
          onConversationCreated(convId);
        }

        const assistantMsg: Message = {
          id: resp.message_id,
          conversation_id: convId,
          role: 'assistant',
          content: resp.content,
          tool_calls: resp.tool_calls_made ?? [],
          input_tokens: resp.input_tokens,
          output_tokens: resp.output_tokens,
          latency_ms: resp.latency_ms,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        setError('Failed to get a response. Please try again.');
        setMessages((prev) => prev.filter((m) => m.id !== optimisticUser.id));
      } finally {
        setIsLoading(false);
      }
    },
    [input, isLoading, currentConvId, tenantId, onConversationCreated]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleFeedbackToggle = (msgId: string) => {
    setFeedback((prev) => ({
      ...prev,
      [msgId]: {
        open: !prev[msgId]?.open,
        rating: prev[msgId]?.rating ?? 3,
        type: prev[msgId]?.type ?? 'general',
        submitted: prev[msgId]?.submitted ?? false,
      },
    }));
  };

  const handleFeedbackSubmit = async (msg: Message) => {
    const fb = feedback[msg.id];
    if (!fb || !currentConvId) return;
    try {
      await submitFeedback(tenantId, {
        message_id: msg.id,
        conversation_id: currentConvId,
        rating: fb.rating,
        feedback_type: fb.type,
      });
      setFeedback((prev) => ({
        ...prev,
        [msg.id]: { ...prev[msg.id], submitted: true, open: false },
      }));
    } catch {
      // silent
    }
  };

  const renderMarkdown = (content: string) => {
    const html = marked.parse(content) as string;
    return <div className="prose-dark" dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="flex flex-col h-full bg-gray-900">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-indigo-600 flex items-center justify-center mb-4 shadow-lg">
              <Bot className="w-9 h-9 text-white" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">Aegis AI Compliance Assistant</h2>
            <p className="text-gray-400 max-w-md mb-8 text-sm leading-relaxed">
              Ask me anything about your compliance posture, vendor risks, audit findings, or generate reports.
            </p>
            <div className="grid grid-cols-2 gap-2 max-w-lg w-full">
              {SUGGESTED_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => void handleSend(prompt)}
                  className="text-left px-3 py-2 rounded-xl border border-gray-700 bg-gray-800 text-gray-300 text-xs hover:border-indigo-500 hover:bg-gray-750 hover:text-white transition-all duration-150"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'user' ? (
              <div className="max-w-[70%] bg-indigo-600 text-white px-4 py-3 rounded-tl-3xl rounded-bl-3xl rounded-tr-sm shadow-md text-sm whitespace-pre-wrap">
                {msg.content}
              </div>
            ) : (
              <div className="max-w-[80%] flex flex-col gap-1">
                <div className="bg-gray-800 text-gray-100 px-4 py-3 rounded-tr-3xl rounded-br-3xl rounded-tl-sm shadow-md text-sm">
                  {renderMarkdown(msg.content)}

                  {/* Tool calls */}
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="mt-2 border-t border-gray-700 pt-2">
                      <button
                        onClick={() =>
                          setToolsCollapsed((prev) => ({
                            ...prev,
                            [msg.id]: !prev[msg.id],
                          }))
                        }
                        className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-300 transition-colors"
                      >
                        {toolsCollapsed[msg.id] ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronUp className="w-3 h-3" />
                        )}
                        Tools used ({msg.tool_calls.length})
                      </button>
                      {!toolsCollapsed[msg.id] && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {msg.tool_calls.map((tool) => (
                            <span
                              key={tool}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-700 text-gray-300 text-xs"
                            >
                              <Wrench className="w-3 h-3 text-indigo-400" />
                              {formatToolName(tool)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Token / latency info + feedback */}
                <div className="flex items-center gap-2 px-1">
                  {(msg.input_tokens != null || msg.latency_ms != null) && (
                    <span className="text-xs text-gray-500">
                      {msg.input_tokens != null && msg.output_tokens != null
                        ? `↑${msg.input_tokens} ↓${msg.output_tokens} tokens`
                        : ''}
                      {msg.latency_ms != null
                        ? ` • ${msg.latency_ms}ms`
                        : ''}
                    </span>
                  )}
                  <div className="ml-auto flex items-center gap-1">
                    {feedback[msg.id]?.submitted ? (
                      <span className="text-xs text-gray-500">Thanks!</span>
                    ) : (
                      <>
                        <button
                          onClick={() => handleFeedbackToggle(msg.id)}
                          title="Rate response"
                          className="p-1 rounded hover:bg-gray-700 text-gray-500 hover:text-green-400 transition-colors"
                        >
                          <ThumbsUp className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleFeedbackToggle(msg.id)}
                          title="Rate response"
                          className="p-1 rounded hover:bg-gray-700 text-gray-500 hover:text-red-400 transition-colors"
                        >
                          <ThumbsDown className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Feedback dropdown */}
                {feedback[msg.id]?.open && !feedback[msg.id]?.submitted && (
                  <div className="bg-gray-800 border border-gray-700 rounded-xl p-3 text-xs shadow-lg">
                    <p className="text-gray-300 mb-2 font-medium">Rate this response</p>
                    <div className="flex gap-1 mb-2">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          onClick={() =>
                            setFeedback((prev) => ({
                              ...prev,
                              [msg.id]: { ...prev[msg.id], rating: n },
                            }))
                          }
                          className={`w-8 h-8 rounded-lg font-bold transition-colors ${
                            feedback[msg.id]?.rating === n
                              ? 'bg-indigo-600 text-white'
                              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                          }`}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                    <select
                      value={feedback[msg.id]?.type ?? 'general'}
                      onChange={(e) =>
                        setFeedback((prev) => ({
                          ...prev,
                          [msg.id]: { ...prev[msg.id], type: e.target.value },
                        }))
                      }
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-2 py-1 text-gray-300 text-xs mb-2"
                    >
                      <option value="general">General</option>
                      <option value="accuracy">Accuracy</option>
                      <option value="helpfulness">Helpfulness</option>
                      <option value="completeness">Completeness</option>
                    </select>
                    <div className="flex gap-2">
                      <button
                        onClick={() => void handleFeedbackSubmit(msg)}
                        className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-3 py-1 text-xs transition-colors"
                      >
                        Submit
                      </button>
                      <button
                        onClick={() =>
                          setFeedback((prev) => ({
                            ...prev,
                            [msg.id]: { ...prev[msg.id], open: false },
                          }))
                        }
                        className="flex-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg px-3 py-1 text-xs transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 rounded-tr-3xl rounded-br-3xl rounded-tl-sm px-4 py-3 shadow-md">
              <div className="flex items-center gap-1.5">
                <span className="typing-dot w-2 h-2 rounded-full bg-indigo-400 inline-block" />
                <span className="typing-dot w-2 h-2 rounded-full bg-indigo-400 inline-block" />
                <span className="typing-dot w-2 h-2 rounded-full bg-indigo-400 inline-block" />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-center">
            <div className="bg-red-900/50 border border-red-700 text-red-300 rounded-xl px-4 py-2 text-sm max-w-sm text-center">
              {error}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-gray-700 bg-gray-900 px-4 py-3">
        <div className="flex items-end gap-2 bg-gray-800 border border-gray-700 rounded-2xl px-3 py-2 focus-within:border-indigo-500 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              autoResize();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask Aegis AI anything about your compliance..."
            rows={1}
            className="flex-1 bg-transparent text-gray-100 placeholder-gray-500 text-sm resize-none outline-none leading-6 py-1"
            style={{ maxHeight: '152px' }}
            disabled={isLoading}
          />
          <button
            onClick={() => void handleSend()}
            disabled={!input.trim() || isLoading}
            className="flex-shrink-0 w-8 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:cursor-not-allowed flex items-center justify-center transition-colors mb-0.5"
          >
            <Send className="w-4 h-4 text-white" />
          </button>
        </div>
        <p className="text-center text-xs text-gray-600 mt-2">
          AI responses may contain errors. Always verify critical compliance decisions.
        </p>
      </div>
    </div>
  );
}
