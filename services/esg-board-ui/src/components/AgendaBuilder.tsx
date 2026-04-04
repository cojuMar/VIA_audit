import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle, MessageCircle, Info, Monitor, Plus, X, Clock,
  ClipboardList, ChevronDown,
} from 'lucide-react';
import {
  fetchMeetings, fetchMeeting, addAgendaItem, completeMeeting,
} from '../api';
import type { BoardMeeting, AgendaItem } from '../types';

interface Props { tenantId: string }

const ITEM_TYPES = ['discussion', 'approval', 'presentation', 'information', 'other'] as const;

function itemTypeIcon(type: string) {
  switch (type) {
    case 'approval': return <CheckCircle className="w-4 h-4 text-green-500" />;
    case 'discussion': return <MessageCircle className="w-4 h-4 text-blue-500" />;
    case 'information': return <Info className="w-4 h-4 text-gray-400" />;
    case 'presentation': return <Monitor className="w-4 h-4 text-purple-500" />;
    default: return <ClipboardList className="w-4 h-4 text-gray-400" />;
  }
}

function itemStatusColor(status: string) {
  switch (status) {
    case 'approved': return 'bg-green-100 text-green-700';
    case 'presented': return 'bg-blue-100 text-blue-700';
    case 'deferred': return 'bg-orange-100 text-orange-700';
    default: return 'bg-gray-100 text-gray-600';
  }
}

function formatDuration(totalMinutes: number) {
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} hr`;
  return `${h} hr ${m} min`;
}

interface AddItemFormProps {
  meetingId: string;
  nextSequence: number;
  onClose: () => void;
  onSubmit: (data: object) => void;
  submitting: boolean;
}
function AddItemForm({ meetingId, nextSequence, onClose, onSubmit, submitting }: AddItemFormProps) {
  const [title, setTitle] = useState('');
  const [itemType, setItemType] = useState<string>('discussion');
  const [presenter, setPresenter] = useState('');
  const [duration, setDuration] = useState(15);
  const [description, setDescription] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      meeting_id: meetingId,
      sequence_number: nextSequence,
      title,
      item_type: itemType,
      presenter: presenter || undefined,
      duration_minutes: duration,
      description: description || undefined,
    });
  };

  return (
    <div className="border border-indigo-200 bg-indigo-50 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-indigo-900">Add Agenda Item #{nextSequence}</p>
        <button onClick={onClose}><X className="w-4 h-4 text-indigo-500" /></button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Title</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            required
          />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
            <select
              value={itemType}
              onChange={(e) => setItemType(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {ITEM_TYPES.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Presenter</label>
            <input
              type="text"
              value={presenter}
              onChange={(e) => setPresenter(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Duration (min)</label>
            <input
              type="number"
              min={1}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="flex-1 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
          <button type="submit" disabled={submitting} className="flex-1 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {submitting ? 'Adding…' : 'Add Item'}
          </button>
        </div>
      </form>
    </div>
  );
}

interface MinutesEditorProps {
  meetingId: string;
  existingMinutes?: string;
  onComplete: () => void;
}
function MinutesEditor({ meetingId, existingMinutes, onComplete }: MinutesEditorProps) {
  const queryClient = useQueryClient();
  const [minutes, setMinutes] = useState(existingMinutes ?? '');
  const [quorumMet, setQuorumMet] = useState(true);
  const [open, setOpen] = useState(false);

  const completeMutation = useMutation({
    mutationFn: (data: object) => completeMeeting(meetingId, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['meeting', meetingId] });
      void queryClient.invalidateQueries({ queryKey: ['meetings'] });
      setOpen(false);
      onComplete();
    },
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
      >
        Complete Meeting &amp; Enter Minutes
      </button>
    );
  }

  return (
    <div className="border border-indigo-200 bg-indigo-50 rounded-xl p-4 space-y-3">
      <p className="text-sm font-semibold text-indigo-900">Meeting Minutes</p>
      <textarea
        value={minutes}
        onChange={(e) => setMinutes(e.target.value)}
        rows={8}
        placeholder="Enter meeting minutes, decisions made, and action items…"
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="quorum-met"
          checked={quorumMet}
          onChange={(e) => setQuorumMet(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="quorum-met" className="text-sm text-gray-700">Quorum was met</label>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="flex-1 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => completeMutation.mutate({
            minutes_text: minutes,
            quorum_met: quorumMet,
            actual_date: new Date().toISOString(),
          })}
          disabled={completeMutation.isPending}
          className="flex-1 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
        >
          {completeMutation.isPending ? 'Saving…' : 'Save &amp; Complete'}
        </button>
      </div>
    </div>
  );
}

export default function AgendaBuilder({ tenantId: _tenantId }: Props) {
  const queryClient = useQueryClient();
  const [selectedMeetingId, setSelectedMeetingId] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  const { data: meetingsRaw } = useQuery<BoardMeeting[]>({
    queryKey: ['meetings'],
    queryFn: () => fetchMeetings({ limit: 50 }),
    retry: 1,
  });
  const meetings = meetingsRaw ?? [];

  const { data: meeting } = useQuery<BoardMeeting>({
    queryKey: ['meeting', selectedMeetingId],
    queryFn: () => fetchMeeting(selectedMeetingId),
    enabled: !!selectedMeetingId,
  });

  const addItemMutation = useMutation({
    mutationFn: addAgendaItem,
    onSuccess: () => {
      setShowAddForm(false);
      void queryClient.invalidateQueries({ queryKey: ['meeting', selectedMeetingId] });
    },
  });

  const agendaItems: AgendaItem[] = meeting?.agenda_items
    ? [...meeting.agenda_items].sort((a, b) => a.sequence_number - b.sequence_number)
    : [];

  const totalMinutes = agendaItems.reduce((sum, item) => sum + item.duration_minutes, 0);
  const nextSequence = agendaItems.length > 0 ? Math.max(...agendaItems.map((i) => i.sequence_number)) + 1 : 1;

  const isCompleted = meeting?.status === 'completed';

  // Running time tracker
  let cumulativeMinutes = 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Agenda Builder</h2>
          <p className="text-sm text-gray-500 mt-0.5">Build and manage meeting agendas</p>
        </div>
      </div>

      {/* Meeting Selector */}
      <div className="metric-card">
        <label className="block text-sm font-medium text-gray-700 mb-2">Select Meeting</label>
        <div className="relative">
          <select
            value={selectedMeetingId}
            onChange={(e) => setSelectedMeetingId(e.target.value)}
            className="w-full appearance-none border border-gray-300 rounded-lg pl-3 pr-8 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Choose a meeting…</option>
            {meetings.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title} — {new Date(m.scheduled_date).toLocaleDateString()} [{m.status}]
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-3 w-4 h-4 text-gray-400 pointer-events-none" />
        </div>
      </div>

      {!selectedMeetingId ? (
        <div className="text-center py-16 text-gray-400">
          <ClipboardList className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>Select a meeting to build its agenda</p>
        </div>
      ) : !meeting ? (
        <div className="text-center py-8 text-gray-400">Loading meeting…</div>
      ) : (
        <div className="grid grid-cols-3 gap-6">
          {/* Main agenda timeline */}
          <div className="col-span-2 space-y-4">
            {/* Meeting info */}
            <div className="metric-card bg-indigo-50 border-indigo-200">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-base font-bold text-gray-900">{meeting.title}</h3>
                  <p className="text-sm text-gray-600 mt-0.5">{new Date(meeting.scheduled_date).toLocaleString()}</p>
                  {meeting.location && <p className="text-xs text-gray-500 mt-0.5">{meeting.location}</p>}
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${meeting.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'}`}>
                    {meeting.status}
                  </span>
                </div>
              </div>
            </div>

            {/* Estimated duration */}
            <div className="flex items-center gap-2 px-1">
              <Clock className="w-4 h-4 text-indigo-600" />
              <span className="text-sm font-medium text-gray-700">Estimated duration: </span>
              <span className="text-sm font-bold text-indigo-700">{formatDuration(totalMinutes)}</span>
              <span className="text-xs text-gray-400">({agendaItems.length} item{agendaItems.length !== 1 ? 's' : ''})</span>
            </div>

            {/* Agenda Timeline */}
            {agendaItems.length === 0 ? (
              <div className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center text-gray-400">
                <ClipboardList className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">No agenda items yet. Add the first item below.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {agendaItems.map((item) => {
                  const startMinute = cumulativeMinutes;
                  cumulativeMinutes += item.duration_minutes;
                  const startHour = Math.floor(startMinute / 60);
                  const startMin = startMinute % 60;
                  const timeLabel = `+${startHour > 0 ? `${startHour}h ` : ''}${startMin}min`;

                  return (
                    <div key={item.id} className="flex gap-3">
                      {/* Time marker */}
                      <div className="flex flex-col items-center w-14 shrink-0">
                        <span className="text-xs text-gray-400 font-mono">{timeLabel}</span>
                        <div className="flex-1 w-0.5 bg-gray-200 mt-1" />
                      </div>

                      {/* Item card */}
                      <div className={`flex-1 border rounded-xl p-3 mb-2 ${item.status === 'approved' ? 'border-green-200 bg-green-50' : item.status === 'deferred' ? 'border-orange-200 bg-orange-50' : 'border-gray-200 bg-white'}`}>
                        <div className="flex items-start gap-2">
                          <span className="w-6 h-6 flex items-center justify-center bg-indigo-100 text-indigo-700 text-xs font-bold rounded-full shrink-0 mt-0.5">
                            {item.sequence_number}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              {itemTypeIcon(item.item_type)}
                              <span className="text-sm font-semibold text-gray-800">{item.title}</span>
                              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${itemStatusColor(item.status)}`}>{item.status}</span>
                            </div>
                            <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                              {item.presenter && <span>Presenter: {item.presenter}</span>}
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />{item.duration_minutes} min
                              </span>
                            </div>
                            {item.description && (
                              <p className="text-xs text-gray-500 mt-1 line-clamp-2">{item.description}</p>
                            )}
                            {/* Show decisions/actions when completed */}
                            {isCompleted && (
                              <>
                                {item.decision && (
                                  <div className="mt-2 flex items-start gap-1.5">
                                    <CheckCircle className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                                    <p className="text-xs text-green-700 font-medium">{item.decision}</p>
                                  </div>
                                )}
                                {item.action_items.length > 0 && (
                                  <div className="mt-1.5 space-y-0.5">
                                    {item.action_items.map((ai, i) => (
                                      <div key={i} className="flex items-start gap-1.5">
                                        <span className="text-indigo-400 text-xs mt-0.5">→</span>
                                        <p className="text-xs text-gray-600">{ai}</p>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* End marker */}
                <div className="flex gap-3">
                  <div className="w-14 flex justify-center">
                    <span className="text-xs text-indigo-600 font-mono font-semibold">{formatDuration(totalMinutes)}</span>
                  </div>
                  <div className="flex-1 flex items-center gap-2 pb-2">
                    <div className="h-0.5 bg-indigo-200 flex-1 rounded" />
                    <span className="text-xs text-indigo-500 font-medium">End</span>
                  </div>
                </div>
              </div>
            )}

            {/* Add Item */}
            {!isCompleted && (
              showAddForm ? (
                <AddItemForm
                  meetingId={selectedMeetingId}
                  nextSequence={nextSequence}
                  onClose={() => setShowAddForm(false)}
                  onSubmit={(data) => addItemMutation.mutate(data)}
                  submitting={addItemMutation.isPending}
                />
              ) : (
                <button
                  onClick={() => setShowAddForm(true)}
                  className="w-full py-2.5 border-2 border-dashed border-gray-300 rounded-xl text-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600 transition-colors flex items-center justify-center gap-2"
                >
                  <Plus className="w-4 h-4" />Add Agenda Item
                </button>
              )
            )}
          </div>

          {/* Right panel */}
          <div className="space-y-4">
            {/* Duration summary */}
            <div className="metric-card">
              <p className="text-xs font-semibold text-gray-500 uppercase mb-3">Meeting Summary</p>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Total items</span>
                  <span className="font-semibold text-gray-800">{agendaItems.length}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Duration</span>
                  <span className="font-semibold text-indigo-700">{formatDuration(totalMinutes)}</span>
                </div>
                {[...ITEM_TYPES].map((type) => {
                  const count = agendaItems.filter((i) => i.item_type === type).length;
                  if (count === 0) return null;
                  return (
                    <div key={type} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-1.5">
                        {itemTypeIcon(type)}
                        <span className="text-gray-600 capitalize">{type}</span>
                      </div>
                      <span className="font-medium text-gray-700">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Attendees */}
            {meeting.attendees.length > 0 && (
              <div className="metric-card">
                <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Attendees ({meeting.attendees.length})</p>
                <div className="space-y-1">
                  {meeting.attendees.map((a, i) => (
                    <div key={i} className="text-sm text-gray-700 flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-indigo-300 shrink-0" />
                      {a}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Minutes / Complete */}
            {!isCompleted && (
              <MinutesEditor
                meetingId={selectedMeetingId}
                existingMinutes={meeting.minutes_text}
                onComplete={() => void queryClient.invalidateQueries({ queryKey: ['meeting', selectedMeetingId] })}
              />
            )}

            {isCompleted && meeting.minutes_text && (
              <div className="metric-card bg-green-50 border-green-200">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle className="w-4 h-4 text-green-600" />
                  <p className="text-xs font-semibold text-green-700 uppercase">Meeting Completed</p>
                  {meeting.minutes_approved && (
                    <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full ml-auto">Minutes Approved</span>
                  )}
                </div>
                <p className="text-xs text-gray-700 whitespace-pre-wrap line-clamp-6">{meeting.minutes_text}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
