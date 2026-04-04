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
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr>
            <th className="text-left py-2 pr-4 font-medium text-gray-500 whitespace-nowrap">Client</th>
            {allCategories.map(cat => (
              <th key={cat} className="px-2 py-2 font-medium text-gray-500 whitespace-nowrap">
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
                          className={clsx(
                            'rounded px-2 py-1.5 text-center font-medium cursor-default',
                            riskColor(cell.avg_risk)
                          )}
                          title={`Risk: ${(cell.avg_risk * 100).toFixed(0)}% (${cell.count} events)`}
                        >
                          {(cell.avg_risk * 100).toFixed(0)}%
                        </div>
                      ) : (
                        <div className="bg-gray-100 rounded px-2 py-1.5 text-center text-gray-400">—</div>
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
