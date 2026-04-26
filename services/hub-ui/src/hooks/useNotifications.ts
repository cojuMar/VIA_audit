import { useState, useEffect, useCallback, useRef } from 'react';
import type { AuthUser } from '../contexts/AuthContext';

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  entity_type: string | null;
  entity_id: string | null;
  severity: 'info' | 'warning' | 'critical';
  read: boolean;
  created_at: string;
}

interface UseNotificationsResult {
  notifications: Notification[];
  unreadCount: number;
  isLoading: boolean;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  refresh: () => void;
}

const POLL_INTERVAL = 30_000; // 30 seconds

function buildParams(user: AuthUser): string {
  return `user_id=${encodeURIComponent(user.id)}&tenant_id=${encodeURIComponent(user.tenant_id)}`;
}

export function useNotifications(user: AuthUser | null): UseNotificationsResult {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isLoading, setIsLoading]         = useState(false);
  const timerRef                          = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNotifications = useCallback(async () => {
    if (!user) return;
    try {
      setIsLoading(true);
      const res = await fetch(`/auth/notifications?${buildParams(user)}&limit=50`);
      if (res.ok) {
        const data: Notification[] = await res.json();
        setNotifications(data);
      }
    } catch (err) {
      // Surface — never swallow. Wiring to @via/ui-kit's <ToasterProvider>
      // lands when the hub-ui root adopts it (Sprint 27).
      console.warn('[useNotifications] fetch failed:', err);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  // Initial fetch + polling
  useEffect(() => {
    if (!user) return;
    fetchNotifications();
    timerRef.current = setInterval(fetchNotifications, POLL_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [user, fetchNotifications]);

  const markRead = useCallback(async (id: string) => {
    if (!user) return;
    // Optimistic update
    setNotifications(prev =>
      prev.map(n => (n.id === id ? { ...n, read: true } : n))
    );
    try {
      await fetch(
        `/auth/notifications/${id}/read?tenant_id=${encodeURIComponent(user.tenant_id)}`,
        { method: 'PATCH' }
      );
    } catch (err) {
      console.warn('[useNotifications] mark failed:', err);
    }
  }, [user]);

  const markAllRead = useCallback(async () => {
    if (!user) return;
    // Optimistic update
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    try {
      await fetch(
        `/auth/notifications/read-all?${buildParams(user)}`,
        { method: 'PATCH' }
      );
    } catch (err) {
      console.warn('[useNotifications] mark failed:', err);
    }
  }, [user]);

  const unreadCount = notifications.filter(n => !n.read).length;

  return {
    notifications,
    unreadCount,
    isLoading,
    markRead,
    markAllRead,
    refresh: fetchNotifications,
  };
}
