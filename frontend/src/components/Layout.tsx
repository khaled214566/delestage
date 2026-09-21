import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import ErrorBoundary from './ErrorBoundary';
import '../App.css';

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>🔌 Delestage</h2>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`} end>
            Calcul du déficit
          </NavLink>
          <NavLink to="/orders" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            Ordres de délestage
          </NavLink>
          <NavLink to="/monitoring" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            📡 Monitoring en direct
          </NavLink>
          <NavLink to="/bcc" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            ⚡ Conduite BCC
          </NavLink>
          <NavLink to="/admin" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            🛡️ Administration
          </NavLink>
          <NavLink to="/simulator" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            🎬 Simulateur Démo
          </NavLink>
          <NavLink to="/evaluation" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            📊 Évaluation &amp; Benchmarks
          </NavLink>
          <NavLink to="/citizen" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`} target="_blank">
            🌐 Portail Citoyen ↗
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          {user && (
            <div className="user-badge-sidebar">
              <div className="user-info">
                <span className="user-name">{user.name}</span>
                <span className="user-role">{user.role}</span>
              </div>
              <button onClick={logout} className="btn-small btn-ghost">Déconnexion</button>
            </div>
          )}
        </div>
      </aside>
      <main className="main-content">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  );
}
