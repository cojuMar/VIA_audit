import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  FileText,
  Shield,
  Search,
  Lock,
  Download,
  AlertCircle,
} from 'lucide-react';
import { getDocuments, getDownloadUrl } from '../api';
import type { PortalDocument } from '../types';
import NDASigningModal from './NDASigningModal';

interface Props {
  slug: string;
  ndaVersion: string;
  requireNda: boolean;
}

const NDA_STORAGE_KEY = 'aegis_nda_email';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function isExpired(iso: string): boolean {
  return new Date(iso) < new Date();
}

const DOC_TYPE_STYLES: Record<string, string> = {
  soc2_report: 'bg-blue-100 text-blue-700',
  iso_cert: 'bg-green-100 text-green-700',
  pentest: 'bg-orange-100 text-orange-700',
  security_overview: 'bg-gray-100 text-gray-600',
};

function DocTypeIcon({ type }: { type: string }) {
  if (type === 'soc2_report' || type === 'iso_cert') return <Shield size={20} className="text-gray-400" />;
  if (type === 'pentest') return <Search size={20} className="text-gray-400" />;
  return <FileText size={20} className="text-gray-400" />;
}

function DocCard({
  doc,
  ndaEmail,
  slug,
  onNDARequired,
}: {
  doc: PortalDocument;
  ndaEmail: string | null;
  slug: string;
  onNDARequired: () => void;
}) {
  const [downloading, setDownloading] = useState(false);
  const needsNda = doc.requires_nda && !ndaEmail;
  const typeLabel = doc.document_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  const handleDownload = async () => {
    if (needsNda) {
      onNDARequired();
      return;
    }
    if (!ndaEmail) return;
    setDownloading(true);
    try {
      const { url } = await getDownloadUrl(slug, doc.id, ndaEmail);
      window.open(url, '_blank');
    } catch {
      alert('Download failed. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="relative bg-white border border-gray-200 rounded-xl p-5 flex flex-col gap-3 shadow-sm hover:shadow-md transition-shadow">
      {/* Lock overlay for NDA-gated docs */}
      {needsNda && (
        <div className="absolute inset-0 rounded-xl bg-white/70 flex flex-col items-center justify-center z-10 backdrop-blur-[1px]">
          <Lock size={24} className="text-gray-400 mb-1" />
          <span className="text-xs font-medium text-gray-500">Sign NDA to Access</span>
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className="p-2 bg-gray-50 rounded-lg">
          <DocTypeIcon type={doc.document_type} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 text-sm leading-tight">{doc.display_name}</p>
          {doc.description && (
            <p className="text-gray-500 text-xs mt-0.5 line-clamp-2">{doc.description}</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <span
          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
            DOC_TYPE_STYLES[doc.document_type] ?? 'bg-gray-100 text-gray-600'
          }`}
        >
          {typeLabel}
        </span>
        {doc.file_size_bytes !== null && (
          <span className="text-xs text-gray-400">{formatBytes(doc.file_size_bytes)}</span>
        )}
      </div>

      {doc.valid_until && (
        <div className={`flex items-center gap-1 text-xs ${isExpired(doc.valid_until) ? 'text-red-600' : 'text-gray-400'}`}>
          <AlertCircle size={12} />
          {isExpired(doc.valid_until) ? 'Expired ' : 'Valid until '}
          {formatDate(doc.valid_until)}
        </div>
      )}

      <button
        onClick={handleDownload}
        disabled={downloading}
        className="mt-auto flex items-center justify-center gap-2 w-full py-2 text-sm font-medium text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {downloading ? (
          <span className="inline-block w-4 h-4 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
        ) : (
          <Download size={14} />
        )}
        {needsNda ? 'Sign NDA to Access' : 'Download'}
      </button>
    </div>
  );
}

export default function DocumentLibrary({ slug, ndaVersion, requireNda }: Props) {
  const [ndaEmail, setNdaEmail] = useState<string | null>(() =>
    sessionStorage.getItem(NDA_STORAGE_KEY)
  );
  const [showNdaBanner, setShowNdaBanner] = useState(false);
  const [showNdaModal, setShowNdaModal] = useState(false);

  useEffect(() => {
    if (requireNda && !ndaEmail) {
      setShowNdaBanner(true);
    }
  }, [requireNda, ndaEmail]);

  const { data: documents, isLoading, isError } = useQuery({
    queryKey: ['documents', slug, ndaEmail],
    queryFn: () => getDocuments(slug, ndaEmail ?? undefined),
  });

  const handleNdaSuccess = (email: string) => {
    sessionStorage.setItem(NDA_STORAGE_KEY, email);
    setNdaEmail(email);
    setShowNdaModal(false);
    setShowNdaBanner(false);
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="inline-block w-8 h-8 border-2 border-gray-200 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-16 text-gray-500">
        Failed to load documents. Please refresh and try again.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* NDA Banner */}
      {showNdaBanner && !ndaEmail && (
        <div className="flex items-center justify-between bg-amber-50 border border-amber-200 rounded-xl px-5 py-4">
          <div className="flex items-center gap-3">
            <Lock size={20} className="text-amber-600" />
            <div>
              <p className="text-sm font-semibold text-amber-800">NDA Required</p>
              <p className="text-xs text-amber-700">
                Some documents require a signed NDA before download. Sign now to unlock access.
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowNdaModal(true)}
            className="ml-4 px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-lg hover:bg-amber-700 transition-colors whitespace-nowrap"
          >
            Sign NDA
          </button>
        </div>
      )}

      {/* Signed confirmation */}
      {ndaEmail && (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-700">
          <Shield size={16} />
          NDA signed as <strong>{ndaEmail}</strong> — all documents are unlocked.
        </div>
      )}

      {/* Document Grid */}
      {documents && documents.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {documents.map(doc => (
            <DocCard
              key={doc.id}
              doc={doc}
              ndaEmail={ndaEmail}
              slug={slug}
              onNDARequired={() => setShowNdaModal(true)}
            />
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 gap-3">
          <FileText size={40} strokeWidth={1} />
          <p className="text-sm">No documents available at this time.</p>
        </div>
      )}

      {/* NDA Modal */}
      {showNdaModal && (
        <NDASigningModal
          slug={slug}
          nda_version={ndaVersion}
          onSuccess={handleNdaSuccess}
          onClose={() => setShowNdaModal(false)}
        />
      )}
    </div>
  );
}
