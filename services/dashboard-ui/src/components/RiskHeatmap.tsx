import { clsx } from 'clsx'

interface HeatmapCell {
  category: string
  avg_risk: number
  count: number
}

interface HeatmapRow {
  tenant_id: string
  label: string
  categories: HeatmapCell[]
}

interface RiskHeatmapProps {
  data: HeatmapRow[]
}

function riskColor(value: number): string {
  if (value >= 0.8) return 'bg-red-600 text-white'
  if (value >= 0.6) return 'bg-orange-400 text-white'
  if (value >= 0.4) return 'bg-amber-300 text-gray-900'
  if (value >= 0.2) return 'bg-yellow-200 text-gray-900'
  return 'bg-green-100 text-gray-700'
}

/** Categorical band so the cell doesn't communicate severity by color alone. */
function riskBand(value: number): 'Critical' | 'High' | 'Medium' | 'Low' | 'Minimal' {
  if (value >= 0.8) return 'Critical'
  if (value >= 0.6) return 'High'
  if (value >= 0.4) return 'Medium'
  if (value >= 0.2) return 'Low'
  return 'Minimal'
}

export function RiskHeatmap({ data }: RiskHeatmapProps) {
  if (!data.length) {
    return <div className="text-sm text-gray-400 text-center py-8">No data available</div>
  }

  // Collect all unique categories
  const allCategories = Array.from(
    new Set(data.flatMap(row => row.categories.map(c => c.category)))
  ).sort()

  return (
    <div className="overflow-x-auto">
      <table
        className="w-full text-xs border-collapse"
        aria-label="Risk heatmap by client and category"
      >
        <thead>
          <tr>
            <th scope="col" className="text-left py-2 pr-4 font-medium text-gray-500 whitespace-nowrap">Client</th>
            {allCategories.map(cat => (
              <th scope="col" key={cat} className="px-2 py-2 font-medium text-gray-500 whitespace-nowrap">
                {cat.replace('_', ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map(row => {
            const catMap = Object.fromEntries(row.categories.map(c => [c.category, c]))
            return (
              <tr key={row.tenant_id}>
                <td className="py-1 pr-4 font-medium text-gray-700 whitespace-nowrap">
                  {row.label}
                </td>
                {allCategories.map(cat => {
                  const cell = catMap[cat]
                  return (
                    <td key={cat} className="px-1 py-1">
                      {cell ? (
                        <div
                          role="img"
                          aria-label={`${riskBand(cell.avg_risk)} risk — ${(cell.avg_risk * 100).toFixed(0)} percent across ${cell.count} events`}
                          className={clsx(
                            'rounded px-2 py-1.5 text-center font-medium cursor-default',
                            riskColor(cell.avg_risk)
                          )}
                          title={`${riskBand(cell.avg_risk)} — ${(cell.avg_risk * 100).toFixed(0)}% (${cell.count} events)`}
                        >
                          <span className="block text-[10px] uppercase tracking-wide opacity-80">
                            {riskBand(cell.avg_risk)}
                          </span>
                          {(cell.avg_risk * 100).toFixed(0)}%
                        </div>
                      ) : (
                        <div
                          aria-label="No data"
                          className="bg-gray-100 rounded px-2 py-1.5 text-center text-gray-400"
                        >
                          —
                        </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
