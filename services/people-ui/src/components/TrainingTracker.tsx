import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import {
  Plus,
  BookOpen,
  Bell,
  CheckCircle,
  RefreshCw,
  Users,
} from 'lucide-react';
import {
  fetchCourses,
  fetchAssignments,
  createCourse,
  markAssignmentComplete,
  sendReminder,
  bulkAssignCourse,
  fetchEmployees,
  setTenant,
} from '../api';
import type { TrainingCourse, TrainingAssignment, Employee } from '../types';

interface Props {
  tenantId: string;
}

const STATUS_BADGE: Record<string, string> = {
  assigned: 'bg-gray-700 text-gray-300',
  in_progress: 'bg-blue-900 text-blue-200',
  completed: 'bg-green-900 text-green-200',
  overdue: 'bg-red-900 text-red-200',
  waived: 'bg-purple-900 text-purple-200',
};

const CATEGORY_COLORS: Record<string, string> = {
  Security: 'bg-red-900 text-red-200',
  Compliance: 'bg-yellow-900 text-yellow-200',
  HR: 'bg-blue-900 text-blue-200',
  IT: 'bg-purple-900 text-purple-200',
  Finance: 'bg-green-900 text-green-200',
  Safety: 'bg-orange-900 text-orange-200',
  Leadership: 'bg-indigo-900 text-indigo-200',
};

function CourseModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    title: '',
    course_key: '',
    category: 'Security',
    provider: '',
    duration_minutes: 60,
    passing_score_pct: 80,
    recurrence_days: 365,
    is_active: true,
  });

  const mutation = useMutation({
    mutationFn: () => createCourse(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['courses'] });
      onDone();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl overflow-y-auto max-h-[90vh]">
        <h3 className="text-lg font-semibold text-white mb-4">New Course</h3>
        <div className="space-y-3">
          <div>
            <label className="label">Title</label>
            <input className="input" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          </div>
          <div>
            <label className="label">Course Key</label>
            <input className="input font-mono" value={form.course_key} placeholder="e.g., SEC_101" onChange={(e) => setForm((f) => ({ ...f, course_key: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Category</label>
              <select className="select" value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
                {['Security', 'Compliance', 'HR', 'IT', 'Finance', 'Safety', 'Leadership'].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Provider</label>
              <input className="input" value={form.provider} onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="label">Duration (min)</label>
              <input className="input" type="number" min={1} value={form.duration_minutes} onChange={(e) => setForm((f) => ({ ...f, duration_minutes: Number(e.target.value) }))} />
            </div>
            <div>
              <label className="label">Pass Score %</label>
              <input className="input" type="number" min={0} max={100} value={form.passing_score_pct} onChange={(e) => setForm((f) => ({ ...f, passing_score_pct: Number(e.target.value) }))} />
            </div>
            <div>
              <label className="label">Recurrence (days)</label>
              <input className="input" type="number" min={1} value={form.recurrence_days ?? ''} onChange={(e) => setForm((f) => ({ ...f, recurrence_days: Number(e.target.value) }))} />
            </div>
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-5">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending || !form.title}>
            {mutation.isPending ? 'Creating…' : 'Create Course'}
          </button>
        </div>
        {mutation.isError && <p className="text-red-400 text-sm mt-2">Failed. Please try again.</p>}
      </div>
    </div>
  );
}

function BulkAssignModal({
  courses,
  onClose,
  onDone,
}: {
  courses: TrainingCourse[];
  onClose: () => void;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const { data: employees } = useQuery<Employee[]>({ queryKey: ['employees'], queryFn: fetchEmployees });
  const [courseId, setCourseId] = useState('');
  const [selectedEmpIds, setSelectedEmpIds] = useState<string[]>([]);
  const [dueDate, setDueDate] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      bulkAssignCourse({ course_id: courseId, employee_ids: selectedEmpIds, due_date: dueDate || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assignments'] });
      onDone();
    },
  });

  const toggleEmp = (id: string) =>
    setSelectedEmpIds((prev) => prev.includes(id) ? prev.filter((e) => e !== id) : [...prev, id]);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg shadow-2xl overflow-y-auto max-h-[90vh]">
        <h3 className="text-lg font-semibold text-white mb-4">Bulk Assign Course</h3>
        <div className="space-y-4">
          <div>
            <label className="label">Course</label>
            <select className="select" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">Select course…</option>
              {courses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Due Date (optional)</label>
            <input className="input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </div>
          <div>
            <label className="label">Employees ({selectedEmpIds.length} selected)</label>
            <div className="bg-gray-800 rounded-lg max-h-48 overflow-y-auto divide-y divide-gray-700">
              {(employees ?? []).map((emp) => (
                <label key={emp.id} className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-700">
                  <input type="checkbox" checked={selectedEmpIds.includes(emp.id)} onChange={() => toggleEmp(emp.id)} />
                  <span className="text-sm text-gray-300">{emp.full_name}</span>
                  {emp.department && <span className="text-xs text-gray-500">· {emp.department}</span>}
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="flex gap-3 justify-end mt-5">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !courseId || selectedEmpIds.length === 0}
          >
            {mutation.isPending ? 'Assigning…' : `Assign to ${selectedEmpIds.length} employees`}
          </button>
        </div>
        {mutation.isError && <p className="text-red-400 text-sm mt-2">Failed. Please try again.</p>}
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
      qc.invalidateQueries({ queryKey: ['assignments'] });
      onDone();
    },
  });
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-sm shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-2">Mark Complete</h3>
        <p className="text-sm text-gray-400 mb-4">
          Course: <strong className="text-gray-200">{courseTitle}</strong>
        </p>
        <div className="mb-4">
          <label className="label">Score (%)</label>
          <input className="input" type="number" min={0} max={100} value={score} onChange={(e) => setScore(e.target.value)} />
        </div>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Mark Complete'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Tab 1: Course Catalog ────────────────────────────────────────────────────
function CourseCatalog({ tenantId }: { tenantId: string }) {
  const [showCreate, setShowCreate] = useState(false);
  const [showBulk, setShowBulk] = useState(false);

  const { data: courses } = useQuery<TrainingCourse[]>({
    queryKey: ['courses', tenantId],
    queryFn: fetchCourses,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-300">Course Catalog</h2>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => setShowBulk(true)}>
            <Users size={13} /> Bulk Assign
          </button>
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            <Plus size={13} /> Add Course
          </button>
        </div>
      </div>

      {(!courses || courses.length === 0) ? (
        <div className="text-center text-gray-500 py-12">No courses found.</div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {courses.map((course) => (
            <div key={course.id} className="card hover:border-gray-700 transition-colors">
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-medium text-gray-200 text-sm leading-snug">{course.title}</h3>
                {!course.is_active && (
                  <span className="badge bg-gray-700 text-gray-500 flex-shrink-0 text-xs">Inactive</span>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5 mb-3">
                <span className={`badge text-xs ${CATEGORY_COLORS[course.category] ?? 'bg-gray-700 text-gray-300'}`}>
                  {course.category}
                </span>
              </div>
              <div className="space-y-1 text-xs text-gray-400">
                <div className="flex justify-between">
                  <span className="text-gray-500">Provider</span>
                  <span>{course.provider}</span>
                </div>
                {course.duration_minutes && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Duration</span>
                    <span>{course.duration_minutes} min</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-gray-500">Pass Score</span>
                  <span>{course.passing_score_pct}%</span>
                </div>
                {course.recurrence_days && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Recurrence</span>
                    <span>Every {course.recurrence_days}d</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <CourseModal onClose={() => setShowCreate(false)} onDone={() => setShowCreate(false)} />}
      {showBulk && courses && (
        <BulkAssignModal courses={courses} onClose={() => setShowBulk(false)} onDone={() => setShowBulk(false)} />
      )}
    </div>
  );
}

// ─── Tab 2: Assignments ───────────────────────────────────────────────────────
function Assignments({ tenantId }: { tenantId: string }) {
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [deptFilter, setDeptFilter] = useState<string>('');
  const [courseFilter, setCourseFilter] = useState<string>('');
  const [completeModal, setCompleteModal] = useState<{ id: string; title: string } | null>(null);

  const qc = useQueryClient();

  const { data: assignments } = useQuery<TrainingAssignment[]>({
    queryKey: ['assignments', tenantId, statusFilter, deptFilter, courseFilter],
    queryFn: () =>
      fetchAssignments({
        status: statusFilter !== 'all' ? statusFilter : undefined,
        department: deptFilter || undefined,
        course_id: courseFilter || undefined,
      }),
  });

  const { data: courses } = useQuery<TrainingCourse[]>({ queryKey: ['courses', tenantId], queryFn: fetchCourses });

  const reminderMutation = useMutation({
    mutationFn: (id: string) => sendReminder(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['assignments'] }),
  });

  const overdueCount = (assignments ?? []).filter((a) => a.status === 'overdue').length;
  const statuses = ['all', 'assigned', 'in_progress', 'completed', 'overdue', 'waived'];

  return (
    <div>
      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="flex gap-1.5">
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === s
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200'
              }`}
            >
              {s === 'all' ? 'All' : s.replace(/_/g, ' ')}
              {s === 'overdue' && overdueCount > 0 && (
                <span className="ml-1 bg-red-600 text-white rounded-full px-1.5 text-xs">
                  {overdueCount}
                </span>
              )}
            </button>
          ))}
        </div>
        <select
          className="select w-44"
          value={courseFilter}
          onChange={(e) => setCourseFilter(e.target.value)}
        >
          <option value="">All Courses</option>
          {(courses ?? []).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </div>

      {(!assignments || assignments.length === 0) ? (
        <div className="text-center text-gray-500 py-12">No assignments found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="th">Employee</th>
                <th className="th">Course</th>
                <th className="th">Due Date</th>
                <th className="th">Status</th>
                <th className="th">Reminders</th>
                <th className="th">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {assignments.map((a) => (
                <tr key={a.id} className="hover:bg-gray-800/50">
                  <td className="td text-xs font-mono text-gray-400">{a.employee_id}</td>
                  <td className="td font-medium text-gray-200 text-sm">
                    {a.course?.title ?? a.course_id}
                  </td>
                  <td className="td text-xs text-gray-400">
                    {a.due_date ? new Date(a.due_date).toLocaleDateString() : '—'}
                  </td>
                  <td className="td">
                    <span className={`badge ${STATUS_BADGE[a.status] ?? 'bg-gray-700 text-gray-300'}`}>
                      {a.status.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="td text-gray-400">{a.reminder_sent_count}</td>
                  <td className="td">
                    <div className="flex gap-1.5">
                      {a.status === 'overdue' && (
                        <button
                          className="btn-secondary text-xs py-0.5"
                          onClick={() => reminderMutation.mutate(a.id)}
                          disabled={reminderMutation.isPending}
                        >
                          <Bell size={11} /> Remind
                        </button>
                      )}
                      {a.status === 'in_progress' && (
                        <button
                          className="btn-primary text-xs py-0.5"
                          onClick={() =>
                            setCompleteModal({ id: a.id, title: a.course?.title ?? a.course_id })
                          }
                        >
                          <CheckCircle size={11} /> Complete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {completeModal && (
        <CompleteModal
          assignmentId={completeModal.id}
          courseTitle={completeModal.title}
          onClose={() => setCompleteModal(null)}
          onDone={() => setCompleteModal(null)}
        />
      )}
    </div>
  );
}

// ─── Tab 3: Completions ───────────────────────────────────────────────────────
function Completions({ tenantId }: { tenantId: string }) {
  const { data: assignments } = useQuery<TrainingAssignment[]>({
    queryKey: ['completions', tenantId],
    queryFn: () => fetchAssignments({ status: 'completed' }),
  });

  const { data: courses } = useQuery<TrainingCourse[]>({
    queryKey: ['courses', tenantId],
    queryFn: fetchCourses,
  });

  // Build trend data — last 30 days
  const now = Date.now();
  const trendData = Array.from({ length: 30 }, (_, i) => {
    const date = new Date(now - (29 - i) * 86400000);
    return {
      day: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      completions: 0,
    };
  });

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card">
          <div className="text-xs text-gray-500 mb-1">Total Completions (30d)</div>
          <div className="text-2xl font-bold text-indigo-400">{assignments?.length ?? 0}</div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500 mb-1">Courses Available</div>
          <div className="text-2xl font-bold text-blue-400">{courses?.length ?? 0}</div>
        </div>
        <div className="card">
          <div className="text-xs text-gray-500 mb-1">Active Learners</div>
          <div className="text-2xl font-bold text-green-400">
            {new Set(assignments?.map((a) => a.employee_id) ?? []).size}
          </div>
        </div>
      </div>

      {/* Trend chart */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Completion Trend (30 days)</h2>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis
              dataKey="day"
              tick={{ fill: '#9ca3af', fontSize: 11 }}
              tickLine={false}
              interval={4}
            />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
              labelStyle={{ color: '#f9fafb' }}
            />
            <Line
              type="monotone"
              dataKey="completions"
              stroke="#6366f1"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Recent completions table */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Recent Completions</h2>
        {(!assignments || assignments.length === 0) ? (
          <div className="text-center text-gray-500 py-8">
            <BookOpen size={28} className="mx-auto mb-2 text-gray-700" />
            No completions recorded.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="th">Employee</th>
                  <th className="th">Course</th>
                  <th className="th">Status</th>
                  <th className="th">Due Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {assignments.slice(0, 50).map((a) => (
                  <tr key={a.id} className="hover:bg-gray-800/50">
                    <td className="td text-xs font-mono text-gray-400">{a.employee_id}</td>
                    <td className="td font-medium text-gray-200 text-sm">
                      {a.course?.title ?? a.course_id}
                    </td>
                    <td className="td">
                      <span className="badge bg-green-900 text-green-200 flex items-center gap-1 w-fit">
                        <CheckCircle size={11} /> Completed
                      </span>
                    </td>
                    <td className="td text-xs text-gray-400">
                      {a.due_date ? new Date(a.due_date).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function TrainingTracker({ tenantId }: Props) {
  setTenant(tenantId);
  const [tab, setTab] = useState<'catalog' | 'assignments' | 'completions'>('catalog');

  const { data: overdueAssignments } = useQuery<TrainingAssignment[]>({
    queryKey: ['overdue-count', tenantId],
    queryFn: () => fetchAssignments({ status: 'overdue' }),
  });

  const overdueCount = overdueAssignments?.length ?? 0;

  const tabs = [
    { id: 'catalog', label: 'Course Catalog' },
    { id: 'assignments', label: 'Assignments', badge: overdueCount },
    { id: 'completions', label: 'Completions' },
  ] as const;

  return (
    <div className="p-6 space-y-5">
      {/* Tab Bar */}
      <div className="flex gap-2 border-b border-gray-800 pb-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`tab-btn flex items-center gap-2 ${tab === t.id ? 'tab-btn-active' : 'tab-btn-inactive'}`}
          >
            {t.label}
            {'badge' in t && t.badge > 0 && (
              <span className="bg-red-600 text-white text-xs rounded-full px-1.5 py-0">{t.badge}</span>
            )}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1 text-xs text-gray-500">
          <RefreshCw size={12} />
          Training Tracker
        </div>
      </div>

      {tab === 'catalog' && <CourseCatalog tenantId={tenantId} />}
      {tab === 'assignments' && <Assignments tenantId={tenantId} />}
      {tab === 'completions' && <Completions tenantId={tenantId} />}
    </div>
  );
}
