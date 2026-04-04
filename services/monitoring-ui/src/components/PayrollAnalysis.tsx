import { useState, useRef, useCallback } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Upload, FileText, AlertTriangle, Users, TrendingUp, BarChart2, ChevronDown, ChevronRight } from 'lucide-react';
import { runAnalysis } from '../api';
import type { MonitoringFinding, Severity } from '../types';
import FindingsTable from './FindingsTable';

interface Props {
  tenantId: string;
}

interface PayrollRecord {
  employee_id: string;
  amount: number;
  period?: string;
  [key: string]: unknown;
}

interface AnalysisResult {
  run_id: string;
  findings_count: number;
  findings: MonitoringFinding[];
}

function parseCsv(text: string): PayrollRecord[] {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''));
  return lines.slice(1).map(line => {
    const vals = line.split(',').map(v => v.trim().replace(/"/g, ''));
    const obj: Record<string, unknown> = {};
    headers.forEach((h, i) => { obj[h] = vals[i] ?? ''; });
    return {
      ...obj,
      employee_id: String(obj['employee_id'] ?? ''),
      amount: parseFloat(String(obj['amount'] ?? '0')) || 0,
    } as PayrollRecord;
  });
}

function stats(data: PayrollRecord[]) {
  if (data.length === 0) return { mean: 0, std: 0 };
  const amounts = data.map(d => d.amount);
  const mean = amounts.reduce((a, b) => a + b, 0) / amounts.length;
  const variance = amounts.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / amounts.length;
  return { mean, std: Math.sqrt(variance) };
}

function severityColor(s: Severity): string {
  return { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#3b82f6', info: '#6b7280' }[s] ?? '#6b7280';
}

interface FindingGroupProps {
  type: string;
  findings: MonitoringFinding[];
}

function FindingGroup({ type, findings }: FindingGroupProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-800 hover:bg-gray-750 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          {open ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
          <span className="text-sm font-medium text-gray-200">{type.replace(/_/g, ' ').toUpperCase()}</span>
          <span className="px-2 py-0.5 rounded-full bg-gray-700 text-xs text-gray-300">{findings.length}</span>
        </div>
      </button>
      {open && (
        <div className="divide-y divide-gray-700/50">
          {findings.map(f => (
            <div key={f.id} className="px-4 py-3 bg-gray-850 text-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-gray-200 font-medium">{f.title}</p>
                  <p className="text-gray-400 text-xs mt-0.5">{f.description}</p>
                </div>
                <span
                  className="px-2 py-0.5 rounded text-xs font-bold uppercase flex-shrink-0"
                  style={{ backgroundColor: severityColor(f.severity) + '33', color: severityColor(f.severity) }}
                >
                  {f.severity}
                </span>
              </div>
              {Object.keys(f.evidence).length > 0 && (
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {Object.entries(f.evidence).slice(0, 6).map(([k, v]) => (
                    <div key={k} className="bg-gray-800 rounded p-1.5">
                      <p className="text-xs text-gray-500">{k}</p>
                      <p className="text-xs text-gray-300 font-mono">{String(v)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PayrollAnalysis({ tenantId }: Props) {
  const [dragging, setDragging] = useState(false);
  const [rawText, setRawText] = useState('');
  const [records, setRecords] = useState<PayrollRecord[]>([]);
  const [parseError, setParseError] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const processText = (text: string) => {
    setRawText(text);
    setParseError('');
    try {
      let parsed: PayrollRecord[];
      const trimmed = text.trim();
      if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
        const j = JSON.parse(trimmed);
        parsed = Array.isArray(j) ? j : [j];
      } else {
        parsed = parseCsv(trimmed);
      }
      if (parsed.length === 0) { setParseError('No records found.'); return; }
      if (!parsed[0].employee_id) { setParseError('Missing required field: employee_id'); return; }
      setRecords(parsed);
    } catch {
      setParseError('Failed to parse input. Please check the format.');
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
    if (records.length === 0) return;
    setLoading(true);
    setError('');
    try {
      const res = await runAnalysis(tenantId, 'payroll', records);
      setResult(res);
    } catch (e) {
      setError('Analysis failed. Check the backend connection.');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const { mean, std } = stats(records);

  const scatterData = records.map((r, i) => ({
    x: i,
    y: r.amount,
    severity: result?.findings.find(f => f.entity_id === r.employee_id)?.severity ?? 'info',
    employee_id: r.employee_id,
  }));

  const findingsByType: Record<string, MonitoringFinding[]> = {};
  result?.findings.forEach(f => {
    if (!findingsByType[f.finding_type]) findingsByType[f.finding_type] = [];
    findingsByType[f.finding_type].push(f);
  });

  const outlierCount = result?.findings.filter(f => f.finding_type === 'payroll_outlier').length ?? 0;
  const ghostCount = result?.findings.filter(f => f.finding_type === 'payroll_ghost').length ?? 0;
  const benfordCount = result?.findings.filter(f => f.finding_type === 'payroll_benford').length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Payroll Analysis</h2>
        <p className="text-gray-400 text-sm mt-1">Detect outliers, ghost employees, and Benford's law deviations in payroll data</p>
      </div>

      {/* Upload Panel */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
        <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <Upload size={16} className="text-indigo-400" />
          Upload Payroll Data
        </h3>

        {/* Drop zone */}
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${
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
          <p className="text-gray-600 text-xs mt-3">Required fields: employee_id, amount, period</p>
          <input ref={fileRef} type="file" accept=".csv,.json" className="hidden" onChange={handleFile} />
        </div>

        {/* Or paste */}
        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-2">Or paste data directly:</p>
          <textarea
            rows={5}
            value={rawText}
            onChange={e => processText(e.target.value)}
            placeholder={"employee_id,amount,period\nEMP001,5000,2024-01\nEMP002,5200,2024-01"}
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>

        {parseError && (
          <p className="mt-2 text-sm text-red-400 flex items-center gap-2">
            <AlertTriangle size={14} /> {parseError}
          </p>
        )}

        {records.length > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-sm text-green-400">{records.length} records loaded</p>
            <button
              onClick={analyze}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Analyzing...' : 'Analyze Payroll'}
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
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Records Analyzed</p>
              <p className="text-2xl font-bold text-white flex items-center gap-2">
                <Users size={18} className="text-indigo-400" />{records.length}
              </p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-orange-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Outliers Found</p>
              <p className="text-2xl font-bold text-orange-400 flex items-center gap-2">
                <TrendingUp size={18} />{outlierCount}
              </p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-yellow-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Benford Deviation</p>
              <p className="text-2xl font-bold text-yellow-400 flex items-center gap-2">
                <BarChart2 size={18} />{benfordCount}
              </p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Ghost Employees</p>
              <p className="text-2xl font-bold text-red-400 flex items-center gap-2">
                <AlertTriangle size={18} />{ghostCount}
              </p>
            </div>
          </div>

          {/* Scatter Chart */}
          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
            <h3 className="text-base font-semibold text-white mb-4">Payroll Outlier Chart</h3>
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="x"
                  name="Employee #"
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  label={{ value: 'Employee Index', position: 'insideBottom', offset: -5, fill: '#6b7280', fontSize: 11 }}
                />
                <YAxis
                  dataKey="y"
                  name="Amount"
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                  formatter={(v: unknown) => [`$${Number(v).toLocaleString()}`, 'Amount']}
                />
                <ReferenceLine y={mean} stroke="#6b7280" strokeDasharray="4 2" label={{ value: 'Mean', fill: '#9ca3af', fontSize: 10 }} />
                {std > 0 && (
                  <>
                    <ReferenceLine y={mean + 2 * std} stroke="#eab308" strokeDasharray="4 2" label={{ value: '+2σ', fill: '#eab308', fontSize: 10 }} />
                    <ReferenceLine y={Math.max(0, mean - 2 * std)} stroke="#eab308" strokeDasharray="4 2" label={{ value: '-2σ', fill: '#eab308', fontSize: 10 }} />
                    <ReferenceLine y={mean + 3 * std} stroke="#ef4444" strokeDasharray="4 2" label={{ value: '+3σ', fill: '#ef4444', fontSize: 10 }} />
                  </>
                )}
                <Legend />
                <Scatter
                  name="Payroll Records"
                  data={scatterData}
                  fill="#6366f1"
                  opacity={0.7}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          {/* Findings grouped by type */}
          {Object.keys(findingsByType).length > 0 && (
            <div className="space-y-3">
              <h3 className="text-base font-semibold text-white">Findings by Type</h3>
              {Object.entries(findingsByType).map(([type, findings]) => (
                <FindingGroup key={type} type={type} findings={findings} />
              ))}
            </div>
          )}
        </>
      )}

      {/* Historical */}
      <div>
        <h3 className="text-base font-semibold text-white mb-4">Historical Payroll Findings</h3>
        <FindingsTable
          tenantId={tenantId}
          findingType="payroll"
          title="Payroll Findings"
        />
      </div>
    </div>
  );
}
