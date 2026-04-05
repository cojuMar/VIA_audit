import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RadialBarChart,
  RadialBar,
} from 'recharts';
import {
  ArrowLeft,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  User,
  Shield,
  BookOpen,
  UserCheck,
  Pencil,
  X,
} from 'lucide-react';
import {
  fetchEmployee,
  fetchEmployeeCompliance,
  fetchEmployeePolicyStatus,
  fetchAssignments,
  fetchBackgroundChecks,
  acknowledgePolicy,
  markAssignmentComplete,
  updateEmployee,
  setTenant,
} from '../api';
import type {
  Employee,
  EmployeeComplianceScore,
  PolicyAckStatus,
  TrainingAssignment,
  BackgroundCheck,
} from '../types';

interface Props {
  tenantId: string;
  employeeId: string;
  onBack: () => void;
}

const GREEN = '#22c55e';
const AMBER = '#f59e0b';
const RED = '#ef4444';

function scoreColor(score: number) {
  if (score >= 90) return GREEN;
  if (score >= 70) return AMBER;
  return RED;
}

function ScoreGauge({ score, label, icon }: { score: number; label: string; icon: React.ReactNode }) {
  const color = scoreColor(score);
  const data = [{ name: label, value: score, fill: color }];
  return (
    <div className="card flex flex-col items-center gap-1">
      <div className="flex items-center gap-1.5 text-gray-400 text-xs font-semibold uppercase tracking-wider mb-1">
        {icon}
        {label}
      </div>
      <RadialBarChart
        width={110}
        height={110}
        cx={55}
        cy={55}
        innerRadius={36}
        outerRadius={50}
        barSize={11}
        data={data}
        startAngle={90}
        endAngle={-270}
      >
        <RadialBar dataKey="value" cornerRadius={6} background={{ fill: '#374151' }} />
      </RadialBarChart>
      <div className="text-2xl font-bold" style={{ color }}>
        {score.toFixed(0)}
      </div>
    </div>
  );
}

const STATUS_TRAINING_BADGE: Record<string, string> = {
  assigned: 'bg-gray-700 text-gray-300',
  in_progress: 'bg-blue-900 text-blue-200',
  completed: 'bg-green-900 text-green-200',
  overdue: 'bg-red-900 text-red-200',
  waived: 'bg-purple-900 text-purple-200',
};

const BG_STATUS_BADGE: Record<string, string> = {
  pending: 'bg-gray-700 text-gray-300',
  in_progress: 'bg-blue-900 text-blue-200',
  passed: 'bg-green-900 text-green-200',
  failed: 'bg-red-900 text-red-200',
  expired: 'bg-orange-900 text-orange-200',
  cancelled: 'bg-gray-800 text-gray-400',
};

function EditEmployeeModal({
  employee,
  onClose,
  onSaved,
}: {
  employee: Employee;
  onClose: () => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [formData, setFormData] = useState({
    full_name: employee.full_name,
    email: employee.email,
    department: employee.department ?? '',
    job_title: employee.job_title ?? '',
    employment_status: employee.employment_status,
  });
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      updateEmployee(employee.id, {
        full_name: formData.full_name.trim(),
        email: formData.email.trim(),
        department: formData.department.trim() || null,
        job_title: formData.job_title.trim() || null,
        employment_status: formData.employment_status,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employee', employee.id] });
      qc.invalidateQueries({ queryKey: ['employees'] });
      onSaved();
    },
    onError: (err: Error) => {
      setError(err.message ?? 'Failed to update employee');
    },
  });

  const handleSubmit = () => {
    if (!formData.full_name.trim()) { setError('Full name is required'); return; }
    if (!formData.email.trim()) { setError('Email is required'); return; }
    setError(null);
    mutation.mutate();
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-white">Edit Employee</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-200">
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-900/30 border border-red-700 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="label">Full Name <span className="text-red-400">*</span></label>
              <input
                className="input"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
              />
            </div>
            <div className="col-span-2">
              <label className="label">Email <span className="text-red-400">*</span></label>
              <input
                className="input"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Department</label>
              <input
                className="input"
                value={formData.department}
                onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                placeholder="e.g. Engineering"
              />
            </div>
            <div>
              <label className="label">Job Title</label>
              <input
                className="input"
                value={formData.job_title}
                onChange={(e) => setFormData({ ...formData, job_title: e.target.value })}
                placeholder="e.g. Senior Developer"
              />
            </div>
            <div className="col-span-2">
              <label className="label">Employment Status</label>
              <select
                className="input"
                value={formData.employment_status}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    employment_status: e.target.value as Employee['employment_status'],
                  })
                }
              >
                <option value="active">Active</option>
                <option value="on_leave">On Leave</option>
                <option value="terminated">Terminated</option>
              </select>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-700">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={handleSubmit}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

function AcknowledgeModal({
  policyId,
  policyTitle,
  employeeId,
  onClose,
  onDone,
}: {
  policyId: string;
  policyTitle: string;
  employeeId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => acknowledgePolicy(policyId, employeeId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employee-policy-status'] });
      onDone();
    },
  });
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-2">Acknowledge Policy</h3>
        <p className="text-sm text-gray-400 mb-6">
          Confirm acknowledgment of: <strong className="text-gray-200">{policyTitle}</strong>
        </p>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Acknowledging…' : 'Acknowledge'}
          </button>
        </div>
        {mutation.isError && (
          <p className="text-red-400 text-sm mt-2">Failed to acknowledge. Please try again.</p>
        )}
      </div>
    </div>
  );
}

function CompleteModal({
  assignmentId,
  courseTitle,
  onClose,
  onDone,
}: {
  assignmentId: string;
  courseTitle: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [score, setScore] = useState('100');
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => markAssignmentComplete(assignmentId, Number(score)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employee-assignments'] });
      onDone();
    },
  });
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-2">Mark Training Complete</h3>
        <p className="text-sm text-gray-400 mb-4">
          Course: <strong className="text-gray-200">{courseTitle}</strong>
        </p>
        <div className="mb-4">
          <label className="label">Score (%)</label>
          <input
            className="input"
            type="number"
            min={0}
            max={100}
            value={score}
            onChange={(e) => setScore(e.target.value)}
          />
        </div>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Saving…' : 'Mark Complete'}
          </button>
        </div>
        {mutation.isError && (
          <p className="text-red-400 text-sm mt-2">Failed. Please try again.</p>
        )}
      </div>
    </div>
  );
}

export default function EmployeeComplianceDashboard({ tenantId, employeeId, onBack }: Props) {
  setTenant(tenantId);
  const [ackModal, setAckModal] = useState<{ policyId: string; title: string } | null>(null);
  const [completeModal, setCompleteModal] = useState<{ assignmentId: string; courseTitle: string } | null>(null);
  const [showEditEmployee, setShowEditEmployee] = useState(false);

  const { data: employee } = useQuery<Employee>({
    queryKey: ['employee', employeeId],
    queryFn: () => fetchEmployee(employeeId),
  });

  const { data: compliance } = useQuery<EmployeeComplianceScore>({
    queryKey: ['employee-compliance', employeeId],
    queryFn: () => fetchEmployeeCompliance(employeeId),
  });

  const { data: policyStatuses } = useQuery<PolicyAckStatus[]>({
    queryKey: ['employee-policy-status', employeeId],
    queryFn: () => fetchEmployeePolicyStatus(employeeId),
  });

  const { data: assignments } = useQuery<TrainingAssignment[]>({
    queryKey: ['employee-assignments', employeeId],
    queryFn: () => fetchAssignments({ employee_id: employeeId }),
  });

  const { data: bgChecks } = useQuery<BackgroundCheck[]>({
    queryKey: ['employee-bg-checks', employeeId],
    queryFn: () => fetchBackgroundChecks({ employee_id: employeeId }),
  });

  const statusColors: Record<string, string> = {
    compliant: 'text-green-400',
    at_risk: 'text-amber-400',
    non_compliant: 'text-red-400',
  };

  return (
    <div className="space-y-6 p-6">
      {/* Back + Header */}
      <div className="flex items-start gap-4">
        <button className="btn-secondary mt-0.5" onClick={onBack}>
          <ArrowLeft size={14} /> Back
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <User size={20} className="text-gray-400" />
            <h1 className="text-2xl font-bold text-white">
              {employee?.full_name ?? employeeId}
            </h1>
            {compliance && (
              <span className={`text-sm font-semibold ${statusColors[compliance.status] ?? ''}`}>
                — {compliance.status.replace(/_/g, ' ')}
              </span>
            )}
          </div>
          <div className="text-sm text-gray-400 mt-0.5">
            {employee?.job_title && <span>{employee.job_title}</span>}
            {employee?.department && <span> · {employee.department}</span>}
            {employee?.email && <span> · {employee.email}</span>}
          </div>
        </div>
        {employee && (
          <button
            className="btn-secondary mt-0.5 flex items-center gap-1.5"
            onClick={() => setShowEditEmployee(true)}
          >
            <Pencil size={13} /> Edit
          </button>
        )}
      </div>

      {/* Score Gauges */}
      {compliance && (
        <div className="grid grid-cols-4 gap-4">
          <ScoreGauge
            score={compliance.overall_score}
            label="Overall"
            icon={<CheckCircle size={12} />}
          />
          <ScoreGauge
            score={compliance.policy_score}
            label="Policy"
            icon={<Shield size={12} />}
          />
          <ScoreGauge
            score={compliance.training_score}
            label="Training"
            icon={<BookOpen size={12} />}
          />
          <ScoreGauge
            score={compliance.background_check_score}
            label="Background"
            icon={<UserCheck size={12} />}
          />
        </div>
      )}

      {/* Policy Acknowledgments */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <Shield size={16} className="text-blue-400" />
          Policy Acknowledgments
        </h2>
        {!policyStatuses || policyStatuses.length === 0 ? (
          <div className="text-gray-500 text-sm py-4 text-center">No policy data available.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Policy</th>
                  <th className="th">Required</th>
                  <th className="th">Status</th>
                  <th className="th">Acknowledged</th>
                  <th className="th">Days Until Due</th>
                  <th className="th">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {policyStatuses.map((ps) => (
                  <tr key={ps.policy_id} className="hover:bg-gray-800/50">
                    <td className="td font-medium text-gray-200">{ps.title}</td>
                    <td className="td">
                      {ps.required ? (
                        <span className="badge bg-blue-900 text-blue-200">Required</span>
                      ) : (
                        <span className="text-gray-500">—</span>
                      )}
                    </td>
                    <td className="td">
                      {!ps.required ? (
                        <span className="text-gray-500">—</span>
                      ) : ps.acknowledged && !ps.is_overdue ? (
                        <span className="flex items-center gap-1 text-green-400">
                          <CheckCircle size={13} /> Acknowledged
                        </span>
                      ) : ps.is_overdue ? (
                        <span className="flex items-center gap-1 text-red-400">
                          <AlertTriangle size={13} /> Overdue
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-amber-400">
                          <Clock size={13} /> Pending
                        </span>
                      )}
                    </td>
                    <td className="td text-gray-400 text-xs">
                      {ps.acknowledged_at ? new Date(ps.acknowledged_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="td">
                      {ps.days_until_due != null ? (
                        <span
                          className={
                            ps.days_until_due < 0
                              ? 'text-red-400'
                              : ps.days_until_due <= 7
                              ? 'text-amber-400'
                              : 'text-gray-300'
                          }
                        >
                          {ps.days_until_due < 0
                            ? `${Math.abs(ps.days_until_due)}d overdue`
                            : `${ps.days_until_due}d`}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="td">
                      {ps.required && (ps.is_overdue || !ps.acknowledged) && (
                        <button
                          className="btn-primary text-xs py-1"
                          onClick={() => setAckModal({ policyId: ps.policy_id, title: ps.title })}
                        >
                          Acknowledge
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Training Assignments */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <BookOpen size={16} className="text-amber-400" />
          Training Assignments
        </h2>
        {!assignments || assignments.length === 0 ? (
          <div className="text-gray-500 text-sm py-4 text-center">No training assignments.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Course</th>
                  <th className="th">Category</th>
                  <th className="th">Provider</th>
                  <th className="th">Due Date</th>
                  <th className="th">Status</th>
                  <th className="th">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {assignments.map((a) => (
                  <tr key={a.id} className="hover:bg-gray-800/50">
                    <td className="td font-medium text-gray-200">
                      {a.course?.title ?? a.course_id}
                    </td>
                    <td className="td">
                      {a.course?.category ? (
                        <span className="badge bg-gray-700 text-gray-300">{a.course.category}</span>
                      ) : '—'}
                    </td>
                    <td className="td text-gray-400">{a.course?.provider ?? '—'}</td>
                    <td className="td text-gray-400 text-xs">
                      {a.due_date ? new Date(a.due_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="td">
                      <span className={`badge ${STATUS_TRAINING_BADGE[a.status] ?? 'bg-gray-700 text-gray-300'}`}>
                        {a.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="td">
                      {a.status === 'in_progress' && (
                        <button
                          className="btn-primary text-xs py-1"
                          onClick={() =>
                            setCompleteModal({
                              assignmentId: a.id,
                              courseTitle: a.course?.title ?? a.course_id,
                            })
                          }
                        >
                          Mark Complete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Background Checks */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <UserCheck size={16} className="text-purple-400" />
          Background Checks
        </h2>
        {!bgChecks || bgChecks.length === 0 ? (
          <div className="text-gray-500 text-sm py-4 text-center">No background checks on record.</div>
        ) : (
          <div className="relative pl-6">
            <div className="absolute left-2 top-0 bottom-0 w-0.5 bg-gray-700" />
            {bgChecks.map((check) => {
              const isExpired =
                check.expiry_date && new Date(check.expiry_date) < new Date();
              const isSoon =
                !isExpired &&
                check.expiry_date &&
                (new Date(check.expiry_date).getTime() - Date.now()) / 86400000 < 60;
              return (
                <div key={check.id} className="relative mb-4 last:mb-0">
                  <div
                    className="absolute -left-4 top-1.5 w-2.5 h-2.5 rounded-full border-2 border-gray-900"
                    style={{
                      background:
                        check.status === 'passed'
                          ? '#22c55e'
                          : check.status === 'failed'
                          ? '#ef4444'
                          : check.status === 'in_progress'
                          ? '#3b82f6'
                          : check.status === 'expired'
                          ? '#f97316'
                          : '#6b7280',
                    }}
                  />
                  <div className="bg-gray-800 rounded-lg px-4 py-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium text-gray-200 text-sm">{check.check_type}</span>
                      <span className={`badge ${BG_STATUS_BADGE[check.status] ?? 'bg-gray-700 text-gray-300'}`}>
                        {check.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 space-y-0.5">
                      <div>Provider: {check.provider}</div>
                      <div>Initiated: {new Date(check.initiated_at).toLocaleDateString()}</div>
                      {check.completed_at && (
                        <div>Completed: {new Date(check.completed_at).toLocaleDateString()}</div>
                      )}
                      {check.expiry_date && (
                        <div
                          className={
                            isExpired
                              ? 'text-red-400'
                              : isSoon
                              ? 'text-amber-400'
                              : ''
                          }
                        >
                          Expires: {new Date(check.expiry_date).toLocaleDateString()}
                          {isExpired && ' (expired)'}
                          {isSoon && !isExpired && ' (expiring soon)'}
                        </div>
                      )}
                      {check.adjudication && (
                        <div>
                          Adjudication:{' '}
                          <span
                            className={
                              check.adjudication === 'clear'
                                ? 'text-green-400'
                                : check.adjudication === 'adverse_action'
                                ? 'text-red-400'
                                : 'text-amber-400'
                            }
                          >
                            {check.adjudication.replace(/_/g, ' ')}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Edit Employee Modal */}
      {showEditEmployee && employee && (
        <EditEmployeeModal
          employee={employee}
          onClose={() => setShowEditEmployee(false)}
          onSaved={() => setShowEditEmployee(false)}
        />
      )}

      {/* Modals */}
      {ackModal && (
        <AcknowledgeModal
          policyId={ackModal.policyId}
          policyTitle={ackModal.title}
          employeeId={employeeId}
          onClose={() => setAckModal(null)}
          onDone={() => setAckModal(null)}
        />
      )}
      {completeModal && (
        <CompleteModal
          assignmentId={completeModal.assignmentId}
          courseTitle={completeModal.courseTitle}
          onClose={() => setCompleteModal(null)}
          onDone={() => setCompleteModal(null)}
        />
      )}
    </div>
  );
}
