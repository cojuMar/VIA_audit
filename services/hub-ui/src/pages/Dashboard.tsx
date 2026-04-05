import { type ReactNode, useState, useEffect } from 'react';
import { ExternalLink, BookOpen, ArrowRight, Shield, Activity, Users, FileText, Plug, Bot, BarChart2, Calendar, Leaf, Smartphone, Building2, Globe } from 'lucide-react';
import { MODULES, WORKFLOW_STEPS, type Module } from '../data/modules';
import type { UserRole } from '../contexts/AuthContext';

/** Ping each module's /health endpoint and return how many responded OK */
function useModuleHealth() {
  const [online, setOnline] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const checks = MODULES.map(async (m) => {
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 2000);
        const res = await fetch(`http://localhost:${m.port}/health`, {
          signal: ctrl.signal,
          method: 'GET',
        });
        clearTimeout(timer);
        return res.ok;
      } catch {
        return false;
      }
    });
    Promise.all(checks).then((results) => {
      if (!cancelled) setOnline(results.filter(Boolean).length);
    });
    return () => { cancelled = true; };
  }, []);

  return online;
}

const TENANT_ID = '00000000-0000-0000-0000-000000000001';

const MODULE_ICONS: Record<string, ReactNode> = {
  framework:       <Shield className="h-5 w-5" />,
  tprm:            <Building2 className="h-5 w-5" />,
  'trust-portal':  <Globe className="h-5 w-5" />,
  monitoring:      <Activity className="h-5 w-5" />,
  people:          <Users className="h-5 w-5" />,
  pbc:             <FileText className="h-5 w-5" />,
  integration:     <Plug className="h-5 w-5" />,
  'ai-agent':      <Bot className="h-5 w-5" />,
  risk:            <BarChart2 className="h-5 w-5" />,
  'audit-planning':<Calendar className="h-5 w-5" />,
  esg:             <Leaf className="h-5 w-5" />,
  mobile:          <Smartphone className="h-5 w-5" />,
};

const CATEGORY_LABELS: Record<string, string> = {
  core: 'Core Platform',
  operations: 'Operations',
  reporting: 'Reporting',
  field: 'Field',
};

interface Props {
  role: UserRole;
  onOpenTutorials: () => void;
}

export default function Dashboard({ onOpenTutorials }: Props) {
  const onlineCount = useModuleHealth();
  const grouped = {
    core:       MODULES.filter(m => m.category === 'core'),
    operations: MODULES.filter(m => m.category === 'operations'),
    reporting:  MODULES.filter(m => m.category === 'reporting'),
    field:      MODULES.filter(m => m.category === 'field'),
  };

  return (
    <div className="mx-auto max-w-screen-2xl px-4 pb-16 pt-8 md:px-8">

      {/* Hero */}
      <div
        className="mb-10 rounded-2xl p-8"
        style={{
          background: 'linear-gradient(135deg, var(--brand-subtle) 0%, var(--surface-raised) 100%)',
          border: '1px solid var(--line-focus)',
        }}
      >
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" style={{ color: 'var(--ink-primary)' }}>
              Welcome to VIA
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-relaxed" style={{ color: 'var(--ink-secondary)' }}>
              Your enterprise tri-modal audit platform — combining risk management, continuous
              monitoring, compliance frameworks, and ESG reporting in one integrated system.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <a
                href={`http://localhost:5182?tenantId=${TENANT_ID}`}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary"
              >
                Open Risk Dashboard
                <ArrowRight className="h-3.5 w-3.5" />
              </a>
              <button onClick={onOpenTutorials} className="btn-secondary">
                <BookOpen className="h-3.5 w-3.5" />
                View Tutorials
              </button>
            </div>
          </div>
          <div className="flex flex-col gap-2 text-sm shrink-0">
            {([
              [
                onlineCount === null
                  ? 'Checking modules…'
                  : `${onlineCount} / ${MODULES.length} modules online`,
                onlineCount !== null && onlineCount > 0,
              ],
              ['PostgreSQL healthy', true],
              ['Demo tenant seeded', true],
            ] as [string, boolean][]).map(([label, ok]) => (
              <div key={label} className="flex items-center gap-2">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{
                    backgroundColor: onlineCount === null && label.startsWith('Checking')
                      ? 'var(--ink-muted)'
                      : ok
                      ? 'var(--status-success)'
                      : 'var(--status-danger)',
                  }}
                />
                <span style={{ color: 'var(--ink-secondary)' }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Workflow */}
      <section className="mb-10">
        <p className="section-label">Recommended Workflow</p>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 overflow-x-auto pb-2">
          {WORKFLOW_STEPS.map((step, i) => (
            <div key={step.label} className="flex items-center gap-2 shrink-0">
              <div className="flex flex-col items-center">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold"
                  style={{
                    backgroundColor: 'var(--brand-subtle)',
                    border: '1px solid var(--brand)',
                    color: 'var(--brand-text)',
                  }}
                >
                  {i + 1}
                </div>
                <span className="mt-1.5 text-xs font-medium whitespace-nowrap" style={{ color: 'var(--ink-primary)' }}>
                  {step.label}
                </span>
                <span className="text-[10px] whitespace-nowrap" style={{ color: 'var(--ink-muted)' }}>
                  {step.desc}
                </span>
              </div>
              {i < WORKFLOW_STEPS.length - 1 && (
                <div className="hidden sm:flex items-center gap-1 mt-[-18px] mx-1">
                  <div className="h-px w-10" style={{ background: 'linear-gradient(to right, var(--brand), transparent)' }} />
                  <ArrowRight className="h-3 w-3 shrink-0" style={{ color: 'var(--brand)', opacity: 0.4 }} />
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Module grid */}
      {(Object.entries(grouped) as [string, Module[]][]).map(([cat, mods]) =>
        mods.length === 0 ? null : (
          <section key={cat} className="mb-8">
            <p className="section-label">{CATEGORY_LABELS[cat]}</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {mods.map(mod => <ModuleCard key={mod.id} mod={mod} />)}
            </div>
          </section>
        )
      )}

      {/* Infrastructure */}
      <section className="mt-10">
        <p className="section-label">Infrastructure</p>
        <div className="flex flex-wrap gap-3">
          <InfraChip label="PostgreSQL"  detail="localhost:5432" href={null} />
          <InfraChip label="Redis"       detail="localhost:6379" href={null} />
          <InfraChip label="MinIO"       detail="localhost:9001" href="http://localhost:9001" />
        </div>
      </section>

      {/* Quick reference */}
      <section
        className="mt-10 rounded-xl p-6"
        style={{ border: '1px solid var(--line)', backgroundColor: 'var(--surface-raised)' }}
      >
        <p className="section-label">Quick Reference</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
          <div>
            <h3 className="font-medium mb-2" style={{ color: 'var(--ink-primary)' }}>Tenant Scoping</h3>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--ink-secondary)' }}>
              Append{' '}
              <code
                className="rounded px-1 py-0.5 text-xs"
                style={{ backgroundColor: 'var(--surface-overlay)', color: 'var(--brand-text)' }}
              >
                ?tenantId=UUID
              </code>
              {' '}to any module URL. Demo tenant:
            </p>
            <code
              className="mt-1.5 block text-[11px] rounded px-2 py-1.5"
              style={{ backgroundColor: 'var(--surface-overlay)', color: 'var(--status-success)' }}
            >
              {TENANT_ID}
            </code>
          </div>
          <div>
            <h3 className="font-medium mb-2" style={{ color: 'var(--ink-primary)' }}>Useful Commands</h3>
            <div className="space-y-1 font-mono text-[11px]">
              <CodeLine cmd="docker compose ps"              desc="Check container status" />
              <CodeLine cmd="docker compose logs -f hub-ui"  desc="Follow hub logs" />
              <CodeLine cmd="docker compose restart hub-ui"  desc="Restart one service" />
              <CodeLine cmd="stop.bat"                       desc="Shut everything down" />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function ModuleCard({ mod }: { mod: Module }) {
  const url = `http://localhost:${mod.port}?tenantId=${TENANT_ID}`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="module-card group flex flex-col gap-3"
    >
      <div className="flex items-start justify-between">
        <div
          className="flex h-9 w-9 items-center justify-center rounded-lg text-white shrink-0"
          style={{ backgroundColor: mod.iconBg.replace('bg-', '') }}
        >
          {/* Use inline style for icon bg since it's dynamic */}
          <span className={`${mod.iconBg} rounded-lg flex h-9 w-9 items-center justify-center text-white`}>
            {MODULE_ICONS[mod.id]}
          </span>
        </div>
        <ExternalLink className="h-3.5 w-3.5 transition-colors shrink-0" style={{ color: 'var(--ink-muted)' }} />
      </div>
      <div>
        <div className="font-semibold text-sm leading-tight" style={{ color: 'var(--ink-primary)' }}>
          {mod.name}
        </div>
        <div className="text-[11px] mt-0.5" style={{ color: 'var(--ink-muted)' }}>{mod.tagline}</div>
      </div>
      <p className="text-xs leading-relaxed line-clamp-2 flex-1" style={{ color: 'var(--ink-secondary)' }}>
        {mod.description}
      </p>
      <div className="flex items-center justify-between mt-auto pt-1">
        <span className={`pill ${mod.pill} text-[10px]`}>:{mod.port}</span>
      </div>
    </a>
  );
}

function InfraChip({ label, detail, href }: { label: string; detail: string; href: string | null }) {
  const cls = "flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm";
  const style = {
    border: '1px solid var(--line)',
    backgroundColor: 'var(--surface-raised)',
    color: 'var(--ink-secondary)',
  };
  const inner = (
    <>
      <span className="font-medium" style={{ color: 'var(--ink-primary)' }}>{label}</span>
      <span style={{ color: 'var(--line-strong)' }}>·</span>
      <span className="text-xs font-mono" style={{ color: 'var(--ink-muted)' }}>{detail}</span>
      {href && <ExternalLink className="h-3 w-3 ml-1" style={{ color: 'var(--ink-muted)' }} />}
    </>
  );
  return href
    ? <a href={href} target="_blank" rel="noopener noreferrer" className={cls} style={style}>{inner}</a>
    : <div className={cls} style={style}>{inner}</div>;
}

function CodeLine({ cmd, desc }: { cmd: string; desc: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <code style={{ color: 'var(--status-success)' }} className="shrink-0">{cmd}</code>
      <span style={{ color: 'var(--line-strong)' }}>—</span>
      <span style={{ color: 'var(--ink-muted)' }} className="text-[11px]">{desc}</span>
    </div>
  );
}
