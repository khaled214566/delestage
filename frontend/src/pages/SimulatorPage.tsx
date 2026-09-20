import { useState, useEffect, useCallback } from 'react';
import { getSimulatorStatus, triggerBeat, resetSimulator, type SimulatorStatus, type BeatResult } from '../api/client';
import { Link } from 'react-router-dom';

export default function SimulatorPage() {
  const [status, setStatus] = useState<SimulatorStatus | null>(null);
  const [activeBeat, setActiveBeat] = useState<number | null>(null);
  const [results, setResults] = useState<Record<number, BeatResult>>({});
  const [loadingBeat, setLoadingBeat] = useState<number | null>(null);
  const [resetting, setResetting] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const s = await getSimulatorStatus();
      setStatus(s);
    } catch (err) {
      console.error('Erreur status simulateur:', err);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  const handleRunBeat = async (beatNum: number) => {
    setLoadingBeat(beatNum);
    try {
      const res = await triggerBeat(beatNum);
      setResults(prev => ({ ...prev, [beatNum]: res }));
      setActiveBeat(beatNum);
      await loadStatus();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      alert('Erreur: ' + (e.response?.data?.detail ?? 'Échec du déclenchement du Beat ' + beatNum));
    } finally {
      setLoadingBeat(null);
    }
  };

  const handleReset = async () => {
    if (!confirm('Voulez-vous réinitialiser toutes les alimentations et clore les événements de simulation ?')) return;
    setResetting(true);
    try {
      await resetSimulator();
      setResults({});
      setActiveBeat(null);
      await loadStatus();
      alert('✅ Démo réinitialisée avec succès.');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      alert('Erreur reset: ' + (e.response?.data?.detail ?? 'Erreur'));
    } finally {
      setResetting(false);
    }
  };

  const beats = [
    {
      num: 1,
      title: 'Beat 1 : Plan J-1 (300 MW)',
      desc: 'Prévision d’un déficit de pointe de 300 MW pour la tranche du soir. L’algorithme pré-alloue les quotas entre les 2 CRC et les 7 BCC.',
      badge: 'J-1',
      linkText: 'Voir Calcul du Déficit',
      linkUrl: '/deficit',
    },
    {
      num: 2,
      title: 'Beat 2 : Hausse en Direct (+50 MW)',
      desc: 'Le déficit passe subitement à 350 MW. Le système sélectionne et ouvre immédiatement 5 départs dans BCC1 en respectant l’équité.',
      badge: 'Temps Réel',
      linkText: 'Voir Monitoring Télémesure',
      linkUrl: '/monitoring',
    },
    {
      num: 3,
      title: 'Beat 3 : Alerte de Rotation (37 min)',
      desc: 'Une ligne atteint 37 min de coupure (seuil 80% des 45 min). Une proposition de substitution avec conservation exacte de MW est générée.',
      badge: 'Rotation M8',
      linkText: 'Voir Conduite BCC',
      linkUrl: '/bcc',
    },
    {
      num: 4,
      title: 'Beat 4 : Preuve d’Audit SHA-256',
      desc: 'Validation cryptographique de la traçabilité. Re-calcul intégral de la chaîne de hachage pour prouver l’absence totale d’altération.',
      badge: 'Sécurité & Audit',
      linkText: 'Voir Journal d’Audit',
      linkUrl: '/admin',
    },
  ];

  return (
    <div className="simulator-page">
      <div className="simulator-header">
        <div>
          <h2>🎬 Simulateur de Scénario de Démonstration (M11)</h2>
          <p className="simulator-subtitle">
            Déroulement automatique en 4 temps du cycle complet de délestage d'urgence STEG
          </p>
        </div>
        <div className="simulator-top-actions">
          <button
            className="btn-reset-demo"
            onClick={handleReset}
            disabled={resetting}
          >
            {resetting ? 'Réinitialisation…' : '🔄 Réinitialiser la Démo'}
          </button>
        </div>
      </div>

      <div className="simulator-status-bar">
        <div className="status-indicator">
          <span className={`status-bulb ${status?.is_demo_running ? 'bulb-active' : 'bulb-idle'}`} />
          <span className="status-text">{status?.message || 'Chargement du simulateur…'}</span>
        </div>
        <div className="status-meta">
          <strong>{status?.open_events ?? 0}</strong> départ(s) actuellement délesté(s)
        </div>
      </div>

      <div className="beats-grid">
        {beats.map(beat => {
          const isLoading = loadingBeat === beat.num;
          const result = results[beat.num];
          const isCurrent = activeBeat === beat.num;

          return (
            <div key={beat.num} className={`beat-card ${isCurrent ? 'beat-active' : ''}`}>
              <div className="beat-card-header">
                <span className="beat-badge">{beat.badge}</span>
                <span className="beat-number">#{beat.num}</span>
              </div>
              <h3>{beat.title}</h3>
              <p className="beat-desc">{beat.desc}</p>

              <div className="beat-actions">
                <button
                  className="btn-beat-trigger"
                  onClick={() => handleRunBeat(beat.num)}
                  disabled={isLoading}
                >
                  {isLoading ? 'Exécution en cours…' : `▶ Déclencher Beat ${beat.num}`}
                </button>
                <Link to={beat.linkUrl} className="btn-beat-link" target="_blank">
                  {beat.linkText} ↗
                </Link>
              </div>

              {result && (
                <div className="beat-result-box">
                  <div className="result-title">Résultat d'exécution :</div>
                  <div className="result-msg">{result.message}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="simulator-guide-card">
        <h4>💡 Guide pour le Pitch du Jury</h4>
        <ol>
          <li><strong>Beat 1 :</strong> Montrez le plan J-1 préparé par le Dispatching.</li>
          <li><strong>Beat 2 :</strong> Cliquez sur Beat 2 puis basculez sur l'écran <strong>Monitoring</strong> (les graphiques s'animent en direct via WebSockets).</li>
          <li><strong>Beat 3 :</strong> Montrez l'alerte Ambre/Rouge dans l'écran <strong>Conduite BCC</strong> et acceptez la rotation en 1-clic.</li>
          <li><strong>Beat 4 :</strong> Montrez au jury la chaîne d'audit vérifiée sans aucune falsification possible.</li>
          <li><strong>Portail Citoyen :</strong> Ouvrez le <Link to="/citizen" target="_blank" className="text-link">Portail Citoyen ↗</Link> pour prouver la transparence publique en temps réel.</li>
        </ol>
      </div>
    </div>
  );
}
