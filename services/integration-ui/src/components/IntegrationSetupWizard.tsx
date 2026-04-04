import { useState, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { X, Copy, Check, ChevronRight, ChevronLeft, Plus, Trash2 } from 'lucide-react';
import { getFieldMappingTemplates, createIntegration } from '../api';
import type { ConnectorDefinition, FieldMappingTemplate } from '../types';

interface Props {
  connector: ConnectorDefinition;
  tenantId: string;
  onSuccess: () => void;
  onClose: () => void;
}

const SCHEDULE_PRESETS = [
  { label: 'Every 15 min', value: '*/15 * * * *' },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Daily', value: '0 0 * * *' },
  { label: 'Weekly', value: '0 0 * * 0' },
  { label: 'Custom…', value: 'custom' },
];

interface CustomMapping {
  data_type: string;
  source_field: string;
  target_field: string;
  transform_fn: string;
}

function useCopy() {
  const [copied, setCopied] = useState(false);
  const copy = useCallback((text: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, []);
  return { copied, copy };
}

function CopyButton({ text }: { text: string }) {
  const { copied, copy } = useCopy();
  return (
    <button
      onClick={() => copy(text)}
      className="p-1.5 text-gray-400 hover:text-white transition-colors"
      title="Copy"
    >
      {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
    </button>
  );
}

// Step 1: Auth fields per auth type
function AuthFields({
  authType,
  authConfig,
  onChange,
}: {
  authType: ConnectorDefinition['auth_type'];
  authConfig: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  const field = (key: string, label: string, placeholder = '', type = 'text', required = true) => (
    <div key={key}>
      <label className="block text-xs font-medium text-gray-300 mb-1">
        {label} {required && <span className="text-red-400">*</span>}
      </label>
      <input
        type={type}
        value={authConfig[key] ?? ''}
        onChange={(e) => onChange(key, e.target.value)}
        placeholder={placeholder}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
      />
    </div>
  );

  if (authType === 'oauth2') {
    return (
      <div className="space-y-3">
        <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-lg p-3 text-xs text-indigo-300">
          <p className="font-medium mb-1">OAuth 2.0 Setup</p>
          <p>Register your application and obtain client credentials from your provider's developer console. Set the redirect URI to the value provided below.</p>
        </div>
        {field('client_id', 'Client ID', 'your-client-id')}
        {field('client_secret', 'Client Secret', 'your-client-secret', 'password')}
        {field('redirect_uri', 'Redirect URI', 'https://your-app/oauth/callback', 'text', false)}
      </div>
    );
  }

  if (authType === 'api_key') {
    return (
      <div className="space-y-3">
        {field('api_key', 'API Key', 'sk-…')}
        {field('base_url', 'Base URL (optional)', 'https://api.example.com', 'text', false)}
      </div>
    );
  }

  if (authType === 'basic') {
    return (
      <div className="space-y-3">
        {field('username', 'Username', 'username')}
        {field('password', 'Password', '••••••••', 'password')}
      </div>
    );
  }

  if (authType === 'service_account') {
    return (
      <div className="space-y-3">
        <label className="block text-xs font-medium text-gray-300 mb-1">
          Service Account JSON <span className="text-red-400">*</span>
        </label>
        <textarea
          value={authConfig['service_account_json'] ?? ''}
          onChange={(e) => onChange('service_account_json', e.target.value)}
          placeholder='{"type":"service_account","project_id":"…"}'
          rows={6}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
        />
      </div>
    );
  }

  if (authType === 'webhook') {
    const webhookUrl = authConfig['webhook_url'] ?? 'Generated after save';
    const webhookSecret = authConfig['webhook_secret'] ?? 'Generated after save';
    return (
      <div className="space-y-3">
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3 text-xs text-purple-300">
          <p className="font-medium mb-1">Webhook Setup</p>
          <p>A unique webhook URL and secret will be generated after you save this integration. Configure your external system to send events to that URL.</p>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-1">Webhook URL</label>
          <div className="flex items-center bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 gap-2">
            <span className="text-sm text-gray-400 flex-1 font-mono truncate">{webhookUrl}</span>
            <CopyButton text={webhookUrl} />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-300 mb-1">Webhook Secret</label>
          <div className="flex items-center bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 gap-2">
            <span className="text-sm text-gray-400 flex-1 font-mono truncate">{webhookSecret}</span>
            <CopyButton text={webhookSecret} />
          </div>
        </div>
      </div>
    );
  }

  // none
  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3 text-sm text-gray-400">
      No authentication required for this connector.
    </div>
  );
}

export default function IntegrationSetupWizard({ connector, tenantId, onSuccess, onClose }: Props) {
  const [step, setStep] = useState(1);
  const [integrationName, setIntegrationName] = useState(connector.display_name);
  const [schedulePreset, setSchedulePreset] = useState(SCHEDULE_PRESETS[1].value);
  const [customCron, setCustomCron] = useState('');
  const [authConfig, setAuthConfig] = useState<Record<string, string>>({});
  const [selectedDataTypes, setSelectedDataTypes] = useState<Set<string>>(
    new Set(connector.supported_data_types)
  );
  const [customMappings, setCustomMappings] = useState<CustomMapping[]>([]);
  const [newMapping, setNewMapping] = useState<Partial<CustomMapping>>({ data_type: connector.supported_data_types[0] ?? '' });

  const { data: templatesByType = {} } = useQuery({
    queryKey: ['field-mappings', connector.connector_key],
    queryFn: async () => {
      const results: Record<string, FieldMappingTemplate[]> = {};
      await Promise.all(
        connector.supported_data_types.map(async (dt) => {
          try {
            results[dt] = await getFieldMappingTemplates(tenantId, connector.connector_key, dt);
          } catch {
            results[dt] = [];
          }
        })
      );
      return results;
    },
    enabled: step === 3,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createIntegration(tenantId, {
        connector_id: connector.id,
        integration_name: integrationName,
        sync_schedule: schedulePreset === 'custom' ? customCron : schedulePreset,
        auth_config: authConfig as Record<string, unknown>,
        selected_data_types: Array.from(selectedDataTypes),
        field_mappings: customMappings.map((m) => ({
          data_type: m.data_type,
          source_field: m.source_field,
          target_field: m.target_field,
          transform_fn: m.transform_fn || null,
        })),
      }),
    onSuccess: () => onSuccess(),
  });

  const handleAuthChange = (key: string, value: string) => {
    setAuthConfig((prev) => ({ ...prev, [key]: value }));
  };

  const toggleDataType = (dt: string) => {
    setSelectedDataTypes((prev) => {
      const next = new Set(prev);
      if (next.has(dt)) next.delete(dt);
      else next.add(dt);
      return next;
    });
  };

  const addCustomMapping = () => {
    if (newMapping.data_type && newMapping.source_field && newMapping.target_field) {
      setCustomMappings((prev) => [
        ...prev,
        {
          data_type: newMapping.data_type!,
          source_field: newMapping.source_field!,
          target_field: newMapping.target_field!,
          transform_fn: newMapping.transform_fn ?? '',
        },
      ]);
      setNewMapping({ data_type: connector.supported_data_types[0] ?? '' });
    }
  };

  const removeCustomMapping = (idx: number) => {
    setCustomMappings((prev) => prev.filter((_, i) => i !== idx));
  };

  const useDefaults = (dataType: string) => {
    const templates = templatesByType[dataType] ?? [];
    const deduped = templates.filter(
      (t) =>
        !customMappings.some(
          (cm) => cm.data_type === t.data_type && cm.source_field === t.source_field
        )
    );
    setCustomMappings((prev) => [
      ...prev,
      ...deduped.map((t) => ({
        data_type: t.data_type,
        source_field: t.source_field,
        target_field: t.target_field,
        transform_fn: t.transform_fn ?? '',
      })),
    ]);
  };

  const STEPS = ['Authentication', 'Data Selection', 'Field Mappings'];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[92vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-600 w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm">
              {connector.display_name.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h2 className="text-base font-bold text-white">Set Up {connector.display_name}</h2>
              <p className="text-xs text-gray-400">Step {step} of 3 — {STEPS[step - 1]}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-800"
          >
            <X size={20} />
          </button>
        </div>

        {/* Step indicators */}
        <div className="flex px-6 py-3 gap-2 border-b border-gray-800">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-2 flex-1">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                  i + 1 < step
                    ? 'bg-green-500 text-white'
                    : i + 1 === step
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-700 text-gray-400'
                }`}
              >
                {i + 1 < step ? <Check size={12} /> : i + 1}
              </div>
              <span className={`text-xs font-medium truncate ${i + 1 === step ? 'text-white' : 'text-gray-500'}`}>
                {label}
              </span>
              {i < STEPS.length - 1 && <ChevronRight size={14} className="text-gray-600 ml-auto shrink-0" />}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-5">
          {/* Step 1 */}
          {step === 1 && (
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  Integration Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={integrationName}
                  onChange={(e) => setIntegrationName(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">Sync Schedule</label>
                <select
                  value={schedulePreset}
                  onChange={(e) => setSchedulePreset(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
                >
                  {SCHEDULE_PRESETS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
                {schedulePreset === 'custom' && (
                  <input
                    type="text"
                    value={customCron}
                    onChange={(e) => setCustomCron(e.target.value)}
                    placeholder="* * * * *"
                    className="mt-2 w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-indigo-500 transition-colors"
                  />
                )}
              </div>

              <div>
                <h3 className="text-xs font-medium text-gray-300 mb-3">Authentication</h3>
                <AuthFields
                  authType={connector.auth_type}
                  authConfig={authConfig}
                  onChange={handleAuthChange}
                />
              </div>
            </div>
          )}

          {/* Step 2 */}
          {step === 2 && (
            <div className="space-y-3">
              <p className="text-sm text-gray-400 mb-4">
                Select the data types you want to sync from {connector.display_name}.
              </p>
              {connector.supported_data_types.length === 0 ? (
                <p className="text-sm text-gray-500">No data types defined for this connector.</p>
              ) : (
                connector.supported_data_types.map((dt) => (
                  <label
                    key={dt}
                    className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                      selectedDataTypes.has(dt)
                        ? 'bg-indigo-500/10 border-indigo-500/40'
                        : 'bg-gray-800 border-gray-700 hover:border-gray-600'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedDataTypes.has(dt)}
                      onChange={() => toggleDataType(dt)}
                      className="accent-indigo-600"
                    />
                    <div>
                      <p className="text-sm font-medium text-white">{dt}</p>
                      <p className="text-xs text-gray-500 capitalize">
                        {dt.replace(/_/g, ' ')} records from {connector.display_name}
                      </p>
                    </div>
                  </label>
                ))
              )}
            </div>
          )}

          {/* Step 3 */}
          {step === 3 && (
            <div className="space-y-6">
              <p className="text-sm text-gray-400">
                Configure field mappings for each selected data type. Source fields map to normalized target fields in Aegis.
              </p>

              {Array.from(selectedDataTypes).map((dt) => {
                const templates = templatesByType[dt] ?? [];
                const dtMappings = customMappings.filter((m) => m.data_type === dt);
                return (
                  <div key={dt} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold text-white capitalize">{dt.replace(/_/g, ' ')}</h4>
                      {templates.length > 0 && (
                        <button
                          onClick={() => useDefaults(dt)}
                          className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          Use Defaults
                        </button>
                      )}
                    </div>

                    {/* Existing templates */}
                    {templates.length > 0 && (
                      <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-gray-700">
                              <th className="text-left px-3 py-2 text-gray-400 font-medium">Source Field</th>
                              <th className="px-2 py-2 text-gray-600">→</th>
                              <th className="text-left px-3 py-2 text-gray-400 font-medium">Target Field</th>
                              <th className="text-left px-3 py-2 text-gray-400 font-medium">Transform</th>
                              <th className="text-center px-3 py-2 text-gray-400 font-medium">Req</th>
                            </tr>
                          </thead>
                          <tbody>
                            {templates.map((t, idx) => (
                              <tr key={idx} className="border-b border-gray-700/50 last:border-0">
                                <td className="px-3 py-2 text-gray-300 font-mono">{t.source_field}</td>
                                <td className="px-2 py-2 text-gray-600 text-center">→</td>
                                <td className="px-3 py-2 text-gray-300 font-mono">{t.target_field}</td>
                                <td className="px-3 py-2 text-gray-500 font-mono">
                                  {t.transform_fn ?? <span className="text-gray-700">—</span>}
                                </td>
                                <td className="px-3 py-2 text-center">
                                  {t.is_required ? (
                                    <span className="text-red-400 font-bold">*</span>
                                  ) : (
                                    <span className="text-gray-700">—</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Custom mappings for this type */}
                    {dtMappings.length > 0 && (
                      <div className="space-y-1">
                        {dtMappings.map((m, idx) => (
                          <div key={idx} className="flex items-center gap-2 bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2">
                            <span className="text-xs text-gray-300 font-mono flex-1">{m.source_field}</span>
                            <span className="text-xs text-gray-600">→</span>
                            <span className="text-xs text-gray-300 font-mono flex-1">{m.target_field}</span>
                            {m.transform_fn && (
                              <span className="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded font-mono">
                                {m.transform_fn}
                              </span>
                            )}
                            <button
                              onClick={() => removeCustomMapping(customMappings.indexOf(m))}
                              className="text-gray-500 hover:text-red-400 transition-colors"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Add custom mapping */}
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        placeholder="source_field"
                        value={newMapping.data_type === dt ? (newMapping.source_field ?? '') : ''}
                        onChange={(e) => setNewMapping({ ...newMapping, data_type: dt, source_field: e.target.value })}
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                      <span className="text-gray-600 text-xs">→</span>
                      <input
                        type="text"
                        placeholder="target_field"
                        value={newMapping.data_type === dt ? (newMapping.target_field ?? '') : ''}
                        onChange={(e) => setNewMapping({ ...newMapping, data_type: dt, target_field: e.target.value })}
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                      <button
                        onClick={() => {
                          if (newMapping.data_type === dt) addCustomMapping();
                          else setNewMapping({ data_type: dt });
                        }}
                        className="text-indigo-400 hover:text-indigo-300 transition-colors p-1"
                        title="Add mapping"
                      >
                        <Plus size={16} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer nav */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-800">
          <button
            onClick={() => (step === 1 ? onClose() : setStep((s) => s - 1))}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors px-3 py-2 rounded-lg hover:bg-gray-800"
          >
            <ChevronLeft size={16} />
            {step === 1 ? 'Cancel' : 'Back'}
          </button>

          {createMutation.isError && (
            <p className="text-xs text-red-400">Failed to create. Please try again.</p>
          )}

          {step < 3 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              disabled={step === 1 && !integrationName.trim()}
              className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              Continue
              <ChevronRight size={16} />
            </button>
          ) : (
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || selectedDataTypes.size === 0}
              className="flex items-center gap-1.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {createMutation.isPending ? 'Creating…' : 'Create Integration'}
              <Check size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
