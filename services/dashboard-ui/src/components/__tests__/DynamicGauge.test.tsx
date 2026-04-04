import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DynamicGauge } from '../DynamicGauge'
import type { Gauge } from '../../types'

const makeGauge = (value: number): Gauge => ({
  id: 'test_gauge',
  label: 'Test Gauge',
  value,
  unit: 'score',
  thresholds: { warning: 0.6, critical: 0.4 },
})

describe('DynamicGauge', () => {
  it('renders the gauge label', () => {
    render(<DynamicGauge gauge={makeGauge(0.85)} />)
    expect(screen.getByText('Test Gauge')).toBeInTheDocument()
  })

  it('shows Healthy status for score >= warning threshold', () => {
    render(<DynamicGauge gauge={makeGauge(0.85)} />)
    expect(screen.getByText('Healthy')).toBeInTheDocument()
  })

  it('shows Warning status for score between critical and warning', () => {
    render(<DynamicGauge gauge={makeGauge(0.5)} />)
    expect(screen.getByText('Warning')).toBeInTheDocument()
  })

  it('shows Critical status for score below critical threshold', () => {
    render(<DynamicGauge gauge={makeGauge(0.3)} />)
    expect(screen.getByText('Critical')).toBeInTheDocument()
  })

  it('displays percentage value', () => {
    render(<DynamicGauge gauge={makeGauge(0.75)} />)
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('rounds percentage correctly', () => {
    render(<DynamicGauge gauge={makeGauge(0.999)} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
  })
})
