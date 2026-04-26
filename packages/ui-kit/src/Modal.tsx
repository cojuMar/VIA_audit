/**
 * Accessible modal — replaces 25+ ad-hoc modal divs across the 13 UIs.
 *
 *   - role="dialog" + aria-modal="true"
 *   - aria-labelledby points at the title
 *   - Escape key closes
 *   - Focus is trapped while open and restored to the trigger on close
 *   - Backdrop click closes (configurable)
 *
 * WCAG 2.1 AA dialog pattern. See Sprint 27 for the full a11y rollout.
 */
import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
} from 'react';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Default true. Set false for destructive flows that need an explicit click. */
  closeOnBackdrop?: boolean;
  /** Optional custom labelled-by id (overrides the auto-generated one). */
  ariaLabelledBy?: string;
}

const FOCUSABLE =
  'a[href],area[href],input:not([disabled]),select:not([disabled]),' +
  'textarea:not([disabled]),button:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Modal({
  open,
  onClose,
  title,
  children,
  closeOnBackdrop = true,
  ariaLabelledBy,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const generatedTitleId = useId();
  const titleId = ariaLabelledBy ?? generatedTitleId;

  // Trap Tab inside the dialog so screen-reader / keyboard users can't
  // tab into the page underneath.
  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;

      const root = dialogRef.current;
      if (!root) return;
      const items = Array.from(
        root.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((el) => !el.hasAttribute('disabled'));
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement as HTMLElement | null;

      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [open, onClose],
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    // Focus the first focusable element inside the dialog (or the dialog itself).
    const root = dialogRef.current;
    const first = root?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? root)?.focus();

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      previouslyFocused.current?.focus();
    };
  }, [open, onKeyDown]);

  if (!open) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={() => closeOnBackdrop && onClose()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface-card, #fff)',
          borderRadius: 8,
          maxWidth: '90vw',
          maxHeight: '90vh',
          overflow: 'auto',
          padding: 24,
          minWidth: 320,
        }}
      >
        <h2 id={titleId} style={{ marginTop: 0 }}>
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
