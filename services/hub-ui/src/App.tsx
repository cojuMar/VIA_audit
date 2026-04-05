import { useState } from 'react';
import { LogOut, ChevronDown, User } from 'lucide-react';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthProvider, useAuth, type UserRole } from './contexts/AuthContext';
import ThemeSelector from './components/ThemeSelector';
import Dashboard from './pages/Dashboard';
import Tutorials from './pages/Tutorials';
import Login from './pages/Login';

export type Page = 'dashboard' | 'tutorials';

const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  end_user: 'End User',
};
const ROLE_COLORS: Record<UserRole, string> = {
  super_admin: 'var(--status-danger)',
  admin: 'var(--status-warning)',
  end_user: 'var(--status-info)',
};

function AppInner() {
  const { isAuthenticated, user, logout } = useAuth();
  const [page, setPage]         = useState<Page>('dashboard');
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  if (!isAuthenticated) return <Login />;

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--surface-base)' }}>

      {/* Global header */}
      <header
        className="sticky top-0 z-50"
        style={{
          borderBottom: '1px solid var(--line)',
          backgroundColor: 'color-mix(in srgb, var(--surface-raised) 95%, transparent)',
          backdropFilter: 'blur(8px)',
        }}
      >
        <div className="mx-auto flex h-14 max-w-screen-2xl items-center justify-between px-4 md:px-8 gap-4">

          {/* Logo */}
          <button
            onClick={() => setPage('dashboard')}
            className="flex items-center gap-2.5 text-left shrink-0"
          >
            <span
              className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-black text-white select-none"
              style={{ backgroundColor: 'var(--brand)' }}
            >
              V
            </span>
            <div className="leading-none hidden sm:block">
              <span className="block text-sm font-bold tracking-tight" style={{ color: 'var(--ink-primary)' }}>
                VIA
              </span>
              <span className="block text-[10px] uppercase tracking-widest mt-0.5" style={{ color: 'var(--ink-muted)' }}>
                Very Intelligent Auditing
              </span>
            </div>
          </button>

          {/* Nav */}
          <nav className="flex items-center gap-1">
            <button
              onClick={() => setPage('dashboard')}
              className={`nav-btn ${page === 'dashboard' ? 'active' : ''}`}
            >
              Hub
            </button>
            <button
              onClick={() => setPage('tutorials')}
              className={`nav-btn ${page === 'tutorials' ? 'active' : ''}`}
            >
              Tutorials
            </button>
          </nav>

          {/* Right controls */}
          <div className="flex items-center gap-3 shrink-0">
            <ThemeSelector />

            {/* User menu */}
            <div className="relative">
              <button
                onClick={() => setUserMenuOpen(v => !v)}
                className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors"
                style={{
                  backgroundColor: 'var(--surface-overlay)',
                  border: '1px solid var(--line-focus)',
                  color: 'var(--ink-secondary)',
                }}
              >
                <div
                  className="h-6 w-6 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0"
                  style={{ backgroundColor: ROLE_COLORS[user!.role] ?? 'var(--brand)' }}
                >
                  {user!.full_name.charAt(0).toUpperCase()}
                </div>
                <div className="hidden md:flex flex-col items-start leading-none">
                  <span className="text-xs font-medium" style={{ color: 'var(--ink-primary)' }}>
                    {user!.full_name}
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--ink-muted)' }}>
                    {ROLE_LABELS[user!.role]}
                  </span>
                </div>
                <ChevronDown className="h-3.5 w-3.5 shrink-0" />
              </button>

              {userMenuOpen && (
                <>
                  {/* Backdrop */}
                  <div className="fixed inset-0 z-10" onClick={() => setUserMenuOpen(false)} />
                  {/* Dropdown */}
                  <div
                    className="absolute right-0 top-full mt-1.5 w-52 rounded-xl z-20 py-1.5 overflow-hidden"
                    style={{
                      backgroundColor: 'var(--surface-overlay)',
                      border: '1px solid var(--line-focus)',
                      boxShadow: 'var(--shadow-card-lg)',
                    }}
                  >
                    {/* User info header */}
                    <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--line)' }}>
                      <p className="text-sm font-medium" style={{ color: 'var(--ink-primary)' }}>
                        {user!.full_name}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: 'var(--ink-muted)' }}>
                        {user!.email}
                      </p>
                      <span
                        className="inline-block mt-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded"
                        style={{
                          backgroundColor: 'var(--brand-subtle)',
                          color: 'var(--brand-text)',
                        }}
                      >
                        {ROLE_LABELS[user!.role]}
                      </span>
                    </div>

                    {/* Profile option */}
                    <button
                      className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors"
                      style={{ color: 'var(--ink-secondary)' }}
                      onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--surface-raised)'; e.currentTarget.style.color = 'var(--ink-primary)'; }}
                      onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = 'var(--ink-secondary)'; }}
                    >
                      <User className="h-4 w-4" />
                      Profile
                    </button>

                    {/* Logout */}
                    <button
                      onClick={() => { logout(); setUserMenuOpen(false); }}
                      className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors"
                      style={{ color: 'var(--status-danger)' }}
                      onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'rgba(239,68,68,0.08)'; }}
                      onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
                    >
                      <LogOut className="h-4 w-4" />
                      Sign out
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <main>
        {page === 'dashboard' && (
          <Dashboard role={user!.role} onOpenTutorials={() => setPage('tutorials')} />
        )}
        {page === 'tutorials' && <Tutorials role={user!.role} />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </ThemeProvider>
  );
}
