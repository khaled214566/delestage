import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
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
            Tableau de bord
          </NavLink>
          <NavLink to="/deficit" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            Calcul du déficit
          </NavLink>
          <NavLink to="/orders" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            Ordres de délestage
          </NavLink>
          <NavLink to="/monitoring" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            📡 Monitoring en direct
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
        <Outlet />
      </main>
    </div>
  );
}
