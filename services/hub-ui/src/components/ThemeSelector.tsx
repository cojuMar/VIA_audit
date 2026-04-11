import { useState, useEffect, useRef } from 'react';
import { Moon, Sun, ChevronDown, Check } from 'lucide-react';
import { useTheme, type Theme } from '../contexts/ThemeContext';

interface ThemeOption {
  id: Theme;
  label: string;
  description: string;
  swatch: string;        /* primary surface swatch color */
  accent: string;        /* brand accent swatch color    */
  isDark: boolean;
}

const THEMES: ThemeOption[] = [
  {
    id:          'dark',
    label:       'Command Center',
    description: 'Near-black navy · Indigo',
    swatch:      '#0A0F1E',
    accent:      '#6366F1',
    isDark:      true,
  },
  {
    id:          'light',
    label:       'Horizon White',
    description: 'Clean slate white · Indigo',
    swatch:      '#F8FAFC',
    accent:      '#4F46E5',
    isDark:      false,
  },
  {
    id:          'corporate',
    label:       'Corporate Steel',
    description: 'Blue-white · Cobalt',
    swatch:      '#EEF4FB',
    accent:      '#1565C0',
    isDark:      false,
  },
  {
    id:          'professional',
    label:       'Executive Warm',
    description: 'Ivory · Deep violet',
    swatch:      '#FAF8F5',
    accent:      '#5E35B1',
    isDark:      false,
  },
];

const DARK_THEMES  = THEMES.filter(t => t.isDark);
const LIGHT_THEMES = THEMES.filter(t => !t.isDark);

export default function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen]     = useState(false);
  const containerRef        = useRef<HTMLDivElement>(null);

  const current = THEMES.find(t => t.id === theme) ?? THEMES[0];

  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative" title="Switch theme">

      {/* Trigger */}
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all"
        style={{
          backgroundColor: 'var(--surface-overlay)',
          border: `1px solid ${open ? 'var(--brand)' : 'var(--line-focus)'}`,
          color: 'var(--ink-secondary)',
          boxShadow: open ? 'var(--shadow-input)' : 'none',
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {/* Dual swatch */}
        <span className="relative flex h-4 w-6 shrink-0 rounded overflow-hidden"
              style={{ border: '1px solid var(--line-strong)' }}>
          <span className="flex-1" style={{ backgroundColor: current.swatch }} />
          <span className="w-2 shrink-0" style={{ backgroundColor: current.accent }} />
        </span>
        <span style={{ color: 'var(--ink-primary)' }} className="hidden sm:inline">
          {current.label}
        </span>
        {current.isDark
          ? <Moon  className="h-3 w-3 shrink-0" style={{ color: 'var(--ink-muted)' }} />
          : <Sun   className="h-3 w-3 shrink-0" style={{ color: 'var(--ink-muted)' }} />
        }
        <ChevronDown
          className="h-3 w-3 shrink-0 transition-transform"
          style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            color: 'var(--ink-muted)',
          }}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute right-0 top-full mt-2 z-50 w-[230px] rounded-xl overflow-hidden"
          style={{
            backgroundColor: 'var(--surface-overlay)',
            border: '1px solid var(--line-focus)',
            boxShadow: 'var(--shadow-card-lg)',
          }}
          role="listbox"
        >
          {/* Dark group */}
          <GroupLabel label="Dark" icon={<Moon className="h-3 w-3" />} />
          {DARK_THEMES.map(opt => (
            <ThemeRow key={opt.id} opt={opt} current={theme} onSelect={id => { setTheme(id); setOpen(false); }} />
          ))}

          {/* Divider */}
          <div className="mx-3 my-1" style={{ height: '1px', backgroundColor: 'var(--line)' }} />

          {/* Light group */}
          <GroupLabel label="Light / White" icon={<Sun className="h-3 w-3" />} />
          {LIGHT_THEMES.map(opt => (
            <ThemeRow key={opt.id} opt={opt} current={theme} onSelect={id => { setTheme(id); setOpen(false); }} />
          ))}

          <div className="h-1.5" />
        </div>
      )}
    </div>
  );
}

function GroupLabel({ label, icon }: { label: string; icon: React.ReactNode }) {
  return (
    <p
      className="flex items-center gap-1.5 px-3 pt-2.5 pb-1 text-[10px] font-bold uppercase tracking-widest select-none"
      style={{ color: 'var(--ink-muted)' }}
    >
      <span style={{ color: 'var(--ink-muted)' }}>{icon}</span>
      {label}
    </p>
  );
}

function ThemeRow({
  opt, current, onSelect,
}: {
  opt: ThemeOption;
  current: Theme;
  onSelect: (id: Theme) => void;
}) {
  const isActive = current === opt.id;
  return (
    <button
      onClick={() => onSelect(opt.id)}
      className="w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors"
      style={{
        backgroundColor: isActive ? 'var(--brand-subtle)' : 'transparent',
        color: isActive ? 'var(--brand-text)' : 'var(--ink-secondary)',
      }}
      onMouseEnter={e => {
        if (!isActive) e.currentTarget.style.backgroundColor = 'var(--surface-raised)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.backgroundColor = isActive ? 'var(--brand-subtle)' : 'transparent';
      }}
      role="option"
      aria-selected={isActive}
    >
      {/* Dual swatch */}
      <span className="relative flex h-5 w-7 shrink-0 rounded overflow-hidden"
            style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '4px' }}>
        <span className="flex-1" style={{ backgroundColor: opt.swatch }} />
        <span className="w-2 shrink-0" style={{ backgroundColor: opt.accent }} />
      </span>
      <span className="flex-1 text-left">
        <span className="block font-semibold" style={{ color: isActive ? 'var(--brand-text)' : 'var(--ink-primary)' }}>
          {opt.label}
        </span>
        <span className="block text-[10px] mt-0.5" style={{ color: 'var(--ink-muted)' }}>
          {opt.description}
        </span>
      </span>
      {isActive && (
        <Check className="h-3 w-3 shrink-0" style={{ color: 'var(--brand)' }} />
      )}
    </button>
  );
}
