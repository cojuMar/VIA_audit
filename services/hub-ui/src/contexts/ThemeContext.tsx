import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Theme = 'dark' | 'light' | 'corporate' | 'professional';

export const ALL_THEMES: Theme[] = ['dark', 'light', 'corporate', 'professional'];

/** Returns true for any non-dark theme */
export function isLightTheme(t: Theme): boolean {
  return t !== 'dark';
}

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  isLight: boolean;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark',
  setTheme: () => {},
  isLight: false,
});

const STORAGE_KEY = 'via-theme-v3';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
    return stored && (ALL_THEMES as string[]).includes(stored) ? stored : 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  function setTheme(t: Theme) {
    setThemeState(t);
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isLight: isLightTheme(theme) }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
