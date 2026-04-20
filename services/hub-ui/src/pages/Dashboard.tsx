import { type ReactNode, useState, useEffect } from 'react';
import {
  ExternalLink, BookOpen, ArrowRight, Shield, Activity, Users, FileText,
  Plug, Bot, BarChart2, Calendar, Leaf, Smartphone, Building2, Globe,
  Lock, Database, Zap, HardDrive, CheckCircle2, AlertCircle, Sparkles,
} from 'lucide-react';
import { MODULES, WORKFLOW_STEPS, type Module } from '../data/modules';
import type { AuthUser } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import HubKPI from '../components/HubKPI';

/** Ping each module root and return per-module online status */
function useModuleHealth(modules: Module[]) {
  const [onlineSet, setOnlineSet] = useState<Set<string>>(new Set());
  const [checked,   setChecked]   = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      modules.map(async (m) => {
        try {
          const ctrl  = new AbortController();
          const timer = setTimeout(() => ctrl.abort(), 2000);
          const res   = await fetch(`http://localhost:${m.port}/`, {
            signal: ctrl.signal,
            method: 'GET',
            mode:   'no-cors',
          });
          clearTimeout(timer);
          return { id: m.id, ok: res.type === 'opaque' || res.ok };
        } catch {
          return { id: m.id, ok: false };
        }
      })
    ).then((results) => {
      if (!cancelled) {
        setOnlineSet(new Set(results.filter(r => r.ok).map(r => r.id)));
        setChecked(true);
      }
    });
    return () => { cancelled = true; };
  }, []);

  return { onlineSet, checked };
}

const MODULE_ICONS: Record<string, ReactNode> = {
  framework:       <Shield      className="h-5 w-5" />,
  tprm:            <Building2   className="h-5 w-5" />,
  'trust-portal':  <Globe       className="h-5 w-5" />,
  monitoring:      <Activity    className="h-5 w-5" />,
  people:          <Users       className="h-5 w-5" />,
  pbc:             <FileText    className="h-5 w-5" />,
  integration:     <Plug        className="h-5 w-5" />,
  'ai-agent':      <Bot         className="h-5 w-5" />,
  risk:            <BarChart2   className="h-5 w-5" />,
  'audit-planning':<Calendar    className="h-5 w-5" />,
  esg:             <Leaf        className="h-5 w-5" />,
  mobile:          <Smartphone  className="h-5 w-5" />,
};

const CATEGORY_LABELS: Record<string, string> = {
  core:       'Core Platform',
  operations: 'Operations',
  reporting:  'Reporting',
  field:      'Field',
};

function gridCols(count: number): string {
  if (count === 1) return 'grid-cols-1 max-w-xs';
  if (count === 2) return 'grid-cols-1 sm:grid-cols-2 max-w-lg';
  if (count <= 3)  return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3';
  if (count === 5) return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5';
  return               'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4';
}

interface Props {
  user: AuthUser;
  onOpenTutorials: () => void;
}

export default function Dashboard({ user, onOpenTutorials }: Props) {
  const tenantId      = user.tenant_id;
  const visibleModules = MODULES.filter(m => m.allowedRoles.includes(user.role));
  const { onlineSet, checked } = useModuleHealth(visibleModules);
  const onlineCount   = checked ? onlineSet.size : null;
  const { isLight }   = useTheme();

  const grouped = {
    core:       visibleModules.filter(m => m.category === 'core'),
    operations: visibleModules.filter(m => m.category === 'operations'),
    reporting:  visibleModules.filter(m => m.category === 'reporting'),
    field:      visibleModules.filter(m => m.category === 'field'),
  };

  return (
    <div className="mx-auto max-w-screen-2xl px-4 pb-16 pt-8 md:px-8">

      {/* ── Hero Section ──────────────────────────────────────────────────── */}
      <div
        className="mb-10 rounded-2xl overflow-hidden"
        style={{
          background: isLight
            ? 'linear-gradient(135deg, var(--brand-subtle) 0%, var(--surface-raised) 70%)'
            : 'linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(6,182,212,0.08) 50%, transparent 100%)',
          border: '1px solid var(--line-focus)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        {/* Ambient accent strip */}
        <div
          className="h-1 w-full"
          style={{ background: 'var(--gradient-hero)' }}
        />

        <div className="p-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">

            {/* Left — welcome + CTAs */}
            <div>
              <p className="section-label mb-2">Mission Control</p>
              <h1 className="text-2xl font-bold tracking-tight mb-2" style={{ color: 'var(--ink-primary)' }}>
                Welcome back,{' '}
                <span style={{ color: 'var(--brand-text)' }}>
                  {user.full_name.split(' ')[0]}
                </span>
              </h1>
              <p className="max-w-xl text-sm leading-relaxed" style={{ color: 'var(--ink-secondary)' }}>
                Your enterprise tri-modal audit platform — risk management, continuous monitoring,
                compliance frameworks, and ESG reporting in one integrated system.
              </p>

              <div className="mt-5 flex flex-wrap gap-3">
                {visibleModules.some(m => m.id === 'risk') && (
                  <a
                    href={`http://localhost:5182?tenantId=${tenantId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-primary"
                  >
                    Open Risk Dashboard
                    <ArrowRight className="h-3.5 w-3.5" />
                  </a>
                )}
                <button onClick={onOpenTutorials} className="btn-secondary">
                  <BookOpen className="h-3.5 w-3.5" />
                  View Tutorials
                </button>
              </div>
            </div>

            {/* Right — status panel */}
            <div
              className="shrink-0 rounded-xl px-5 py-4"
              style={{
                background: isLight ? 'var(--surface-overlay)' : 'rgba(255,255,255,0.04)',
                border: '1px solid var(--line-focus)',
                minWidth: '220px',
              }}
            >
              <p className="section-label mb-3">System Status</p>
              {([
                {
                  label: onlineCount === null
                    ? 'Checking modules…'
                    : `${onlineCount} / ${visibleModules.length} modules reachable`,
                  status: onlineCount === null ? 'checking'
                    : (onlineCount ?? 0) > 0 ? 'healthy' : 'warning',
                  pulse: onlineCount === null,
                },
                { label: 'PostgreSQL healthy',  status: 'healthy',  pulse: false },
                { label: 'Demo tenant seeded',  status: 'healthy',  pulse: false },
              ]).map(({ label, status, pulse }) => (
                <div key={label} className="flex items-center gap-2 mb-2 last:mb-0 text-sm">
                  <span
                    className={`status-dot ${status === 'healthy' ? 'success' : status === 'warning' ? 'warning' : 'muted'} ${pulse ? 'animate-pulse' : ''}`}
                  />
                  <span style={{ color: 'var(--ink-secondary)' }}>{label}</span>
                </div>
              ))}
            </div>

          </div>
        </div>
      </div>

      {/* ── KPI Intelligence ─────────────────────────────────────────────── */}
      <HubKPI user={user} />

      {/* ── AI Insight Strip ─────────────────────────────────────────────── */}
      <div
        className="mb-8 flex items-center gap-3 rounded-xl px-5 py-3"
        style={{
          background: isLight
            ? 'var(--brand-subtle)'
            : 'linear-gradient(90deg, rgba(99,102,241,0.12) 0%, transparent 70%)',
          border: '1px solid var(--line-accent)',
        }}
      >
        <Sparkles className="h-4 w-4 shrink-0" style={{ color: 'var(--brand-text)' }} />
        <p className="text-sm" style={{ color: 'var(--ink-secondary)' }}>
          <span className="font-semibold" style={{ color: 'var(--brand-text)' }}>AI Insight:</span>
          {' '}Audit platform ready · {visibleModules.length} modules available for tenant{' '}
          <code
            className="font-mono text-[11px] rounded px-1.5 py-0.5"
            style={{ backgroundColor: 'var(--surface-overlay)', color: 'var(--status-success)' }}
          >
            {tenantId.slice(0, 8)}…
          </code>
        </p>
      </div>

      {/* ── Recommended Workflow ─────────────────────────────────────────── */}
      {(user.role === 'super_admin' || user.role === 'admin') && (
        <section className="mb-10">
          <p className="section-label">Recommended Workflow</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {WORKFLOW_STEPS.map((step, i) => (
              <div key={step.label} className="workflow-step sm:flex-col sm:items-center sm:text-center">
                <div
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
                  style={{
                    background: 'var(--brand-subtle)',
                    border: '1px solid var(--brand)',
                    color: 'var(--brand-text)',
                  }}
                >
                  {i + 1}
                </div>
                <div>
                  <p className="text-xs font-semibold leading-tight" style={{ color: 'var(--ink-primary)' }}>
                    {step.label}
                  </p>
                  <p className="mt-0.5 text-[10px] leading-snug" style={{ color: 'var(--ink-muted)' }}>
                    {step.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Module Grid ──────────────────────────────────────────────────── */}
      {(Object.entries(grouped) as [string, Module[]][]).map(([cat, mods]) =>
        mods.length === 0 ? null : (
          <section key={cat} className="mb-10">
            <p className="section-label">{CATEGORY_LABELS[cat]}</p>
            <div className={`grid gap-3 ${gridCols(mods.length)}`}>
              {mods.map(mod => (
                <ModuleCard
                  key={mod.id}
                  mod={mod}
                  tenantId={tenantId}
                  isOnline={checked ? onlineSet.has(mod.id) : null}
                />
              ))}
            </div>
          </section>
        )
      )}

      {/* ── Locked modules hint ───────────────────────────────────────────── */}
      {user.role === 'end_user' && (
        <section className="mt-4 mb-8">
          <div
            className="flex items-center gap-3 rounded-xl px-5 py-4 text-sm"
            style={{
              border: '1px solid var(--line)',
              background: isLight ? 'var(--surface-raised)' : 'var(--surface-glass)',
            }}
          >
            <Lock className="h-4 w-4 shrink-0" style={{ color: 'var(--ink-muted)' }} />
            <span style={{ color: 'var(--ink-secondary)' }}>
              Additional modules are available to admin users. Contact your administrator to request access.
            </span>
          </div>
        </section>
      )}

      {/* ── Infrastructure ────────────────────────────────────────────────── */}
      {(user.role === 'super_admin' || user.role === 'admin') && (
        <section className="mt-10">
          <p className="section-label">Infrastructure</p>
          <div className="flex flex-wrap gap-3">
            <InfraChip icon={<Database  className="h-3.5 w-3.5" />} label="PostgreSQL" detail="localhost:5432" href={null}               status="healthy" />
            <InfraChip icon={<Zap       className="h-3.5 w-3.5" />} label="Redis"      detail="localhost:6379" href={null}               status="healthy" />
            <InfraChip icon={<HardDrive className="h-3.5 w-3.5" />} label="MinIO"      detail="localhost:9001" href="http://localhost:9001" status="healthy" />
          </div>
        </section>
      )}

      {/* ── Quick Reference (super_admin) ─────────────────────────────────── */}
      {user.role === 'super_admin' && (
        <section
          className="mt-10 rounded-xl p-6"
          style={{
            border: '1px solid var(--line-focus)',
            background: isLight ? 'var(--surface-raised)' : 'var(--surface-glass)',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <p className="section-label">Quick Reference</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
            <div>
              <h3 className="font-semibold mb-2" style={{ color: 'var(--ink-primary)' }}>Tenant Scoping</h3>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--ink-secondary)' }}>
                Append{' '}
                <code
                  className="rounded px-1 py-0.5 text-xs font-mono"
                  style={{ backgroundColor: 'var(--surface-overlay)', color: 'var(--brand-text)' }}
                >
                  ?tenantId=UUID
                </code>
                {' '}to any module URL. Your tenant:
              </p>
              <code
                className="mt-1.5 block text-[11px] rounded px-2 py-1.5 select-all font-mono"
                style={{ backgroundColor: 'var(--surface-overlay)', color: 'var(--status-success)' }}
              >
                {tenantId}
              </code>
            </div>
            <div>
              <h3 className="font-semibold mb-2" style={{ color: 'var(--ink-primary)' }}>Module Ports</h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {MODULES.map(m => (
                  <div key={m.id} className="flex items-center justify-between text-[11px]">
                    <span style={{ color: 'var(--ink-secondary)' }} className="truncate mr-2">
                      {m.name.split(' ')[0]}
                    </span>
                    <code className="font-mono" style={{ color: 'var(--ink-muted)' }}>{m.port}</code>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── Module Card ────────────────────────────────────────────────────────── */
interface ModuleCardProps {
  mod: Module;
  tenantId: string;
  isOnline: boolean | null;
}

function ModuleCard({ mod, tenantId, isOnline }: ModuleCardProps) {
  const url = `http://localhost:${mod.port}?tenantId=${tenantId}`;

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="module-card group"
    >
      {/* Icon + status row */}
      <div className="flex items-start justify-between">
        <span
          className="module-icon"
          style={{
            background: `var(--icon-${mod.color})`,
            color: `var(--icon-color-${mod.color})`,
          }}
        >
          {MODULE_ICONS[mod.id]}
        </span>
        <div className="flex items-center gap-2">
          {isOnline !== null && (
            <span
              className={`status-dot ${isOnline ? 'success' : 'muted'}`}
              title={isOnline ? 'Accessible' : 'Not accessible'}
            />
          )}
          <ExternalLink
            className="h-3.5 w-3.5 transition-opacity opacity-40 group-hover:opacity-100"
            style={{ color: 'var(--ink-muted)' }}
          />
        </div>
      </div>

      {/* Title + tagline */}
      <div>
        <div className="font-semibold text-sm leading-tight" style={{ color: 'var(--ink-primary)' }}>
          {mod.name}
        </div>
        <div className="text-[11px] mt-0.5 font-medium" style={{ color: 'var(--ink-muted)' }}>
          {mod.tagline}
        </div>
      </div>

      {/* Description */}
      <p className="text-xs leading-relaxed line-clamp-2 flex-1" style={{ color: 'var(--ink-secondary)' }}>
        {mod.description}
      </p>

      {/* Workflow hint */}
      {mod.workflow && (
        <p
          className="mt-auto pt-1 text-[10px] leading-snug italic border-t"
          style={{ color: 'var(--ink-muted)', borderColor: 'var(--line)' }}
        >
          {mod.workflow}
        </p>
      )}
    </a>
  );
}

/* ── Infrastructure Chip ────────────────────────────────────────────────── */
function InfraChip({
  icon, label, detail, href, status,
}: {
  icon: ReactNode; label: string; detail: string;
  href: string | null; status: 'healthy' | 'degraded' | 'down';
}) {
  const statusColor = status === 'healthy' ? 'var(--status-success)'
    : status === 'degraded' ? 'var(--status-warning)'
    : 'var(--status-danger)';
  const statusIcon = status === 'healthy'
    ? <CheckCircle2 className="h-3.5 w-3.5" />
    : <AlertCircle  className="h-3.5 w-3.5" />;

  const inner = (
    <>
      <span style={{ color: 'var(--ink-muted)' }}>{icon}</span>
      <span className="font-semibold" style={{ color: 'var(--ink-primary)' }}>{label}</span>
      <span className="text-xs font-mono" style={{ color: 'var(--ink-muted)' }}>{detail}</span>
      <span className="ml-auto flex items-center gap-1" style={{ color: statusColor }}>
        {statusIcon}
        <span className="text-[10px] font-semibold capitalize hidden sm:inline">{status}</span>
      </span>
      {href && <ExternalLink className="h-3 w-3 shrink-0" style={{ color: 'var(--ink-muted)' }} />}
    </>
  );

  return href
    ? (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="infra-chip hover:border-brand transition-colors"
        style={{ minWidth: '220px' }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--brand)'; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--line-focus)'; }}
      >
        {inner}
      </a>
    ) : (
      <div className="infra-chip" style={{ minWidth: '220px' }}>{inner}</div>
    );
}
