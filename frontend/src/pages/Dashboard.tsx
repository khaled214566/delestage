import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { checkHealth, type HealthResponse } from '../api/client';
import '../App.css';

function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: checkHealth,
    refetchInterval: 30000,
  });
}

function fmtMw(mw: number) {
  return mw.toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function GridSnapshot() {
  const { data, isLoading, error } = useHealth();

  if (isLoading) return <div className="status loading">Connexion à l'API...</div>;
  if (error || !data) return <div className="status error">❌ API injoignable</div>;

  return (
    <>
      <div className="status ok">
        ✅ API connectée — v{data.version} ({data.environment})
      </div>

      <div className="grid-stats">
        <div className="stat-card">
          <span className="stat-value">{data.feeder_count.toLocaleString('fr-FR')}</span>
          <span className="stat-label">Départs générés</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{fmtMw(data.sheddable_mw)}</span>
          <span className="stat-label">MW délestables</span>
        </div>
        <div className={`stat-card ${data.db_connected ? 'stat-good' : 'stat-bad'}`}>
          <span className="stat-value">{data.db_connected ? 'Connectée' : 'Indisponible'}</span>
          <span className="stat-label">Base de données</span>
        </div>
      </div>
    </>
  );
}

function M1Subtitle() {
  const { data } = useHealth();
  if (!data || data.feeder_count === 0) return null;
  return (
    <span className="module-sub">
      {data.feeder_count.toLocaleString('fr-FR')} départs · {fmtMw(data.sheddable_mw)} MW délestables
    </span>
  );
}

export default function Dashboard() {
  return (
    <div className="dashboard">
      <main>
        <GridSnapshot />

        <div className="info">
          <h2>Modules de la Plateforme</h2>
          <ul>
            <li>✅ M0 — Project Setup &amp; Docker</li>
            <li>
              ✅ M1 — Database Schema &amp; Seed Data
              <M1Subtitle />
            </li>
            <li>✅ M2 — Authentication, Roles &amp; Audit Trail SHA-256</li>
            <li>
              ✅ M3 — <Link to="/deficit" className="module-link">Calcul du Déficit (UC1)</Link>
            </li>
            <li>
              ✅ M4 — <Link to="/orders" className="module-link">Ordres de délestage (UC2)</Link>
            </li>
            <li>✅ M5 — Moteur d'allocation &amp; sélection équitable (UC3)</li>
            <li>
              ✅ M6 — <Link to="/monitoring" className="module-link">Monitoring temps réel &amp; Hub WebSocket (UC4)</Link>
            </li>
            <li>
              ✅ M7 — <Link to="/bcc" className="module-link">Conduite BCC &amp; Manœuvres Terrain (UC5 &amp; UC7)</Link>
            </li>
            <li>
              ✅ M8 — Moteur de Rotation Sécurisée (UC6 - Conservation MW)
            </li>
            <li>
              ✅ M9 — <Link to="/admin" className="module-link">Administration, Paramètres &amp; Vue d'Audit (UC8)</Link>
            </li>
            <li>
              ✅ M10 — <Link to="/citizen" target="_blank" className="module-link">Portail Citoyen &amp; Transparence Publique (UC11 &amp; UC12) ↗</Link>
            </li>
            <li>
              ✅ M11 — <Link to="/simulator" className="module-link">Simulateur de Démo &amp; Scénario en 4 Temps</Link>
            </li>
            <li>
              ✅ M12 — <Link to="/evaluation" className="module-link">Évaluation, Benchmarks &amp; Indice de Gini</Link>
            </li>
          </ul>
        </div>
      </main>
    </div>
  );
}
