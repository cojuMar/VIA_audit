import {
  useState,
  useEffect,
  useRef,
  useCallback,
  type ChangeEvent,
} from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Camera,
  MapPin,
  Star,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Minus,
  Plus,
  Check,
  X,
  Edit3,
  Send,
} from 'lucide-react';
import {
  saveAudit,
  getAudit,
  saveResponse,
  getResponsesForAudit,
  savePhoto,
  getTemplate,
} from '../offline/db';
import { addResponse, submitAudit, createAudit } from '../api';
import { useOnlineStatus } from '../offline/sync';
import type { AuditTemplate, TemplateQuestion, ResponsePayload, FieldAudit } from '../types';

interface AuditPlayerProps {
  tenantId: string;
  assignmentId?: string;
  templateId: string;
  auditId?: string;
  auditorEmail: string;
  locationName: string;
  onComplete: () => void;
  onBack: () => void;
}

type PlayerStage = 'loading' | 'ready' | 'answering' | 'review' | 'signature' | 'submitting' | 'submitted';

interface LocalAnswers {
  [questionId: string]: ResponsePayload;
}

// ── Individual question renderer components ──────────────────────────────────

function YesNoQuestion({
  question,
  value,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  const current = value?.response_value;
  return (
    <div className="grid grid-cols-2 gap-3 mt-4">
      <button
        className={`tap-target rounded-xl py-5 flex flex-col items-center justify-center gap-2 border-2 text-lg font-bold transition-all ${
          current === 'yes'
            ? 'bg-green-500 border-green-500 text-white'
            : 'bg-green-50 border-green-200 text-green-700'
        }`}
        onClick={() => onChange({ response_value: 'yes', boolean_response: true })}
      >
        <Check size={28} />
        Yes
      </button>
      <button
        className={`tap-target rounded-xl py-5 flex flex-col items-center justify-center gap-2 border-2 text-lg font-bold transition-all ${
          current === 'no'
            ? 'bg-red-500 border-red-500 text-white'
            : 'bg-red-50 border-red-200 text-red-700'
        }`}
        onClick={() => onChange({ response_value: 'no', boolean_response: false })}
      >
        <X size={28} />
        No
      </button>
    </div>
  );
}

function MultipleChoiceQuestion({
  question,
  value,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  const current = value?.response_value;
  return (
    <div className="mt-4 space-y-2">
      {question.options.map((option) => (
        <button
          key={option}
          className={`w-full tap-target rounded-xl px-4 py-3 text-left border-2 font-medium transition-all ${
            current === option
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-gray-200 text-gray-800'
          }`}
          onClick={() => onChange({ response_value: option })}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function RatingQuestion({
  value,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  const current = value?.numeric_response ?? 0;
  return (
    <div className="mt-4">
      <div className="flex justify-center gap-3">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onClick={() => onChange({ numeric_response: star, response_value: String(star) })}
            className="tap-target p-2"
          >
            <Star
              size={36}
              className={
                star <= current
                  ? 'text-yellow-400 fill-yellow-400'
                  : 'text-gray-300 fill-gray-100'
              }
            />
          </button>
        ))}
      </div>
      {current > 0 && (
        <p className="text-center text-sm text-gray-600 mt-2">{current} / 5 stars</p>
      )}
    </div>
  );
}

function NumericQuestion({
  value,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  const current = value?.numeric_response ?? 0;
  const set = (n: number) => onChange({ numeric_response: n, response_value: String(n) });
  return (
    <div className="mt-4 flex items-center gap-4 justify-center">
      <button
        className="w-14 h-14 rounded-full bg-gray-200 flex items-center justify-center active:bg-gray-300"
        onClick={() => set(Math.max(0, current - 1))}
      >
        <Minus size={22} />
      </button>
      <input
        type="number"
        value={current}
        onChange={(e) => set(Number(e.target.value))}
        className="input-field text-center text-2xl font-bold w-28"
      />
      <button
        className="w-14 h-14 rounded-full bg-gray-200 flex items-center justify-center active:bg-gray-300"
        onClick={() => set(current + 1)}
      >
        <Plus size={22} />
      </button>
    </div>
  );
}

function TextQuestion({
  value,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  return (
    <div className="mt-4">
      <textarea
        className="input-field min-h-[120px] resize-none"
        placeholder="Enter your answer..."
        value={value?.response_value ?? ''}
        onChange={(e) => onChange({ response_value: e.target.value })}
        rows={4}
      />
    </div>
  );
}

function PhotoQuestion({
  question,
  value,
  auditId,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  auditId: string;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [thumbnails, setThumbnails] = useState<string[]>([]);

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (ev) => {
      const dataUrl = ev.target?.result as string;
      const syncId = crypto.randomUUID();

      // Save photo locally
      await savePhoto({
        sync_id: syncId,
        audit_id: auditId,
        data_url: dataUrl,
        filename: file.name,
        _synced: false,
      });

      const newRefs = [...(value?.photo_references ?? []), syncId];
      setThumbnails((prev) => [...prev, dataUrl]);
      onChange({ photo_references: newRefs });
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="mt-4 space-y-3">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleFileChange}
      />
      <button
        onClick={() => fileRef.current?.click()}
        className="w-full tap-target rounded-xl border-2 border-dashed border-blue-300 bg-blue-50 flex flex-col items-center justify-center py-6 gap-2 text-blue-600 active:bg-blue-100"
      >
        <Camera size={32} />
        <span className="font-semibold">Take Photo</span>
        <span className="text-xs text-blue-400">Required for this question</span>
      </button>

      {thumbnails.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {thumbnails.map((src, i) => (
            <img
              key={i}
              src={src}
              alt={`Photo ${i + 1}`}
              className="w-full h-24 object-cover rounded-lg border border-gray-200"
            />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400 text-center">
        {value?.photo_references?.length ?? 0} photo(s) captured
      </p>
    </div>
  );
}

function GpsQuestion({
  value,
  onChange,
}: {
  question: TemplateQuestion;
  value?: ResponsePayload;
  onChange: (r: Partial<ResponsePayload>) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const capture = () => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported on this device');
      return;
    }
    setLoading(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        onChange({
          gps_latitude: pos.coords.latitude,
          gps_longitude: pos.coords.longitude,
          response_value: `${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)}`,
        });
        setLoading(false);
      },
      (err) => {
        setError(err.message);
        setLoading(false);
      },
      { enableHighAccuracy: true, timeout: 15000 }
    );
  };

  return (
    <div className="mt-4 space-y-3">
      <button
        onClick={capture}
        disabled={loading}
        className="w-full btn-primary gap-2 py-4"
      >
        {loading ? <Loader2 size={20} className="animate-spin" /> : <MapPin size={20} />}
        {loading ? 'Getting location…' : 'Capture GPS Location'}
      </button>

      {value?.gps_latitude != null && value.gps_longitude != null && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-3 flex items-start gap-2">
          <CheckCircle2 size={16} className="text-green-600 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-green-800">
            <p className="font-medium">Location captured</p>
            <p className="text-xs mt-0.5">
              {value.gps_latitude.toFixed(6)}, {value.gps_longitude.toFixed(6)}
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
          <AlertTriangle size={16} className="text-red-500 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
    </div>
  );
}

function SignatureCanvas({
  onSave,
}: {
  onSave: (dataUrl: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const isDrawing = useRef(false);
  const [hasSignature, setHasSignature] = useState(false);

  const getPos = (e: React.TouchEvent | React.MouseEvent, canvas: HTMLCanvasElement) => {
    const rect = canvas.getBoundingClientRect();
    if ('touches' in e) {
      const touch = e.touches[0];
      return { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
    }
    return { x: (e as React.MouseEvent).clientX - rect.left, y: (e as React.MouseEvent).clientY - rect.top };
  };

  const startDraw = (e: React.TouchEvent | React.MouseEvent) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    isDrawing.current = true;
    const pos = getPos(e, canvas);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  };

  const draw = (e: React.TouchEvent | React.MouseEvent) => {
    e.preventDefault();
    if (!isDrawing.current) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const pos = getPos(e, canvas);
    ctx.lineTo(pos.x, pos.y);
    ctx.strokeStyle = '#1e3a8a';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
    setHasSignature(true);
  };

  const stopDraw = () => {
    isDrawing.current = false;
    if (hasSignature && canvasRef.current) {
      onSave(canvasRef.current.toDataURL());
    }
  };

  const clear = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setHasSignature(false);
    onSave('');
  };

  return (
    <div className="mt-4 space-y-2">
      <div className="border-2 border-gray-300 rounded-xl overflow-hidden bg-white">
        <canvas
          ref={canvasRef}
          width={340}
          height={180}
          className="w-full touch-none"
          style={{ height: '180px' }}
          onMouseDown={startDraw}
          onMouseMove={draw}
          onMouseUp={stopDraw}
          onMouseLeave={stopDraw}
          onTouchStart={startDraw}
          onTouchMove={draw}
          onTouchEnd={stopDraw}
        />
        <div className="border-t border-gray-200 px-3 py-1 flex justify-between items-center">
          <span className="text-xs text-gray-400">Sign above</span>
          <button onClick={clear} className="text-xs text-red-500 tap-target px-2">
            Clear
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main AuditPlayer ─────────────────────────────────────────────────────────

export default function AuditPlayer({
  tenantId: _tenantId,
  assignmentId,
  templateId,
  auditId: initialAuditId,
  auditorEmail,
  locationName,
  onComplete,
  onBack,
}: AuditPlayerProps) {
  const isOnline = useOnlineStatus();

  const [stage, setStage] = useState<PlayerStage>('loading');
  const [template, setTemplate] = useState<AuditTemplate | null>(null);
  const [auditId, setAuditId] = useState<string>(initialAuditId ?? '');
  const [currentSectionIdx, setCurrentSectionIdx] = useState(0);
  const [currentQIdx, setCurrentQIdx] = useState(0);
  const [answers, setAnswers] = useState<LocalAnswers>({});
  const [signature, setSignature] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [gpsCoords, setGpsCoords] = useState<{ lat: number; lon: number } | null>(null);

  // ── Initialize: load template and existing answers ──────────────────────
  useEffect(() => {
    async function init() {
      // Try IndexedDB first
      let tpl = await getTemplate(templateId);

      if (!tpl && isOnline) {
        try {
          const { fetchTemplate } = await import('../api');
          tpl = await fetchTemplate(templateId);
          if (tpl) {
            const { saveTemplate } = await import('../offline/db');
            await saveTemplate(tpl);
          }
        } catch (e) {
          console.error('Failed to fetch template:', e);
        }
      }

      if (!tpl) {
        setStage('ready');
        return;
      }

      setTemplate(tpl);

      // Create or load audit record
      let aid = auditId;
      if (!aid) {
        aid = crypto.randomUUID();
        const newAudit: FieldAudit = {
          id: aid,
          assignment_id: assignmentId,
          template_id: templateId,
          auditor_email: auditorEmail,
          location_name: locationName,
          status: 'in_progress',
          started_at: new Date().toISOString(),
          total_findings: 0,
          _localOnly: true,
          _pendingSync: true,
        };

        await saveAudit(newAudit);

        // Try to create on server
        if (isOnline) {
          try {
            const serverAudit = await createAudit({
              id: aid,
              assignment_id: assignmentId,
              template_id: templateId,
              auditor_email: auditorEmail,
              location_name: locationName,
              status: 'in_progress',
              started_at: newAudit.started_at,
            });
            await saveAudit({ ...serverAudit, _pendingSync: false, _localOnly: false });
          } catch {
            // Will sync later
          }
        }

        setAuditId(aid);
      } else {
        // Load existing answers
        const existing = await getResponsesForAudit(aid);
        const map: LocalAnswers = {};
        for (const r of existing) {
          map[r.question_id] = r;
        }
        setAnswers(map);
      }

      // Capture GPS if template requires it
      if (tpl.requires_gps && navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (pos) => setGpsCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
          () => { /* silent */ },
          { enableHighAccuracy: true, timeout: 10000 }
        );
      }

      setStage('answering');
    }

    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateId]);

  const currentSection = template?.sections[currentSectionIdx];
  const currentQuestion = currentSection?.questions[currentQIdx];
  const totalSections = template?.sections.length ?? 1;

  // ── Answer handling ─────────────────────────────────────────────────────
  const handleAnswer = useCallback(
    async (questionId: string, patch: Partial<ResponsePayload>) => {
      const question = currentSection?.questions.find((q) => q.id === questionId);
      if (!question) return;

      const existing = answers[questionId];
      const isFinding = detectFinding(question, patch);
      const severity = isFinding ? (existing?.finding_severity ?? 'medium') : undefined;

      const response: ResponsePayload = {
        sync_id: existing?.sync_id ?? crypto.randomUUID(),
        question_id: questionId,
        photo_references: existing?.photo_references ?? [],
        is_finding: isFinding,
        finding_severity: severity,
        client_answered_at: new Date().toISOString(),
        ...patch,
      };

      // Add GPS coords to every response if available
      if (gpsCoords) {
        response.gps_latitude = gpsCoords.lat;
        response.gps_longitude = gpsCoords.lon;
      }

      // Save locally immediately
      await saveResponse(auditId, response);
      setAnswers((prev) => ({ ...prev, [questionId]: response }));

      // Try server if online
      if (isOnline) {
        addResponse(auditId, response).catch(() => { /* queued locally */ });
      }
    },
    [auditId, answers, currentSection, gpsCoords, isOnline]
  );

  const updateFindingSeverity = useCallback(
    async (questionId: string, severity: string) => {
      const existing = answers[questionId];
      if (!existing) return;
      const updated = { ...existing, finding_severity: severity };
      await saveResponse(auditId, updated);
      setAnswers((prev) => ({ ...prev, [questionId]: updated }));
    },
    [answers, auditId]
  );

  const updateComment = useCallback(
    async (questionId: string, comment: string) => {
      const existing = answers[questionId];
      if (!existing) return;
      const updated = { ...existing, comment };
      await saveResponse(auditId, updated);
      setAnswers((prev) => ({ ...prev, [questionId]: updated }));
    },
    [answers, auditId]
  );

  // ── Navigation ──────────────────────────────────────────────────────────
  const goNext = () => {
    if (!template || !currentSection) return;
    if (currentQIdx < currentSection.questions.length - 1) {
      setCurrentQIdx((i) => i + 1);
    } else if (currentSectionIdx < totalSections - 1) {
      setCurrentSectionIdx((i) => i + 1);
      setCurrentQIdx(0);
    } else {
      setStage('review');
    }
  };

  const goBack = () => {
    if (currentQIdx > 0) {
      setCurrentQIdx((i) => i - 1);
    } else if (currentSectionIdx > 0) {
      const prevSection = template!.sections[currentSectionIdx - 1];
      setCurrentSectionIdx((i) => i - 1);
      setCurrentQIdx(prevSection.questions.length - 1);
    } else {
      onBack();
    }
  };

  // ── Submit ──────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    setStage('submitting');
    setSubmitError(null);

    const findingCount = Object.values(answers).filter((a) => a.is_finding).length;

    try {
      const audit = await getAudit(auditId);
      const updatedAudit: FieldAudit = {
        ...(audit ?? {
          id: auditId,
          template_id: templateId,
          auditor_email: auditorEmail,
          location_name: locationName,
          started_at: new Date().toISOString(),
          total_findings: 0,
        }),
        status: 'submitted',
        completed_at: new Date().toISOString(),
        submitted_at: new Date().toISOString(),
        total_findings: findingCount,
        _pendingSync: true,
      };

      await saveAudit(updatedAudit);

      if (isOnline) {
        await submitAudit(auditId, {
          signature_data: signature || undefined,
          gps_latitude: gpsCoords?.lat,
          gps_longitude: gpsCoords?.lon,
        });
        await saveAudit({ ...updatedAudit, _pendingSync: false });
      }

      setStage('submitted');
    } catch (err) {
      setSubmitError('Submission failed. Your audit has been saved locally and will sync when online.');
      setStage('submitting');
    }
  };

  // ── Render helpers ──────────────────────────────────────────────────────

  if (stage === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center space-y-3">
          <Loader2 size={40} className="animate-spin text-blue-600 mx-auto" />
          <p className="text-gray-600">Loading audit template…</p>
        </div>
      </div>
    );
  }

  if (stage === 'submitted') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6 text-center">
        <CheckCircle2 size={64} className="text-green-500 mb-4" />
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Audit Submitted!</h2>
        <p className="text-gray-600 mb-2">
          {Object.values(answers).filter((a) => a.is_finding).length} finding(s) recorded
        </p>
        {!isOnline && (
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 mb-6">
            Saved offline — will sync when you're back online
          </p>
        )}
        <button onClick={onComplete} className="btn-primary w-full mt-4">
          Done
        </button>
      </div>
    );
  }

  if (stage === 'review') {
    return (
      <ReviewScreen
        template={template!}
        answers={answers}
        onUpdateSeverity={updateFindingSeverity}
        onUpdateComment={updateComment}
        onBack={() => {
          const lastSection = template!.sections[template!.sections.length - 1];
          setCurrentSectionIdx(template!.sections.length - 1);
          setCurrentQIdx(lastSection.questions.length - 1);
          setStage('answering');
        }}
        onProceedToSignature={() => setStage('signature')}
        onProceedToSubmit={handleSubmit}
        templateRequiresSignature={template?.requires_signature ?? false}
      />
    );
  }

  if (stage === 'signature') {
    return (
      <div className="min-h-screen bg-gray-50 pb-safe">
        <header className="bg-white border-b border-gray-200 px-4 py-4 flex items-center gap-3">
          <button onClick={() => setStage('review')} className="tap-target p-1 -ml-1">
            <ChevronLeft size={24} />
          </button>
          <div>
            <h1 className="font-bold text-gray-900">Auditor Signature</h1>
            <p className="text-sm text-gray-500">{locationName}</p>
          </div>
        </header>
        <div className="p-4 space-y-4">
          <p className="text-sm text-gray-600">
            By signing below, you certify that this audit was conducted accurately and completely.
          </p>
          <SignatureCanvas onSave={setSignature} />
          {submitError && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3 flex gap-2 text-sm text-red-700">
              <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
              {submitError}
            </div>
          )}
          <button
            onClick={handleSubmit}
            disabled={stage === 'submitting'}
            className="btn-primary w-full gap-2 py-4"
          >
            {stage === 'submitting' ? (
              <><Loader2 size={18} className="animate-spin" /> Submitting…</>
            ) : (
              <><Send size={18} /> Submit Audit</>
            )}
          </button>
          {!isOnline && (
            <p className="text-xs text-amber-600 text-center">
              Offline: audit will be submitted when connection is restored
            </p>
          )}
        </div>
      </div>
    );
  }

  if (stage === 'submitting') {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-6 text-center">
        <Loader2 size={48} className="animate-spin text-blue-600 mb-4" />
        <p className="text-gray-700 font-medium">Submitting audit…</p>
        {submitError && (
          <div className="mt-4 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-700 text-left">
            <p>{submitError}</p>
            <button onClick={onComplete} className="btn-primary mt-3 w-full">
              Done
            </button>
          </div>
        )}
      </div>
    );
  }

  if (!currentSection || !currentQuestion) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">No template available offline. Please connect to load templates.</p>
      </div>
    );
  }

  const currentAnswer = answers[currentQuestion.id];
  const isFinding = currentAnswer?.is_finding ?? false;
  const needsPhotoForFinding =
    isFinding && currentQuestion.requires_photo_if === 'no' &&
    (!currentAnswer?.photo_references || currentAnswer.photo_references.length === 0);
  const questionProgress =
    template!.sections
      .slice(0, currentSectionIdx)
      .reduce((sum, s) => sum + s.questions.length, 0) + currentQIdx + 1;
  const totalQuestions = template!.sections.reduce((sum, s) => sum + s.questions.length, 0);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col pb-safe">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={goBack} className="tap-target p-1 -ml-1">
            <ChevronLeft size={24} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-bold text-gray-900 text-sm truncate">{locationName}</h1>
            <p className="text-xs text-gray-500 truncate">{currentSection.name}</p>
          </div>
          <span className="text-xs text-gray-400 flex-shrink-0">
            {questionProgress}/{totalQuestions}
          </span>
        </div>

        {/* Section progress bar */}
        <div className="mt-2 flex gap-1">
          {template!.sections.map((_, idx) => (
            <div
              key={idx}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                idx < currentSectionIdx
                  ? 'bg-blue-600'
                  : idx === currentSectionIdx
                  ? 'bg-blue-400'
                  : 'bg-gray-200'
              }`}
            />
          ))}
        </div>
      </header>

      {/* Question area */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Finding badge */}
        {isFinding && (
          <div className="mb-3 bg-red-50 border border-red-300 rounded-xl px-3 py-2 flex items-center gap-2">
            <AlertTriangle size={16} className="text-red-500 flex-shrink-0" />
            <span className="text-sm font-semibold text-red-700">FINDING DETECTED</span>
          </div>
        )}

        <div className={`rounded-xl p-4 mb-3 ${isFinding ? 'border-2 border-red-400 bg-red-50' : 'bg-white border border-gray-100 shadow-sm'}`}>
          {currentQuestion.is_required && (
            <span className="text-xs font-semibold text-red-500 uppercase tracking-wide">Required</span>
          )}
          <p className="text-lg font-semibold text-gray-900 mt-1 leading-snug">
            {currentQuestion.question_text}
          </p>

          {/* Photo requirement notice */}
          {needsPhotoForFinding && (
            <div className="mt-2 text-sm text-orange-700 bg-orange-50 rounded-lg p-2 flex items-center gap-1">
              <Camera size={14} />
              Photo required for this finding
            </div>
          )}

          {/* Render question type */}
          {currentQuestion.question_type === 'yes_no' && (
            <YesNoQuestion
              question={currentQuestion}
              value={currentAnswer}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
          {currentQuestion.question_type === 'multiple_choice' && (
            <MultipleChoiceQuestion
              question={currentQuestion}
              value={currentAnswer}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
          {currentQuestion.question_type === 'rating' && (
            <RatingQuestion
              question={currentQuestion}
              value={currentAnswer}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
          {currentQuestion.question_type === 'numeric' && (
            <NumericQuestion
              question={currentQuestion}
              value={currentAnswer}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
          {currentQuestion.question_type === 'text' && (
            <TextQuestion
              question={currentQuestion}
              value={currentAnswer}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
          {currentQuestion.question_type === 'photo' && (
            <PhotoQuestion
              question={currentQuestion}
              value={currentAnswer}
              auditId={auditId}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
          {currentQuestion.question_type === 'signature' && (
            <SignatureCanvas onSave={(dataUrl) => handleAnswer(currentQuestion.id, { response_value: dataUrl })} />
          )}
          {currentQuestion.question_type === 'gps_location' && (
            <GpsQuestion
              question={currentQuestion}
              value={currentAnswer}
              onChange={(patch) => handleAnswer(currentQuestion.id, patch)}
            />
          )}
        </div>

        {/* Photo capture if finding requires it */}
        {isFinding && currentQuestion.requires_photo_if === 'no' && (
          <div className="mb-3">
            <p className="label-text">Finding Photo Evidence</p>
            <PhotoQuestion
              question={currentQuestion}
              value={currentAnswer}
              auditId={auditId}
              onChange={(patch) =>
                handleAnswer(currentQuestion.id, {
                  ...currentAnswer,
                  ...patch,
                  photo_references: patch.photo_references ?? currentAnswer?.photo_references ?? [],
                })
              }
            />
          </div>
        )}

        {/* Finding severity selector */}
        {isFinding && (
          <div className="mb-3">
            <p className="label-text">Finding Severity</p>
            <div className="grid grid-cols-4 gap-2">
              {['critical', 'high', 'medium', 'low'].map((sev) => (
                <button
                  key={sev}
                  onClick={() => updateFindingSeverity(currentQuestion.id, sev)}
                  className={`tap-target rounded-lg py-2 text-xs font-semibold capitalize border-2 ${
                    currentAnswer?.finding_severity === sev
                      ? SEV_ACTIVE[sev]
                      : 'border-gray-200 text-gray-600 bg-white'
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Comment field (shown when finding or comment required) */}
        {(isFinding || currentQuestion.requires_comment_if) && (
          <div className="mb-3">
            <p className="label-text flex items-center gap-1">
              <Edit3 size={13} />
              {isFinding ? 'Finding Notes' : 'Comment'}
            </p>
            <textarea
              className="input-field min-h-[80px] resize-none"
              placeholder="Add notes or corrective action…"
              value={currentAnswer?.comment ?? ''}
              onChange={(e) => updateComment(currentQuestion.id, e.target.value)}
              rows={3}
            />
          </div>
        )}
      </div>

      {/* Navigation footer */}
      <div className="bg-white border-t border-gray-200 px-4 py-3 flex gap-3 flex-shrink-0 safe-bottom">
        <button onClick={goBack} className="btn-secondary flex-1 gap-1">
          <ChevronLeft size={18} />
          Back
        </button>
        <button
          onClick={goNext}
          disabled={currentQuestion.is_required && !currentAnswer}
          className="btn-primary flex-1 gap-1"
        >
          {isLastQuestion(currentSectionIdx, currentQIdx, template!) ? 'Review' : 'Next'}
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}

// ── Review screen ────────────────────────────────────────────────────────────

function ReviewScreen({
  template,
  answers,
  onUpdateSeverity,
  onUpdateComment,
  onBack,
  onProceedToSignature,
  onProceedToSubmit,
  templateRequiresSignature,
}: {
  template: AuditTemplate;
  answers: LocalAnswers;
  onUpdateSeverity: (qId: string, sev: string) => void;
  onUpdateComment: (qId: string, comment: string) => void;
  onBack: () => void;
  onProceedToSignature: () => void;
  onProceedToSubmit: () => void;
  templateRequiresSignature: boolean;
}) {
  const allQuestions = template.sections.flatMap((s) => s.questions);
  const findings = allQuestions.filter((q) => answers[q.id]?.is_finding);
  const answeredCount = allQuestions.filter((q) => answers[q.id]).length;

  return (
    <div className="min-h-screen bg-gray-50 pb-safe">
      <header className="bg-white border-b border-gray-200 px-4 py-4 flex items-center gap-3">
        <button onClick={onBack} className="tap-target p-1 -ml-1">
          <ChevronLeft size={24} />
        </button>
        <div>
          <h1 className="font-bold text-gray-900">Review Audit</h1>
          <p className="text-sm text-gray-500">
            {answeredCount}/{allQuestions.length} answered · {findings.length} findings
          </p>
        </div>
      </header>

      <div className="p-4 space-y-4">
        {findings.length > 0 && (
          <section>
            <h2 className="section-header text-red-700 flex items-center gap-2">
              <AlertTriangle size={18} />
              Findings ({findings.length})
            </h2>
            <div className="space-y-3">
              {findings.map((q) => {
                const ans = answers[q.id]!;
                return (
                  <div
                    key={q.id}
                    className={`finding-${ans.finding_severity ?? 'medium'} rounded-xl p-4 space-y-2`}
                  >
                    <p className="font-semibold text-sm">{q.question_text}</p>
                    <p className="text-xs opacity-75">
                      Response: {ans.response_value ?? (ans.boolean_response != null ? String(ans.boolean_response) : '—')}
                    </p>
                    {/* Severity picker */}
                    <div className="flex gap-2 flex-wrap">
                      {['critical', 'high', 'medium', 'low'].map((sev) => (
                        <button
                          key={sev}
                          onClick={() => onUpdateSeverity(q.id, sev)}
                          className={`px-2 py-1 rounded text-xs font-semibold capitalize border tap-target ${
                            ans.finding_severity === sev ? SEV_ACTIVE[sev] : 'border-gray-300 text-gray-600'
                          }`}
                        >
                          {sev}
                        </button>
                      ))}
                    </div>
                    {/* Comment */}
                    <textarea
                      className="w-full border border-current/30 bg-white/60 rounded-lg px-2 py-2 text-xs resize-none min-h-[60px]"
                      placeholder="Notes / corrective action…"
                      value={ans.comment ?? ''}
                      onChange={(e) => onUpdateComment(q.id, e.target.value)}
                      rows={2}
                    />
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* All answers summary */}
        <section>
          <h2 className="section-header">All Responses</h2>
          {template.sections.map((section) => (
            <div key={section.name} className="mb-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                {section.name}
              </p>
              <div className="space-y-1">
                {section.questions.map((q) => {
                  const ans = answers[q.id];
                  return (
                    <div key={q.id} className="flex items-start gap-2 py-2 border-b border-gray-100">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-700 leading-tight">{q.question_text}</p>
                      </div>
                      <div className="flex-shrink-0 text-right">
                        {ans ? (
                          <span className={`text-sm font-medium ${ans.is_finding ? 'text-red-600' : 'text-green-600'}`}>
                            {ans.response_value ?? (ans.numeric_response != null ? ans.numeric_response : '✓')}
                          </span>
                        ) : (
                          <span className="text-sm text-gray-400">—</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </section>

        <button
          onClick={templateRequiresSignature ? onProceedToSignature : onProceedToSubmit}
          className="btn-primary w-full gap-2 py-4"
        >
          <Send size={18} />
          {templateRequiresSignature ? 'Sign & Submit' : 'Submit Audit'}
        </button>
      </div>
    </div>
  );
}

// ── Utilities ────────────────────────────────────────────────────────────────

function detectFinding(question: TemplateQuestion, patch: Partial<ResponsePayload>): boolean {
  const val = patch.response_value ?? patch.boolean_response;
  if (question.requires_photo_if === 'no' && val === 'no') return true;
  if (question.requires_comment_if === 'no' && val === 'no') return true;
  if (question.question_type === 'yes_no' && val === false) return true;
  return false;
}

function isLastQuestion(sectionIdx: number, qIdx: number, template: AuditTemplate): boolean {
  return (
    sectionIdx === template.sections.length - 1 &&
    qIdx === template.sections[sectionIdx].questions.length - 1
  );
}

const SEV_ACTIVE: Record<string, string> = {
  critical: 'bg-red-600 border-red-600 text-white',
  high: 'bg-orange-500 border-orange-500 text-white',
  medium: 'bg-yellow-500 border-yellow-500 text-white',
  low: 'bg-blue-500 border-blue-500 text-white',
};
