import { useState, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, ChevronLeft, ChevronRight, CheckCircle } from 'lucide-react'
import { api } from '../api'
import type { CalendarEvent } from '../types'

interface ComplianceCalendarProps {
  tenantId: string
}

const EVENT_TYPE_COLORS: Record<CalendarEvent['event_type'], string> = {
  filing_deadline: 'bg-red-500',
  cert_renewal: 'bg-purple-500',
  control_review: 'bg-blue-500',
  periodic_activity: 'bg-amber-500',
  audit_window: 'bg-green-500',
}

const EVENT_TYPE_LABELS: Record<CalendarEvent['event_type'], string> = {
  filing_deadline: 'Filing Deadline',
  cert_renewal: 'Cert Renewal',
  control_review: 'Control Review',
  periodic_activity: 'Periodic Activity',
  audit_window: 'Audit Window',
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function urgencyBadge(daysUntil: number): React.ReactNode | null {
  if (daysUntil <= 7) {
    return <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-red-500 text-white font-bold">URGENT</span>
  }
  if (daysUntil <= 30) {
    return <span className="inline-block text-xs px-1.5 py-0.5 rounded bg-amber-400 text-white font-semibold">SOON</span>
  }
  return null
}

export function ComplianceCalendar({ tenantId }: ComplianceCalendarProps) {
  const today = new Date()
  const [viewYear, setViewYear] = useState(today.getFullYear())
  const [viewMonth, setViewMonth] = useState(today.getMonth())
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [rebuilding, setRebuilding] = useState(false)

  const queryClient = useQueryClient()

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['calendar', tenantId],
    queryFn: () => api.getCalendar(tenantId),
  })

  async function handleRebuildCalendar() {
    setRebuilding(true)
    try {
      const res = await fetch(`/api/tenants/${tenantId}/calendar/rebuild`, {
        method: 'POST',
        headers: { 'X-Tenant-ID': tenantId },
      })
      if (res.ok) {
        queryClient.invalidateQueries({ queryKey: ['calendar', tenantId] })
      }
    } finally {
      setRebuilding(false)
    }
  }

  // Build calendar grid
  const { calendarDays } = useMemo(() => {
    const firstDay = new Date(viewYear, viewMonth, 1)
    const lastDay = new Date(viewYear, viewMonth + 1, 0)
    const startOffset = firstDay.getDay()

    const days: Array<{ date: Date | null; dateStr: string | null }> = []
    // Fill leading blanks
    for (let i = 0; i < startOffset; i++) {
      days.push({ date: null, dateStr: null })
    }
    // Fill days
    for (let d = 1; d <= lastDay.getDate(); d++) {
      const date = new Date(viewYear, viewMonth, d)
      const dateStr = date.toISOString().slice(0, 10)
      days.push({ date, dateStr })
    }
    // Fill trailing blanks to complete 6 rows
    while (days.length < 42) {
      days.push({ date: null, dateStr: null })
    }
    return { calendarDays: days }
  }, [viewYear, viewMonth])

  // Group events by date
  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    events.forEach(ev => {
      const d = ev.due_date.slice(0, 10)
      if (!map.has(d)) map.set(d, [])
      map.get(d)!.push(ev)
    })
    return map
  }, [events])

  const selectedEvents = selectedDate ? (eventsByDate.get(selectedDate) ?? []) : []

  // Next 10 upcoming events
  const upcomingEvents = useMemo(() => {
    return [...events]
      .filter(e => !e.is_completed && e.days_until_due >= 0)
      .sort((a, b) => a.days_until_due - b.days_until_due)
      .slice(0, 10)
  }, [events])

  function prevMonth() {
    if (viewMonth === 0) { setViewMonth(11); setViewYear(y => y - 1) }
    else setViewMonth(m => m - 1)
  }
  function nextMonth() {
    if (viewMonth === 11) { setViewMonth(0); setViewYear(y => y + 1) }
    else setViewMonth(m => m + 1)
  }

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">Loading calendar...</div>
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Compliance Calendar</h2>
          <p className="text-sm text-gray-500">{events.length} scheduled events</p>
        </div>
        <button
          onClick={handleRebuildCalendar}
          disabled={rebuilding}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${rebuilding ? 'animate-spin' : ''}`} />
          Rebuild Calendar
        </button>
      </div>

      {/* Event type legend */}
      <div className="flex flex-wrap gap-4 text-xs">
        {(Object.entries(EVENT_TYPE_LABELS) as [CalendarEvent['event_type'], string][]).map(([type, label]) => (
          <div key={type} className="flex items-center gap-1.5">
            <span className={`w-3 h-3 rounded-full ${EVENT_TYPE_COLORS[type]}`} />
            <span className="text-gray-600">{label}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar grid */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {/* Month navigation */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <button onClick={prevMonth} className="p-1 rounded hover:bg-gray-100 transition-colors">
              <ChevronLeft className="w-5 h-5 text-gray-500" />
            </button>
            <h3 className="font-semibold text-gray-800">{MONTH_NAMES[viewMonth]} {viewYear}</h3>
            <button onClick={nextMonth} className="p-1 rounded hover:bg-gray-100 transition-colors">
              <ChevronRight className="w-5 h-5 text-gray-500" />
            </button>
          </div>

          {/* Day headers */}
          <div className="grid grid-cols-7 border-b border-gray-100">
            {DAY_NAMES.map(d => (
              <div key={d} className="py-2 text-center text-xs font-medium text-gray-400">{d}</div>
            ))}
          </div>

          {/* Calendar cells */}
          <div className="grid grid-cols-7">
            {calendarDays.map((cell, idx) => {
              const cellEvents = cell.dateStr ? (eventsByDate.get(cell.dateStr) ?? []) : []
              const isToday = cell.dateStr === today.toISOString().slice(0, 10)
              const isSelected = cell.dateStr === selectedDate

              return (
                <div
                  key={idx}
                  onClick={() => cell.dateStr && setSelectedDate(prev => prev === cell.dateStr ? null : cell.dateStr)}
                  className={`min-h-[72px] border-b border-r border-gray-50 p-1.5 ${cell.date ? 'cursor-pointer hover:bg-gray-50' : ''} ${isSelected ? 'bg-blue-50' : ''}`}
                >
                  {cell.date && (
                    <>
                      <div className={`w-6 h-6 flex items-center justify-center rounded-full text-xs font-medium mb-1 ${isToday ? 'bg-blue-600 text-white' : 'text-gray-600'}`}>
                        {cell.date.getDate()}
                      </div>
                      <div className="flex flex-wrap gap-0.5">
                        {cellEvents.slice(0, 3).map((ev, i) => (
                          <span
                            key={i}
                            className={`w-2 h-2 rounded-full ${EVENT_TYPE_COLORS[ev.event_type]} ${ev.is_completed ? 'opacity-40' : ''}`}
                            title={ev.title}
                          />
                        ))}
                        {cellEvents.length > 3 && (
                          <span className="text-xs text-gray-400">+{cellEvents.length - 3}</span>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Right panel */}
        <div className="space-y-4">
          {/* Selected date events */}
          {selectedDate && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 bg-blue-50">
                <h4 className="text-sm font-semibold text-blue-800">
                  {new Date(selectedDate + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
                </h4>
              </div>
              <div className="divide-y divide-gray-50 max-h-56 overflow-y-auto">
                {selectedEvents.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-6">No events on this date.</p>
                ) : selectedEvents.map((ev, i) => (
                  <div key={i} className="px-4 py-3 space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full shrink-0 ${EVENT_TYPE_COLORS[ev.event_type]}`} />
                        <p className="text-xs font-medium text-gray-800">{ev.title}</p>
                      </div>
                      {ev.is_completed && <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />}
                    </div>
                    <p className="text-xs text-gray-500 ml-4">{ev.framework_name}</p>
                    {ev.description && <p className="text-xs text-gray-400 ml-4 line-clamp-2">{ev.description}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upcoming events */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100">
              <h4 className="text-sm font-semibold text-gray-700">Upcoming Events</h4>
            </div>
            <div className="divide-y divide-gray-50 max-h-80 overflow-y-auto">
              {upcomingEvents.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">No upcoming events.</p>
              ) : upcomingEvents.map((ev, i) => (
                <div key={i} className="px-4 py-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${EVENT_TYPE_COLORS[ev.event_type]}`} />
                      <p className="text-xs font-medium text-gray-800 truncate max-w-[150px]">{ev.title}</p>
                    </div>
                    {urgencyBadge(ev.days_until_due)}
                  </div>
                  <p className="text-xs text-gray-400">
                    {ev.framework_name} · in {ev.days_until_due} day{ev.days_until_due !== 1 ? 's' : ''}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
