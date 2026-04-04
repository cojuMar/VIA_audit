import { useState, useEffect, useCallback } from 'react';
import {
  getPendingAudits,
  getPendingResponses,
  getPendingPhotos,
  markResponseSynced,
  markPhotoSynced,
  saveAudit,
  saveAssignment,
  saveTemplate,
  getAllAudits,
  getAllAssignments,
} from './db';
import { syncUpload, syncDownload } from '../api';
import type { SyncStatus } from '../types';

export interface SyncResult {
  new_audits: number;
  duplicate_audits: number;
  responses_inserted: number;
  responses_skipped: number;
  sync_session_id: string;
}

export async function syncToServer(
  tenantId: string,
  auditorEmail: string,
  deviceId: string
): Promise<SyncResult> {
  const pendingAudits = await getPendingAudits();
  const pendingResponses = await getPendingResponses();
  const pendingPhotos = await getPendingPhotos();

  if (pendingAudits.length === 0 && pendingResponses.length === 0 && pendingPhotos.length === 0) {
    return {
      new_audits: 0,
      duplicate_audits: 0,
      responses_inserted: 0,
      responses_skipped: 0,
      sync_session_id: crypto.randomUUID(),
    };
  }

  const payload = {
    tenant_id: tenantId,
    auditor_email: auditorEmail,
    device_id: deviceId,
    synced_at: new Date().toISOString(),
    audits: pendingAudits.map(({ _localOnly: _lo, _pendingSync: _ps, ...audit }) => audit),
    responses: pendingResponses.map(({ audit_id: _ai, _synced: _s, ...r }) => r),
    photo_references: pendingPhotos.map(({ data_url: _d, _synced: _s, ...p }) => p),
  };

  const result: SyncResult = await syncUpload(payload);

  // Mark responses and photos as synced
  await Promise.all([
    ...pendingResponses.map((r) => markResponseSynced(r.sync_id)),
    ...pendingPhotos.map((p) => markPhotoSynced(p.sync_id)),
  ]);

  // Mark audits as no longer pending
  for (const audit of pendingAudits) {
    await saveAudit({ ...audit, _localOnly: false, _pendingSync: false });
  }

  return result;
}

export async function syncFromServer(
  tenantId: string,
  auditorEmail: string,
  lastSync?: string
): Promise<void> {
  const params: Record<string, string> = { email: auditorEmail };
  if (lastSync) params.last_sync = lastSync;
  if (tenantId) params.tenant_id = tenantId;

  const data = await syncDownload(params);

  if (data.assignments && Array.isArray(data.assignments)) {
    for (const assignment of data.assignments) {
      await saveAssignment(assignment);
    }
  }

  if (data.templates && Array.isArray(data.templates)) {
    for (const template of data.templates) {
      await saveTemplate(template);
    }
  }

  if (data.audits && Array.isArray(data.audits)) {
    const existingAudits = await getAllAudits();
    const existingIds = new Set(existingAudits.map((a) => a.id));
    for (const audit of data.audits) {
      if (!existingIds.has(audit.id)) {
        await saveAudit(audit);
      }
    }
  }
}

// React hook: returns online status
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return isOnline;
}

// React hook: full sync status
export function useSyncStatus(tenantId: string, email: string): SyncStatus & { triggerSync: () => Promise<void> } {
  const isOnline = useOnlineStatus();
  const [isSyncing, setIsSyncing] = useState(false);
  const [pendingAudits, setPendingAudits] = useState(0);
  const [pendingResponses, setPendingResponses] = useState(0);
  const [pendingPhotos, setPendingPhotos] = useState(0);
  const [lastSyncAt, setLastSyncAt] = useState<string | undefined>(
    localStorage.getItem('aegis_last_sync') ?? undefined
  );

  const refreshCounts = useCallback(async () => {
    const [audits, responses, photos] = await Promise.all([
      getPendingAudits(),
      getPendingResponses(),
      getPendingPhotos(),
    ]);
    setPendingAudits(audits.length);
    setPendingResponses(responses.length);
    setPendingPhotos(photos.length);
  }, []);

  useEffect(() => {
    refreshCounts();
    const interval = setInterval(refreshCounts, 15000);
    return () => clearInterval(interval);
  }, [refreshCounts]);

  const triggerSync = useCallback(async () => {
    if (!isOnline || isSyncing) return;
    setIsSyncing(true);
    try {
      const deviceId = localStorage.getItem('aegis_device_id') ?? crypto.randomUUID();
      localStorage.setItem('aegis_device_id', deviceId);

      await syncToServer(tenantId, email, deviceId);
      await syncFromServer(tenantId, email, lastSyncAt);

      const now = new Date().toISOString();
      setLastSyncAt(now);
      localStorage.setItem('aegis_last_sync', now);
      await refreshCounts();
    } catch (err) {
      console.error('Sync failed:', err);
    } finally {
      setIsSyncing(false);
    }
  }, [isOnline, isSyncing, tenantId, email, lastSyncAt, refreshCounts]);

  // Auto-sync when coming online
  useEffect(() => {
    if (isOnline && (pendingAudits > 0 || pendingResponses > 0 || pendingPhotos > 0)) {
      triggerSync();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOnline]);

  return {
    pendingAudits,
    pendingResponses,
    pendingPhotos,
    lastSyncAt,
    isOnline,
    isSyncing,
    triggerSync,
  };
}

// Retrieve all local assignments (offline-capable)
export async function getLocalAssignments() {
  return getAllAssignments();
}
