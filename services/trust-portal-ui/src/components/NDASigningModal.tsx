import React, { useEffect, useId, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { signNDA } from '../api';

interface Props {
  slug: string;
  nda_version: string;
  onSuccess: (email: string) => void;
  onClose: () => void;
}

export default function NDASigningModal({ slug, nda_version, onSuccess, onClose }: Props) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim() !== '' && email.trim() !== '' && agreed && !loading;
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);

  // Sprint 27 a11y: Escape closes, focus restores to opener, Tab is trapped
  // inside the dialog. Mirrors the @via/ui-kit/Modal behaviour for portal
  // visitors (this UI ships independently of the rest of the workspace).
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !dialogRef.current) return;
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href],input:not([disabled]),button:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      await signNDA(
        slug,
        {
          signatory_name: name.trim(),
          signatory_email: email.trim(),
          signatory_company: company.trim() || null,
          nda_version,
        }
      );
      onSuccess(email.trim());
    } catch {
      setError('Failed to submit NDA. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 id={titleId} className="text-lg font-semibold text-gray-900">Non-Disclosure Agreement</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* NDA Text */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 h-48 overflow-y-auto text-sm text-gray-600 leading-relaxed">
            <p className="font-semibold text-gray-800 mb-2">MUTUAL NON-DISCLOSURE AGREEMENT</p>
            <p>
              By signing this NDA, you agree to keep all information obtained through this portal
              confidential and not to disclose it to any third party without prior written consent.
              This agreement covers all security documentation, compliance reports, audit results,
              penetration test findings, and any other materials provided through the VIA Trust Portal.
            </p>
            <p className="mt-2">
              You agree to use the confidential information solely for the purpose of evaluating a
              potential business relationship. This agreement shall remain in effect for a period of
              two (2) years from the date of signature, unless otherwise agreed in writing.
            </p>
            <p className="mt-2">
              Any breach of this agreement may result in irreparable harm for which monetary damages
              would be inadequate. The disclosing party shall be entitled to seek equitable relief
              in addition to all other remedies available at law or in equity.
            </p>
            <p className="mt-2 text-xs text-gray-400">NDA Version: {nda_version}</p>
          </div>

          {/* Form Fields */}
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Full Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Jane Smith"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
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
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Company <span className="text-gray-400">(optional)</span>
              </label>
              <input
                type="text"
                value={company}
                onChange={e => setCompany(e.target.value)}
                placeholder="Acme Corp"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Agreement Checkbox */}
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={agreed}
              onChange={e => setAgreed(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-600">
              I have read and agree to the terms of this Non-Disclosure Agreement
            </span>
          </label>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading && (
                <span className="inline-block w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              )}
              Sign &amp; Accept
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
