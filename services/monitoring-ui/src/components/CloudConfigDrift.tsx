import { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Upload, FileText, AlertTriangle, Cloud, Shield, Lock } from 'lucide-react';
import { getCloudSnapshots, getCloudSummary, runAnalysis } from '../api';
import type { MonitoringFinding, Severity } from '../types';

interface Props {
  tenantId: string;
}

interface CloudResource {
  provider: 'aws' | 'gcp' | 'azure';
  resource_type: string;
  resource_id: string;
  resource_name?: string;
  region?: string;
  config: Record<string, unknown>;
}

interface AnalysisResult {
  run_id: string;
  findings_count: number;
  findings: MonitoringFinding[];
}

interface CloudSnapshot {
  id: string;
  created_at: string;
  provider: string;
  findings_count?: number;
  [key: string]: unknown;
}

type Provider = 'aws' | 'gcp' | 'azure';

const EXAMPLE_CONFIGS: Record<Provider, string> = {
  aws: JSON.stringify([
    {
      provider: 'aws',
      resource_type: 's3_bucket',
      resource_id: 'my-bucket-prod',
      resource_name: 'my-bucket-prod',
      region: 'us-east-1',
      config: { public_access_blocked: false, versioning: true, encryption: 'AES256' }
    },
    {
      provider: 'aws',
      resource_type: 'security_group',
      resource_id: 'sg-12345678',
      resource_name: 'web-sg',
      region: 'us-east-1',
      config: { inbound_rules: [{ port: 22, protocol: 'tcp', cidr: '0.0.0.0/0' }] }
    }
  ], null, 2),
  gcp: JSON.stringify([
    {
      provider: 'gcp',
      resource_type: 'storage_bucket',
      resource_id: 'projects/my-proj/buckets/my-bucket',
      resource_name: 'my-bucket',
      config: { iam_public: true, uniform_bucket_level_access: false }
    }
  ], null, 2),
  azure: JSON.stringify([
    {
      provider: 'azure',
      resource_type: 'storage_account',
      resource_id: '/subscriptions/xxx/resourceGroups/rg1/providers/Microsoft.Storage/storageAccounts/mystorage',
      resource_name: 'mystorage',
      region: 'eastus',
      config: { public_blob_access: true, https_only: false, mfa_enabled: false }
    }
  ], null, 2),
};

function severityColor(s: Severity): string {
  return { critical: '#ef4444', high: '#f97316', medium: '#eab308', low: '#3b82f6', info: '#6b7280' }[s] ?? '#6b7280';
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function issueTypeLabel(findingType: string): string {
  const map: Record<string, string> = {
    cloud_s3_public: 'S3 Public Access',
    cloud_sg_open: 'Open Security Group',
    cloud_mfa_disabled: 'MFA Disabled',
    cloud_encryption_off: 'Encryption Off',
    cloud_logging_off: 'Logging Disabled',
    cloud_public_bucket: 'Public Bucket',
  };
  return map[findingType] ?? findingType.replace(/^cloud_/, '').replace(/_/g, ' ');
}

export default function CloudConfigDrift({ tenantId }: Props) {
  const [dragging, setDragging] = useState(false);
  const [rawText, setRawText] = useState('');
  const [resources, setResources] = useState<CloudResource[]>([]);
  const [parseError, setParseError] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<Provider>('aws');
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: snapshots } = useQuery({
    queryKey: ['cloud-snapshots', tenantId],
    queryFn: () => getCloudSnapshots(tenantId),
  });

  const { data: cloudSummary } = useQuery({
    queryKey: ['cloud-summary', tenantId],
    queryFn: () => getCloudSummary(tenantId),
  });

  const processText = (text: string) => {
    setRawText(text);
    setParseError('');
    try {
      const trimmed = text.trim();
      if (!trimmed) return;
      const j = JSON.parse(trimmed);
      const parsed: CloudResource[] = Array.isArray(j) ? j : [j];
      if (parsed.length === 0) { setParseError('No resources found.'); return; }
      setResources(parsed);
    } catch {
      setParseError('Failed to parse JSON. Please check the format.');
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

  const checkConfig = async () => {
    if (resources.length === 0) return;
    setLoading(true);
    setError('');
    try {
      const res = await runAnalysis(tenantId, 'cloud-config', resources);
      setResult(res);
    } catch (e) {
      setError('Analysis failed. Check the backend connection.');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const findings = result?.findings ?? [];

  // Provider breakdown
  const providerData = [
    { name: 'AWS', count: findings.filter(f => String(f.evidence['provider'] ?? '').toLowerCase() === 'aws').length, fill: '#f97316' },
    { name: 'GCP', count: findings.filter(f => String(f.evidence['provider'] ?? '').toLowerCase() === 'gcp').length, fill: '#3b82f6' },
    { name: 'Azure', count: findings.filter(f => String(f.evidence['provider'] ?? '').toLowerCase() === 'azure').length, fill: '#8b5cf6' },
  ].filter(p => p.count > 0);

  // Issue type breakdown
  const typeMap: Record<string, number> = {};
  findings.forEach(f => {
    typeMap[f.finding_type] = (typeMap[f.finding_type] ?? 0) + 1;
  });
  const typeData = Object.entries(typeMap).map(([k, v]) => ({ name: issueTypeLabel(k), count: v }));

  // Historical snapshots
  const typedSnapshots = (snapshots ?? []) as CloudSnapshot[];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Cloud Configuration Drift</h2>
        <p className="text-gray-400 text-sm mt-1">Detect misconfigurations in AWS, GCP, and Azure resources</p>
      </div>

      {/* Upload Panel */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
        <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <Upload size={16} className="text-indigo-400" />
          Submit Cloud Configuration
        </h3>

        {/* Provider example tabs */}
        <div className="mb-4">
          <div className="flex gap-1 border-b border-gray-700 mb-3">
            {(['aws', 'gcp', 'azure'] as Provider[]).map(p => (
              <button
                key={p}
                onClick={() => setActiveTab(p)}
                className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
                  activeTab === p ? 'border-indigo-500 text-indigo-400' : 'border-transparent text-gray-400 hover:text-gray-300'
                }`}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="relative">
            <pre className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-x-auto max-h-40 scrollbar-thin">
              {EXAMPLE_CONFIGS[activeTab]}
            </pre>
            <button
              onClick={() => processText(EXAMPLE_CONFIGS[activeTab])}
              className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
            >
              Use Example
            </button>
          </div>
        </div>

        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragging ? 'border-indigo-500 bg-indigo-900/20' : 'border-gray-600 hover:border-gray-500'
          }`}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <Cloud size={32} className="mx-auto text-gray-500 mb-3" />
          <p className="text-gray-300 font-medium">Drop JSON config file here</p>
          <p className="text-gray-500 text-sm mt-1">or click to browse</p>
          <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleFile} />
        </div>

        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-2">Or paste JSON directly:</p>
          <textarea
            rows={6}
            value={rawText}
            onChange={e => processText(e.target.value)}
            placeholder="Paste cloud resource configuration JSON..."
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>

        {parseError && (
          <p className="mt-2 text-sm text-red-400 flex items-center gap-2">
            <AlertTriangle size={14} /> {parseError}
          </p>
        )}

        {resources.length > 0 && (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-sm text-green-400">{resources.length} resources loaded</p>
            <button
              onClick={checkConfig}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Checking...' : 'Check Config'}
            </button>
          </div>
        )}
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      </div>

      {/* Issues Overview */}
      {result && findings.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Provider Breakdown */}
            {providerData.length > 0 && (
              <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h3 className="text-base font-semibold text-white mb-4">Issues by Provider</h3>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={providerData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                    />
                    <Bar dataKey="count" name="Issues" radius={[4, 4, 0, 0]}>
                      {providerData.map((entry, index) => (
                        <rect key={index} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Issue Type Breakdown */}
            {typeData.length > 0 && (
              <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
                <h3 className="text-base font-semibold text-white mb-4">Issues by Type</h3>
                <div className="space-y-2">
                  {typeData.sort((a, b) => b.count - a.count).map(item => (
                    <div key={item.name} className="flex items-center gap-3">
                      <div className="flex-1 text-sm text-gray-300">{item.name}</div>
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-2 rounded bg-gray-700 overflow-hidden">
                          <div
                            className="h-full rounded bg-orange-500"
                            style={{ width: `${Math.min(100, (item.count / findings.length) * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-6 text-right">{item.count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Issues Table */}
          <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-700">
              <h3 className="text-base font-semibold text-white">Issues Found ({findings.length})</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left px-5 py-3 text-gray-400 font-medium w-28">Severity</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Resource Type</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Resource</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Region</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Issue</th>
                    <th className="text-left px-5 py-3 text-gray-400 font-medium">Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map(f => (
                    <tr key={f.id} className="border-b border-gray-700/50 hover:bg-gray-750">
                      <td className="px-5 py-3">
                        <span
                          className="px-2 py-0.5 rounded text-xs font-bold uppercase"
                          style={{ backgroundColor: severityColor(f.severity) + '33', color: severityColor(f.severity) }}
                        >
                          {f.severity}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-gray-300 text-xs font-mono">
                        {String(f.evidence['resource_type'] ?? f.entity_type ?? '—')}
                      </td>
                      <td className="px-5 py-3 text-gray-200">
                        <p className="font-medium">{f.entity_name ?? f.entity_id ?? '—'}</p>
                        <p className="text-xs text-gray-500">{String(f.evidence['provider'] ?? '').toUpperCase()}</p>
                      </td>
                      <td className="px-5 py-3 text-gray-400 text-xs">
                        {String(f.evidence['region'] ?? '—')}
                      </td>
                      <td className="px-5 py-3 text-gray-300 max-w-xs">
                        <p className="line-clamp-2 text-sm">{f.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{issueTypeLabel(f.finding_type)}</p>
                      </td>
                      <td className="px-5 py-3 text-gray-400 text-xs max-w-xs">
                        <p className="line-clamp-2">{String(f.evidence['recommendation'] ?? f.description ?? '—')}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Historical Snapshots */}
      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
          <h3 className="text-base font-semibold text-white flex items-center gap-2">
            <Shield size={16} className="text-indigo-400" />
            Historical Cloud Config Checks
          </h3>
          {Boolean(cloudSummary) && (
            <div className="flex items-center gap-4 text-sm">
              <span className="text-gray-400">
                Total issues: <span className="text-white font-semibold">
                  {(cloudSummary as Record<string, unknown>)['total_issues'] as React.ReactNode ?? '—'}
                </span>
              </span>
            </div>
          )}
        </div>
        {typedSnapshots.length > 0 ? (
          <div className="divide-y divide-gray-700/50">
            {typedSnapshots.map(snap => (
              <div key={snap.id} className="px-5 py-3 flex items-center justify-between hover:bg-gray-750">
                <div className="flex items-center gap-4">
                  <Lock size={14} className="text-gray-500" />
                  <div>
                    <p className="text-sm text-gray-200">{snap.provider?.toString().toUpperCase()} Config Snapshot</p>
                    <p className="text-xs text-gray-500">{relativeTime(snap.created_at)}</p>
                  </div>
                </div>
                {snap.findings_count !== undefined && (
                  <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                    snap.findings_count > 0 ? 'bg-orange-900/40 text-orange-300' : 'bg-green-900/40 text-green-300'
                  }`}>
                    {snap.findings_count} issues
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-gray-500">No historical snapshots</div>
        )}
      </div>
    </div>
  );
}
