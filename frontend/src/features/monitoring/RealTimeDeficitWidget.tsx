import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  setTelemetryScenario,
  executeEmergencyAutoShed,
  type LiveTelemetryPoint,
  type EmergencyAutoShedResponse,
} from '../../api/client';

interface RealTimeDeficitWidgetProps {
  latestTick?: LiveTelemetryPoint | null;
}

export default function RealTimeDeficitWidget({ latestTick }: RealTimeDeficitWidgetProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Mode: 'LIVE' (follows live grid telemetry) or 'SIMULATION' (manual what-if slider controls)
  const [calcMode, setCalcMode] = useState<'LIVE' | 'SIMULATION'>('LIVE');

  // Manual simulation variables
  const [simDemand, setSimDemand] = useState(4400);
  const [simGen, setSimGen] = useState(3800);
  const [simImports, setSimImports] = useState(200);
  const [simMargin, setSimMargin] = useState(50);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  // Emergency execution result modal state
  const [emergencyResult, setEmergencyResult] = useState<EmergencyAutoShedResponse | null>(null);

  // Sync simulation values when switching to simulation or when live data arrives
  useEffect(() => {
    if (latestTick && calcMode === 'LIVE') {
      setSimDemand(Math.round(latestTick.demand_mw ?? 4400));
      setSimGen(Math.round(latestTick.generation_mw ?? 3800));
      setSimImports(Math.round(latestTick.imports_mw ?? 200));
      setSimMargin(Math.round(latestTick.margin_mw ?? 50));
    }
  }, [latestTick, calcMode]);

  // Current values depending on mode
  const demand = calcMode === 'LIVE' ? (latestTick?.demand_mw ?? simDemand) : simDemand;
  const generation = calcMode === 'LIVE' ? (latestTick?.generation_mw ?? simGen) : simGen;
  const imports = calcMode === 'LIVE' ? (latestTick?.imports_mw ?? simImports) : simImports;
  const margin = calcMode === 'LIVE' ? (latestTick?.margin_mw ?? simMargin) : simMargin;

  // Real-time formula: Deficit = max(0, Demand - (Generation + Imports - Margin))
  const netSupply = generation + imports - margin;
  const rawDeficit = demand - netSupply;
  const deficitMw = Math.max(0, Math.round(rawDeficit * 10) / 10);

  // Emergency automated shedding mutation
  const emergencyMutation = useMutation({
    mutationFn: (deficit: number) => executeEmergencyAutoShed(deficit),
    onSuccess: (data) => {
      setEmergencyResult(data);
      queryClient.invalidateQueries({ queryKey: ['monitoringSummary'] });
      queryClient.invalidateQueries({ queryKey: ['bccDashboard'] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert("❌ Échec du délestage d'urgence automatique : " + (e?.response?.data?.detail || e.message || 'Erreur inconnue'));
    },
  });

  // Presets handlers
  const handleApplyPreset = async (presetId: string, d: number, g: number, imp: number, m: number, telemetryMode?: string) => {
    setActivePreset(presetId);
    setCalcMode('SIMULATION');
    setSimDemand(d);
    setSimGen(g);
    setSimImports(imp);
    setSimMargin(m);

    if (telemetryMode) {
      try {
        await setTelemetryScenario(telemetryMode);
      } catch (e) {
        console.warn('Could not switch backend scenario', e);
      }
    }
  };

  const handleReturnToLive = async () => {
    setCalcMode('LIVE');
    setActivePreset(null);
    try {
      await setTelemetryScenario('MODERATE');
    } catch (e) {
      console.warn('Could not switch scenario', e);
    }
  };

  return (
    <div className="realtime-deficit-widget">
      {/* Header */}
      <div className="rt-deficit-header">
        <div className="rt-deficit-title-group">
          <div>
            <h3 className="rt-header-title">
              Calcul du Déficit en Temps Réel &amp; Télécommande d'Urgence
            </h3>
            <p className="rt-header-subtitle">
              Bilan instantané du déséquilibre réseau :{' '}
              <code>Déficit = Max(0, Demande - (Production + Imports - Marge))</code>
            </p>
          </div>
        </div>

        <div className="rt-mode-toggle">
          <button
            className={`btn-mode ${calcMode === 'LIVE' ? 'active-mode-live' : ''}`}
            onClick={handleReturnToLive}
          >
            ● Télémesure Directe (1 Hz)
          </button>
          <button
            className={`btn-mode ${calcMode === 'SIMULATION' ? 'active-mode-sim' : ''}`}
            onClick={() => setCalcMode('SIMULATION')}
          >
            Simulation Paramétrique (What-If)
          </button>
        </div>
      </div>

      {/* Interactive 4-term Formula Display */}
      <div className="rt-formula-box">
        <div className="rt-formula-term rt-term-demand">
          <span className="rt-term-label">Demande (P_dem)</span>
          <span className="rt-term-val">{demand.toFixed(1)} MW</span>
          <span className="rt-term-sub">Consommation réseau</span>
        </div>

        <span className="rt-operator">−</span>

        <div className="rt-bracket-group">
          <span className="rt-bracket">(</span>
          <div className="rt-formula-term rt-term-gen">
            <span className="rt-term-label">Production (P_prod)</span>
            <span className="rt-term-val">{generation.toFixed(1)} MW</span>
            <span className="rt-term-sub">Centrales nationales</span>
          </div>

          <span className="rt-operator">+</span>

          <div className="rt-formula-term rt-term-imports">
            <span className="rt-term-label">Imports (P_imp)</span>
            <span className="rt-term-val">{imports.toFixed(1)} MW</span>
            <span className="rt-term-sub">Interconnexions</span>
          </div>

          <span className="rt-operator">−</span>

          <div className="rt-formula-term rt-term-margin">
            <span className="rt-term-label">Marge Réserve (M)</span>
            <span className="rt-term-val">{margin.toFixed(1)} MW</span>
            <span className="rt-term-sub">Réserve primaire</span>
          </div>
          <span className="rt-bracket">)</span>
        </div>

        <span className="rt-operator">=</span>

        <div className={`rt-result-term ${deficitMw > 0 ? 'deficit-alert' : 'deficit-balanced'}`}>
          <span className="rt-result-label">Déficit Calculé</span>
          <span className="rt-result-val">{deficitMw.toFixed(1)} MW</span>
          <span className="rt-result-tag">
            {deficitMw > 0 ? 'Délestage Requis' : 'Équilibre Nominal'}
          </span>
        </div>
      </div>

      {/* Preset Real-Time Cases */}
      <div className="rt-cases-section">
        <span className="rt-cases-title">Profils Réseau &amp; Incidents Types :</span>
        <div className="rt-cases-grid">
          <button
            className={`case-button ${activePreset === 'CASE_350' ? 'active-case' : ''}`}
            onClick={() => handleApplyPreset('CASE_350', 4400, 3800, 200, 50, 'MODERATE')}
          >
            <div className="case-info">
              <strong>Cas A : Déclenchement Tranche Thermique (-350 MW)</strong>
              <small>Dem: 4400 | Prod: 3800 | Imp: 200 | M: 50 ➔ <strong>Déficit: 350 MW</strong></small>
            </div>
          </button>

          <button
            className={`case-button ${activePreset === 'CASE_800' ? 'active-case' : ''}`}
            onClick={() => handleApplyPreset('CASE_800', 4820, 3740, 190, 50, 'PEAK')}
          >
            <div className="case-info">
              <strong>Cas B : Pointe de Canicule &amp; Surcharge (+800 MW)</strong>
              <small>Dem: 4820 | Prod: 3740 | Imp: 190 | M: 50 ➔ <strong>Déficit: 940 MW</strong></small>
            </div>
          </button>

          <button
            className={`case-button ${activePreset === 'CASE_BALANCED' ? 'active-case' : ''}`}
            onClick={() => handleApplyPreset('CASE_BALANCED', 3940, 3850, 215, 60, 'BALANCED')}
          >
            <div className="case-info">
              <strong>Cas C : Situation Nominale &amp; Équilibre (0 MW)</strong>
              <small>Dem: 3940 | Prod: 3850 | Imp: 215 | M: 60 ➔ <strong>Déficit: 0 MW</strong></small>
            </div>
          </button>

          <button
            className={`case-button ${activePreset === 'CASE_INTERCO' ? 'active-case' : ''}`}
            onClick={() => handleApplyPreset('CASE_INTERCO', 4300, 3800, 50, 50, 'MODERATE')}
          >
            <div className="case-info">
              <strong>Cas D : Perte Interconnexion Extérieure (-150 MW)</strong>
              <small>Dem: 4300 | Prod: 3800 | Imp: 50 | M: 50 ➔ <strong>Déficit: 500 MW</strong></small>
            </div>
          </button>
        </div>
      </div>

      {/* Manual Sliders when in Simulation mode */}
      {calcMode === 'SIMULATION' && (
        <div className="rt-sliders-panel">
          <div className="slider-row">
            <label>
              Demande Réseau : <strong>{simDemand} MW</strong>
            </label>
            <input
              type="range"
              min="3500"
              max="5500"
              step="10"
              value={simDemand}
              onChange={(e) => setSimDemand(parseFloat(e.target.value))}
            />
          </div>

          <div className="slider-row">
            <label>
              Production Nationale : <strong>{simGen} MW</strong>
            </label>
            <input
              type="range"
              min="3000"
              max="4500"
              step="10"
              value={simGen}
              onChange={(e) => setSimGen(parseFloat(e.target.value))}
            />
          </div>

          <div className="slider-row">
            <label>
              Imports Interconnexions : <strong>{simImports} MW</strong>
            </label>
            <input
              type="range"
              min="0"
              max="500"
              step="10"
              value={simImports}
              onChange={(e) => setSimImports(parseFloat(e.target.value))}
            />
          </div>

          <div className="slider-row">
            <label>
              Marge de Réserve : <strong>{simMargin} MW</strong>
            </label>
            <input
              type="range"
              min="0"
              max="150"
              step="5"
              value={simMargin}
              onChange={(e) => setSimMargin(parseFloat(e.target.value))}
            />
          </div>
        </div>
      )}

      {/* Action Footer */}
      <div className="rt-deficit-footer">
        <div className="rt-footer-diagnosis">
          {deficitMw > 0 ? (
            <span>
              <strong>Déficit actif constaté ({deficitMw.toFixed(1)} MW)</strong> : Risque d'écart sur la fréquence du réseau national. Ordre d'effacement d'urgence nécessaire.
            </span>
          ) : (
            <span>
              <strong>Marge d'exploitation conforme</strong> : L'offre couvre intégralement la demande nationale avec maintien des réserves primaires.
            </span>
          )}
        </div>

        {deficitMw > 0 && (
          <button
            className="btn-emergency-auto-shed"
            onClick={() => emergencyMutation.mutate(deficitMw)}
            disabled={emergencyMutation.isPending}
            title="Calcule la répartition et transmet les ordres d'ouverture aux départs éligibles"
          >
            {emergencyMutation.isPending ? (
              <span className="spinner-inline">Télécommande d'ouverture en cours...</span>
            ) : (
              <span>Déclencher l'effacement d'urgence ({deficitMw.toFixed(1)} MW)</span>
            )}
          </button>
        )}
      </div>

      {/* Emergency Execution Report Modal */}
      {emergencyResult && (
        <div className="modal-backdrop" onClick={() => setEmergencyResult(null)}>
          <div className="modal-box emergency-report-modal" onClick={(e) => e.stopPropagation()}>
            <div className="emergency-modal-header">
              <div className="emergency-title-row">
                <div>
                  <h3 className="emergency-modal-title">
                    Délestage d'Urgence Télécommandé
                  </h3>
                  <p className="emergency-modal-sub">
                    Ordre #{emergencyResult.order_id} exécuté · Fréquence réseau régulée à la valeur nominale
                  </p>
                </div>
              </div>
              <button className="btn-close-modal" onClick={() => setEmergencyResult(null)}>
                ✕
              </button>
            </div>

            <div className="emergency-kpi-summary">
              <div className="em-kpi-card">
                <span className="em-kpi-label">Déficit Initial</span>
                <span className="em-kpi-val text-red">{emergencyResult.total_deficit_mw} MW</span>
              </div>
              <div className="em-kpi-card">
                <span className="em-kpi-label">Puissance Coupée</span>
                <span className="em-kpi-val text-green">{emergencyResult.total_mw_cut} MW</span>
              </div>
              <div className="em-kpi-card">
                <span className="em-kpi-label">Départs Coupés</span>
                <span className="em-kpi-val text-blue">{emergencyResult.cut_feeders_count}</span>
              </div>
              <div className="em-kpi-card">
                <span className="em-kpi-label">Délai d'Exécution</span>
                <span className="em-kpi-val text-purple">&lt; 1 s (Télécommande)</span>
              </div>
            </div>

            <div className="emergency-rule-explanation">
              <strong>Contrôle des critères d'exploitation STEG</strong> : Les {emergencyResult.cut_feeders_count} départs
              ont été sélectionnés et télécommandés selon les règles hiérarchiques de priorité
              (P5 ➔ P1), avec respect des temps de repos matériel et verrouillage absolu des infrastructures P0.
            </div>

            <div className="emergency-feeders-table-wrap">
              <h4>Départs télécommandés à l'ouverture :</h4>
              <table className="emergency-table">
                <thead>
                  <tr>
                    <th>Départ</th>
                    <th>Centre BCC</th>
                    <th>Priorité</th>
                    <th>Puissance Soulagée</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {emergencyResult.cut_feeders.map((f) => (
                    <tr key={f.feeder_id}>
                      <td>
                        <strong>{f.feeder_name}</strong> <small>({f.feeder_id})</small>
                      </td>
                      <td>{f.bcc_name}</td>
                      <td>
                        <span className={`priority-pill priority-${f.priority.toLowerCase()}`}>
                          {f.priority}
                        </span>
                      </td>
                      <td>
                        <strong>{f.mw_cut.toFixed(1)} MW</strong>
                      </td>
                      <td>
                        <span className="status-open-pill">COUPÉ</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="emergency-modal-actions">
              <button
                className="btn-secondary"
                onClick={() => {
                  setEmergencyResult(null);
                  navigate('/bcc');
                }}
              >
                🎮 Suivre les Manœuvres BCC ↗
              </button>
              <button
                className="btn-secondary"
                onClick={() => {
                  setEmergencyResult(null);
                  navigate(`/orders/${emergencyResult.order_id}`);
                }}
              >
                📑 Voir l'Ordre #{emergencyResult.order_id} ↗
              </button>
              <button className="btn-primary" onClick={() => setEmergencyResult(null)}>
                Compris / Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
