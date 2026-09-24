import { useState, useEffect, useCallback } from 'react';
import {
  getBenchmark,
  getGridFairnessMetrics,
  type BenchmarkScenario,
  type GridFairnessMetrics,
} from '../api/client';

export default function EvaluationPage() {
  const [scenarios, setScenarios] = useState<BenchmarkScenario[]>([]);
  const [metrics, setMetrics] = useState<GridFairnessMetrics | null>(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [bm, mt] = await Promise.all([
        getBenchmark(days),
        getGridFairnessMetrics(),
      ]);
      setScenarios(bm.scenarios);
      setMetrics(mt);
    } catch (err) {
      console.error('Erreur chargement benchmarks:', err);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="evaluation-page">
      <div className="evaluation-header">
        <div>
          <h2>Indicateurs de Performance &amp; Évaluation d'Équité</h2>
          <p className="evaluation-subtitle">
            Analyse quantitative de l'équité territoriale, du respect des priorités critiques et de la continuité de service
          </p>
        </div>
        <div className="eval-controls">
          <label>Horizon d'analyse :</label>
          <select value={days} onChange={e => setDays(+e.target.value)}>
            <option value={3}>3 jours</option>
            <option value={7}>7 jours (Période standard)</option>
            <option value={14}>14 jours</option>
            <option value={30}>30 jours (1 mois)</option>
          </select>
          <button className="btn-eval-refresh" onClick={load} disabled={loading}>
            {loading ? 'Calcul en cours…' : 'Actualiser les indicateurs'}
          </button>
        </div>
      </div>

      {/* Live Grid Metrics Summary */}
      <div className="eval-summary-grid">
        <div className="eval-card">
          <span className="eval-card-label">Indice de Gini Actuel (Réseau)</span>
          <span className="eval-card-val text-green">
            {metrics ? metrics.live_gini_index.toFixed(3) : '…'}
          </span>
          <span className="eval-card-sub">0.0 = Équité parfaite | 1.0 = Disparité maximale</span>
        </div>

        <div className="eval-card">
          <span className="eval-card-label">Infrastructures P0 Protégées</span>
          <span className="eval-card-val text-blue">
            {metrics?.p0_protected_count ?? 0} départs
          </span>
          <span className="eval-card-sub">Santé, eau potable et sécurité (0 coupure)</span>
        </div>

        <div className="eval-card">
          <span className="eval-card-label">Énergie Non Distribuée (ENS)</span>
          <span className="eval-card-val text-dark">
            {metrics?.total_ens_mwh ?? 0} MWh
          </span>
          <span className="eval-card-sub">Cumul sur la période observée</span>
        </div>

        <div className="eval-card">
          <span className="eval-card-label">Total Rotations Réalisées</span>
          <span className="eval-card-val text-amber">
            {metrics?.total_rotations ?? 0}
          </span>
          <span className="eval-card-sub">Manœuvres de substitution exécutées</span>
        </div>
      </div>

      {/* Comparative Benchmark Table */}
      <div className="eval-table-container">
        <div className="table-header-box">
          <h3>Comparatif des Méthodes d'Affectation sur {days} jours (170 alimentateurs)</h3>
          <span className="badge-highlight">Évaluation comparative des algorithmes</span>
        </div>

        <table className="benchmark-table">
          <thead>
            <tr>
              <th>Méthode d'affectation</th>
              <th>Indice de Gini (Équité)</th>
              <th>Violations P0 (Critiques)</th>
              <th>Durée Max / Ligne</th>
              <th>Respect Cible (MW)</th>
              <th>Amélioration Gini</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((sc, idx) => {
              const isIntelligent = idx === 0;
              return (
                <tr key={sc.engine_name} className={isIntelligent ? 'row-intelligent' : ''}>
                  <td className="engine-cell">
                    <strong>{sc.engine_name}</strong>
                    <div className="engine-desc">{sc.description}</div>
                  </td>
                  <td className="metric-cell">
                    <span className={`gini-badge ${isIntelligent ? 'gini-best' : 'gini-poor'}`}>
                      {sc.gini_index.toFixed(4)}
                    </span>
                  </td>
                  <td className="metric-cell">
                    {sc.p0_violations === 0 ? (
                      <span className="violation-zero">0 (Conforme)</span>
                    ) : (
                      <span className="violation-bad">{sc.p0_violations} coupures non conformes</span>
                    )}
                  </td>
                  <td className="metric-cell font-mono">{sc.max_duration_min} min</td>
                  <td className="metric-cell font-mono">{sc.target_achievement_pct}%</td>
                  <td className="metric-cell advantage-cell">
                    {isIntelligent ? (
                      <span className="advantage-pill">+{sc.fairness_advantage_pct}% d'amélioration</span>
                    ) : (
                      <span className="text-muted">Référence</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Analytical Takeaway Card */}
      <div className="eval-insights-card">
        <h4>Synthèse Technique pour l'Exploitation Réseau</h4>
        <ul>
          <li>
            <strong>Protection stricte des infrastructures critiques (P0) :</strong> Verrouillage automatique des départs alimentant les établissements hospitaliers, stations de pompage (SONEDE) et centres de sécurité civile, interdisant toute coupure en délestage manuel tournant.
          </li>
          <li>
            <strong>Répartition équitable et maîtrise de la durée d'interruption :</strong> Amélioration significative de l'indice de Gini grâce à la rotation cyclique sous le seuil réglementaire de 45 minutes et à l'arbitrage par historique cumulé d'effacement.
          </li>
          <li>
            <strong>Maintien strict de la consigne de puissance :</strong> Respect rigoureux des quotas d'effacement fixés par le Dispatching National lors de chaque cycle de délestage et de manœuvre de substitution.
          </li>
        </ul>
      </div>
    </div>
  );
}
