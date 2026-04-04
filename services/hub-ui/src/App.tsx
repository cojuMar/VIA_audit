import { useState, type ReactNode } from 'react';
import Dashboard from './pages/Dashboard';
import Tutorials from './pages/Tutorials';
import type { Role } from './data/tutorials';

export type Page = 'dashboard' | 'tutorials';

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');
  const [role, setRole] = useState<Role>('end_user');

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Global nav */}
      <header className="sticky top-0 z-50 border-b border-slate-800 bg-slate-950/90 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-screen-2xl items-center justify-between px-4 md:px-8">
          {/* Logo */}
          <button
            onClick={() => setPage('dashboard')}
            className="flex items-center gap-2.5 text-left"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white select-none">
              A
            </span>
            <div className="leading-none">
              <span className="block text-sm font-semibold text-white tracking-tight">AEGIS 2026</span>
              <span className="block text-[10px] text-slate-400 uppercase tracking-widest mt-0.5">
                Tri-Modal Audit Platform
              </span>
            </div>
          </button>

          {/* Nav links */}
          <nav className="flex items-center gap-1">
            <NavBtn active={page === 'dashboard'} onClick={() => setPage('dashboard')}>
              Hub
            </NavBtn>
            <NavBtn active={page === 'tutorials'} onClick={() => setPage('tutorials')}>
              Tutorials
            </NavBtn>
          </nav>

          {/* Role selector */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 hidden sm:block">Role:</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="rounded-md bg-slate-800 border border-slate-700 text-xs text-slate-200
                         px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500
                         cursor-pointer"
            >
              <option value="end_user">End User</option>
              <option value="admin">Admin</option>
              <option value="super_admin">Super Admin</option>
            </select>
          </div>
        </div>
      </header>

      <main>
        {page === 'dashboard' && (
          <Dashboard role={role} onOpenTutorials={() => setPage('tutorials')} />
        )}
        {page === 'tutorials' && <Tutorials role={role} />}
      </main>
    </div>
  );
}

function NavBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
        active
          ? 'bg-indigo-600 text-white'
          : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'
      }`}
    >
      {children}
    </button>
  );
}
