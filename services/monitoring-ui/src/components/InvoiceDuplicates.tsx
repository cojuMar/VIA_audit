import { useState, useRef, useCallback } from 'react';
import { Upload, FileText, AlertTriangle, Copy, Scissors, GitMerge } from 'lucide-react';
import { runAnalysis } from '../api';
import type { MonitoringFinding } from '../types';
import FindingsTable from './FindingsTable';

interface Props {
  tenantId: string;
}

interface Invoice {
  invoice_id: string;
  vendor_name: string;
  amount: number;
  invoice_date: string;
  [key: string]: unknown;
}

interface AnalysisResult {
  run_id: string;
  findings_count: number;
  findings: MonitoringFinding[];
}

function parseCsv(text: string): Invoice[] {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''));
  return lines.slice(1).map(line => {
    const vals = line.split(',').map(v => v.trim().replace(/"/g, ''));
    const obj: Record<string, unknown> = {};
    headers.forEach((h, i) => { obj[h] = vals[i] ?? ''; });
    return {
      ...obj,
      invoice_id: String(obj['invoice_id'] ?? ''),
      vendor_name: String(obj['vendor_name'] ?? ''),
      amount: parseFloat(String(obj['amount'] ?? '0')) || 0,
      invoice_date: String(obj['invoice_date'] ?? ''),
    } as Invoice;
  });
}

type MatchType = 'EXACT' | 'FUZZY' | 'SPLIT';

interface DuplicatePair {
  invoiceA: Invoice;
  invoiceB: Invoice;
  matchType: MatchType;
  similarity?: number;
  finding: MonitoringFinding;
}

function matchTypeBadge(type: MatchType) {
  const cfg = {
    EXACT: { cls: 'bg-red-800 text-red-100', icon: <Copy size={10} /> },
    FUZZY: { cls: 'bg-orange-800 text-orange-100', icon: <GitMerge size={10} /> },
    SPLIT: { cls: 'bg-yellow-800 text-yellow-100', icon: <Scissors size={10} /> },
  }[type];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${cfg.cls}`}>
      {cfg.icon}{type}
    </span>
  );
}

function InvoiceCard({ invoice }: { invoice: Invoice }) {
  return (
    <div className="bg-gray-800 rounded-lg p-3 border border-gray-700 flex-1">
      <p className="text-xs text-gray-500 mb-2">Invoice</p>
      <div className="space-y-1.5">
        <div>
          <span className="text-xs text-gray-500">ID </span>
          <span className="text-sm text-gray-200 font-mono">{invoice.invoice_id}</span>
        </div>
        <div>
          <span className="text-xs text-gray-500">Vendor </span>
          <span className="text-sm text-gray-200">{invoice.vendor_name}</span>
        </div>
        <div>
          <span className="text-xs text-gray-500">Amount </span>
          <span className="text-sm text-green-400 font-semibold">${invoice.amount.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-xs text-gray-500">Date </span>
          <span className="text-sm text-gray-300">{invoice.invoice_date}</span>
        </div>
      </div>
    </div>
  );
}

export default function InvoiceDuplicates({ tenantId }: Props) {
  const [dragging, setDragging] = useState(false);
  const [rawText, setRawText] = useState('');
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [parseError, setParseError] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const processText = (text: string) => {
    setRawText(text);
    setParseError('');
    try {
      const trimmed = text.trim();
      let parsed: Invoice[];
      if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
        const j = JSON.parse(trimmed);
        parsed = Array.isArray(j) ? j : [j];
      } else {
        parsed = parseCsv(trimmed);
      }
      if (parsed.length === 0) { setParseError('No records found.'); return; }
      if (!parsed[0].invoice_id) { setParseError('Missing required field: invoice_id'); return; }
      setInvoices(parsed);
    } catch {
      setParseError('Failed to parse input.');
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = ev => processText(ev.target?.result as string);
      reader.readAsText(file);
    }
  }, []);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = ev => processText(ev.target?.result as string);
      reader.readAsText(file);
    }
  };

  const analyze = async () => {
    if (invoices.length === 0) return;
    setLoading(true);
    setError('');
    try {
      const res = await runAnalysis(tenantId, 'invoices', invoices);
      setResult(res);
    } catch (e) {
      setError('Analysis failed. Check the backend connection.');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // Build duplicate pairs from findings
  const pairs: DuplicatePair[] = (result?.findings ?? []).map(f => {
    const ev = f.evidence as Record<string, unknown>;
    const idA = String(ev['invoice_id_a'] ?? ev['invoice_a'] ?? '');
    const idB = String(ev['invoice_id_b'] ?? ev['invoice_b'] ?? '');
    const invoiceA = invoices.find(i => i.invoice_id === idA) ?? {
      invoice_id: idA, vendor_name: String(ev['vendor_name'] ?? ''),
      amount: Number(ev['amount_a'] ?? 0), invoice_date: String(ev['date_a'] ?? ''),
    };
    const invoiceB = invoices.find(i => i.invoice_id === idB) ?? {
      invoice_id: idB, vendor_name: String(ev['vendor_name'] ?? ''),
      amount: Number(ev['amount_b'] ?? 0), invoice_date: String(ev['date_b'] ?? ''),
    };
    const matchType: MatchType =
      f.finding_type === 'invoice_split' ? 'SPLIT' :
      (ev['similarity'] && Number(ev['similarity']) < 1) ? 'FUZZY' : 'EXACT';
    return { invoiceA, invoiceB, matchType, similarity: Number(ev['similarity'] ?? 1), finding: f };
  });

  const exactCount = pairs.filter(p => p.matchType === 'EXACT').length;
  const fuzzyCount = pairs.filter(p => p.matchType === 'FUZZY').length;
  const splitCount = pairs.filter(p => p.matchType === 'SPLIT').length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Invoice Duplicate Detection</h2>
        <p className="text-gray-400 text-sm mt-1">Find exact duplicates, near-duplicates, and split invoices in AP data</p>
      </div>

      {/* Upload Panel */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
        <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <Upload size={16} className="text-indigo-400" />
          Upload Invoice Data
        </h3>

        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragging ? 'border-indigo-500 bg-indigo-900/20' : 'border-gray-600 hover:border-gray-500'
          }`}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <FileText size={32} className="mx-auto text-gray-500 mb-3" />
          <p className="text-gray-300 font-medium">Drop CSV or JSON file here</p>
          <p className="text-gray-500 text-sm mt-1">or click to browse</p>
          <p className="text-gray-600 text-xs mt-3">Required fields: invoice_id, vendor_name, amount, invoice_date</p>
          <input ref={fileRef} type="file" accept=".csv,.json" className="hidden" onChange={handleFile} />
        </div>

        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-2">Or paste data directly:</p>
          <textarea
            rows={5}
            value={rawText}
            onChange={e => processText(e.target.value)}
            placeholder={"invoice_id,vendor_name,amount,invoice_date\nINV-001,Acme Corp,1500.00,2024-01-15\nINV-002,Acme Corp,1500.00,2024-01-15"}
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>

        {parseError && (
          <p className="mt-2 text-sm text-red-400 flex items-center gap-2">
            <AlertTriangle size={14} /> {parseError}
          </p>
        )}

        {invoices.length > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-sm text-green-400">{invoices.length} invoices loaded</p>
            <button
              onClick={analyze}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Analyzing...' : 'Analyze Invoices'}
            </button>
          </div>
        )}

        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </div>

      {/* Results */}
      {result && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Invoices Analyzed</p>
              <p className="text-2xl font-bold text-white">{invoices.length}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Exact Duplicates</p>
              <p className="text-2xl font-bold text-red-400 flex items-center gap-2"><Copy size={18} />{exactCount}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-orange-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Near-Duplicates</p>
              <p className="text-2xl font-bold text-orange-400 flex items-center gap-2"><GitMerge size={18} />{fuzzyCount}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-yellow-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Split Invoices</p>
              <p className="text-2xl font-bold text-yellow-400 flex items-center gap-2"><Scissors size={18} />{splitCount}</p>
            </div>
          </div>

          {/* Duplicate Pairs */}
          {pairs.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-base font-semibold text-white">Duplicate Pairs</h3>
              {pairs.map((pair, i) => (
                <div key={i} className="bg-gray-800 rounded-xl border border-gray-700 p-4">
                  <div className="flex items-start gap-4">
                    <InvoiceCard invoice={pair.invoiceA} />

                    {/* Center badge */}
                    <div className="flex flex-col items-center justify-center gap-2 flex-shrink-0 pt-8">
                      {matchTypeBadge(pair.matchType)}
                      {pair.matchType === 'FUZZY' && pair.similarity !== undefined && (
                        <span className="text-xs text-gray-400">{(pair.similarity * 100).toFixed(0)}% match</span>
                      )}
                      <div className="w-8 border-t border-gray-600" />
                    </div>

                    <InvoiceCard invoice={pair.invoiceB} />
                  </div>
                  <div className="mt-3 pt-3 border-t border-gray-700/50">
                    <p className="text-xs text-gray-400">{pair.finding.description}</p>
                    {pair.finding.risk_score !== null && (
                      <p className="text-xs text-gray-500 mt-1">Risk score: {pair.finding.risk_score}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Historical */}
      <div>
        <h3 className="text-base font-semibold text-white mb-4">Historical AP Findings</h3>
        <FindingsTable
          tenantId={tenantId}
          findingType="invoice"
          title="Accounts Payable Findings"
        />
      </div>
    </div>
  );
}
