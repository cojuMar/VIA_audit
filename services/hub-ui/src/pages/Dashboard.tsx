import { ExternalLink, BookOpen, ArrowRight, Shield, Activity, Users, FileText, Plug, Bot, BarChart2, Calendar, Leaf, Smartphone, Building2, Globe } from 'lucide-react';
import { MODULES, WORKFLOW_STEPS } from '../data/modules';
import type { Role } from '../data/tutorials';

const TENANT_ID = '00000000-0000-0000-0000-000000000001';

const MODULE_ICONS: Record<string, React.ReactNode> = {
  framework: <Shield className="h-5 w-5" />,
  tprm: <Building2 className="h-5 w-5" />,
  'trust-portal': <Globe className="h-5 w-5" />,
  monitoring: <Activity className="h-5 w-5" />,
  people: <Users className="h-5 w-5" />,
  pbc: <FileText className="h-5 w-5" />,
  integration: <Plug className="h-5 w-5" />,
  'ai-agent': <Bot className="h-5 w-5" />,
  risk: <BarChart2 className="h-5 w-5" />,
  'audit-planning': <Calendar className="h-5 w-5" />,
  esg: <Leaf className="h-5 w-5" />,
  mobile: <Smartphone className="h-5 w-5" />,
};

const CATEGORY_LABELS: Record<string, string> = {
  core: 'Core Platform',
  operations: 'Operations',
  reporting: 'Reporting',
  field: 'Field',
};

interface Props {
  role: Role;
  onOpenTutorials: () => void;
}

export default function Dashboard({ onOpenTutorials }: Props) {
  const grouped = {
    core: MODULES.filter((m) => m.category === 'core'),
    operations: MODULES.filter((m) => m.category === 'operations'),
    reporting: MODULES.filter((m) => m.category === 'reporting'),
    field: MODULES.filter((m) => m.category === 'field'),
  };

  return (
    <div className="mx-auto max-w-screen-2xl px-4 pb-16 pt-8 md:px-8">

      {/* Hero banner */}
      <div className="mb-10 rounded-2xl bg-gradient-to-br from-indigo-900/40 via-slate-800/60 to-slate-800/40
                      border border-indigo-500/20 p-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Welcome to Aegis 2026
            </h1>
            <p className="mt-2 max-w-xl text-sm text-slate-400 leading-relaxed">
              Your enterprise tri-modal audit platform — combining risk management, continuous
              monitoring, compliance frameworks, and ESG reporting in one integrated system.
              Select a module below to get started, or follow the recommended workflow.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <a
                href={`http://localhost:5182?tenantId=${TENANT_ID}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500
                           px-4 py-2 text-sm font-medium text-white transition-colors"
              >
                Open Risk Dashboard
                <ArrowRight className="h-3.5 w-3.5" />
              </a>
              <button
                onClick={onOpenTutorials}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-700 hover:bg-slate-600
                           px-4 py-2 text-sm font-medium text-slate-200 transition-colors"
              >
                <BookOpen className="h-3.5 w-3.5" />
                View Tutorials
              </button>
            </div>
          </div>
          <div className="flex flex-col gap-2 text-sm text-slate-400 shrink-0">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>12 modules running</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span>PostgreSQL healthy</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span>Demo tenant seeded</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recommended workflow */}
      <section className="mb-10">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-slate-500">
          Recommended Workflow
        </h2>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 overflow-x-auto pb-2">
          {WORKFLOW_STEPS.map((step, i) => (
            <div key={step.label} className="flex items-center gap-2 shrink-0">
              <div className="flex flex-col items-center">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600/20 border border-indigo-500/40 text-xs font-bold text-indigo-300">
                  {i + 1}
                </div>
                <span className="mt-1.5 text-xs font-medium text-slate-300 whitespace-nowrap">
                  {step.label}
                </span>
                <span className="text-[10px] text-slate-500 whitespace-nowrap">{step.desc}</span>
              </div>
              {i < WORKFLOW_STEPS.length - 1 && (
                <div className="hidden sm:flex items-center gap-1 mt-[-18px] mx-1">
                  <div className="h-px w-10 bg-gradient-to-r from-indigo-500/40 to-indigo-500/10" />
                  <ArrowRight className="h-3 w-3 text-indigo-500/40 shrink-0" />
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Module grid — grouped by category */}
      {(Object.entries(grouped) as [string, typeof MODULES[0][]][]).map(([cat, mods]) => (
        mods.length === 0 ? null : (
          <section key={cat} className="mb-8">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">
              {CATEGORY_LABELS[cat]}
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {mods.map((mod) => (
                <ModuleCard key={mod.id} mod={mod} />
              ))}
            </div>
          </section>
        )
      ))}

      {/* Infrastructure */}
      <section className="mt-10">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">
          Infrastructure
        </h2>
        <div className="flex flex-wrap gap-3">
          <InfraLink label="PostgreSQL" href={null} detail="localhost:5432" />
          <InfraLink label="Redis" href={null} detail="localhost:6379" />
          <InfraLink
            label="MinIO Console"
            href="http://localhost:9001"
            detail="aegis_minio / aegis_minio_dev_pw"
          />
        </div>
      </section>

      {/* Quick reference */}
      <section className="mt-10 rounded-xl border border-slate-800 bg-slate-900/50 p-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-slate-500">
          Quick Reference
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
          <div>
            <h3 className="font-medium text-slate-200 mb-2">Tenant Scoping</h3>
            <p className="text-slate-400 text-xs leading-relaxed">
              Append <code className="bg-slate-800 rounded px-1 py-0.5 text-indigo-300">?tenantId=UUID</code> to any
              module URL. The demo tenant is always available at:
            </p>
            <code className="mt-1.5 block text-[11px] text-emerald-300 bg-slate-800 rounded px-2 py-1.5">
              {TENANT_ID}
            </code>
          </div>
          <div>
            <h3 className="font-medium text-slate-200 mb-2">Useful Commands</h3>
            <div className="space-y-1 font-mono text-[11px]">
              <CodeLine cmd="docker compose ps" desc="Check container status" />
              <CodeLine cmd="docker compose logs -f risk-service" desc="Follow a service log" />
              <CodeLine cmd="docker compose restart risk-service" desc="Restart one service" />
              <CodeLine cmd="stop.bat" desc="Shut everything down" />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function ModuleCard({ mod }: { mod: typeof MODULES[0] }) {
  const url = `http://localhost:${mod.port}?tenantId=${TENANT_ID}`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="module-card group flex flex-col gap-3"
    >
      <div className="flex items-start justify-between">
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${mod.iconBg} text-white shrink-0`}>
          {MODULE_ICONS[mod.id]}
        </div>
        <ExternalLink className="h-3.5 w-3.5 text-slate-600 group-hover:text-slate-400 transition-colors shrink-0" />
      </div>
      <div>
        <div className="font-semibold text-slate-100 text-sm leading-tight">{mod.name}</div>
        <div className="text-[11px] text-slate-500 mt-0.5">{mod.tagline}</div>
      </div>
      <p className="text-xs text-slate-400 leading-relaxed line-clamp-2 flex-1">
        {mod.description}
      </p>
      <div className="flex items-center justify-between mt-auto pt-1">
        <span className={`pill ${mod.pill} text-[10px]`}>
          :{mod.port}
        </span>
        {mod.workflow && (
          <span className="text-[10px] text-slate-600 italic hidden xl:block truncate ml-2 max-w-[120px]">
            {mod.workflow}
          </span>
        )}
      </div>
    </a>
  );
}

function InfraLink({ label, href, detail }: { label: string; href: string | null; detail: string }) {
  const cls =
    'flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 px-4 py-2.5 text-sm text-slate-300';
  const inner = (
    <>
      <span className="font-medium">{label}</span>
      <span className="text-slate-600">·</span>
      <span className="text-xs text-slate-500 font-mono">{detail}</span>
      {href && <ExternalLink className="h-3 w-3 text-slate-600 ml-1" />}
    </>
  );
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={`${cls} hover:border-slate-700`}>
      {inner}
    </a>
  ) : (
    <div className={cls}>{inner}</div>
  );
}

function CodeLine({ cmd, desc }: { cmd: string; desc: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <code className="text-emerald-300 shrink-0">{cmd}</code>
      <span className="text-slate-600">—</span>
      <span className="text-slate-500 text-[11px]">{desc}</span>
    </div>
  );
}
