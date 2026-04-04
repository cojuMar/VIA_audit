import { RadialBarChart, RadialBar, PolarAngleAxis } from 'recharts'
import { clsx } from 'clsx'
import type { Gauge } from '../types'

interface DynamicGaugeProps {
  gauge: Gauge
}

function getColor(value: number, thresholds: { warning: number; critical: number }): string {
  if (value < thresholds.critical) return '#ef4444'   // red
  if (value < thresholds.warning) return '#f59e0b'    // amber
  return '#10b981'                                     // green
}

function getLabel(value: number, thresholds: { warning: number; critical: number }): string {
  if (value < thresholds.critical) return 'Critical'
  if (value < thresholds.warning) return 'Warning'
  return 'Healthy'
}

export function DynamicGauge({ gauge }: DynamicGaugeProps) {
  const color = getColor(gauge.value, gauge.thresholds)
  const statusLabel = getLabel(gauge.value, gauge.thresholds)
  const pct = Math.round(gauge.value * 100)

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col items-center shadow-sm">
      <div className="relative">
        <RadialBarChart
          width={120}
          height={120}
          cx={60}
          cy={60}
          innerRadius={40}
          outerRadius={55}
          data={[{ value: pct, fill: color }]}
          startAngle={180}
          endAngle={-180}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
          <RadialBar
            background={{ fill: '#f3f4f6' }}
            dataKey="value"
            cornerRadius={6}
            fill={color}
            angleAxisId={0}
          />
        </RadialBarChart>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold text-gray-900">{pct}%</span>
        </div>
      </div>
      <p className="mt-2 text-sm font-medium text-gray-700 text-center">{gauge.label}</p>
      <span
        className={clsx('mt-1 text-xs font-medium px-2 py-0.5 rounded-full', {
          'bg-green-100 text-green-700': statusLabel === 'Healthy',
          'bg-amber-100 text-amber-700': statusLabel === 'Warning',
          'bg-red-100 text-red-700': statusLabel === 'Critical',
        })}
      >
        {statusLabel}
      </span>
    </div>
  )
}
