import { useState } from 'react'
import { ModeSelector } from './components/ModeSelector'
import { FirmDashboard } from './components/FirmDashboard'
import { SMBDashboard } from './components/SMBDashboard'
import { AutonomousDashboard } from './components/AutonomousDashboard'
import { ThemeProvider } from './components/ThemeProvider'
import type { Mode, Framework } from './types'

export default function App() {
  const [mode, setMode] = useState<Mode>('smb')
  const [framework, setFramework] = useState<Framework>('soc2')

  return (
    <ThemeProvider>
      <div className="min-h-screen bg-gray-50">
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center">
              <span className="text-white font-bold text-sm">A</span>
            </div>
            <span className="font-semibold text-gray-900 text-lg">Aegis Compliance</span>
          </div>
          <div className="flex items-center gap-4">
            <select
              value={framework}
              onChange={e => setFramework(e.target.value as Framework)}
              className="text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="soc2">SOC 2</option>
              <option value="iso27001">ISO 27001</option>
              <option value="pci_dss">PCI DSS</option>
            </select>
            <ModeSelector currentMode={mode} onModeChange={setMode} />
          </div>
        </header>

        <main className="p-6">
          {mode === 'firm' && <FirmDashboard framework={framework} />}
          {mode === 'smb' && <SMBDashboard framework={framework} />}
          {mode === 'autonomous' && <AutonomousDashboard framework={framework} />}
        </main>
      </div>
    </ThemeProvider>
  )
}
