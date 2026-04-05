import React, { useState, useEffect, useRef } from 'react';
import { Send, ChevronDown, ChevronUp } from 'lucide-react';
import { createChatSession, sendChatMessage } from '../api';
import type { ChatMessage } from '../types';

interface Props {
  slug: string;
  welcomeMessage: string | null;
}

const SESSION_TOKEN_KEY = 'aegis_chat_token';

function SourcesToggle({ sources }: { sources: Array<{ title: string; score: number }> }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {sources.length} source{sources.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <div className="mt-1 space-y-1">
          {sources.map((s, i) => (
            <div key={i} className="flex items-center justify-between text-xs bg-gray-100 rounded px-2 py-1">
              <span className="text-gray-600 truncate">{s.title}</span>
              <span className="ml-2 text-gray-400 shrink-0">{Math.round(s.score * 100)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 mb-3">
      <div className="bg-gray-100 rounded-2xl rounded-bl-none px-4 py-3 max-w-xs">
        <div className="flex gap-1 items-center h-4">
          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

export default function SecurityChatbot({ slug, welcomeMessage }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const welcome = welcomeMessage ?? 'Hello! I can answer questions about our security posture, compliance certifications, and documentation. How can I help?';
    return [{ role: 'assistant', content: welcome, sources: [] }];
  });
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize session
  useEffect(() => {
    const stored = sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (stored) {
      setSessionToken(stored);
      return;
    }
    createChatSession(slug).then(session => {
      sessionStorage.setItem(SESSION_TOKEN_KEY, session.session_token);
      setSessionToken(session.session_token);
    }).catch(console.error);
  }, [slug]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading || !sessionToken) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: text, sources: [] }]);
    setLoading(true);

    try {
      const response = await sendChatMessage(slug, sessionToken, text);
      setMessages(prev => [...prev, response]);
    } catch {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="flex flex-col border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
      {/* Chat Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">
          AI
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-900">Security Assistant</p>
          <p className="text-xs text-green-500">Online</p>
        </div>
      </div>

      {/* Message Area */}
      <div className="flex flex-col overflow-y-auto max-h-96 p-4 gap-1">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex mb-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-none'
                  : 'bg-gray-100 text-gray-800 rounded-bl-none'
              }`}
            >
              <p>{msg.content}</p>
              {msg.role === 'assistant' && <SourcesToggle sources={msg.sources} />}
            </div>
          </div>
        ))}
        {loading && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 px-4 py-3 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about our security certifications, policies, or controls..."
          rows={1}
          className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[38px] max-h-32 leading-5"
          style={{ height: 'auto' }}
          disabled={!sessionToken}
        />
        <button
          onClick={() => void handleSend()}
          disabled={!input.trim() || loading || !sessionToken}
          className="p-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
      </div>

      {/* Watermark */}
      <div className="text-right px-4 pb-2">
        <span className="text-[10px] text-gray-300">Powered by VIA RAG Pipeline</span>
      </div>
    </div>
  );
}
