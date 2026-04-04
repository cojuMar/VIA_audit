import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, ChevronDown, ChevronUp, Loader2, CheckCircle, XCircle, Printer } from 'lucide-react';
import { submitDeflection, getDeflectionResult } from '../api';
import type { DeflectionResult } from '../types';

interface Props {
  slug: string;
}

type Step = 'form' | 'processing' | 'results';

const QUESTIONNAIRE_TYPES = [
  { value: 'sig_lite', label: 'SIG Lite' },
  { value: 'caiq_v4', label: 'CAIQ v4' },
  { value: 'soc2_inquiry', label: 'SOC 2 Inquiry' },
  { value: 'custom', label: 'Custom' },
  { value: 'unknown', label: 'Unknown' },
];

function AccordionItem({ mapping }: { mapping: DeflectionResult['deflection_mappings'][0] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="text-sm font-medium text-gray-800 pr-4 line-clamp-2">{mapping.question}</span>
        {open ? <ChevronUp size={16} className="shrink-0 text-gray-400" /> : <ChevronDown size={16} className="shrink-0 text-gray-400" />}
      </button>
      {open && (
        <div className="px-4 py-4 space-y-4 bg-white">
          {/* AI Response */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">AI Response</p>
            <p className="text-sm text-gray-700 leading-relaxed">{mapping.ai_response}</p>
          </div>

          {/* Evidence Sources */}
          {mapping.rag_evidence.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Evidence Sources</p>
              <div className="space-y-2">
                {mapping.rag_evidence.map((ev, i) => (
                  <div key={i} className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
                    <p className="text-xs font-medium text-gray-700">{ev.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{ev.snippet}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function QuestionnaireDeflector({ slug }: Props) {
  const [step, setStep] = useState<Step>('form');

  // Form state
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [qType, setQType] = useState('sig_lite');
  const [bulkText, setBulkText] = useState('');
  const [questions, setQuestions] = useState<string[]>([]);
  const [newQuestion, setNewQuestion] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Processing / results state
  const [deflectionId, setDeflectionId] = useState<string | null>(null);
  const [result, setResult] = useState<DeflectionResult | null>(null);
  const [pollError, setPollError] = useState(false);

  // Derive all questions (bulk + individual)
  const allQuestions = [
    ...bulkText.split('\n').map(q => q.trim()).filter(Boolean),
    ...questions,
  ];

  // Polling
  const poll = useCallback(async (id: string) => {
    try {
      const data = await getDeflectionResult(slug, id);
      if (data.status === 'completed' || data.status === 'failed') {
        setResult(data);
        setStep('results');
      }
      // If still pending/processing, caller will retry
      return data.status;
    } catch {
      setPollError(true);
      setStep('results');
      return 'failed';
    }
  }, [slug]);

  useEffect(() => {
    if (step !== 'processing' || !deflectionId) return;

    let cancelled = false;
    const interval = setInterval(async () => {
      if (cancelled) return;
      const status = await poll(deflectionId);
      if (status === 'completed' || status === 'failed') {
        clearInterval(interval);
      }
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [step, deflectionId, poll]);

  const handleAddQuestion = () => {
    const q = newQuestion.trim();
    if (!q) return;
    setQuestions(prev => [...prev, q]);
    setNewQuestion('');
  };

  const handleRemoveQuestion = (idx: number) => {
    setQuestions(prev => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (allQuestions.length === 0) {
      setFormError('Please add at least one question.');
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      const res = await submitDeflection(slug, {
        requester_name: name.trim(),
        requester_email: email.trim(),
        requester_company: company.trim() || null,
        questionnaire_type: qType,
        questions: allQuestions,
      });
      setDeflectionId(res.id);
      setResult(res);
      if (res.status === 'completed') {
        setStep('results');
      } else {
        setStep('processing');
      }
    } catch {
      setFormError('Submission failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReset = () => {
    setStep('form');
    setName('');
    setEmail('');
    setCompany('');
    setQType('sig_lite');
    setBulkText('');
    setQuestions([]);
    setNewQuestion('');
    setDeflectionId(null);
    setResult(null);
    setPollError(false);
    setFormError(null);
  };

  // ── Step 1: Form ────────────────────────────────────────────────────────────
  if (step === 'form') {
    return (
      <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Your Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Jane Smith"
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="jane@example.com"
              required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Company</label>
            <input
              type="text"
              value={company}
              onChange={e => setCompany(e.target.value)}
              placeholder="Acme Corp"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Questionnaire Type <span className="text-red-500">*</span>
            </label>
            <select
              value={qType}
              onChange={e => setQType(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              {QUESTIONNAIRE_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Bulk paste */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Paste Questions{' '}
            <span className="text-gray-400 font-normal">(one per line)</span>
          </label>
          <textarea
            value={bulkText}
            onChange={e => setBulkText(e.target.value)}
            rows={5}
            placeholder="Does your organization have a SOC 2 Type II report?&#10;What is your data retention policy?&#10;Do you encrypt data at rest?"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
        </div>

        {/* Individual question add */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Add Individual Questions</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={newQuestion}
              onChange={e => setNewQuestion(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); handleAddQuestion(); }
              }}
              placeholder="Type a question..."
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={handleAddQuestion}
              className="flex items-center gap-1 px-3 py-2 text-sm bg-gray-100 border border-gray-300 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <Plus size={14} /> Add
            </button>
          </div>
          {questions.length > 0 && (
            <ul className="mt-2 space-y-1">
              {questions.map((q, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700 bg-gray-50 rounded-lg px-3 py-2">
                  <span className="flex-1">{q}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveQuestion(i)}
                    className="text-gray-300 hover:text-red-500 transition-colors shrink-0 mt-0.5"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Question count badge */}
        {allQuestions.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
              {allQuestions.length} question{allQuestions.length !== 1 ? 's' : ''} ready
            </span>
          </div>
        )}

        {formError && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {formError}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !name || !email}
          className="flex items-center gap-2 px-6 py-2.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting && <Loader2 size={16} className="animate-spin" />}
          Submit for AI Analysis
        </button>
      </form>
    );
  }

  // ── Step 2: Processing ──────────────────────────────────────────────────────
  if (step === 'processing') {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-6 text-center">
        <Loader2 size={48} className="animate-spin text-blue-500" />
        <div>
          <p className="text-base font-semibold text-gray-800">Analyzing your questionnaire...</p>
          <p className="text-sm text-gray-500 mt-1">
            Our AI is mapping your questions to our security evidence. This may take up to a minute.
          </p>
        </div>
        <div className="flex gap-1">
          {[0, 1, 2].map(i => (
            <span
              key={i}
              className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    );
  }

  // ── Step 3: Results ─────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 max-w-3xl">
      {/* Summary bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        {pollError || result?.status === 'failed' ? (
          <div className="flex items-center gap-2 text-red-600">
            <XCircle size={20} />
            <span className="text-sm font-medium">Processing failed. Please try again.</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-green-600">
            <CheckCircle size={20} />
            <span className="text-sm font-medium">
              {result?.deflection_mappings.length ?? 0} question
              {result?.deflection_mappings.length !== 1 ? 's' : ''} answered
            </span>
            <span className="text-xs text-gray-400 ml-1">— Powered by Claude AI</span>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => window.print()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <Printer size={14} /> Download as PDF
          </button>
          <button
            onClick={handleReset}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Submit Another
          </button>
        </div>
      </div>

      {/* Results accordion */}
      {result?.deflection_mappings && result.deflection_mappings.length > 0 ? (
        <div className="space-y-2">
          {result.deflection_mappings.map((mapping, i) => (
            <AccordionItem key={i} mapping={mapping} />
          ))}
        </div>
      ) : (
        !pollError && (
          <p className="text-sm text-gray-500 text-center py-8">No results available.</p>
        )
      )}
    </div>
  );
}
