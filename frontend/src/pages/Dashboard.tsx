import { useQuery } from '@tanstack/react-query';
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
          <h2>Modules</h2>
          <ul>
            <li>✅ M0 — Project Setup</li>
            <li>
              ✅ M1 — Database Schema &amp; Seed Data
              <M1Subtitle />
            </li>
            <li>✅ M2 — Authentication, Roles &amp; Audit</li>
            <li>✅ M3 — Deficit Computation</li>
            <li>✅ M4 — Ordres de délestage (Shed Orders)</li>
            <li>✅ M5 — Moteur d'allocation &amp; sélection équitable</li>
            <li>🔄 M6 — Monitoring temps réel &amp; Hub WebSocket (En cours)</li>
            <li>⬜ M7 — BCC Execution</li>
            <li>⬜ M8 — Rotation Engine</li>
            <li>⬜ M9 — Administration &amp; Audit View</li>
            <li>⬜ M10 — Citizen Platform</li>
            <li>⬜ M11 — Demo Simulator</li>
            <li>⬜ M12 — Evaluation &amp; Tests</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
