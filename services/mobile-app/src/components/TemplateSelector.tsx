import { useState, useEffect, useRef, type ChangeEvent } from 'react';
import {
  Search,
  Clock,
  Camera,
  MapPin,
  PenLine,
  ChevronRight,
  Loader2,
  Building2,
  Play,
  X,
} from 'lucide-react';
import { getAllTemplates, saveAudit } from '../offline/db';
import { fetchTemplates, createAudit } from '../api';
import { saveTemplate } from '../offline/db';
import { useOnlineStatus } from '../offline/sync';
import type { AuditTemplate, FieldAudit } from '../types';

interface TemplateSelectorProps {
  tenantId: string;
  auditorEmail: string;
  onAuditCreated: (audit: FieldAudit) => void;
  onBack: () => void;
}

export default function TemplateSelector({
  tenantId: _tenantId,
  auditorEmail,
  onAuditCreated,
  onBack,
}: TemplateSelectorProps) {
  const isOnline = useOnlineStatus();

  const [templates, setTemplates] = useState<AuditTemplate[]>([]);
  const [filtered, setFiltered] = useState<AuditTemplate[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<AuditTemplate | null>(null);

  // Location form
  const [locationName, setLocationName] = useState('');
  const [locationAddress, setLocationAddress] = useState('');
  const [gpsCapturing, setGpsCapturing] = useState(false);
  const [gpsCoords, setGpsCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        // Load from IndexedDB first
        let tpls = await getAllTemplates();

        // Refresh from server if online
        if (isOnline) {
          try {
            const serverTpls: AuditTemplate[] = await fetchTemplates();
            for (const tpl of serverTpls) {
              await saveTemplate(tpl);
            }
            tpls = serverTpls;
          } catch {
            // Use cached
          }
        }

        setTemplates(tpls);
        setFiltered(tpls);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [isOnline]);

  useEffect(() => {
    const q = search.toLowerCase();
    if (!q) {
      setFiltered(templates);
      return;
    }
    setFiltered(
      templates.filter(
        (t) =>
          t.display_name.toLowerCase().includes(q) ||
          t.description?.toLowerCase().includes(q) ||
          t.template_key?.toLowerCase().includes(q)
      )
    );
  }, [search, templates]);

  const captureGps = () => {
    if (!navigator.geolocation) {
      setGpsError('Geolocation not supported');
      return;
    }
    setGpsCapturing(true);
    setGpsError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGpsCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setGpsCapturing(false);
      },
      (err) => {
        setGpsError(err.message);
        setGpsCapturing(false);
      },
      { enableHighAccuracy: true, timeout: 15000 }
    );
  };

  const handleStartAudit = async () => {
    if (!selected || !locationName.trim()) return;
    setCreating(true);

    const auditId = crypto.randomUUID();
    const now = new Date().toISOString();

    const newAudit: FieldAudit = {
      id: auditId,
      template_id: selected.id,
      auditor_email: auditorEmail,
      location_name: locationName.trim(),
      status: 'in_progress',
      started_at: now,
      total_findings: 0,
      gps_latitude: gpsCoords?.lat,
      gps_longitude: gpsCoords?.lon,
      _localOnly: true,
      _pendingSync: true,
    };

    // Save locally first (offline-first)
    await saveAudit(newAudit);

    // Try server
    if (isOnline) {
      try {
        const serverAudit = await createAudit({
          id: auditId,
          template_id: selected.id,
          auditor_email: auditorEmail,
          location_name: locationName.trim(),
          status: 'in_progress',
          started_at: now,
          gps_latitude: gpsCoords?.lat,
          gps_longitude: gpsCoords?.lon,
        });
        await saveAudit({ ...serverAudit, _localOnly: false, _pendingSync: false });
        onAuditCreated({ ...serverAudit, _localOnly: false, _pendingSync: false });
      } catch {
        // Use local
        onAuditCreated(newAudit);
      }
    } else {
      onAuditCreated(newAudit);
    }

    setCreating(false);
  };

  // ── Location form overlay ─────────────────────────────────────────────────
  if (selected) {
    return (
      <div className="min-h-screen bg-gray-50 pb-safe">
        <header className="bg-white border-b border-gray-200 px-4 py-4 flex items-center gap-3">
          <button onClick={() => setSelected(null)} className="tap-target p-1 -ml-1">
            <X size={24} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-bold text-gray-900 truncate">{selected.display_name}</h1>
            <p className="text-sm text-gray-500">Set location details</p>
          </div>
        </header>

        <div className="p-4 space-y-4">
          {/* Template summary card */}
          <div className="card bg-blue-50 border-blue-100">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center text-xl">
                {selected.icon ?? '📋'}
              </div>
              <div>
                <p className="font-semibold text-blue-900">{selected.display_name}</p>
                <p className="text-xs text-blue-600">
                  {selected.question_count} questions · ~{selected.estimated_duration_minutes} min
                </p>
              </div>
            </div>
            <div className="flex gap-2 flex-wrap mt-3">
              {selected.requires_gps && (
                <span className="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                  <MapPin size={11} /> GPS
                </span>
              )}
              {selected.requires_photo_evidence && (
                <span className="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Camera size={11} /> Photos
                </span>
              )}
              {selected.requires_signature && (
                <span className="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                  <PenLine size={11} /> Signature
                </span>
              )}
            </div>
          </div>

          {/* Location name */}
          <div>
            <label className="label-text flex items-center gap-1">
              <Building2 size={13} />
              Location Name *
            </label>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. Warehouse A, Floor 2"
              value={locationName}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setLocationName(e.target.value)}
              autoFocus
            />
          </div>

          {/* Address */}
          <div>
            <label className="label-text">Address (optional)</label>
            <input
              type="text"
              className="input-field"
              placeholder="123 Main St, City, State"
              value={locationAddress}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setLocationAddress(e.target.value)}
            />
          </div>

          {/* GPS */}
          <div>
            <label className="label-text flex items-center gap-1">
              <MapPin size={13} />
              GPS Coordinates
            </label>
            {gpsCoords ? (
              <div className="bg-green-50 border border-green-200 rounded-xl p-3 flex items-center justify-between">
                <div className="text-sm text-green-800">
                  <p className="font-medium">Location captured</p>
                  <p className="text-xs mt-0.5 text-green-600">
                    {gpsCoords.lat.toFixed(5)}, {gpsCoords.lon.toFixed(5)}
                  </p>
                </div>
                <button
                  onClick={() => setGpsCoords(null)}
                  className="text-green-600 tap-target px-2 text-sm"
                >
                  Change
                </button>
              </div>
            ) : (
              <button
                onClick={captureGps}
                disabled={gpsCapturing}
                className="btn-secondary w-full gap-2"
              >
                {gpsCapturing ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <MapPin size={16} />
                )}
                {gpsCapturing ? 'Getting location…' : 'Capture GPS Location'}
              </button>
            )}
            {gpsError && (
              <p className="text-xs text-red-500 mt-1">{gpsError}</p>
            )}
          </div>

          {/* Start button */}
          <button
            onClick={handleStartAudit}
            disabled={!locationName.trim() || creating}
            className="btn-primary w-full gap-2 py-4 text-lg mt-2"
          >
            {creating ? (
              <><Loader2 size={20} className="animate-spin" /> Starting…</>
            ) : (
              <><Play size={20} /> Start Audit</>
            )}
          </button>

          {!isOnline && (
            <p className="text-xs text-amber-600 text-center">
              Offline mode: audit will sync when you reconnect
            </p>
          )}
        </div>
      </div>
    );
  }

  // ── Template list ─────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50 pb-safe">
      <header className="bg-white border-b border-gray-200 px-4 py-4 flex items-center gap-3">
        <button onClick={onBack} className="tap-target p-1 -ml-1">
          <X size={24} />
        </button>
        <h1 className="font-bold text-gray-900 flex-1">Start New Audit</h1>
      </header>

      {/* Search */}
      <div className="px-4 pt-4 pb-2">
        <div className="relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            ref={searchRef}
            type="text"
            className="input-field pl-10"
            placeholder="Search templates…"
            value={search}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 tap-target p-1"
            >
              <X size={14} className="text-gray-400" />
            </button>
          )}
        </div>
      </div>

      {/* Template list */}
      <div className="px-4 py-2 space-y-3">
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card animate-pulse h-24 bg-gray-100" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="card text-center py-10 text-gray-500">
            <Search size={32} className="mx-auto mb-2 text-gray-300" />
            <p className="font-medium">
              {search ? 'No templates match your search' : 'No templates available'}
            </p>
            {!isOnline && (
              <p className="text-sm mt-1 text-amber-600">
                Go online to download templates
              </p>
            )}
          </div>
        ) : (
          filtered.map((tpl) => (
            <TemplateCard key={tpl.id} template={tpl} onSelect={() => setSelected(tpl)} />
          ))
        )}
      </div>
    </div>
  );
}

function TemplateCard({
  template,
  onSelect,
}: {
  template: AuditTemplate;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className="card w-full text-left tap-target active:bg-gray-50"
    >
      <div className="flex items-start gap-3">
        <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center text-2xl flex-shrink-0">
          {getTemplateIcon(template)}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 truncate">{template.display_name}</p>
          {template.description && (
            <p className="text-sm text-gray-500 truncate mt-0.5">{template.description}</p>
          )}
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <Clock size={11} />
              {template.estimated_duration_minutes} min
            </span>
            <span className="flex items-center gap-1 text-xs text-gray-500">
              ~{template.question_count} questions
            </span>
          </div>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            {template.requires_gps && (
              <span className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                <MapPin size={10} /> GPS
              </span>
            )}
            {template.requires_photo_evidence && (
              <span className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                <Camera size={10} /> Photo
              </span>
            )}
            {template.requires_signature && (
              <span className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                <PenLine size={10} /> Sign
              </span>
            )}
          </div>
        </div>
        <ChevronRight size={18} className="text-gray-400 flex-shrink-0 mt-2" />
      </div>
    </button>
  );
}

function getTemplateIcon(template: AuditTemplate): string {
  const key = (template.template_key ?? '').toLowerCase();
  if (key.includes('fire') || key.includes('safety')) return '🔥';
  if (key.includes('food') || key.includes('kitchen')) return '🍽️';
  if (key.includes('security')) return '🔒';
  if (key.includes('health')) return '🏥';
  if (key.includes('env') || key.includes('environ')) return '🌿';
  if (key.includes('it') || key.includes('tech')) return '💻';
  if (key.includes('finance') || key.includes('financial')) return '💰';
  if (key.includes('hr') || key.includes('people')) return '👥';
  return '📋';
}
