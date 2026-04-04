import { Building2, Shield, Cpu } from 'lucide-react'
import { clsx } from 'clsx'
import type { Mode } from '../types'

interface ModeSelectorProps {
  currentMode: Mode
  onModeChange: (mode: Mode) => void
}

const MODES: { id: Mode; label: string; icon: typeof Building2; description: string }[] = [
  { id: 'firm', label: 'Firm', icon: Building2, description: 'Multi-client portfolio view' },
  { id: 'smb', label: 'SMB', icon: Shield, description: 'Evidence & audit hub' },
  { id: 'autonomous', label: 'Autonomous', icon: Cpu, description: 'Real-time health monitoring' },
]

export function ModeSelector({ currentMode, onModeChange }: ModeSelectorProps) {
  return (
    <div className="flex rounded-lg border border-gray-200 bg-gray-100 p-1 gap-1">
      {MODES.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onModeChange(id)}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all',
            currentMode === id
              ? 'bg-white text-brand-600 shadow-sm'
              : 'text-gray-600 hover:text-gray-900'
          )}
        >
          <Icon size={14} />
          {label}
        </button>
      ))}
    </div>
  )
}
