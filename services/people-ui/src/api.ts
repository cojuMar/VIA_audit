import axios from 'axios';
import type {
  Employee,
  HRPolicy,
  PolicyAckStatus,
  TrainingCourse,
  TrainingAssignment,
  BackgroundCheck,
  EmployeeComplianceScore,
  OrgComplianceSummary,
  Escalation,
} from './types';

const http = axios.create({
  baseURL: '/api',
});

export function setTenant(tenantId: string) {
  http.defaults.headers.common['X-Tenant-ID'] = tenantId;
}

// ── Employees ──────────────────────────────────────────────────────────────
export const fetchEmployees = (): Promise<Employee[]> =>
  http.get('/employees').then((r) => r.data);

export const fetchEmployee = (id: string): Promise<Employee> =>
  http.get(`/employees/${id}`).then((r) => r.data);

export const createEmployee = (data: Partial<Employee>): Promise<Employee> =>
  http.post('/employees', data).then((r) => r.data);

export const updateEmployee = (id: string, data: Partial<Employee>): Promise<Employee> =>
  http.put(`/employees/${id}`, data).then((r) => r.data);

// ── HR Policies ────────────────────────────────────────────────────────────
export const fetchPolicies = (): Promise<HRPolicy[]> =>
  http.get('/policies').then((r) => r.data);

export const fetchPolicy = (id: string): Promise<HRPolicy> =>
  http.get(`/policies/${id}`).then((r) => r.data);

export const createPolicy = (data: Partial<HRPolicy>): Promise<HRPolicy> =>
  http.post('/policies', data).then((r) => r.data);

export const updatePolicy = (id: string, data: Partial<HRPolicy>): Promise<HRPolicy> =>
  http.put(`/policies/${id}`, data).then((r) => r.data);

export const fetchPolicyAckStatus = (policyId: string): Promise<PolicyAckStatus[]> =>
  http.get(`/policies/${policyId}/ack-status`).then((r) => r.data);

export const acknowledgePolicy = (
  policyId: string,
  employeeId: string,
): Promise<void> =>
  http.post(`/policies/${policyId}/acknowledge`, { employee_id: employeeId }).then((r) => r.data);

export const fetchEmployeePolicyStatus = (employeeId: string): Promise<PolicyAckStatus[]> =>
  http.get(`/employees/${employeeId}/policy-status`).then((r) => r.data);

// ── Training Courses ───────────────────────────────────────────────────────
export const fetchCourses = (): Promise<TrainingCourse[]> =>
  http.get('/training/courses').then((r) => r.data);

export const createCourse = (data: Partial<TrainingCourse>): Promise<TrainingCourse> =>
  http.post('/training/courses', data).then((r) => r.data);

export const updateCourse = (id: string, data: Partial<TrainingCourse>): Promise<TrainingCourse> =>
  http.put(`/training/courses/${id}`, data).then((r) => r.data);

// ── Training Assignments ───────────────────────────────────────────────────
export const fetchAssignments = (params?: {
  status?: string;
  department?: string;
  course_id?: string;
  employee_id?: string;
}): Promise<TrainingAssignment[]> =>
  http.get('/training/assignments', { params }).then((r) => r.data);

export const createAssignment = (data: {
  employee_id: string;
  course_id: string;
  due_date?: string;
}): Promise<TrainingAssignment> =>
  http.post('/training/assignments', data).then((r) => r.data);

export const markAssignmentComplete = (
  id: string,
  score: number,
): Promise<TrainingAssignment> =>
  http.post(`/training/assignments/${id}/complete`, { score }).then((r) => r.data);

export const sendReminder = (id: string): Promise<void> =>
  http.post(`/training/assignments/${id}/remind`).then((r) => r.data);

export const bulkAssignCourse = (data: {
  course_id: string;
  employee_ids: string[];
  due_date?: string;
}): Promise<{ created: number }> =>
  http.post('/training/assignments/bulk', data).then((r) => r.data);

// ── Background Checks ──────────────────────────────────────────────────────
export const fetchBackgroundChecks = (params?: {
  status?: string;
  employee_id?: string;
}): Promise<BackgroundCheck[]> =>
  http.get('/background-checks', { params }).then((r) => r.data);

export const createBackgroundCheck = (data: {
  employee_id: string;
  check_type: string;
  provider: string;
  expiry_date?: string;
}): Promise<BackgroundCheck> =>
  http.post('/background-checks', data).then((r) => r.data);

export const updateBackgroundCheckStatus = (
  id: string,
  data: { status: BackgroundCheck['status']; adjudication?: BackgroundCheck['adjudication']; completed_at?: string },
): Promise<BackgroundCheck> =>
  http.patch(`/background-checks/${id}`, data).then((r) => r.data);

// ── Compliance Scores ──────────────────────────────────────────────────────
export const fetchOrgCompliance = (): Promise<OrgComplianceSummary> =>
  http.get('/compliance/org').then((r) => r.data);

export const fetchEmployeeCompliance = (
  employeeId: string,
): Promise<EmployeeComplianceScore> =>
  http.get(`/compliance/employees/${employeeId}`).then((r) => r.data);

export const fetchAllEmployeeScores = (): Promise<EmployeeComplianceScore[]> =>
  http.get('/compliance/employees').then((r) => r.data);

// ── Escalations ────────────────────────────────────────────────────────────
export const fetchEscalations = (params?: {
  type?: string;
  resolved?: boolean;
}): Promise<Escalation[]> =>
  http.get('/escalations', { params }).then((r) => r.data);

export const resolveEscalation = (id: string): Promise<Escalation> =>
  http.post(`/escalations/${id}/resolve`).then((r) => r.data);

export const runEscalationCheck = (): Promise<{ escalations_created: number; message: string }> =>
  http.post('/escalations/run').then((r) => r.data);
