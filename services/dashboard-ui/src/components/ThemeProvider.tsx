import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { WhiteLabelConfig } from '../types'
import { api } from '../api'

const defaultTheme: WhiteLabelConfig = {
  firm_name: 'VIA Compliance',
  primary_color: '#1a56db',
  secondary_color: '#7e3af2',
  accent_color: '#0e9f6e',
  font_family: 'Inter',
}

const ThemeContext = createContext<WhiteLabelConfig>(defaultTheme)

export function useTheme() {
  return useContext(ThemeContext)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<WhiteLabelConfig>(defaultTheme)

  useEffect(() => {
    api.getWhiteLabel().then(config => {
      setTheme(config)
      // Apply CSS custom properties for white-labeling
      document.documentElement.style.setProperty('--color-brand-primary', config.primary_color)
      document.documentElement.style.setProperty('--color-brand-secondary', config.secondary_color)
      document.documentElement.style.setProperty('--color-brand-accent', config.accent_color)
      document.title = `${config.firm_name} — Compliance Platform`
    }).catch(() => {/* use defaults */})
  }, [])

  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>
}
