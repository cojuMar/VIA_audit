import { useState, useMemo } from 'react';
import { Search, ChevronDown, ChevronRight, Clock, BarChart2, Tag, Lock, BookOpen, CheckCircle } from 'lucide-react';
import { TUTORIALS, type Role, type Tutorial } from '../data/tutorials';

const ROLE_LABELS: Record<Role, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  end_user: 'End User',
};

const ROLE_COLORS: Record<Role, string> = {
  super_admin: 'pill-rose',
  admin: 'pill-amber',
  end_user: 'pill-blue',
};

const DIFFICULTY_COLORS = {
  Beginner: 'pill-green',
  Intermediate: 'pill-blue',
  Advanced: 'pill-rose',
};

interface Props {
  role: Role;
}

export default function Tutorials({ role }: Props) {
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('All');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());

  // Filter tutorials visible to this role
  const accessible = useMemo(
    () => TUTORIALS.filter((t) => t.roles.includes(role)),
    [role],
  );

  const categories = useMemo(() => {
    const cats = Array.from(new Set(accessible.map((t) => t.category))).sort();
    return ['All', ...cats];
  }, [accessible]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return accessible.filter((t) => {
      const matchCat = activeCategory === 'All' || t.category === activeCategory;
      const matchSearch =
        !q ||
        t.title.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.tags.some((tag) => tag.includes(q));
      return matchCat && matchSearch;
    });
  }, [accessible, search, activeCategory]);

  // Tutorials not visible to this role
  const locked = useMemo(
    () => TUTORIALS.filter((t) => !t.roles.includes(role)),
    [role],
  );

  function toggleComplete(id: string) {
    setCompletedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const progress = accessible.length > 0
    ? Math.round((completedIds.size / accessible.length) * 100)
    : 0;

  return (
    <div className="mx-auto max-w-screen-xl px-4 pb-16 pt-8 md:px-8">

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white tracking-tight">Tutorials</h1>
        <p className="mt-1 text-sm text-slate-400">
          Step-by-step guides tailored to your role:{' '}
          <span className={`pill ${ROLE_COLORS[role]} ml-1`}>{ROLE_LABELS[role]}</span>
        </p>
      </div>

      {/* Progress bar */}
      <div className="mb-8 rounded-xl border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-indigo-400" />
            <span className="text-sm font-medium text-slate-200">Your Progress</span>
          </div>
          <span className="text-sm font-semibold text-indigo-300">{progress}%</span>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-indigo-400 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {completedIds.size} of {accessible.length} tutorials completed
          {locked.length > 0 && ` · ${locked.length} tutorial${locked.length > 1 ? 's' : ''} require a higher role`}
        </p>
      </div>

      {/* Search + category filters */}
      <div className="mb-6 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search tutorials…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-lg bg-slate-800 border border-slate-700 pl-9 pr-3 py-2
                       text-sm text-slate-200 placeholder-slate-500 focus:outline-none
                       focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                activeCategory === cat
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      {search || activeCategory !== 'All' ? (
        <p className="mb-4 text-xs text-slate-500">
          Showing {filtered.length} of {accessible.length} tutorials
        </p>
      ) : null}

      {/* Tutorial list */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-slate-800 py-16 text-center">
          <Search className="h-8 w-8 text-slate-700 mb-3" />
          <p className="text-sm text-slate-400">No tutorials match your search.</p>
          <button
            onClick={() => { setSearch(''); setActiveCategory('All'); }}
            className="mt-3 text-xs text-indigo-400 hover:text-indigo-300"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((tutorial) => (
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

      {/* Locked tutorials */}
      {locked.length > 0 && (
        <section className="mt-12">
          <h2 className="mb-4 text-xs font-semibold uppercase tracking-widest text-slate-500 flex items-center gap-2">
            <Lock className="h-3.5 w-3.5" />
            Requires Higher Role Access
          </h2>
          <div className="space-y-2">
            {locked.map((t) => (
              <LockedCard key={t.id} tutorial={t} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function TutorialCard({
  tutorial,
  isExpanded,
  isCompleted,
  onToggle,
  onComplete,
}: {
  tutorial: Tutorial;
  isExpanded: boolean;
  isCompleted: boolean;
  onToggle: () => void;
  onComplete: () => void;
}) {
  const [activeStep, setActiveStep] = useState(0);

  return (
    <div className={`tutorial-card transition-all ${isCompleted ? 'opacity-70' : ''}`}>
      {/* Header row */}
      <button onClick={onToggle} className="w-full text-left">
        <div className="flex items-start gap-3">
          {/* Complete toggle */}
          <button
            onClick={(e) => { e.stopPropagation(); onComplete(); }}
            className={`mt-0.5 shrink-0 h-5 w-5 rounded-full border flex items-center justify-center transition-colors ${
              isCompleted
                ? 'border-emerald-500 bg-emerald-500/20 text-emerald-400'
                : 'border-slate-600 hover:border-emerald-500/50'
            }`}
            title={isCompleted ? 'Mark incomplete' : 'Mark complete'}
          >
            {isCompleted && <CheckCircle className="h-3.5 w-3.5" />}
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-sm font-semibold ${isCompleted ? 'line-through text-slate-500' : 'text-slate-100'}`}>
                {tutorial.title}
              </span>
              <span className={`pill ${DIFFICULTY_COLORS[tutorial.difficulty]} text-[10px]`}>
                {tutorial.difficulty}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400 leading-relaxed line-clamp-2">
              {tutorial.description}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" /> {tutorial.duration}
              </span>
              <span className="flex items-center gap-1">
                <BarChart2 className="h-3 w-3" /> {tutorial.steps.length} steps
              </span>
              <span className="flex items-center gap-1">
                <Tag className="h-3 w-3" /> {tutorial.category}
              </span>
              {tutorial.tags.slice(0, 3).map((tag) => (
                <span key={tag} className="rounded bg-slate-700/50 px-1.5 py-0.5">
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <div className="shrink-0 text-slate-500">
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </div>
        </div>
      </button>

      {/* Expanded steps */}
      {isExpanded && (
        <div className="mt-5 border-t border-slate-700 pt-5">
          <div className="flex gap-5">
            {/* Step nav */}
            <div className="flex flex-col gap-1 shrink-0 w-40 hidden md:flex">
              {tutorial.steps.map((step, i) => (
                <button
                  key={i}
                  onClick={() => setActiveStep(i)}
                  className={`text-left text-xs rounded-lg px-3 py-2 transition-colors leading-snug ${
                    activeStep === i
                      ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/40'
                      : 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50'
                  }`}
                >
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-50 block mb-0.5">
                    Step {i + 1}
                  </span>
                  {step.title}
                </button>
              ))}
            </div>

            {/* Step content */}
            <div className="flex-1 min-w-0">
              {/* Mobile step tabs */}
              <div className="flex gap-1.5 mb-4 md:hidden overflow-x-auto pb-1">
                {tutorial.steps.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setActiveStep(i)}
                    className={`shrink-0 h-7 w-7 rounded-full text-xs font-semibold transition-colors ${
                      activeStep === i
                        ? 'bg-indigo-600 text-white'
                        : 'bg-slate-700 text-slate-400'
                    }`}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>

              <div className="rounded-xl bg-slate-900/60 border border-slate-700/50 p-5">
                <h3 className="font-semibold text-slate-100 text-sm mb-3">
                  {tutorial.steps[activeStep].title}
                </h3>
                <p className="text-sm text-slate-300 leading-relaxed">
                  {tutorial.steps[activeStep].content}
                </p>
              </div>

              {/* Navigation */}
              <div className="mt-3 flex items-center justify-between">
                <button
                  disabled={activeStep === 0}
                  onClick={() => setActiveStep(activeStep - 1)}
                  className="text-xs text-slate-500 hover:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  ← Previous
                </button>
                <span className="text-[10px] text-slate-600">
                  {activeStep + 1} / {tutorial.steps.length}
                </span>
                {activeStep < tutorial.steps.length - 1 ? (
                  <button
                    onClick={() => setActiveStep(activeStep + 1)}
                    className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    Next →
                  </button>
                ) : (
                  <button
                    onClick={onComplete}
                    className="text-xs font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                  >
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
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/30 px-5 py-4 opacity-50">
      <Lock className="h-4 w-4 text-slate-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-sm text-slate-400 font-medium">{tutorial.title}</span>
        <span className="ml-2 text-xs text-slate-600">— {tutorial.category}</span>
      </div>
      <span className={`pill ${ROLE_COLORS[requiredRole]} text-[10px] shrink-0`}>
        {ROLE_LABELS[requiredRole]}+
      </span>
    </div>
  );
}
