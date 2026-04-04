import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield, AlertTriangle, Leaf, Users, Gavel, Plus, X, Clock,
  CheckCircle, Calendar, MapPin, Video, ChevronRight,
} from 'lucide-react';
import {
  fetchCommittees, fetchMeetings, createCommittee, createMeeting,
  fetchMeeting, completeMeeting, approveMinutes, fetchBoardCalendar,
} from '../api';
import type { BoardCommittee, BoardMeeting, AgendaItem } from '../types';

interface Props { tenantId: string }

const COMMITTEE_TYPES = ['audit', 'risk', 'esg', 'compensation', 'nomination', 'executive', 'other'];
const MEETING_TYPES = ['regular', 'special', 'annual', 'emergency'];
const MEETING_STATUSES = ['scheduled', 'in_progress', 'completed', 'cancelled'];
const CURRENT_YEAR = new Date().getFullYear();
const QUARTERS = ['Q1', 'Q2', 'Q3', 'Q4'] as const;

function committeeIcon(type: string) {
  switch (type) {
    case 'audit': return <Shield className="w-5 h-5 text-blue-600" />;
    case 'risk': return <AlertTriangle className="w-5 h-5 text-orange-600" />;
    case 'esg': return <Leaf className="w-5 h-5 text-green-600" />;
    case 'compensation': return <Gavel className="w-5 h-5 text-purple-600" />;
    default: return <Users className="w-5 h-5 text-gray-600" />;
  }
}

function statusColor(status: string) {
  switch (status) {
    case 'completed': return 'bg-green-100 text-green-700';
    case 'in_progress': return 'bg-yellow-100 text-yellow-700';
    case 'cancelled': return 'bg-red-100 text-red-700';
    default: return 'bg-blue-100 text-blue-700';
  }
}

function meetingTypeColor(type: string) {
  switch (type) {
    case 'annual': return 'bg-purple-100 text-purple-700';
    case 'special': return 'bg-orange-100 text-orange-700';
    case 'emergency': return 'bg-red-100 text-red-700';
    default: return 'bg-blue-100 text-blue-700';
  }
}

function getQuarter(dateStr: string): string {
  const month = new Date(dateStr).getMonth() + 1;
  if (month <= 3) return 'Q1';
  if (month <= 6) return 'Q2';
  if (month <= 9) return 'Q3';
  return 'Q4';
}

function daysUntil(dateStr: string): number {
  const now = new Date();
  const d = new Date(dateStr);
  return Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

interface AddCommitteeModalProps {
  onClose: () => void;
  onSubmit: (data: object) => void;
  submitting: boolean;
}
function AddCommitteeModal({ onClose, onSubmit, submitting }: AddCommitteeModalProps) {
  const [name, setName] = useState('');
  const [type, setType] = useState('audit');
  const [chair, setChair] = useState('');
  const [membersRaw, setMembersRaw] = useState('');
  const [quorum, setQuorum] = useState(3);
  const [frequency, setFrequency] = useState('quarterly');
  const [charter, setCharter] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      committee_type: type,
      chair: chair || undefined,
      members: membersRaw.split(',').map((s) => s.trim()).filter(Boolean),
      quorum_requirement: quorum,
      meeting_frequency: frequency,
      charter: charter || undefined,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Add Committee</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {COMMITTEE_TYPES.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Chair</label>
              <input
                type="text"
                value={chair}
                onChange={(e) => setChair(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Quorum</label>
              <input
                type="number"
                min={1}
                value={quorum}
                onChange={(e) => setQuorum(Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Members (comma-separated)</label>
            <input
              type="text"
              value={membersRaw}
              onChange={(e) => setMembersRaw(e.target.value)}
              placeholder="John Smith, Jane Doe, ..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Meeting Frequency</label>
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {['weekly', 'monthly', 'quarterly', 'semi-annual', 'annual'].map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Charter</label>
            <textarea
              value={charter}
              onChange={(e) => setCharter(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={submitting} className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {submitting ? 'Saving…' : 'Create Committee'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface CreateMeetingModalProps {
  committees: BoardCommittee[];
  onClose: () => void;
  onSubmit: (data: object) => void;
  submitting: boolean;
}
function CreateMeetingModal({ committees, onClose, onSubmit, submitting }: CreateMeetingModalProps) {
  const [title, setTitle] = useState('');
  const [committeeId, setCommitteeId] = useState('');
  const [meetingType, setMeetingType] = useState('regular');
  const [scheduledDate, setScheduledDate] = useState('');
  const [location, setLocation] = useState('');
  const [virtualLink, setVirtualLink] = useState('');
  const [attendeesRaw, setAttendeesRaw] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      title,
      committee_id: committeeId || undefined,
      meeting_type: meetingType,
      scheduled_date: scheduledDate,
      location: location || undefined,
      virtual_link: virtualLink || undefined,
      attendees: attendeesRaw.split(',').map((s) => s.trim()).filter(Boolean),
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Create Meeting</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Committee</label>
              <select
                value={committeeId}
                onChange={(e) => setCommitteeId(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">No Committee</option>
                {committees.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Meeting Type</label>
              <select
                value={meetingType}
                onChange={(e) => setMeetingType(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {MEETING_TYPES.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Scheduled Date</label>
            <input
              type="datetime-local"
              value={scheduledDate}
              onChange={(e) => setScheduledDate(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Virtual Link</label>
              <input
                type="text"
                value={virtualLink}
                onChange={(e) => setVirtualLink(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Attendees (comma-separated)</label>
            <input
              type="text"
              value={attendeesRaw}
              onChange={(e) => setAttendeesRaw(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
            <button type="submit" disabled={submitting} className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
              {submitting ? 'Saving…' : 'Create Meeting'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface MeetingDrawerProps {
  meetingId: string;
  onClose: () => void;
}
function MeetingDrawer({ meetingId, onClose }: MeetingDrawerProps) {
  const queryClient = useQueryClient();
  const [showCompleteForm, setShowCompleteForm] = useState(false);
  const [minutesText, setMinutesText] = useState('');
  const [quorumMet, setQuorumMet] = useState(true);

  const { data: meeting, isLoading } = useQuery<BoardMeeting>({
    queryKey: ['meeting', meetingId],
    queryFn: () => fetchMeeting(meetingId),
  });

  const completeMutation = useMutation({
    mutationFn: (data: object) => completeMeeting(meetingId, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['meeting', meetingId] });
      void queryClient.invalidateQueries({ queryKey: ['meetings'] });
      setShowCompleteForm(false);
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => approveMinutes(meetingId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['meeting', meetingId] });
    },
  });

  const agendaItemIcon = (type: string) => {
    switch (type) {
      case 'approval': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'discussion': return <Users className="w-4 h-4 text-blue-500" />;
      case 'presentation': return <Calendar className="w-4 h-4 text-purple-500" />;
      default: return <ChevronRight className="w-4 h-4 text-gray-400" />;
    }
  };

  const itemStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'bg-green-100 text-green-700';
      case 'presented': return 'bg-blue-100 text-blue-700';
      case 'deferred': return 'bg-orange-100 text-orange-700';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-end justify-end z-50">
      <div className="bg-white h-full w-full max-w-lg shadow-2xl overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center">
          <h3 className="text-lg font-semibold">Meeting Details</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        {isLoading ? (
          <div className="p-6 text-gray-400">Loading…</div>
        ) : !meeting ? (
          <div className="p-6 text-gray-400">Meeting not found.</div>
        ) : (
          <div className="p-6 space-y-5">
            <div>
              <h4 className="text-lg font-bold text-gray-900">{meeting.title}</h4>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColor(meeting.status)}`}>{meeting.status}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${meetingTypeColor(meeting.meeting_type)}`}>{meeting.meeting_type}</span>
                {meeting.committee_name && (
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{meeting.committee_name}</span>
                )}
              </div>
            </div>

            <div className="space-y-2 text-sm text-gray-600">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-gray-400" />
                <span>{new Date(meeting.scheduled_date).toLocaleString()}</span>
              </div>
              {meeting.location && (
                <div className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-gray-400" />
                  <span>{meeting.location}</span>
                </div>
              )}
              {meeting.virtual_link && (
                <div className="flex items-center gap-2">
                  <Video className="w-4 h-4 text-gray-400" />
                  <a href={meeting.virtual_link} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">{meeting.virtual_link}</a>
                </div>
              )}
              {meeting.quorum_met !== undefined && (
                <div className="flex items-center gap-2">
                  {meeting.quorum_met
                    ? <CheckCircle className="w-4 h-4 text-green-500" />
                    : <X className="w-4 h-4 text-red-500" />}
                  <span>Quorum {meeting.quorum_met ? 'met' : 'not met'}</span>
                </div>
              )}
            </div>

            {meeting.attendees.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Attendees</p>
                <div className="flex flex-wrap gap-1.5">
                  {meeting.attendees.map((a, i) => (
                    <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{a}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Agenda Items */}
            {meeting.agenda_items && meeting.agenda_items.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Agenda ({meeting.agenda_items.length} items)</p>
                <div className="space-y-2">
                  {[...meeting.agenda_items]
                    .sort((a: AgendaItem, b: AgendaItem) => a.sequence_number - b.sequence_number)
                    .map((item: AgendaItem) => (
                      <div key={item.id} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                        <span className="w-6 h-6 flex items-center justify-center bg-indigo-100 text-indigo-700 text-xs font-bold rounded-full shrink-0">
                          {item.sequence_number}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            {agendaItemIcon(item.item_type)}
                            <span className="text-sm font-medium text-gray-800 truncate">{item.title}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${itemStatusColor(item.status)}`}>{item.status}</span>
                            {item.presenter && <span className="text-xs text-gray-500">{item.presenter}</span>}
                            <span className="text-xs text-gray-400">{item.duration_minutes}min</span>
                          </div>
                          {item.decision && (
                            <p className="text-xs text-green-700 mt-1 font-medium">Decision: {item.decision}</p>
                          )}
                          {item.action_items.length > 0 && (
                            <ul className="mt-1 space-y-0.5">
                              {item.action_items.map((ai, i) => (
                                <li key={i} className="text-xs text-gray-600 flex items-start gap-1">
                                  <span className="text-indigo-400 mt-0.5">•</span>{ai}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Minutes */}
            {meeting.minutes_text && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-gray-500 uppercase">Minutes</p>
                  {!meeting.minutes_approved && (
                    <button
                      onClick={() => approveMutation.mutate()}
                      disabled={approveMutation.isPending}
                      className="text-xs px-3 py-1 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                    >
                      {approveMutation.isPending ? 'Approving…' : 'Approve Minutes'}
                    </button>
                  )}
                  {meeting.minutes_approved && (
                    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" /> Approved
                    </span>
                  )}
                </div>
                <pre className="text-xs text-gray-700 whitespace-pre-wrap bg-gray-50 p-3 rounded-lg border">{meeting.minutes_text}</pre>
              </div>
            )}

            {/* Complete Meeting */}
            {meeting.status !== 'completed' && meeting.status !== 'cancelled' && (
              <div>
                {!showCompleteForm ? (
                  <button
                    onClick={() => setShowCompleteForm(true)}
                    className="w-full py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
                  >
                    Complete Meeting
                  </button>
                ) : (
                  <div className="border border-indigo-200 bg-indigo-50 rounded-lg p-4 space-y-3">
                    <p className="text-sm font-semibold text-indigo-900">Complete Meeting</p>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Minutes</label>
                      <textarea
                        value={minutesText}
                        onChange={(e) => setMinutesText(e.target.value)}
                        rows={5}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        placeholder="Enter meeting minutes…"
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="quorum"
                        checked={quorumMet}
                        onChange={(e) => setQuorumMet(e.target.checked)}
                        className="rounded"
                      />
                      <label htmlFor="quorum" className="text-sm text-gray-700">Quorum was met</label>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setShowCompleteForm(false)}
                        className="flex-1 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => completeMutation.mutate({ minutes_text: minutesText, quorum_met: quorumMet, actual_date: new Date().toISOString() })}
                        disabled={completeMutation.isPending}
                        className="flex-1 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                      >
                        {completeMutation.isPending ? 'Saving…' : 'Save & Complete'}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function BoardGovernance({ tenantId: _tenantId }: Props) {
  const queryClient = useQueryClient();
  const [showAddCommittee, setShowAddCommittee] = useState(false);
  const [showCreateMeeting, setShowCreateMeeting] = useState(false);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [calendarYear] = useState(CURRENT_YEAR);

  const { data: committeesRaw } = useQuery<BoardCommittee[]>({
    queryKey: ['committees'],
    queryFn: () => fetchCommittees(true),
    retry: 1,
  });
  const committees = committeesRaw ?? [];

  const { data: meetingsRaw } = useQuery<BoardMeeting[]>({
    queryKey: ['meetings'],
    queryFn: () => fetchMeetings({ limit: 50 }),
    retry: 1,
  });
  const meetings = meetingsRaw ?? [];

  const { data: _calendarData } = useQuery({
    queryKey: ['board-calendar', calendarYear],
    queryFn: () => fetchBoardCalendar(calendarYear),
    retry: 1,
  });

  const committeeMutation = useMutation({
    mutationFn: createCommittee,
    onSuccess: () => {
      setShowAddCommittee(false);
      void queryClient.invalidateQueries({ queryKey: ['committees'] });
    },
  });

  const meetingMutation = useMutation({
    mutationFn: createMeeting,
    onSuccess: () => {
      setShowCreateMeeting(false);
      void queryClient.invalidateQueries({ queryKey: ['meetings'] });
    },
  });

  // Upcoming meetings sorted by date
  const upcomingMeetings = [...meetings]
    .filter((m) => m.status === 'scheduled' && new Date(m.scheduled_date) >= new Date())
    .sort((a, b) => new Date(a.scheduled_date).getTime() - new Date(b.scheduled_date).getTime())
    .slice(0, 5);

  // Calendar grid: meetings by quarter
  const meetingsByQuarter: Record<string, BoardMeeting[]> = { Q1: [], Q2: [], Q3: [], Q4: [] };
  meetings.forEach((m) => {
    if (new Date(m.scheduled_date).getFullYear() === calendarYear) {
      const q = getQuarter(m.scheduled_date);
      meetingsByQuarter[q].push(m);
    }
  });

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Board Governance</h2>
          <p className="text-sm text-gray-500 mt-0.5">Committees, meetings, and board calendar</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddCommittee(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            <Plus className="w-4 h-4" />Add Committee
          </button>
          <button
            onClick={() => setShowCreateMeeting(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            <Plus className="w-4 h-4" />Create Meeting
          </button>
        </div>
      </div>

      {/* Committees */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Committees</h3>
        {committees.length === 0 ? (
          <p className="text-sm text-gray-400 italic">No committees found.</p>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {committees.map((c) => (
              <div key={c.id} className="metric-card hover:shadow-md transition-shadow">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-gray-50 rounded-lg">{committeeIcon(c.committee_type)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-semibold text-gray-800 truncate">{c.name}</p>
                      {c.is_active && (
                        <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full">Active</span>
                      )}
                    </div>
                    {c.chair && <p className="text-xs text-gray-500 mt-0.5">Chair: {c.chair}</p>}
                    <p className="text-xs text-gray-500">{c.members.length} members</p>
                    {c.meeting_count !== undefined && (
                      <p className="text-xs text-indigo-600 font-medium mt-1">{c.meeting_count} meetings</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Annual Calendar */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Board Calendar {calendarYear}</h3>
        <div className="grid grid-cols-4 gap-3">
          {QUARTERS.map((q) => (
            <div key={q} className="bg-gray-50 rounded-xl p-3 min-h-32">
              <p className="text-xs font-bold text-gray-500 uppercase mb-2">{q}</p>
              {meetingsByQuarter[q].length === 0 ? (
                <p className="text-xs text-gray-300 italic">No meetings</p>
              ) : (
                <div className="space-y-1.5">
                  {meetingsByQuarter[q].map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setSelectedMeetingId(m.id)}
                      className="w-full text-left p-2 bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow border border-gray-100"
                    >
                      <p className="text-xs font-medium text-gray-800 truncate">{m.title}</p>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${meetingTypeColor(m.meeting_type)}`}>{m.meeting_type}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${statusColor(m.status)}`}>{m.status}</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{new Date(m.scheduled_date).toLocaleDateString()}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Upcoming Meetings */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Upcoming Meetings</h3>
        {upcomingMeetings.length === 0 ? (
          <p className="text-sm text-gray-400 italic">No upcoming meetings.</p>
        ) : (
          <div className="space-y-2">
            {upcomingMeetings.map((m) => {
              const days = daysUntil(m.scheduled_date);
              return (
                <button
                  key={m.id}
                  onClick={() => setSelectedMeetingId(m.id)}
                  className="w-full text-left metric-card hover:shadow-md transition-shadow flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-12 h-12 rounded-lg flex flex-col items-center justify-center text-white text-xs font-bold ${days <= 7 ? 'bg-red-500' : days <= 14 ? 'bg-orange-400' : 'bg-indigo-500'}`}>
                      <span className="text-lg leading-none">{days}</span>
                      <span className="text-xs opacity-80">days</span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-800">{m.title}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <Clock className="w-3 h-3 text-gray-400" />
                        <span className="text-xs text-gray-500">{new Date(m.scheduled_date).toLocaleString()}</span>
                        {m.committee_name && (
                          <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{m.committee_name}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Modals */}
      {showAddCommittee && (
        <AddCommitteeModal
          onClose={() => setShowAddCommittee(false)}
          onSubmit={(data) => committeeMutation.mutate(data)}
          submitting={committeeMutation.isPending}
        />
      )}
      {showCreateMeeting && (
        <CreateMeetingModal
          committees={committees}
          onClose={() => setShowCreateMeeting(false)}
          onSubmit={(data) => meetingMutation.mutate(data)}
          submitting={meetingMutation.isPending}
        />
      )}
      {selectedMeetingId && (
        <MeetingDrawer
          meetingId={selectedMeetingId}
          onClose={() => setSelectedMeetingId(null)}
        />
      )}
    </div>
  );
}
