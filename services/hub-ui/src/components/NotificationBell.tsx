import { useRef, useState, useEffect, type ReactNode } from 'react';
import {
  Bell, FileText, CheckCircle2, XCircle, Clock, AlertCircle,
  Users, Activity, Building2, BarChart2, X,
} from 'lucide-react';
import type { AuthUser } from '../contexts/AuthContext';
import { useNotifications, type Notification } from '../hooks/useNotifications';

// ── Type metadata ─────────────────────────────────────────────────────────────

interface TypeMeta {
  icon: ReactNode;
  color: string;
}

function getTypeMeta(type: string, severity: string): TypeMeta {
  const danger  = 'var(--status-danger)';
  const warning = 'var(--status-warning)';
  const info    = 'var(--status-info)';
  const success = 'var(--status-success)';

  const map: Record<string, TypeMeta> = {
    workpaper_assigned:    { icon: <FileText    className="h-3.5 w-3.5" />, color: info    },
    workpaper_approved:    { icon: <CheckCircle2 className="h-3.5 w-3.5" />, color: success },
    workpaper_rejected:    { icon: <XCircle     className="h-3.5 w-3.5" />, color: warning },
    pbc_due:               { icon: <Clock       className="h-3.5 w-3.5" />, color: warning },
    pbc_overdue:           { icon: <AlertCircle className="h-3.5 w-3.5" />, color: danger  },
    engagement_assigned:   { icon: <Users       className="h-3.5 w-3.5" />, color: info    },
    milestone_missed:      { icon: <Clock       className="h-3.5 w-3.5" />, color: warning },
    risk_treatment_due:    { icon: <BarChart2   className="h-3.5 w-3.5" />, color: warning },
    monitoring_finding:    { icon: <Activity    className="h-3.5 w-3.5" />, color: danger  },
    vendor_assessment_due: { icon: <Building2   className="h-3.5 w-3.5" />, color: warning },
  };

  const fallbackColor = severity === 'critical' ? danger : severity === 'warning' ? warning : info;
  return map[type] ?? { icon: <Bell className="h-3.5 w-3.5" />, color: fallbackColor };
}

// ── Time-ago helper ────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)  return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ── Tab type ──────────────────────────────────────────────────────────────────

type Tab = 'all' | 'unread';

// ── Notification item ──────────────────────────────────────────────────────────

function NotificationItem({
  n,
  onMarkRead,
}: {
  n: Notification;
  onMarkRead: (id: string) => void;
}) {
  const { icon, color } = getTypeMeta(n.type, n.severity);

  return (
    <button
      onClick={() => { if (!n.read) onMarkRead(n.id); }}
      className="w-full flex items-start gap-3 px-4 py-3 text-left transition-colors"
      style={{
        backgroundColor: n.read ? 'transparent' : 'var(--brand-subtle)',
        cursor: n.read ? 'default' : 'pointer',
        borderBottom: '1px solid var(--line)',
      }}
      onMouseEnter={e => {
        if (!n.read) e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--brand-subtle) 80%, var(--surface-raised))';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.backgroundColor = n.read ? 'transparent' : 'var(--brand-subtle)';
      }}
    >
      {/* Type icon */}
      <span
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full mt-0.5"
        style={{ backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`, color }}
      >
        {icon}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p
            className="text-xs font-semibold leading-tight"
            style={{ color: n.read ? 'var(--ink-secondary)' : 'var(--ink-primary)' }}
          >
            {n.title}
          </p>
          {!n.read && (
            <span
              className="shrink-0 h-2 w-2 rounded-full mt-1"
              style={{ backgroundColor: color }}
            />
          )}
        </div>
        {n.body && (
          <p
            className="text-[11px] leading-snug mt-0.5 line-clamp-2"
            style={{ color: 'var(--ink-muted)' }}
          >
            {n.body}
          </p>
        )}
        <p className="text-[10px] mt-1" style={{ color: 'var(--ink-muted)' }}>
          {timeAgo(n.created_at)}
        </p>
      </div>
    </button>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ tab }: { tab: Tab }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
      <Bell className="h-8 w-8 mb-3" style={{ color: 'var(--ink-muted)' }} />
      <p className="text-sm font-medium" style={{ color: 'var(--ink-secondary)' }}>
        {tab === 'unread' ? 'All caught up' : 'No notifications'}
      </p>
      <p className="text-[11px] mt-1" style={{ color: 'var(--ink-muted)' }}>
        {tab === 'unread'
          ? 'No unread notifications right now.'
          : 'Notifications will appear here when there is activity.'}
      </p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  user: AuthUser;
}

export default function NotificationBell({ user }: Props) {
  const [open, setOpen]   = useState(false);
  const [tab, setTab]     = useState<Tab>('all');
  const containerRef      = useRef<HTMLDivElement>(null);

  const { notifications, unreadCount, isLoading, markRead, markAllRead } =
    useNotifications(user);

  // Close on outside click / Escape
  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const displayed = tab === 'unread'
    ? notifications.filter(n => !n.read)
    : notifications;

  const hasUnread = unreadCount > 0;

  return (
    <div ref={containerRef} className="relative">

      {/* Trigger */}
      <button
        onClick={() => setOpen(v => !v)}
        aria-label={`Notifications${hasUnread ? ` — ${unreadCount} unread` : ''}`}
        aria-expanded={open}
        className="relative flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
        style={{
          backgroundColor: open ? 'var(--brand-subtle)' : 'var(--surface-overlay)',
          border: `1px solid ${open ? 'var(--brand)' : 'var(--line-focus)'}`,
          color: 'var(--ink-secondary)',
        }}
        onMouseEnter={e => {
          if (!open) e.currentTarget.style.backgroundColor = 'var(--surface-raised)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.backgroundColor = open ? 'var(--brand-subtle)' : 'var(--surface-overlay)';
        }}
      >
        <Bell className="h-4 w-4" />

        {/* Badge */}
        {hasUnread && (
          <span
            className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-bold text-white leading-none"
            style={{ backgroundColor: 'var(--status-danger)' }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div
          className="absolute right-0 top-full mt-2 z-50 overflow-hidden rounded-xl"
          style={{
            width: '360px',
            backgroundColor: 'var(--surface-overlay)',
            border: '1px solid var(--line-focus)',
            boxShadow: 'var(--shadow-card-lg)',
          }}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: '1px solid var(--line)' }}
          >
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--ink-primary)' }}>
                Notifications
              </h3>
              {isLoading && (
                <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none"
                     style={{ color: 'var(--ink-muted)' }}>
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
              )}
            </div>
            <div className="flex items-center gap-2">
              {hasUnread && (
                <button
                  onClick={markAllRead}
                  className="text-[11px] font-medium transition-colors"
                  style={{ color: 'var(--brand-text)' }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = '0.7'; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = '1'; }}
                >
                  Mark all read
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="flex h-5 w-5 items-center justify-center rounded transition-colors"
                style={{ color: 'var(--ink-muted)' }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--ink-primary)'; }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--ink-muted)'; }}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div
            className="flex gap-0"
            style={{ borderBottom: '1px solid var(--line)', padding: '0 16px' }}
          >
            {(['all', 'unread'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="relative py-2.5 px-3 text-xs font-medium transition-colors capitalize"
                style={{
                  color: tab === t ? 'var(--brand-text)' : 'var(--ink-muted)',
                  borderBottom: tab === t ? '2px solid var(--brand)' : '2px solid transparent',
                  marginBottom: '-1px',
                }}
              >
                {t}
                {t === 'unread' && unreadCount > 0 && (
                  <span
                    className="ml-1.5 rounded-full px-1.5 py-0.5 text-[9px] font-bold"
                    style={{ backgroundColor: 'var(--status-danger)', color: '#fff' }}
                  >
                    {unreadCount}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Notification list */}
          <div style={{ maxHeight: '380px', overflowY: 'auto' }}>
            {displayed.length === 0 ? (
              <EmptyState tab={tab} />
            ) : (
              displayed.map(n => (
                <NotificationItem key={n.id} n={n} onMarkRead={markRead} />
              ))
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div
              className="px-4 py-2.5 text-center"
              style={{ borderTop: '1px solid var(--line)' }}
            >
              <p className="text-[10px]" style={{ color: 'var(--ink-muted)' }}>
                Showing {displayed.length} of {notifications.length} notifications
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
