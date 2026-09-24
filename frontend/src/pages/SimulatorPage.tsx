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
      title: 'Scénario 1 : Prévision J-1 (Déficit de pointe 300 MW)',
      desc: 'Déséquilibre prévisionnel de 300 MW pour la tranche de pointe du soir. Répartition hiérarchique des quotas entre les 2 CRC et les 7 BCC selon la méthode des plus forts restes.',
      badge: 'Planification J-1',
      linkText: 'Consulter le plan de déficit',
      linkUrl: '/deficit',
    },
    {
      num: 2,
      title: 'Scénario 2 : Aléa Temps Réel (+50 MW)',
      desc: 'Survenance d\'un aléa réseau portant le déficit global à 350 MW. Déclenchement coordonné de l\'effacement d\'urgence avec sélection ordonnée des départs selon les priorités P5/P4.',
      badge: 'Télémesure Temps Réel',
      linkText: 'Consulter la télémesure',
      linkUrl: '/monitoring',
    },
    {
      num: 3,
      title: 'Scénario 3 : Rotation Réglementaire de Charge (Seuil 80%)',
      desc: 'Atteinte du seuil de pré-alerte de durée d\'interruption (36 min sur 45 min réglementaires). Proposition automatique d\'un départ de substitution avec maintien strict du bilan MW.',
      badge: 'Rotation de Charge',
      linkText: 'Accéder à la conduite BCC',
      linkUrl: '/bcc',
    },
    {
      num: 4,
      title: 'Scénario 4 : Contrôle d\'Intégrité du Registre d\'Audit',
      desc: 'Vérification cryptographique de la chaîne SHA-256 de traçabilité garantissant l\'intégrité absolue des ordres, manœuvres et dérogations d\'exploitation.',
      badge: 'Audit & Conformité',
      linkText: 'Consulter le registre d\'audit',
      linkUrl: '/admin',
    },
  ];

  return (
    <div className="simulator-page">
      <div className="simulator-header">
        <div>
          <h2>Simulateur de Scénarios d'Exploitation Réseau</h2>
          <p className="simulator-subtitle">
            Reproduction séquentielle des phases opérationnelles de gestion du délestage tournant STEG
          </p>
        </div>
        <div className="simulator-top-actions">
          <button
            className="btn-reset-demo"
            onClick={handleReset}
            disabled={resetting}
          >
            {resetting ? 'Réinitialisation en cours…' : 'Réinitialiser la simulation'}
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
                <span className="beat-number">Scénario {beat.num}</span>
              </div>
              <h3>{beat.title}</h3>
              <p className="beat-desc">{beat.desc}</p>

              <div className="beat-actions">
                <button
                  className="btn-beat-trigger"
                  onClick={() => handleRunBeat(beat.num)}
                  disabled={isLoading}
                >
                  {isLoading ? 'Exécution en cours…' : `Exécuter le scénario ${beat.num}`}
                </button>
                <Link to={beat.linkUrl} className="btn-beat-link" target="_blank">
                  {beat.linkText} ↗
                </Link>
              </div>

              {result && (
                <div className="beat-result-box">
                  <div className="result-title">Résultat de la simulation :</div>
                  <div className="result-msg">{result.message}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="simulator-guide-card">
        <h4>Protocole d'Exploitation du Simulateur Réseau</h4>
        <ol>
          <li><strong>Scénario 1 (Planification J-1) :</strong> Consultation du plan d'effacement prévisionnel établi par le Dispatching National et validé pour les tranches de pointe.</li>
          <li><strong>Scénario 2 (Ajustement temps réel) :</strong> Déclenchement de l'effacement d'urgence suite à un déficit imprévu et suivi instantané des flux sur l'écran <strong>Monitoring</strong>.</li>
          <li><strong>Scénario 3 (Rotation de charge) :</strong> Traitement de la pré-alerte réglementaire dans l'écran <strong>Conduite BCC</strong> avec validation de la substitution de départs.</li>
          <li><strong>Scénario 4 (Traçabilité &amp; Audit) :</strong> Exécution du contrôle d'intégrité de la chaîne cryptographique certifiant la conformité du journal d'exploitation.</li>
          <li><strong>Supervision publique :</strong> Consultation du <Link to="/citizen" target="_blank" className="text-link">Portail public citoyen ↗</Link> pour attester de la diffusion transparente de l'état du réseau en temps réel.</li>
        </ol>
      </div>
    </div>
  );
}
