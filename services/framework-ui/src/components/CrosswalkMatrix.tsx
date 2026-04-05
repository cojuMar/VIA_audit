import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import type { CrosswalkPair } from '../types'

interface CrosswalkMatrixProps {
  tenantId: string
}

type TooltipState = {
  x: number
  y: number
  text: string
} | null

function cellColor(pairs: number): string {
  if (pairs === 0) return '#ffffff'
  if (pairs <= 5) return '#bfdbfe'
  if (pairs <= 15) return '#60a5fa'
  return '#1d4ed8'
}

function cellTextColor(pairs: number): string {
  if (pairs >= 16) return '#ffffff'
  return '#1e3a8a'
}

export function CrosswalkMatrix({ tenantId }: CrosswalkMatrixProps) {
  const [tooltip, setTooltip] = useState<TooltipState>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['crosswalk', tenantId],
    queryFn: () => api.getCrosswalk(tenantId),
  })

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading crosswalk data...</div>
  }

  const pairs: CrosswalkPair[] = data?.pairs ?? []

  // Gather unique framework names
  const frameworkSet = new Set<string>()
  pairs.forEach(p => {
    frameworkSet.add(p.framework_a)
    frameworkSet.add(p.framework_b)
  })
  const frameworks = Array.from(frameworkSet).sort()

  if (frameworks.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-400">
        <div className="text-4xl">&#x26F6;</div>
        <p className="text-sm">Activate 2 or more frameworks to see crosswalk coverage</p>
      </div>
    )
  }

  // Build lookup map
  const pairMap = new Map<string, number>()
  pairs.forEach(p => {
    pairMap.set(`${p.framework_a}||${p.framework_b}`, p.crosswalk_control_pairs)
    pairMap.set(`${p.framework_b}||${p.framework_a}`, p.crosswalk_control_pairs)
  })

  function getCellValue(a: string, b: string): number {
    if (a === b) return -1
    return pairMap.get(`${a}||${b}`) ?? 0
  }

  return (
    <div className="space-y-6" onMouseLeave={() => setTooltip(null)}>
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Crosswalk Matrix</h2>
        <p className="text-sm text-gray-500 mt-1">
          Control overlap between your active compliance frameworks
        </p>
      </div>

      {/* Legend */}
      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-sm text-indigo-800">
        <p className="font-medium mb-1">Test Once, Comply Many</p>
        <p className="text-indigo-600">
          When you provide evidence for a control in Framework A, VIA automatically credits the equivalent control in Framework B — no duplicate work required.
        </p>
      </div>

      {/* Color legend */}
      <div className="flex items-center gap-6 text-xs text-gray-500">
        <span className="font-medium text-gray-700">Coverage:</span>
        {[
          { label: '0 pairs', color: '#ffffff', border: true },
          { label: '1–5 pairs', color: '#bfdbfe', border: false },
          { label: '6–15 pairs', color: '#60a5fa', border: false },
          { label: '16+ pairs', color: '#1d4ed8', border: false },
        ].map(({ label, color, border }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div
              className="w-4 h-4 rounded"
              style={{ background: color, border: border ? '1px solid #e5e7eb' : undefined }}
            />
            <span>{label}</span>
          </div>
        ))}
      </div>

      {/* Matrix */}
      <div className="overflow-x-auto relative">
        <table className="border-collapse text-xs">
          <thead>
            <tr>
              <th className="w-32 p-2" />
              {frameworks.map(fw => (
                <th
                  key={fw}
                  className="p-2 text-left font-medium text-gray-600 whitespace-nowrap max-w-[120px]"
                  style={{ writingMode: 'vertical-lr', transform: 'rotate(180deg)', height: '120px' }}
                >
                  <span className="truncate block max-w-[110px]">{fw}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {frameworks.map(fwA => (
              <tr key={fwA}>
                <td className="p-2 font-medium text-gray-700 whitespace-nowrap pr-3 text-right max-w-[130px]">
                  <span className="block truncate">{fwA}</span>
                </td>
                {frameworks.map(fwB => {
                  const val = getCellValue(fwA, fwB)
                  const isDiag = fwA === fwB
                  return (
                    <td
                      key={fwB}
                      className="p-0 border border-gray-100 relative"
                      onMouseEnter={e => {
                        if (isDiag) return
                        setTooltip({
                          x: e.clientX,
                          y: e.clientY,
                          text: val > 0
                            ? `${val} control${val !== 1 ? 's' : ''} in ${fwA} satisfy requirements in ${fwB}`
                            : `No crosswalk overlap between ${fwA} and ${fwB}`,
                        })
                      }}
                      onMouseMove={e => {
                        if (isDiag || !tooltip) return
                        setTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null)
                      }}
                    >
                      <div
                        className="w-10 h-10 flex items-center justify-center font-medium transition-opacity hover:opacity-80"
                        style={{
                          background: isDiag ? '#f9fafb' : cellColor(val),
                          color: isDiag ? '#d1d5db' : cellTextColor(val),
                        }}
                      >
                        {isDiag ? '—' : val > 0 ? val : ''}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="fixed z-50 bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-xl max-w-xs pointer-events-none"
            style={{ left: tooltip.x + 12, top: tooltip.y - 10 }}
          >
            {tooltip.text}
          </div>
        )}
      </div>
    </div>
  )
}
