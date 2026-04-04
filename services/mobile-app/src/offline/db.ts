import { openDB, DBSchema, IDBPDatabase } from 'idb';
import type { AuditTemplate, Assignment, FieldAudit, ResponsePayload } from '../types';

interface PhotoRecord {
  sync_id: string;
  audit_id: string;
  data_url: string;
  filename: string;
  caption?: string;
  gps_lat?: number;
  gps_lon?: number;
  _synced?: boolean;
}

interface ResponseRecord extends ResponsePayload {
  audit_id: string;
  _synced?: boolean;
}

interface AuditRecord extends FieldAudit {
  _localOnly?: boolean;
  _pendingSync?: boolean;
}

interface AegisDB extends DBSchema {
  templates: {
    key: string;
    value: AuditTemplate;
  };
  assignments: {
    key: string;
    value: Assignment;
  };
  audits: {
    key: string;
    value: AuditRecord;
  };
  responses: {
    key: string;
    value: ResponseRecord;
  };
  photos: {
    key: string;
    value: PhotoRecord;
  };
}

let dbInstance: IDBPDatabase<AegisDB> | null = null;

export async function getDB(): Promise<IDBPDatabase<AegisDB>> {
  if (dbInstance) return dbInstance;
  dbInstance = await openDB<AegisDB>('aegis-field-db', 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains('templates')) {
        db.createObjectStore('templates', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('assignments')) {
        db.createObjectStore('assignments', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('audits')) {
        db.createObjectStore('audits', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('responses')) {
        db.createObjectStore('responses', { keyPath: 'sync_id' });
      }
      if (!db.objectStoreNames.contains('photos')) {
        db.createObjectStore('photos', { keyPath: 'sync_id' });
      }
    },
  });
  return dbInstance;
}

// Templates
export async function saveTemplate(template: AuditTemplate): Promise<void> {
  const db = await getDB();
  await db.put('templates', template);
}

export async function getTemplate(id: string): Promise<AuditTemplate | undefined> {
  const db = await getDB();
  return db.get('templates', id);
}

export async function getAllTemplates(): Promise<AuditTemplate[]> {
  const db = await getDB();
  return db.getAll('templates');
}

// Assignments
export async function saveAssignment(assignment: Assignment): Promise<void> {
  const db = await getDB();
  await db.put('assignments', assignment);
}

export async function getAllAssignments(): Promise<Assignment[]> {
  const db = await getDB();
  return db.getAll('assignments');
}

// Audits
export async function saveAudit(audit: FieldAudit & { _localOnly?: boolean; _pendingSync?: boolean }): Promise<void> {
  const db = await getDB();
  await db.put('audits', audit);
}

export async function getAudit(id: string): Promise<FieldAudit | undefined> {
  const db = await getDB();
  return db.get('audits', id);
}

export async function getAllAudits(): Promise<FieldAudit[]> {
  const db = await getDB();
  return db.getAll('audits');
}

export async function getPendingAudits(): Promise<FieldAudit[]> {
  const db = await getDB();
  const all = await db.getAll('audits');
  return all.filter((a) => (a as AuditRecord)._pendingSync === true);
}

// Responses
export async function saveResponse(audit_id: string, response: ResponsePayload): Promise<void> {
  const db = await getDB();
  const record: ResponseRecord = { ...response, audit_id, _synced: false };
  await db.put('responses', record);
}

export async function getResponsesForAudit(audit_id: string): Promise<ResponsePayload[]> {
  const db = await getDB();
  const all = await db.getAll('responses');
  return all.filter((r) => r.audit_id === audit_id);
}

export async function getPendingResponses(): Promise<ResponseRecord[]> {
  const db = await getDB();
  const all = await db.getAll('responses');
  return all.filter((r) => !r._synced);
}

export async function markResponseSynced(sync_id: string): Promise<void> {
  const db = await getDB();
  const record = await db.get('responses', sync_id);
  if (record) {
    await db.put('responses', { ...record, _synced: true });
  }
}

// Photos
export async function savePhoto(data: PhotoRecord): Promise<void> {
  const db = await getDB();
  await db.put('photos', { ...data, _synced: false });
}

export async function getPhotosForAudit(audit_id: string): Promise<PhotoRecord[]> {
  const db = await getDB();
  const all = await db.getAll('photos');
  return all.filter((p) => p.audit_id === audit_id);
}

export async function getPendingPhotos(): Promise<PhotoRecord[]> {
  const db = await getDB();
  const all = await db.getAll('photos');
  return all.filter((p) => !p._synced);
}

export async function markPhotoSynced(sync_id: string): Promise<void> {
  const db = await getDB();
  const record = await db.get('photos', sync_id);
  if (record) {
    await db.put('photos', { ...record, _synced: true });
  }
}
