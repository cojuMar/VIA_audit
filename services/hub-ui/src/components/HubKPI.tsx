import { useState, useEffect, type ReactNode } from 'react';
import {
  Calendar, AlertCircle, BarChart2, ClipboardList, FileText,
} from 'lucide-react';
import RingGauge, { gaugeColor } from './RingGauge';
import type { AuthUser } from '../contexts/AuthContext';

// ── API types ────────────────────────────────────────────────────────────────

interface HubSummary {
  active_engagements: number;
  open_issues:        number;
  total_issues:       number;
  open_risks:         number;
  total_risks:        number;
  pbc_completion:     number;   // 0–1
  pbc_fulfilled:      number;
  pbc_total:          number;
  wp_progress:        number;   // 0–1
  wp_final:           number;
  wp_total:           number;
  issue_resolution:   number;   // 0–1
}

// ── Hook ────────────────────────────────────────────────────────────────────

function useHubSummary(user: AuthUser) {
  const [data,    setData]    = useState<HubSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);

    fetch('/api/dashboard/hub/summary', {
      headers: { 'X-Tenant-ID': user.tenant_id },
    })
      .then(res => {
        if (!res.ok) throw new Error(res.statusText);
        return res.json() as Promise<HubSummary>;
      })
      .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });

    return () => { cancelled = true; };
  }, [user.tenant_id]);

  return { data, loading, error };
}

// ── Tile skeleton ────────────────────────────────────────────────────────────

function TileSkeleton() {
  return (
    <div
      className="kpi-tile flex flex-col gap-3 animate-pulse"
      style={{ minHeight: 120 }}
    >
      <div className="h-3 w-24 rounded" style={{ backgroundColor: 'var(--line-strong)' }} />
      <div className="flex items-center gap-4">
        <div className="h-[72px] w-[72px] rounded-full" style={{ backgroundColor: 'var(--line-strong)' }} />
        <div className="space-y-2">
          <div className="h-6 w-12 rounded" style={{ backgroundColor: 'var(--line-strong)' }} />
          <div className="h-3 w-20 rounded" style={{ backgroundColor: 'var(--line-strong)' }} />
        </div>
      </div>
    </div>
  );
}

// ── KPI tile ─────────────────────────────────────────────────────────────────

interface KpiTileProps {
  icon:    ReactNode;
  label:   string;
  /** Primary display value (string or number) */
  value:   string | number;
  /** Sub-label beneath the primary value */
  sub?:    string;
  /** If provided, shows a ring gauge at this ratio (0–1) */
  ratio?:  number;
  /** Gauge colour override; auto-derived from ratio if omitted */
  colorOverride?: 'success' | 'warning' | 'danger' | 'info' | 'muted';
  /** Invert threshold logic (high = bad, e.g. open issues) */
  invertThreshold?: boolean;
}

function KpiTile({ icon, label, value, sub, ratio, colorOverride, invertThreshold }: KpiTileProps) {
  const color = colorOverride
    ?? (ratio !== undefined
      ? gaugeColor(ratio, { invert: invertThreshold })
      : 'info');

  const statusColor = color === 'success' ? 'var(--status-success)'
    : color === 'warning' ? 'var(--status-warning)'
    : color === 'danger'  ? 'var(--status-danger)'
    : color === 'info'    ? 'var(--status-info)'
    : 'var(--ink-muted)';

  return (
    <div className="kpi-tile flex flex-col gap-2">
      {/* Header row */}
      <div className="flex items-center gap-1.5">
        <span style={{ color: statusColor }}>{icon}</span>
        <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--ink-muted)' }}>
          {label}
        </span>
      </div>

      {/* Body */}
      <div className="flex items-center gap-4">
        {ratio !== undefined ? (
          <RingGauge
            ratio={ratio}
            size={72}
            strokeWidth={6}
            color={color}
            label={`${Math.round(ratio * 100)}%`}
          />
        ) : (
          /* Count-mode: large number, no ring */
          <div
            className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full text-2xl font-black"
            style={{
              background: `color-mix(in srgb, ${statusColor} 12%, transparent)`,
              color: statusColor,
            }}
          >
            {value}
          </div>
        )}

        <div className="min-w-0">
          {ratio !== undefined && (
            <p className="text-2xl font-black leading-none" style={{ color: 'var(--ink-primary)' }}>
              {value}
            </p>
          )}
          {sub && (
            <p className="mt-1 text-[11px] leading-snug" style={{ color: 'var(--ink-muted)' }}>
              {sub}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── HubKPI ───────────────────────────────────────────────────────────────────

interface Props {
  user: AuthUser;
}

export default function HubKPI({ user }: Props) {
  const { data, loading, error } = useHubSummary(user);

  if (error) return null;  // fail silently — KPIs are additive, not critical

  if (loading) {
    return (
      <section className="mb-8">
        <p className="section-label mb-3">Live KPIs</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => <TileSkeleton key={i} />)}
        </div>
      </section>
    );
  }

  if (!data) return null;

  const issueRatioForGauge = data.total_issues > 0
    ? (data.total_issues - data.open_issues) / data.total_issues
    : 1;

  return (
    <section className="mb-8">
      <p className="section-label mb-3">Live KPIs</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">

        {/* Active Engagements — count tile */}
        <KpiTile
          icon={<Calendar className="h-3.5 w-3.5" />}
          label="Active Engagements"
          value={data.active_engagements}
          sub="engagements in progress"
          colorOverride={data.active_engagements > 0 ? 'info' : 'muted'}
        />

        {/* Open Issues — count tile (high = bad) */}
        <KpiTile
          icon={<AlertCircle className="h-3.5 w-3.5" />}
          label="Open Issues"
          value={data.open_issues}
          sub={`of ${data.total_issues} total`}
          colorOverride={
            data.open_issues === 0 ? 'success'
            : data.open_issues <= 3 ? 'warning'
            : 'danger'
          }
        />

        {/* Open Risks — count tile */}
        <KpiTile
          icon={<BarChart2 className="h-3.5 w-3.5" />}
          label="Open Risks"
          value={data.open_risks}
          sub={`of ${data.total_risks} tracked`}
          colorOverride={
            data.open_risks === 0 ? 'success'
            : data.open_risks <= 5 ? 'warning'
            : 'danger'
          }
        />

        {/* PBC Completion — ring gauge */}
        <KpiTile
          icon={<ClipboardList className="h-3.5 w-3.5" />}
          label="PBC Completion"
          ratio={data.pbc_completion}
          value={`${data.pbc_fulfilled} / ${data.pbc_total}`}
          sub="requests fulfilled"
        />

        {/* Workpaper Progress — ring gauge */}
        <KpiTile
          icon={<FileText className="h-3.5 w-3.5" />}
          label="Workpaper Progress"
          ratio={data.wp_progress}
          value={`${data.wp_final} / ${data.wp_total}`}
          sub="workpapers finalised"
        />

      </div>
    </section>
  );
}
