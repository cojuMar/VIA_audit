/**
 * Layout — minimal page chrome shared by every module UI.
 *
 * Each module currently re-implements its own header strip. This collapses
 * the common bits: a header slot, a sidebar slot, and a content region.
 * Modules can still drop their own theming via CSS variables.
 */
import type { ReactNode } from 'react';

export interface LayoutProps {
  header?: ReactNode;
  sidebar?: ReactNode;
  children: ReactNode;
}

export function Layout({ header, sidebar, children }: LayoutProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {header && (
        <header
          role="banner"
          style={{
            borderBottom: '1px solid var(--line-focus, #e5e7eb)',
            padding: '12px 20px',
          }}
        >
          {header}
        </header>
      )}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {sidebar && (
          <aside
            aria-label="Sidebar navigation"
            style={{
              width: 240,
              borderRight: '1px solid var(--line-focus, #e5e7eb)',
              padding: 16,
              overflowY: 'auto',
            }}
          >
            {sidebar}
          </aside>
        )}
        <main role="main" style={{ flex: 1, padding: 20, overflowY: 'auto' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
