import { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Upload, FileText, AlertTriangle, Users, Shield } from 'lucide-react';
import { getSoDRules, getSoDViolations, getSoDSummary, runAnalysis } from '../api';
import type { MonitoringFinding, Severity } from '../types';

interface Props {
  tenantId: string;
}

interface UserRecord {
  user_id: string;
  user_name?: string;
  roles: string;
  [key: string]: unknown;
}

interface ScanResult {
  run_id: string;
  findings_count: number;
  findings: MonitoringFinding[];
}

function parseCsv(text: string): UserRecord[] {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''));
  return lines.slice(1).map(line => {
    const vals = line.split(',').map(v => v.trim().replace(/"/g, ''));
    const obj: Record<string, unknown> = {};
    headers.forEach((h, i) => { obj[h] = vals[i] ?? ''; });
    return {
      ...obj,
      user_id: String(obj['user_id'] ?? ''),
      user_name: String(obj['user_name'] ?? ''),
      roles: String(obj['roles'] ?? ''),
    } as UserRecord;
  });
}

function severityColor(s: Severity): string {
  return { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#3b82f6', info: '#6b7280' }[s] ?? '#6b7280';
}

function severityBg(s: Severity): string {
  return { critical: 'bg-red-900/60', high: 'bg-orange-900/60', medium: 'bg-yellow-900/60', low: 'bg-blue-900/60', info: 'bg-gray-800' }[s] ?? 'bg-gray-800';
}

const FRAMEWORK_COLORS: Record<string, string> = {
  SOX: 'bg-blue-900/60 text-blue-300 border border-blue-700',
  SOC2: 'bg-purple-900/60 text-purple-300 border border-purple-700',
  ISO27001: 'bg-green-900/60 text-green-300 border border-green-700',
  NIST: 'bg-yellow-900/60 text-yellow-300 border border-yellow-700',
  PCIDSS: 'bg-red-900/60 text-red-300 border border-red-700',
};

function FrameworkBadge({ tag }: { tag: string }) {
  const cls = FRAMEWORK_COLORS[tag] ?? 'bg-gray-700 text-gray-300 border border-gray-600';
  return <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${cls}`}>{tag}</span>;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function SoDMatrix({ tenantId }: Props) {
  const [dragging, setDragging] = useState(false);
  const [rawText, setRawText] = useState('');
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [parseError, setParseError] = useState('');
  const [loading, setLoading] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: sodRules } = useQuery({
    queryKey: ['sod-rules', tenantId],
    queryFn: () => getSoDRules(tenantId),
  });

  const { data: existingViolations } = useQuery({
    queryKey: ['sod-violations', tenantId],
    queryFn: () => getSoDViolations(tenantId),
  });

  const { data: sodSummary } = useQuery({
    queryKey: ['sod-summary', tenantId],
    queryFn: () => getSoDSummary(tenantId),
  });

  const processText = (text: string) => {
    setRawText(text);
    setParseError('');
    try {
      const trimmed = text.trim();
      let parsed: UserRecord[];
      if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
        const j = JSON.parse(trimmed);
        parsed = Array.isArray(j) ? j : [j];
      } else {
        parsed = parseCsv(trimmed);
      }
      if (parsed.length === 0) { setParseError('No records found.'); return; }
      if (!parsed[0].user_id) { setParseError('Missing required field: user_id'); return; }
      setUsers(parsed);
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

  const scan = async () => {
    if (users.length === 0) return;
    setLoading(true);
    setError('');
    try {
      const res = await runAnalysis(tenantId, 'sod', users);
      setScanResult(res);
    } catch (e) {
      setError('Scan failed. Check the backend connection.');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  // Build violation matrix: users × rules
  const violatingFindings = scanResult?.findings ?? existingViolations?.map(v => ({
    id: v.id,
    run_id: '',
    rule_id: v.sod_rule_id,
    finding_type: 'sod_conflict',
    severity: (sodRules?.find(r => r.id === v.sod_rule_id)?.severity ?? 'high') as Severity,
    title: `SoD Violation: ${v.user_name ?? v.user_id}`,
    description: `${v.role_a_detail} + ${v.role_b_detail}`,
    entity_type: 'user',
    entity_id: v.user_id,
    entity_name: v.user_name,
    evidence: { role_a: v.role_a_detail, role_b: v.role_b_detail, dept: v.department } as Record<string, unknown>,
    risk_score: v.risk_score,
    status: 'open' as const,
    detected_at: v.detected_at,
  })) ?? [];

  const matrixUsers = [...new Set(violatingFindings.map(f => f.entity_id).filter(Boolean))] as string[];
  const matrixRules = sodRules ?? [];

  const getCell = (userId: string, ruleId: string): Severity | null => {
    const f = violatingFindings.find(vf => vf.entity_id === userId && vf.rule_id === ruleId);
    return f ? f.severity : null;
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Segregation of Duties</h2>
        <p className="text-gray-400 text-sm mt-1">Identify users with conflicting access rights across financial and IT systems</p>
      </div>

      {/* SoD Rules Table */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-700">
          <h3 className="text-base font-semibold text-white flex items-center gap-2">
            <Shield size={16} className="text-indigo-400" />
            SoD Conflict Rules
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Rule Name</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Role A</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Role B</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Severity</th>
                <th className="text-left px-5 py-3 text-gray-400 font-medium">Frameworks</th>
              </tr>
            </thead>
            <tbody>
              {sodRules && sodRules.length > 0 ? sodRules.map(rule => (
                <tr key={rule.id} className="border-b border-gray-700/50 hover:bg-gray-750">
                  <td className="px-5 py-3">
                    <p className="text-gray-200 font-medium">{rule.display_name}</p>
                    <p className="text-xs text-gray-500">{rule.rule_key}</p>
                  </td>
                  <td className="px-5 py-3 text-gray-300 text-xs font-mono">{rule.role_a}</td>
                  <td className="px-5 py-3 text-gray-300 text-xs font-mono">{rule.role_b}</td>
                  <td className="px-5 py-3">
                    <span
                      className="px-2 py-0.5 rounded text-xs font-bold uppercase"
                      style={{ backgroundColor: severityColor(rule.severity) + '33', color: severityColor(rule.severity) }}
                    >
                      {rule.severity}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap gap-1">
                      {rule.framework_references.map(f => <FrameworkBadge key={f} tag={f} />)}
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="px-5 py-8 text-center text-gray-500">No rules configured</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* User Upload & Scan */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
        <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <Upload size={16} className="text-indigo-400" />
          User Access Scan
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
          <p className="text-gray-300 font-medium">Drop user-role CSV or JSON file here</p>
          <p className="text-gray-500 text-sm mt-1">or click to browse</p>
          <p className="text-gray-600 text-xs mt-3">Required fields: user_id, user_name, roles (comma-separated)</p>
          <input ref={fileRef} type="file" accept=".csv,.json" className="hidden" onChange={handleFile} />
        </div>

        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-2">Or paste data directly:</p>
          <textarea
            rows={4}
            value={rawText}
            onChange={e => processText(e.target.value)}
            placeholder={"user_id,user_name,roles\nUSR001,Jane Smith,\"AP_APPROVER,PAYMENT_PROCESSOR\"\nUSR002,John Doe,GL_PREPARER"}
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>

        {parseError && (
          <p className="mt-2 text-sm text-red-400 flex items-center gap-2">
            <AlertTriangle size={14} /> {parseError}
          </p>
        )}

        {users.length > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-sm text-green-400">{users.length} users loaded</p>
            <button
              onClick={scan}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Scanning...' : 'Scan for Violations'}
            </button>
          </div>
        )}
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </div>

      {/* Violations View */}
      {(scanResult || (existingViolations && existingViolations.length > 0)) && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Users with Violations</p>
              <p className="text-2xl font-bold text-white flex items-center gap-2">
                <Users size={18} className="text-orange-400" />
                {sodSummary?.unique_users_affected ?? matrixUsers.length}
              </p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-red-900/50">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Critical Conflicts</p>
              <p className="text-2xl font-bold text-red-400">
                {sodSummary?.by_severity?.['critical'] ?? violatingFindings.filter(f => f.severity === 'critical').length}
              </p>
            </div>
            <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">Total Violations</p>
              <p className="text-2xl font-bold text-orange-400">{sodSummary?.total ?? violatingFindings.length}</p>
            </div>
          </div>

          {/* Violation Matrix Heatmap */}
          {matrixUsers.length > 0 && matrixRules.length > 0 && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-700">
                <h3 className="text-base font-semibold text-white">Violation Matrix</h3>
              </div>
              <div className="p-4 overflow-x-auto">
                <table className="text-xs">
                  <thead>
                    <tr>
                      <th className="text-left pr-4 pb-3 text-gray-400 font-medium min-w-32">User</th>
                      {matrixRules.map(r => (
                        <th key={r.id} className="pb-3 px-2 text-gray-400 font-medium text-center" style={{ minWidth: 60 }}>
                          <span className="inline-block max-w-14 truncate text-xs">{r.rule_key}</span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {matrixUsers.map(userId => {
                      const finding = violatingFindings.find(f => f.entity_id === userId);
                      const userName = finding?.entity_name ?? userId;
                      return (
                        <tr key={userId} className="border-t border-gray-700/30">
                          <td className="pr-4 py-1.5 text-gray-300 font-medium">{userName}</td>
                          {matrixRules.map(rule => {
                            const sev = getCell(userId, rule.id);
                            return (
                              <td key={rule.id} className="px-2 py-1.5 text-center">
                                {sev ? (
                                  <div
                                    className={`w-8 h-6 rounded mx-auto flex items-center justify-center text-xs font-bold ${severityBg(sev)}`}
                                    title={sev}
                                    style={{ color: severityColor(sev) }}
                                  >
                                    {sev.charAt(0).toUpperCase()}
                                  </div>
                                ) : (
                                  <div className="w-8 h-6 rounded mx-auto bg-gray-700/30" />
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Violations Table */}
          <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-700">
              <h3 className="text-base font-semibold text-white">Violations Detail</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">User</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Email</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Dept</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Conflicting Roles</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Severity</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Risk</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Detected</th>
                  </tr>
                </thead>
                <tbody>
                  {existingViolations && existingViolations.length > 0 ? existingViolations.map(v => {
                    const rule = sodRules?.find(r => r.id === v.sod_rule_id);
                    return (
                      <tr key={v.id} className="border-b border-gray-700/50 hover:bg-gray-750">
                        <td className="px-5 py-3 text-gray-200 font-medium">{v.user_name ?? v.user_id}</td>
                        <td className="px-5 py-3 text-gray-400 text-xs">{v.user_email ?? '—'}</td>
                        <td className="px-5 py-3 text-gray-400 text-xs">{v.department ?? '—'}</td>
                        <td className="px-5 py-3 text-xs">
                          <div className="flex flex-col gap-1">
                            <span className="bg-gray-700 rounded px-1.5 py-0.5 text-gray-300 font-mono">{v.role_a_detail}</span>
                            <span className="text-gray-600 text-center">+</span>
                            <span className="bg-gray-700 rounded px-1.5 py-0.5 text-gray-300 font-mono">{v.role_b_detail}</span>
                          </div>
                          {rule && <p className="text-gray-500 mt-1">{rule.display_name}</p>}
                        </td>
                        <td className="px-5 py-3">
                          <span
                            className="px-2 py-0.5 rounded text-xs font-bold uppercase"
                            style={{ backgroundColor: severityColor(rule?.severity ?? 'high') + '33', color: severityColor(rule?.severity ?? 'high') }}
                          >
                            {rule?.severity ?? 'high'}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-gray-400">{v.risk_score?.toFixed(1) ?? '—'}</td>
                        <td className="px-5 py-3 text-gray-400">{relativeTime(v.detected_at)}</td>
                      </tr>
                    );
                  }) : violatingFindings.map(f => (
                    <tr key={f.id} className="border-b border-gray-700/50 hover:bg-gray-750">
                      <td className="px-5 py-3 text-gray-200 font-medium">{f.entity_name ?? f.entity_id}</td>
                      <td className="px-5 py-3 text-gray-400 text-xs">{String(f.evidence['email'] ?? '—')}</td>
                      <td className="px-5 py-3 text-gray-400 text-xs">{String(f.evidence['dept'] ?? '—')}</td>
                      <td className="px-5 py-3 text-xs">
                        <div className="flex flex-col gap-1">
                          <span className="bg-gray-700 rounded px-1.5 py-0.5 text-gray-300 font-mono">{String(f.evidence['role_a'] ?? '')}</span>
                          <span className="bg-gray-700 rounded px-1.5 py-0.5 text-gray-300 font-mono">{String(f.evidence['role_b'] ?? '')}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <span className="px-2 py-0.5 rounded text-xs font-bold uppercase"
                          style={{ backgroundColor: severityColor(f.severity) + '33', color: severityColor(f.severity) }}
                        >{f.severity}</span>
                      </td>
                      <td className="px-5 py-3 text-gray-400">{f.risk_score?.toFixed(1) ?? '—'}</td>
                      <td className="px-5 py-3 text-gray-400">{relativeTime(f.detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
