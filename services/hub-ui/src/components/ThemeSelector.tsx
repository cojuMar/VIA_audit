import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme, type Theme } from '../contexts/ThemeContext';

const THEMES: { id: Theme; label: string; icon: typeof Sun }[] = [
  { id: 'light',   label: 'Light',   icon: Sun     },
  { id: 'neutral', label: 'Neutral', icon: Monitor },
  { id: 'dark',    label: 'Dark',    icon: Moon    },
];

export default function ThemeSelector() {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className="flex items-center rounded-lg p-0.5 gap-0.5"
      style={{ backgroundColor: 'var(--surface-overlay)', border: '1px solid var(--line-focus)' }}
      title="Switch theme"
    >
      {THEMES.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setTheme(id)}
          title={label}
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-all"
          style={{
            backgroundColor: theme === id ? 'var(--brand)' : 'transparent',
            color: theme === id ? '#fff' : 'var(--ink-muted)',
          }}
        >
          <Icon className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{label}</span>
        </button>
      ))}
    </div>
  );
}
