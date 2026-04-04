import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ModeSelector } from '../ModeSelector'

describe('ModeSelector', () => {
  it('renders all three mode buttons', () => {
    render(<ModeSelector currentMode="smb" onModeChange={() => {}} />)
    expect(screen.getByText('Firm')).toBeInTheDocument()
    expect(screen.getByText('SMB')).toBeInTheDocument()
    expect(screen.getByText('Autonomous')).toBeInTheDocument()
  })

  it('calls onModeChange with correct mode when clicked', () => {
    const onChange = vi.fn()
    render(<ModeSelector currentMode="smb" onModeChange={onChange} />)
    fireEvent.click(screen.getByText('Firm'))
    expect(onChange).toHaveBeenCalledWith('firm')
    fireEvent.click(screen.getByText('Autonomous'))
    expect(onChange).toHaveBeenCalledWith('autonomous')
  })

  it('highlights the current mode button', () => {
    render(<ModeSelector currentMode="firm" onModeChange={() => {}} />)
    const firmBtn = screen.getByText('Firm').closest('button')
    expect(firmBtn?.className).toContain('bg-white')
  })
})
