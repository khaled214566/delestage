import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getBccDashboard,
  confirmOpen,
  confirmClose,
  type BccExecutionDashboard,
  type FeederExecutionItem,
} from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import RotationPanel from './RotationPanel';

const BCC_LIST = [
  { id: 'BCC1', name: 'BCC Tunis (Nord)' },
  { id: 'BCC2', name: 'BCC Nabeul (Nord)' },
  { id: 'BCC3', name: 'BCC Sousse (Nord)' },
  { id: 'BCC4', name: 'BCC Bizerte (Nord)' },
  { id: 'BCC5', name: 'BCC Sfax (Sud)' },
  { id: 'BCC6', name: 'BCC Gabès (Sud)' },
  { id: 'BCC7', name: 'BCC Gafsa (Sud)' },
];

export default function BccExecutionScreen() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Determine initial BCC: operator's scoped BCC or BCC1
  const defaultBcc = (user?.role === 'BCC_OPERATOR' && user.scope_id) ? user.scope_id : 'BCC1';
  const [selectedBcc, setSelectedBcc] = useState(defaultBcc);

  // Per-feeder editable MW input
  const [editedMw, setEditedMw] = useState<Record<string, number>>({});

  // Justification modal state
  const [justificationFeeder, setJustificationFeeder] = useState<FeederExecutionItem | null>(null);
  const [justificationText, setJustificationText] = useState('');

  // Local seconds tick for live countdown timers
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const { data: dashboard, isLoading, error } = useQuery<BccExecutionDashboard>({
    queryKey: ['bccDashboard', selectedBcc],
    queryFn: () => getBccDashboard(selectedBcc),
    refetchInterval: 4000,
  });

  const openMutation = useMutation({
    mutationFn: (payload: { feederId: string; mwActual: number; justification?: string }) =>
      confirmOpen({
        order_id: 1, // Active order
        feeder_id: payload.feederId,
        mw_actual: payload.mwActual,
        justification: payload.justification,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bccDashboard', selectedBcc] });
      setJustificationFeeder(null);
      setJustificationText('');
    },
  });

  const closeMutation = useMutation({
    mutationFn: (eventId: number) => confirmClose(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bccDashboard', selectedBcc] });
    },
  });

  const handleOpenClick = (feeder: FeederExecutionItem) => {
    const mw = editedMw[feeder.feeder_id] ?? feeder.avg_mw;
    // If feeder is in rest period (< 180 min), open justification dialog
    if (feeder.rest_time_left_min && feeder.rest_time_left_min > 0) {
      setJustificationFeeder(feeder);
      return;
    }
    openMutation.mutate({ feederId: feeder.feeder_id, mwActual: mw });
  };

  const handleJustificationSubmit = () => {
    if (!justificationFeeder || !justificationText.trim()) return;
    const mw = editedMw[justificationFeeder.feeder_id] ?? justificationFeeder.avg_mw;
    openMutation.mutate({
      feederId: justificationFeeder.feeder_id,
      mwActual: mw,
      justification: justificationText,
    });
  };

  const formatElapsed = (openTimeStr: string | null) => {
    if (!openTimeStr) return '-';
    const diffSec = Math.max(0, Math.floor((Date.now() - new Date(openTimeStr).getTime()) / 1000));
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    return `${mins}m ${secs < 10 ? '0' : ''}${secs}s`;
  };

  if (isLoading && !dashboard) return <div className="status loading">Chargement de la console BCC...</div>;
  if (error || !dashboard) return <div className="status error">Impossible de charger les données du BCC.</div>;

  const openFeeders = dashboard.feeders.filter(f => f.status === 'OPEN');
  const availableFeeders = dashboard.feeders.filter(f => f.status !== 'OPEN' && f.priority !== 'P0' && !f.is_critical);
  const protectedFeeders = dashboard.feeders.filter(f => f.priority === 'P0' || f.is_critical);

  return (
    <div className="bcc-execution-screen">
      {/* Top bar with Region Selector */}
      <div className="bcc-topbar">
        <div>
          <h2>⚡ Poste de Conduite &amp; Manœuvres Terrain : {dashboard.bcc_name}</h2>
          <p className="bcc-subtitle">
            Saisie manuelle des ouvertures et rétablissements de départs MT (UC5 &amp; UC7)
          </p>
        </div>

        {user?.role !== 'BCC_OPERATOR' && (
          <div className="bcc-selector-wrap">
            <label>Centre BCC : </label>
            <select
              className="bcc-dropdown"
              value={selectedBcc}
              onChange={(e) => setSelectedBcc(e.target.value)}
            >
              {BCC_LIST.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* KPI Stats */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <span className="kpi-title">Cible Régionale</span>
          <span className="kpi-value highlight-blue">{dashboard.target_mw.toFixed(1)} MW</span>
          <span className="kpi-subtext">Objectif Dispatching</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-title">Coupure Réalisée</span>
          <span className="kpi-value highlight-green">{dashboard.actual_mw.toFixed(1)} MW</span>
          <span className="kpi-subtext">Puissance délestée</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-title">Écart Restant</span>
          <span className={`kpi-value ${dashboard.gap_mw > 0 ? 'highlight-orange' : 'highlight-green'}`}>
            {dashboard.gap_mw > 0 ? `+${dashboard.gap_mw.toFixed(1)}` : dashboard.gap_mw.toFixed(1)} MW
          </span>
          <span className="kpi-subtext">Cible - Réalisé</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-title">Départs Coupés</span>
          <span className="kpi-value">{dashboard.open_feeders_count}</span>
          <span className="kpi-subtext">sur {dashboard.feeders.length} départs totaux</span>
        </div>
      </div>

      {/* Rotation Alerts & 1-Click Execution (UC6) */}
      <RotationPanel bccId={selectedBcc} />

      {/* Section 1: Départs actuellement coupés */}
      <div className="bcc-panel active-cuts-panel">
        <h3>🚨 Départs Actuellement Coupés (Manœuvres en cours)</h3>
        {openFeeders.length === 0 ? (
          <div className="empty-state-notice">
            Aucun départ n'est actuellement coupé sur le secteur de {dashboard.bcc_name}.
          </div>
        ) : (
          <div className="feeder-action-cards">
            {openFeeders.map((f) => (
              <div key={f.feeder_id} className={`action-card open-card alarm-${f.alarm_level?.toLowerCase() || 'green'}`}>
                <div className="action-card-header">
                  <div>
                    <h4 className="card-feeder-name">{f.feeder_name}</h4>
                    <span className="card-substation">{f.substation_name} · ({f.feeder_id})</span>
                  </div>
                  <div className="card-timer">
                    <span className="timer-label">Temps coupé :</span>
                    <span className="timer-val">{formatElapsed(f.open_time)}</span>
                  </div>
                </div>

                <div className="action-card-body">
                  <div className="card-metric">
                    <span>Puissance soulagée :</span>
                    <strong>{f.avg_mw.toFixed(1)} MW</strong>
                  </div>
                  <div className="card-metric">
                    <span>Priorité :</span>
                    <span className="priority-pill">{f.priority}</span>
                  </div>
                </div>

                <div className="action-card-footer">
                  <button
                    className="btn-large btn-restore"
                    onClick={() => f.current_event_id && closeMutation.mutate(f.current_event_id)}
                    disabled={closeMutation.isPending}
                  >
                    🔌 Confirmer le Rétablissement
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Départs disponibles et éligibles */}
      <div className="bcc-panel available-panel">
        <h3>⚡ Départs Disponibles pour Délestage (Recommandations &amp; Éligibles)</h3>
        <div className="feeder-action-cards">
          {availableFeeders.map((f) => {
            const currentMw = editedMw[f.feeder_id] ?? f.avg_mw;
            const hasRestViolation = f.rest_time_left_min && f.rest_time_left_min > 0;

            return (
              <div
                key={f.feeder_id}
                className={`action-card available-card ${f.is_planned_in_order ? 'planned-highlight' : ''}`}
              >
                <div className="action-card-header">
                  <div>
                    <div className="feeder-title-row">
                      <h4 className="card-feeder-name">{f.feeder_name}</h4>
                      {f.is_planned_in_order && <span className="planned-badge">★ Recommandé</span>}
                    </div>
                    <span className="card-substation">{f.substation_name} · ({f.feeder_id})</span>
                  </div>
                  <span className="priority-pill">{f.priority}</span>
                </div>

                <div className="action-card-body">
                  <div className="card-input-row">
                    <label>Puissance mesurée (MW) :</label>
                    <input
                      type="number"
                      step="0.1"
                      className="mw-input-field"
                      value={currentMw}
                      onChange={(e) =>
                        setEditedMw({ ...editedMw, [f.feeder_id]: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                  {hasRestViolation && (
                    <div className="rest-warning-box">
                      ⚠️ En repos ({f.rest_time_left_min} min restantes). Justification exigée.
                    </div>
                  )}
                </div>

                <div className="action-card-footer">
                  <button
                    className="btn-large btn-open"
                    onClick={() => handleOpenClick(f)}
                    disabled={openMutation.isPending}
                  >
                    ⚡ Confirmer l'Ouverture du Disjoncteur
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Section 3: Départs protégés P0 */}
      <div className="bcc-panel protected-panel">
        <h3>🔒 Départs Prioritaires Protégés (P0 - Infrastructures Critiques &amp; Vitales)</h3>
        <p className="protected-help">
          Ces départs alimentent des hôpitaux, centres de secours ou stations de pompage vitales. La plateforme
          interdit formellement toute ouverture de disjoncteur sur ces circuits (Règle stricte P0).
        </p>
        <div className="protected-grid">
          {protectedFeeders.map((f) => (
            <div key={f.feeder_id} className="protected-pill">
              <span className="lock-icon">🔒</span>
              <span className="protected-name">{f.feeder_name}</span>
              <span className="protected-sub">({f.avg_mw.toFixed(1)} MW · {f.substation_name})</span>
              <span className="p0-tag">P0 VITAL</span>
            </div>
          ))}
        </div>
      </div>

      {/* Justification Modal */}
      {justificationFeeder && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>⚠️ Dérogation de Temps de Repos</h3>
            <p>
              Le départ <strong>{justificationFeeder.feeder_name} ({justificationFeeder.feeder_id})</strong> a été délesté
              récemment et dispose encore de <strong>{justificationFeeder.rest_time_left_min} minutes</strong> de repos
              obligatoire.
            </p>
            <p className="modal-instruction">
              Conformément aux règles d'exploitation de la STEG, veuillez saisir le motif impérieux de cette déconnexion
              anticipée (qui sera scellé dans le journal d'audit infalsifiable) :
            </p>
            <textarea
              className="modal-textarea"
              placeholder="Ex: Demande urgente du dispatching national face à un effondrement de fréquence..."
              value={justificationText}
              onChange={(e) => setJustificationText(e.target.value)}
              rows={3}
            />
            <div className="modal-actions">
              <button className="btn-small btn-ghost" onClick={() => setJustificationFeeder(null)}>
                Annuler
              </button>
              <button
                className="btn-small btn-primary"
                onClick={handleJustificationSubmit}
                disabled={!justificationText.trim() || openMutation.isPending}
              >
                Confirmer l'ouverture avec dérogation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
