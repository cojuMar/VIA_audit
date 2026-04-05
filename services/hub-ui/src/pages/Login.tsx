import { useState, type FormEvent } from 'react';
import { Eye, EyeOff, Shield, AlertCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useTheme, type Theme } from '../contexts/ThemeContext';

const THEME_LABELS: Record<Theme, string> = { dark: 'Dark', neutral: 'Neutral', light: 'Light' };

const DEMO_ACCOUNTS = [
  { email: 'admin@via.com',   password: 'admin123',   role: 'Super Admin',  color: 'text-rose-400' },
  { email: 'auditor@via.com', password: 'auditor123', role: 'Admin',        color: 'text-amber-400' },
  { email: 'user@via.com',    password: 'user123',    role: 'End User',     color: 'text-sky-400' },
];

export default function Login() {
  const { login, isLoading, error } = useAuth();
  const { theme, setTheme }         = useTheme();

  const [email,      setEmail]      = useState('');
  const [password,   setPassword]   = useState('');
  const [showPw,     setShowPw]     = useState(false);
  const [localError, setLocalError] = useState('');

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLocalError('');
    if (!email || !password) { setLocalError('Email and password are required.'); return; }
    try {
      await login(email.trim(), password);
    } catch { /* error already set in context */ }
  }

  function fillDemo(acc: typeof DEMO_ACCOUNTS[0]) {
    setEmail(acc.email);
    setPassword(acc.password);
    setLocalError('');
  }

  const displayError = localError || error;

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--surface-base)' }}
    >
      {/* Theme switcher — top right */}
      <div className="absolute top-4 right-4 flex items-center gap-1">
        {(['dark', 'neutral', 'light'] as Theme[]).map(t => (
          <button
            key={t}
            onClick={() => setTheme(t)}
            className="px-2.5 py-1 rounded text-xs font-medium transition-all"
            style={{
              backgroundColor: theme === t ? 'var(--brand)' : 'var(--surface-overlay)',
              color: theme === t ? '#fff' : 'var(--ink-secondary)',
              border: `1px solid ${theme === t ? 'var(--brand)' : 'var(--line-focus)'}`,
            }}
          >
            {THEME_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="w-full max-w-md">

        {/* Logo / Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
               style={{ backgroundColor: 'var(--brand)', boxShadow: '0 8px 24px var(--brand-subtle)' }}>
            <span className="text-2xl font-black text-white tracking-tighter">V</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight" style={{ color: 'var(--ink-primary)' }}>
            VIA
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--ink-muted)' }}>
            Very Intelligent Auditing
          </p>
        </div>

        {/* Login card */}
        <div
          className="rounded-2xl p-8"
          style={{
            backgroundColor: 'var(--surface-raised)',
            border: '1px solid var(--line-focus)',
            boxShadow: 'var(--shadow-card-lg)',
          }}
        >
          <h2 className="text-lg font-semibold mb-6" style={{ color: 'var(--ink-primary)' }}>
            Sign in to your account
          </h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--ink-secondary)' }}>
                Email address
              </label>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="via-input"
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium mb-1.5" style={{ color: 'var(--ink-secondary)' }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="via-input pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--ink-muted)' }}
                >
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {displayError && (
              <div
                className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm"
                style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--status-danger)' }}
              >
                <AlertCircle className="h-4 w-4 shrink-0" />
                {displayError}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="btn-primary w-full mt-2"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  Signing in…
                </span>
              ) : 'Sign in'}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px" style={{ backgroundColor: 'var(--line-focus)' }} />
            <span className="text-xs" style={{ color: 'var(--ink-muted)' }}>Demo accounts</span>
            <div className="flex-1 h-px" style={{ backgroundColor: 'var(--line-focus)' }} />
          </div>

          {/* Demo accounts */}
          <div className="space-y-2">
            {DEMO_ACCOUNTS.map(acc => (
              <button
                key={acc.email}
                onClick={() => fillDemo(acc)}
                className="w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-colors"
                style={{
                  backgroundColor: 'var(--surface-overlay)',
                  border: '1px solid var(--line)',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--line-focus)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--line)')}
              >
                <div className="flex items-center gap-2.5">
                  <Shield className="h-3.5 w-3.5" style={{ color: 'var(--ink-muted)' }} />
                  <span style={{ color: 'var(--ink-secondary)' }}>{acc.email}</span>
                </div>
                <span className={`text-xs font-medium ${acc.color}`}>{acc.role}</span>
              </button>
            ))}
          </div>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: 'var(--ink-muted)' }}>
          VIA Platform · Tri-Modal Audit Intelligence
        </p>
      </div>
    </div>
  );
}
