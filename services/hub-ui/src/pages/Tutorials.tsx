import { useState, useMemo } from 'react';
import { Search, ChevronDown, ChevronRight, Clock, BarChart2, Tag, Lock, BookOpen, CheckCircle } from 'lucide-react';
import { TUTORIALS, type Role, type Tutorial } from '../data/tutorials';
import type { UserRole } from '../contexts/AuthContext';

const ROLE_LABELS: Record<Role, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  end_user: 'End User',
};
const ROLE_BADGE_STYLE: Record<Role, { bg: string; color: string }> = {
  super_admin: { bg: 'rgba(239,68,68,0.12)',  color: 'var(--status-danger)'  },
  admin:       { bg: 'rgba(245,158,11,0.12)', color: 'var(--status-warning)' },
  end_user:    { bg: 'rgba(59,130,246,0.12)', color: 'var(--status-info)'    },
};
const DIFF_STYLE: Record<string, { bg: string; color: string }> = {
  Beginner:     { bg: 'rgba(16,185,129,0.12)', color: 'var(--status-success)' },
  Intermediate: { bg: 'rgba(59,130,246,0.12)', color: 'var(--status-info)'    },
  Advanced:     { bg: 'rgba(239,68,68,0.12)',  color: 'var(--status-danger)'  },
};

interface Props { role: UserRole; }

export default function Tutorials({ role }: Props) {
  const [search,        setSearch]        = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [expandedId,    setExpandedId]    = useState<string | null>(null);
  const [completedIds,  setCompletedIds]  = useState<Set<string>>(new Set());

  const accessible = useMemo(
    () => TUTORIALS.filter(t => t.roles.includes(role as Role)),
    [role],
  );
  const locked = useMemo(
    () => TUTORIALS.filter(t => !t.roles.includes(role as Role)),
    [role],
  );

  const categories = useMemo(() => {
    const cats = Array.from(new Set(accessible.map(t => t.category))).sort();
    return ['All', ...cats];
  }, [accessible]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return accessible.filter(t => {
      const matchCat    = activeCategory === 'All' || t.category === activeCategory;
      const matchSearch = !q || t.title.toLowerCase().includes(q) ||
                          t.description.toLowerCase().includes(q) ||
                          t.tags.some(tag => tag.includes(q));
      return matchCat && matchSearch;
    });
  }, [accessible, search, activeCategory]);

  const progress = accessible.length > 0
    ? Math.round((completedIds.size / accessible.length) * 100) : 0;

  function toggleComplete(id: string) {
    setCompletedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const roleBadge = ROLE_BADGE_STYLE[role as Role] ?? ROLE_BADGE_STYLE.end_user;

  return (
    <div className="mx-auto max-w-screen-xl px-4 pb-16 pt-8 md:px-8">

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight" style={{ color: 'var(--ink-primary)' }}>
          Tutorials
        </h1>
        <p className="mt-1 text-sm flex items-center gap-2" style={{ color: 'var(--ink-secondary)' }}>
          Guides tailored to your role:
          <span className="pill text-[10px] font-medium" style={{ backgroundColor: roleBadge.bg, color: roleBadge.color }}>
            {ROLE_LABELS[role as Role] ?? 'User'}
          </span>
        </p>
      </div>

      {/* Progress */}
      <div className="mb-8 rounded-xl p-5" style={{ border: '1px solid var(--line)', backgroundColor: 'var(--surface-raised)' }}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4" style={{ color: 'var(--brand)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--ink-primary)' }}>Your Progress</span>
          </div>
          <span className="text-sm font-semibold" style={{ color: 'var(--brand-text)' }}>{progress}%</span>
        </div>
        <div className="h-2 w-full rounded-full overflow-hidden" style={{ backgroundColor: 'var(--surface-overlay)' }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${progress}%`, background: 'linear-gradient(to right, var(--brand), var(--brand-hover))' }}
          />
        </div>
        <p className="mt-2 text-xs" style={{ color: 'var(--ink-muted)' }}>
          {completedIds.size} of {accessible.length} completed
          {locked.length > 0 && ` · ${locked.length} tutorial${locked.length > 1 ? 's' : ''} require a higher role`}
        </p>
      </div>

      {/* Search + filters */}
      <div className="mb-6 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4" style={{ color: 'var(--ink-muted)' }} />
          <input
            type="text"
            placeholder="Search tutorials…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="via-input pl-9"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className="rounded-lg px-3 py-2 text-xs font-medium transition-colors"
              style={{
                backgroundColor: activeCategory === cat ? 'var(--brand)' : 'var(--surface-overlay)',
                color: activeCategory === cat ? '#fff' : 'var(--ink-secondary)',
                border: `1px solid ${activeCategory === cat ? 'var(--brand)' : 'var(--line-focus)'}`,
              }}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl py-16 text-center"
             style={{ border: '1px solid var(--line)' }}>
          <Search className="h-8 w-8 mb-3" style={{ color: 'var(--line-strong)' }} />
          <p className="text-sm" style={{ color: 'var(--ink-secondary)' }}>No tutorials match your search.</p>
          <button
            onClick={() => { setSearch(''); setActiveCategory('All'); }}
            className="mt-3 text-xs"
            style={{ color: 'var(--brand)' }}
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(tutorial => (
            <TutorialCard
              key={tutorial.id}
              tutorial={tutorial}
              isExpanded={expandedId === tutorial.id}
              isCompleted={completedIds.has(tutorial.id)}
              onToggle={() => setExpandedId(expandedId === tutorial.id ? null : tutorial.id)}
              onComplete={() => toggleComplete(tutorial.id)}
            />
          ))}
        </div>
      )}

      {/* Locked */}
      {locked.length > 0 && (
        <section className="mt-12">
          <p className="section-label flex items-center gap-1.5">
            <Lock className="h-3.5 w-3.5" /> Requires Higher Role
          </p>
          <div className="space-y-2">
            {locked.map(t => <LockedCard key={t.id} tutorial={t} />)}
          </div>
        </section>
      )}
    </div>
  );
}

function TutorialCard({
  tutorial, isExpanded, isCompleted, onToggle, onComplete,
}: {
  tutorial: Tutorial; isExpanded: boolean; isCompleted: boolean;
  onToggle: () => void; onComplete: () => void;
}) {
  const [activeStep, setActiveStep] = useState(0);
  const diffStyle = DIFF_STYLE[tutorial.difficulty] ?? DIFF_STYLE.Beginner;

  return (
    <div className={`tutorial-card ${isCompleted ? 'opacity-60' : ''}`}>
      <button onClick={onToggle} className="w-full text-left">
        <div className="flex items-start gap-3">
          {/* Complete toggle */}
          <button
            onClick={e => { e.stopPropagation(); onComplete(); }}
            className="mt-0.5 shrink-0 h-5 w-5 rounded-full border flex items-center justify-center transition-all"
            style={{
              borderColor: isCompleted ? 'var(--status-success)' : 'var(--line-strong)',
              backgroundColor: isCompleted ? 'rgba(16,185,129,0.15)' : 'transparent',
              color: 'var(--status-success)',
            }}
          >
            {isCompleted && <CheckCircle className="h-3.5 w-3.5" />}
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-sm font-semibold ${isCompleted ? 'line-through' : ''}`}
                    style={{ color: isCompleted ? 'var(--ink-muted)' : 'var(--ink-primary)' }}>
                {tutorial.title}
              </span>
              <span className="pill text-[10px]" style={{ backgroundColor: diffStyle.bg, color: diffStyle.color }}>
                {tutorial.difficulty}
              </span>
            </div>
            <p className="mt-1 text-xs leading-relaxed line-clamp-2" style={{ color: 'var(--ink-secondary)' }}>
              {tutorial.description}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]" style={{ color: 'var(--ink-muted)' }}>
              <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {tutorial.duration}</span>
              <span className="flex items-center gap-1"><BarChart2 className="h-3 w-3" /> {tutorial.steps.length} steps</span>
              <span className="flex items-center gap-1"><Tag className="h-3 w-3" /> {tutorial.category}</span>
              {tutorial.tags.slice(0, 3).map(tag => (
                <span key={tag} className="rounded px-1.5 py-0.5" style={{ backgroundColor: 'var(--surface-base)' }}>{tag}</span>
              ))}
            </div>
          </div>

          <div style={{ color: 'var(--ink-muted)' }} className="shrink-0">
            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--line)' }}>
          <div className="flex gap-5">
            {/* Step nav (desktop) */}
            <div className="flex flex-col gap-1 shrink-0 w-40 hidden md:flex">
              {tutorial.steps.map((step, i) => (
                <button
                  key={i}
                  onClick={() => setActiveStep(i)}
                  className="text-left text-xs rounded-lg px-3 py-2 transition-all leading-snug"
                  style={{
                    backgroundColor: activeStep === i ? 'var(--brand-subtle)' : 'transparent',
                    color: activeStep === i ? 'var(--brand-text)' : 'var(--ink-muted)',
                    border: activeStep === i ? '1px solid var(--brand)' : '1px solid transparent',
                  }}
                >
                  <span className="block text-[10px] font-bold uppercase tracking-wider opacity-50 mb-0.5">
                    Step {i + 1}
                  </span>
                  {step.title}
                </button>
              ))}
            </div>

            {/* Step content */}
            <div className="flex-1 min-w-0">
              {/* Mobile step dots */}
              <div className="flex gap-1.5 mb-4 md:hidden overflow-x-auto pb-1">
                {tutorial.steps.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setActiveStep(i)}
                    className="shrink-0 h-7 w-7 rounded-full text-xs font-semibold transition-colors"
                    style={{
                      backgroundColor: activeStep === i ? 'var(--brand)' : 'var(--surface-overlay)',
                      color: activeStep === i ? '#fff' : 'var(--ink-secondary)',
                    }}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>

              <div className="rounded-xl p-5"
                   style={{ backgroundColor: 'var(--surface-base)', border: '1px solid var(--line)' }}>
                <h3 className="font-semibold text-sm mb-3" style={{ color: 'var(--ink-primary)' }}>
                  {tutorial.steps[activeStep].title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--ink-secondary)' }}>
                  {tutorial.steps[activeStep].content}
                </p>
              </div>

              <div className="mt-3 flex items-center justify-between">
                <button
                  disabled={activeStep === 0}
                  onClick={() => setActiveStep(activeStep - 1)}
                  className="text-xs transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  style={{ color: 'var(--ink-secondary)' }}
                >
                  ← Previous
                </button>
                <span className="text-[10px]" style={{ color: 'var(--ink-muted)' }}>
                  {activeStep + 1} / {tutorial.steps.length}
                </span>
                {activeStep < tutorial.steps.length - 1 ? (
                  <button
                    onClick={() => setActiveStep(activeStep + 1)}
                    className="text-xs"
                    style={{ color: 'var(--brand)' }}
                  >
                    Next →
                  </button>
                ) : (
                  <button onClick={onComplete} className="text-xs font-medium" style={{ color: 'var(--status-success)' }}>
                    Mark Complete ✓
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LockedCard({ tutorial }: { tutorial: Tutorial }) {
  const requiredRole = tutorial.roles[0] as Role;
  const badge = ROLE_BADGE_STYLE[requiredRole] ?? ROLE_BADGE_STYLE.end_user;
  return (
    <div className="flex items-center gap-3 rounded-xl px-5 py-4 opacity-50"
         style={{ border: '1px solid var(--line)', backgroundColor: 'var(--surface-raised)' }}>
      <Lock className="h-4 w-4 shrink-0" style={{ color: 'var(--ink-muted)' }} />
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium" style={{ color: 'var(--ink-secondary)' }}>{tutorial.title}</span>
        <span className="ml-2 text-xs" style={{ color: 'var(--ink-muted)' }}>— {tutorial.category}</span>
      </div>
      <span className="pill text-[10px] shrink-0" style={{ backgroundColor: badge.bg, color: badge.color }}>
        {ROLE_LABELS[requiredRole]}+
      </span>
    </div>
  );
}
