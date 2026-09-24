import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import '../App.css';

const DEMO_ACCOUNTS = [
  { username: 'ahmed', label: 'Ahmed', role: 'Dispatcher', scope: 'National' },
  { username: 'sana', label: 'Sana', role: 'BCC Opérateur', scope: 'BCC1 — Grand Tunis' },
  { username: 'crc_n', label: 'CRC Nord', role: 'CRC Opérateur', scope: 'Région Nord' },
  { username: 'admin', label: 'Admin', role: 'Administrateur', scope: 'Système' },
];

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('ahmed');
  const [password, setPassword] = useState('delestage123');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err: any) {
      if (err?.response?.status === 401) {
        setError("Nom d'utilisateur ou mot de passe incorrect");
      } else if (err?.response?.data?.detail) {
        const detail = err.response.data.detail;
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      } else if (err?.response?.status >= 500) {
        setError(`Erreur interne du serveur (${err.response.status}).`);
      } else {
        setError("Erreur de connexion au serveur backend (vérifiez le port 8000).");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleSelectDemo(demoUser: string) {
    setUsername(demoUser);
    setPassword('delestage123');
  }

  return (
    <div className="login-page">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>Plateforme Nationale de Délestage</h1>
        <p className="login-sub">Société Tunisienne de l'Électricité et du Gaz (STEG)</p>

        <label>
          Nom d'utilisateur
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="ex: ahmed"
            autoFocus
            required
          />
        </label>
        <label>
          Mot de passe
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button type="submit" disabled={submitting}>
          {submitting ? 'Connexion en cours...' : 'Se connecter'}
        </button>

        <div className="demo-accounts-box">
          <span className="demo-title">Profils d'accès de test (Mot de passe : <code>delestage123</code>) :</span>
          <div className="demo-chips-grid">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.username}
                type="button"
                className={`demo-chip ${username === acc.username ? 'active-chip' : ''}`}
                onClick={() => handleSelectDemo(acc.username)}
              >
                <div className="demo-chip-name"><strong>{acc.label}</strong> ({acc.username})</div>
                <div className="demo-chip-sub">{acc.role} · {acc.scope}</div>
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  );
}
