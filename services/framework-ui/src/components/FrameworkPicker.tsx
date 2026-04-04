import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Shield, Lock, DollarSign, Cpu, Leaf, Globe, CheckCircle, XCircle, Plus } from 'lucide-react'
import { api } from '../api'
import type { ComplianceFramework } from '../types'

interface FrameworkPickerProps {
  tenantId: string
  onFrameworkToggled?: (slug: string, active: boolean) => void
}

type Category = ComplianceFramework['category'] | 'all'

const CATEGORY_COLORS: Record<ComplianceFramework['category'], string> = {
  security: 'bg-blue-100 text-blue-700 border-blue-200',
  privacy: 'bg-purple-100 text-purple-700 border-purple-200',
  financial: 'bg-green-100 text-green-700 border-green-200',
  operational: 'bg-orange-100 text-orange-700 border-orange-200',
  ai: 'bg-indigo-100 text-indigo-700 border-indigo-200',
  sustainability: 'bg-teal-100 text-teal-700 border-teal-200',
  'sector-specific': 'bg-rose-100 text-rose-700 border-rose-200',
}

const CATEGORY_ICONS: Record<ComplianceFramework['category'], React.ReactNode> = {
  security: <Shield className="w-4 h-4" />,
  privacy: <Lock className="w-4 h-4" />,
  financial: <DollarSign className="w-4 h-4" />,
  operational: <Globe className="w-4 h-4" />,
  ai: <Cpu className="w-4 h-4" />,
  sustainability: <Leaf className="w-4 h-4" />,
  'sector-specific': <Globe className="w-4 h-4" />,
}

const COST_TIER_COLORS: Record<string, string> = {
  low: 'bg-green-50 text-green-600 border-green-100',
  medium: 'bg-amber-50 text-amber-600 border-amber-100',
  high: 'bg-red-50 text-red-600 border-red-100',
}

const CATEGORIES: Category[] = ['all', 'security', 'privacy', 'financial', 'operational', 'ai', 'sustainability', 'sector-specific']

export function FrameworkPicker({ tenantId, onFrameworkToggled }: FrameworkPickerProps) {
  const [selectedCategory, setSelectedCategory] = useState<Category>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedSlug, setExpandedSlug] = useState<string | null>(null)

  const queryClient = useQueryClient()

  const { data: allFrameworks = [], isLoading: loadingAll } = useQuery({
    queryKey: ['frameworks'],
    queryFn: () => api.getFrameworks(),
  })

  const { data: tenantFrameworks = [], isLoading: loadingTenant } = useQuery({
    queryKey: ['tenant-frameworks', tenantId],
    queryFn: () => api.getTenantFrameworks(tenantId),
  })

  const { data: expandedFramework } = useQuery({
    queryKey: ['framework-detail', expandedSlug],
    queryFn: () => expandedSlug ? api.getFramework(expandedSlug) : null,
    enabled: !!expandedSlug,
  })

  const activateMutation = useMutation({
    mutationFn: (slug: string) => api.activateFramework(tenantId, slug),
    onSuccess: (_data, slug) => {
      queryClient.invalidateQueries({ queryKey: ['tenant-frameworks', tenantId] })
      onFrameworkToggled?.(slug, true)
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: (slug: string) => api.deactivateFramework(tenantId, slug),
    onSuccess: (_data, slug) => {
      queryClient.invalidateQueries({ queryKey: ['tenant-frameworks', tenantId] })
      onFrameworkToggled?.(slug, false)
    },
  })

  const activeSlugSet = new Set(tenantFrameworks.map(f => f.slug))

  const filtered = allFrameworks.filter(fw => {
    const matchesCategory = selectedCategory === 'all' || fw.category === selectedCategory
    const matchesSearch = fw.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      fw.issuing_body.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesCategory && matchesSearch
  })

  const activeCount = activeSlugSet.size
  const isLoading = loadingAll || loadingTenant

  function handleToggle(fw: ComplianceFramework) {
    const isActive = activeSlugSet.has(fw.slug)
    if (isActive) {
      deactivateMutation.mutate(fw.slug)
    } else {
      activateMutation.mutate(fw.slug)
    }
  }

  function handleCardClick(slug: string) {
    setExpandedSlug(prev => prev === slug ? null : slug)
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading framework catalog...</div>
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Framework Library</h2>
          <p className="text-sm text-gray-500">{allFrameworks.length} frameworks available · {activeCount} active</p>
        </div>
        {activeCount >= 2 && (
          <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-2 text-sm text-indigo-700">
            <CheckCircle className="w-4 h-4 shrink-0" />
            <span>Test Once, Comply Many — crosswalk active across {activeCount} frameworks</span>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search frameworks..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                selectedCategory === cat
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
              }`}
            >
              {cat === 'all' ? 'All' : cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Framework Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filtered.map(fw => {
          const isActive = activeSlugSet.has(fw.slug)
          const isExpanded = expandedSlug === fw.slug
          const isPending = activateMutation.isPending || deactivateMutation.isPending

          return (
            <div
              key={fw.slug}
              className={`bg-white rounded-xl border shadow-sm transition-all cursor-pointer ${
                isActive ? 'border-blue-300 ring-1 ring-blue-200' : 'border-gray-200 hover:border-gray-300'
              } ${isExpanded ? 'col-span-1' : ''}`}
              onClick={() => handleCardClick(fw.slug)}
            >
              <div className="p-4 space-y-3">
                {/* Category badge + cost tier */}
                <div className="flex items-center justify-between">
                  <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${CATEGORY_COLORS[fw.category]}`}>
                    {CATEGORY_ICONS[fw.category]}
                    {fw.category}
                  </span>
                  {fw.metadata.cost_tier && (
                    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${COST_TIER_COLORS[fw.metadata.cost_tier]}`}>
                      {fw.metadata.cost_tier} cost
                    </span>
                  )}
                </div>

                {/* Name + version */}
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 leading-tight">{fw.name}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">{fw.issuing_body} · v{fw.version}</p>
                </div>

                {/* Description */}
                <p className="text-xs text-gray-500 line-clamp-2">{fw.description}</p>

                {/* Expanded detail */}
                {isExpanded && expandedFramework && (
                  <div className="border-t border-gray-100 pt-3 space-y-2">
                    <p className="text-xs font-medium text-gray-700">
                      {expandedFramework.controls?.length ?? 0} controls
                    </p>
                    {expandedFramework.controls && expandedFramework.controls.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {[...new Set(expandedFramework.controls.map(c => c.domain))].slice(0, 6).map(domain => (
                          <span key={domain} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                            {domain}
                          </span>
                        ))}
                      </div>
                    )}
                    {fw.metadata.geographic_scope && (
                      <p className="text-xs text-gray-500">Scope: {fw.metadata.geographic_scope}</p>
                    )}
                    {fw.metadata.renewal_period_days && (
                      <p className="text-xs text-gray-500">Renewal: every {fw.metadata.renewal_period_days} days</p>
                    )}
                  </div>
                )}

                {/* Toggle button */}
                <div className="pt-1" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => handleToggle(fw)}
                    disabled={isPending}
                    className={`w-full flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-50 ${
                      isActive
                        ? 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100'
                        : 'bg-blue-50 text-blue-600 border-blue-200 hover:bg-blue-100'
                    }`}
                  >
                    {isActive ? (
                      <><XCircle className="w-3.5 h-3.5" /> Deactivate</>
                    ) : (
                      <><Plus className="w-3.5 h-3.5" /> Activate</>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          No frameworks match your filters.
        </div>
      )}
    </div>
  )
}
