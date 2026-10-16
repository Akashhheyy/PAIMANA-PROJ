import { NavLink, Outlet } from 'react-router-dom';
import { AlertTriangle, FolderKanban, LayoutDashboard } from 'lucide-react';
import { BackendStatus } from './BackendStatus';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/projects', label: 'Projects', icon: FolderKanban, end: false },
  { to: '/early-warnings', label: 'Early Warnings', icon: AlertTriangle, end: false },
];

/**
 * App shell: sidebar navigation + branded header with backend status.
 * Only "Overview" is implemented in Phase 9.2; the other entries route to
 * an explicit "later phase" notice (no fabricated data).
 */
export function Layout() {
  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            P
          </span>
          <div>
            <strong>PAIMANA AI</strong>
            <span className="brand-sub">Risk Monitoring</span>
          </div>
        </div>
        <nav className="nav">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `nav-link${isActive ? ' active' : ''}`
              }
            >
              <Icon size={17} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <p className="sidebar-foot muted">SIH prototype · April 2026</p>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <div className="titles">
            <h1>PAIMANA AI</h1>
            <p>Infrastructure Risk Monitoring and Early Warning System</p>
          </div>
          <BackendStatus />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
