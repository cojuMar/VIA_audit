/**
 * Minimal toast surface — extracted from risk-ui's hand-rolled toaster.
 *
 * Stand-alone (no third-party dep). Wired into `@via/api-client.onError`
 * so a forced 500 anywhere in the stack visibly surfaces in the UI.
 */
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface Toast {
  id: string;
  kind: ToastKind;
  message: string;
  /** Auto-dismiss after N ms; 0 = sticky. Defaults to 5000. */
  durationMs?: number;
}

interface ToastContextValue {
  toasts: Toast[];
  push: (t: Omit<Toast, 'id'>) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error(
      'useToast must be used inside <ToasterProvider>. ' +
        'Wrap your <App/> in <ToasterProvider> at the root.',
    );
  }
  return ctx;
}

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { ...t, id }]);
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, push, dismiss }}>
      {children}
      <ToastViewport toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport({
  toasts,
  dismiss,
}: {
  toasts: Toast[];
  dismiss: (id: string) => void;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        right: 16,
        bottom: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        zIndex: 1100,
      }}
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} dismiss={dismiss} />
      ))}
    </div>
  );
}

function ToastItem({
  toast,
  dismiss,
}: {
  toast: Toast;
  dismiss: (id: string) => void;
}) {
  useEffect(() => {
    const ms = toast.durationMs ?? 5000;
    if (ms <= 0) return;
    const t = setTimeout(() => dismiss(toast.id), ms);
    return () => clearTimeout(t);
  }, [toast, dismiss]);

  const bg =
    toast.kind === 'error'
      ? '#dc2626'
      : toast.kind === 'warning'
        ? '#d97706'
        : toast.kind === 'success'
          ? '#16a34a'
          : '#334155';

  return (
    <div
      style={{
        background: bg,
        color: 'white',
        padding: '10px 14px',
        borderRadius: 6,
        minWidth: 220,
        maxWidth: 360,
        fontSize: 14,
        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
      }}
    >
      {toast.message}
    </div>
  );
}
