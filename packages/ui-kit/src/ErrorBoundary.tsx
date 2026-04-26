/**
 * ErrorBoundary — single canonical implementation for every VIA UI.
 *
 * Replaces the 6 byte-identical copies that lived under
 *   services/{audit-planning,monitoring,pbc,people,risk,tprm}-ui/src/components/ErrorBoundary.tsx
 *
 * Behaviour:
 *   - Logs to console (and to `onError` if provided) so a parent
 *     telemetry hook can ship the error to the monitoring service.
 *   - Renders the optional `fallback` if supplied; otherwise a built-in
 *     "try again" panel.
 */
import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Always surface — we explicitly do NOT want silent failures.
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info.componentStack);
    this.props.onError?.(error, info);
  }

  reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    return (
      <div
        role="alert"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 200,
          gap: 16,
          padding: 24,
          textAlign: 'center',
        }}
      >
        <p style={{ fontWeight: 600 }}>Something went wrong</p>
        <p style={{ fontSize: 14, color: '#6b7280' }}>
          {this.state.error?.message ?? 'An unexpected error occurred.'}
        </p>
        <button
          type="button"
          onClick={this.reset}
          style={{
            padding: '8px 16px',
            borderRadius: 6,
            background: '#4f46e5',
            color: 'white',
            border: 0,
            cursor: 'pointer',
          }}
        >
          Try again
        </button>
      </div>
    );
  }
}
