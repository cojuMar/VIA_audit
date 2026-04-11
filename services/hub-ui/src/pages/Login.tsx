import { useState, type FormEvent } from 'react';
import { Eye, EyeOff, AlertCircle, ArrowRight, Shield, Lock, BarChart2, FileText } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import ThemeSelector from '../components/ThemeSelector';

const DEMO_ACCOUNTS = [
  { email: 'admin@via.com',   password: 'admin123',   role: 'Super Admin', badge: 'pill-indigo' },
  { email: 'auditor@via.com', password: 'auditor123', role: 'Admin',       badge: 'pill-warning' },
  { email: 'user@via.com',    password: 'user123',    role: 'End User',    badge: 'pill-neutral' },
];

const FEATURE_PILLS = [
  { icon: <Shield  className="h-3.5 w-3.5" />, label: 'SOC 2 · ISO 27001 · NIST'   },
  { icon: <BarChart2 className="h-3.5 w-3.5" />, label: 'Real-time Risk Intelligence' },
  { icon: <FileText className="h-3.5 w-3.5" />, label: 'Automated Workpapers'        },
  { icon: <Lock className="h-3.5 w-3.5" />,    label: 'WCAG AA · GDPR Ready'        },
];

export default function Login() {
  const { login, isLoading, error } = useAuth();
  const { isLight } = useTheme();

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
    } catch { /* error set in context */ }
  }

  function fillDemo(acc: typeof DEMO_ACCOUNTS[0]) {
    setEmail(acc.email);
    setPassword(acc.password);
    setLocalError('');
  }

  const displayError = localError || error;

  return (
    <div className="min-h-screen flex" style={{ backgroundColor: 'var(--surface-base)' }}>

      {/* ── Left brand panel (desktop only) ────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:flex-col lg:w-[55%] relative overflow-hidden"
        style={{
          background: isLight
            ? 'var(--gradient-hero)'
            : 'radial-gradient(ellipse at 30% 40%, rgba(99,102,241,0.25) 0%, transparent 55%), radial-gradient(ellipse at 70% 70%, rgba(6,182,212,0.15) 0%, transparent 45%), #0A0F1E',
          borderRight: '1px solid var(--line-focus)',
        }}
      >
        {/* Animated orbs — only on dark */}
        {!isLight && (
          <>
            <div className="orb-1" />
            <div className="orb-2" />
            <div className="orb-3" />
          </>
        )}

        {/* Content */}
        <div className="relative z-10 flex flex-col justify-between h-full p-12">

          {/* Logo */}
          <div className="flex items-center gap-3">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-xl text-lg font-black text-white select-none"
              style={{
                background: isLight ? 'rgba(255,255,255,0.25)' : 'var(--brand)',
                boxShadow: isLight ? 'none' : 'var(--shadow-btn)',
                backdropFilter: isLight ? 'blur(8px)' : 'none',
              }}
            >
              V
            </span>
            <div>
              <span
                className="block text-lg font-bold tracking-tight"
                style={{ color: '#ffffff' }}
              >
                VIA
              </span>
              <span className="block text-[10px] uppercase tracking-widest" style={{ color: 'rgba(255,255,255,0.65)' }}>
                Very Intelligent Auditing
              </span>
            </div>
          </div>

          {/* Center hero text */}
          <div className="max-w-sm">
            <p
              className="text-xs font-bold uppercase tracking-widest mb-4"
              style={{ color: 'rgba(255,255,255,0.55)', letterSpacing: '0.15em' }}
            >
              Enterprise Audit Intelligence
            </p>
            <h1
              className="text-4xl font-bold leading-tight mb-4"
              style={{ color: '#ffffff', textShadow: isLight ? 'none' : '0 2px 20px rgba(0,0,0,0.3)' }}
            >
              Tri-Modal Audit Platform
            </h1>
            <p
              className="text-base leading-relaxed mb-8"
              style={{ color: 'rgba(255,255,255,0.72)' }}
            >
              Continuous monitoring, intelligent risk management, and automated
              compliance — unified in one enterprise-grade platform.
            </p>

            {/* Feature pills */}
            <div className="flex flex-wrap gap-2">
              {FEATURE_PILLS.map(f => (
                <span
                  key={f.label}
                  className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: 'rgba(255,255,255,0.15)',
                    color: '#ffffff',
                    backdropFilter: 'blur(8px)',
                    border: '1px solid rgba(255,255,255,0.20)',
                  }}
                >
                  {f.icon}
                  {f.label}
                </span>
              ))}
            </div>
          </div>

          {/* Bottom credentials */}
          <div className="flex items-center gap-2">
            <span
              className="text-xs"
              style={{ color: 'rgba(255,255,255,0.45)' }}
            >
              VIA Platform · Tri-Modal Audit Intelligence
            </span>
          </div>
        </div>
      </div>

      {/* ── Right login panel ───────────────────────────────────────────────── */}
      <div
        className="flex-1 flex flex-col items-center justify-center p-6 md:p-10 relative"
        style={{ backgroundColor: 'var(--surface-base)' }}
      >
        {/* Theme selector */}
        <div className="absolute top-4 right-4">
          <ThemeSelector />
        </div>

        {/* Mobile logo (only shows when left panel is hidden) */}
        <div className="lg:hidden flex items-center gap-2.5 mb-10">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-xl text-base font-black text-white select-none"
            style={{ background: 'var(--brand)', boxShadow: 'var(--shadow-btn)' }}
          >
            V
          </span>
          <div>
            <span className="block text-base font-bold tracking-tight" style={{ color: 'var(--ink-primary)' }}>VIA</span>
            <span className="block text-[10px] uppercase tracking-widest" style={{ color: 'var(--ink-muted)' }}>Very Intelligent Auditing</span>
          </div>
        </div>

        {/* Login card */}
        <div
          className="w-full max-w-[400px]"
          style={{
            background: isLight ? 'var(--surface-raised)' : 'rgba(255,255,255,0.04)',
            backdropFilter: isLight ? 'none' : 'blur(24px) saturate(200%)',
            border: isLight ? '1px solid var(--line)' : '1px solid rgba(255,255,255,0.10)',
            borderRadius: '20px',
            boxShadow: isLight
              ? 'var(--shadow-card-lg)'
              : '0 8px 48px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.08)',
            padding: '36px',
          }}
        >
          {/* Card header */}
          <div className="mb-6">
            <p className="section-label mb-1">Workspace Access</p>
            <h2 className="text-xl font-semibold" style={{ color: 'var(--ink-primary)' }}>
              Welcome back
            </h2>
            <p className="text-sm mt-1" style={{ color: 'var(--ink-secondary)' }}>
              Sign in to continue to your workspace
            </p>
          </div>

          {/* Subtle divider */}
          <div className="mb-6" style={{ height: '1px', backgroundColor: 'var(--line-focus)' }} />

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label
                className="block mb-1.5 text-[11px] font-bold uppercase tracking-widest"
                style={{ color: 'var(--ink-muted)' }}
              >
                Work Email
              </label>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="via-input"
              />
            </div>

            {/* Password */}
            <div>
              <label
                className="block mb-1.5 text-[11px] font-bold uppercase tracking-widest"
                style={{ color: 'var(--ink-muted)' }}
              >
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
                  className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                  style={{ color: 'var(--ink-muted)' }}
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Error message */}
            {displayError && (
              <div
                className="flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm"
                style={{
                  background: 'var(--badge-error-bg)',
                  color: 'var(--badge-error-text)',
                  border: '1px solid var(--badge-error-bg)',
                }}
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
              style={{ height: '44px', fontSize: '15px' }}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  Signing in…
                </span>
              ) : (
                <>
                  Sign In
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="mt-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="flex-1 h-px" style={{ backgroundColor: 'var(--line-focus)' }} />
              <span className="text-xs font-medium" style={{ color: 'var(--ink-muted)' }}>
                Demo accounts
              </span>
              <div className="flex-1 h-px" style={{ backgroundColor: 'var(--line-focus)' }} />
            </div>

            <div className="space-y-1.5">
              {DEMO_ACCOUNTS.map(acc => (
                <button
                  key={acc.email}
                  onClick={() => fillDemo(acc)}
                  className="w-full flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-all"
                  style={{
                    backgroundColor: 'var(--surface-overlay)',
                    border: '1px solid var(--line)',
                    color: 'var(--ink-secondary)',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = 'var(--brand)';
                    e.currentTarget.style.backgroundColor = 'var(--brand-subtle)';
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = 'var(--line)';
                    e.currentTarget.style.backgroundColor = 'var(--surface-overlay)';
                  }}
                >
                  <span className="text-xs font-mono" style={{ color: 'var(--ink-secondary)' }}>
                    {acc.email}
                  </span>
                  <span className={`pill ${acc.badge}`}>
                    {acc.role}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Footer */}
          <p className="text-center text-[11px] mt-6" style={{ color: 'var(--ink-muted)' }}>
            Don't have access?{' '}
            <span style={{ color: 'var(--brand-text)', cursor: 'default' }}>Contact your IT administrator</span>
          </p>
        </div>
      </div>
    </div>
  );
}
