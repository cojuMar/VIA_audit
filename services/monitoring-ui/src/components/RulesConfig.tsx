import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  DollarSign,
  TrendingUp,
  CreditCard,
  Users,
  Cloud,
  ChevronDown,
  ChevronRight,
  Save,
  Check,
} from 'lucide-react';
import { getRules, getTenantConfig, updateRuleConfig } from '../api';
import type { MonitoringRule, TenantRuleConfig, Severity } from '../types';

interface Props {
  tenantId: string;
}

type Category = 'payroll' | 'ap' | 'card' | 'sod' | 'cloud';

const CATEGORY_META: Record<Category, { label: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  payroll: { label: 'Payroll', icon: DollarSign },
  ap: { label: 'Accounts Payable', icon: TrendingUp },
  card: { label: 'Card Spend', icon: CreditCard },
  sod: { label: 'Segregation of Duties', icon: Users },
  cloud: { label: 'Cloud Configuration', icon: Cloud },
};

function severityBadge(s: Severity) {
  const cls = {
    critical: 'bg-red-700 text-white',
    high: 'bg-orange-600 text-white',
    medium: 'bg-yellow-600 text-white',
    low: 'bg-blue-500 text-white',
    info: 'bg-gray-600 text-white',
  }[s];
  return <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${cls}`}>{s}</span>;
}

function cronToHuman(cron: string): string {
  const parts = cron.split(' ');
  if (parts.length !== 5) return cron;
  const [min, hour, dom, month, dow] = parts;
  if (min === '0' && hour === '*/1' && dom === '*' && month === '*' && dow === '*') return 'Every hour';
  if (dom === '*' && month === '*' && dow === '*') {
    if (min === '0') return `Daily at ${hour}:00`;
    return `Daily at ${hour}:${min.padStart(2, '0')}`;
  }
  if (dom === '*' && month === '*' && dow !== '*') return `Weekly on day ${dow}`;
  if (dow === '*' && month === '*') return `Monthly on day ${dom}`;
  return cron;
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface RuleCardProps {
  rule: MonitoringRule;
  config: TenantRuleConfig | undefined;
  tenantId: string;
}

function RuleCard({ rule, config, tenantId }: RuleCardProps) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [localConfig, setLocalConfig] = useState<Partial<TenantRuleConfig>>({
    is_enabled: config?.is_enabled ?? rule.is_active,
    schedule_cron: config?.schedule_cron ?? '0 2 * * *',
    config_overrides: config?.config_overrides ?? {},
  });
  const [saved, setSaved] = useState(false);

  const mutation = useMutation({
    mutationFn: () => updateRuleConfig(tenantId, rule.rule_key, localConfig),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tenant-config', tenantId] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const overrideKeys = Object.keys(localConfig.config_overrides ?? {});

  return (
    <div className="bg-gray-850 rounded-xl border border-gray-700 overflow-hidden">
      {/* Rule header */}
      <div className="p-4 flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <p className="text-sm font-semibold text-gray-100">{rule.display_name}</p>
            {severityBadge(rule.severity_default)}
          </div>
          <p className="text-xs text-gray-500 mt-1">{rule.description}</p>
          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
            <span>Last run: {relativeTime(config?.last_run_at ?? null)}</span>
            {localConfig.is_enabled && (
              <span>Schedule: {cronToHuman(localConfig.schedule_cron ?? '0 2 * * *')}</span>
            )}
            {config?.next_run_at && (
              <span>Next: {new Date(config.next_run_at).toLocaleString()}</span>
            )}
          </div>
        </div>

        {/* Toggle */}
        <button
          onClick={() => setLocalConfig(c => ({ ...c, is_enabled: !c.is_enabled }))}
          className={`relative w-11 h-6 rounded-full transition-colors flex-shrink-0 mt-1 ${
            localConfig.is_enabled ? 'bg-green-600' : 'bg-gray-600'
          }`}
          title={localConfig.is_enabled ? 'Disable rule' : 'Enable rule'}
        >
          <span
            className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform shadow ${
              localConfig.is_enabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>

        {/* Expand */}
        <button
          onClick={() => setExpanded(o => !o)}
          className="p-1 text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0 mt-0.5"
        >
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>

      {/* Expanded config */}
      {expanded && localConfig.is_enabled && (
        <div className="border-t border-gray-700 p-4 space-y-4">
          {/* Schedule */}
          <div>
            <label className="text-xs text-gray-400 block mb-1.5">Schedule (cron expression)</label>
            <div className="flex items-center gap-3">
              <input
                type="text"
                value={localConfig.schedule_cron ?? ''}
                onChange={e => setLocalConfig(c => ({ ...c, schedule_cron: e.target.value }))}
                className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-indigo-500 w-48"
                placeholder="0 2 * * *"
              />
              <span className="text-xs text-gray-500">{cronToHuman(localConfig.schedule_cron ?? '')}</span>
            </div>
          </div>

          {/* Config overrides */}
          {overrideKeys.length > 0 && (
            <div>
              <p className="text-xs text-gray-400 mb-2">Config Overrides</p>
              <div className="space-y-3">
                {overrideKeys.map(key => {
                  const val = (localConfig.config_overrides ?? {})[key];
                  const isNum = typeof val === 'number';
                  return (
                    <div key={key}>
                      <label className="text-xs text-gray-500 block mb-1 capitalize">{key.replace(/_/g, ' ')}</label>
                      {isNum ? (
                        <div className="flex items-center gap-3">
                          <input
                            type="range"
                            min={0}
                            max={100}
                            value={Number(val)}
                            onChange={e => setLocalConfig(c => ({
                              ...c,
                              config_overrides: { ...(c.config_overrides ?? {}), [key]: Number(e.target.value) }
                            }))}
                            className="w-32 accent-indigo-500"
                          />
                          <span className="text-xs text-gray-300 w-8">{Number(val)}</span>
                        </div>
                      ) : (
                        <input
                          type="text"
                          value={String(val)}
                          onChange={e => setLocalConfig(c => ({
                            ...c,
                            config_overrides: { ...(c.config_overrides ?? {}), [key]: e.target.value }
                          }))}
                          className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-indigo-500 w-48"
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Save button */}
          <div className="flex justify-end">
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                saved
                  ? 'bg-green-700 text-white'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50'
              }`}
            >
              {saved ? <><Check size={14} />Saved</> : <><Save size={14} />{mutation.isPending ? 'Saving...' : 'Save'}</>}
            </button>
          </div>
        </div>
      )}

      {/* Disabled state quick save */}
      {!localConfig.is_enabled && (
        <div className="border-t border-gray-700/50 px-4 py-2 flex justify-end">
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
          >
            {saved ? <><Check size={12} />Saved</> : <><Save size={12} />Save</>}
          </button>
        </div>
      )}
    </div>
  );
}

export default function RulesConfig({ tenantId }: Props) {
  const { data: rules, isLoading: rulesLoading } = useQuery({
    queryKey: ['rules', tenantId],
    queryFn: () => getRules(tenantId),
  });

  const { data: tenantConfig } = useQuery({
    queryKey: ['tenant-config', tenantId],
    queryFn: () => getTenantConfig(tenantId),
  });

  const categories: Category[] = ['payroll', 'ap', 'card', 'sod', 'cloud'];

  const rulesByCategory = (cat: Category) => rules?.filter(r => r.category === cat) ?? [];
  const enabledCount = (cat: Category) =>
    rulesByCategory(cat).filter(r => tenantConfig?.find(c => c.rule_key === r.rule_key)?.is_enabled ?? r.is_active).length;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-bold text-white">Rules Configuration</h2>
        <p className="text-gray-400 text-sm mt-1">Enable, schedule, and tune monitoring rules per category</p>
      </div>

      {rulesLoading ? (
        <div className="text-center text-gray-500 py-12">Loading rules...</div>
      ) : (
        categories.map(cat => {
          const meta = CATEGORY_META[cat];
          const Icon = meta.icon;
          const catRules = rulesByCategory(cat);
          if (catRules.length === 0) return null;
          const enabled = enabledCount(cat);

          return (
            <div key={cat} className="space-y-3">
              {/* Category Header */}
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-gray-800 border border-gray-700">
                  <Icon size={18} className="text-indigo-400" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">{meta.label}</h3>
                  <p className="text-xs text-gray-500">{enabled}/{catRules.length} rules enabled</p>
                </div>
                <div className="flex-1 h-1 rounded bg-gray-700 ml-2 overflow-hidden">
                  <div
                    className="h-full rounded bg-indigo-600 transition-all"
                    style={{ width: catRules.length > 0 ? `${(enabled / catRules.length) * 100}%` : '0%' }}
                  />
                </div>
              </div>

              {/* Rule cards */}
              <div className="space-y-2 pl-0">
                {catRules.map(rule => (
                  <RuleCard
                    key={rule.id}
                    rule={rule}
                    config={tenantConfig?.find(c => c.rule_key === rule.rule_key)}
                    tenantId={tenantId}
                  />
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
