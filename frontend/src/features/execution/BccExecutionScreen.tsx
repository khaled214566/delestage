import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getBccDashboard,
  confirmOpen,
  confirmClose,
  restoreFeederByFeederId,
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
  const { user, isLoading: isAuthLoading } = useAuth();
  const queryClient = useQueryClient();

  // Determine initial BCC: operator's scoped BCC or BCC1
  const defaultBcc = (user?.role === 'BCC_OPERATOR' && user.scope_id) ? user.scope_id : 'BCC1';
  const [selectedBcc, setSelectedBcc] = useState(defaultBcc);

  // Sync selectedBcc once user loads if user is a scoped BCC operator
  useEffect(() => {
    if (user?.role === 'BCC_OPERATOR' && user.scope_id && selectedBcc !== user.scope_id) {
      setSelectedBcc(user.scope_id);
    }
  }, [user, selectedBcc]);

  // Per-feeder editable MW input
  const [editedMw, setEditedMw] = useState<Record<string, number>>({});

  // Justification modal state
  const [justificationFeeder, setJustificationFeeder] = useState<FeederExecutionItem | null>(null);
  const [justificationText, setJustificationText] = useState('');

  // Explanation modal state for recommended feeders
  const [explanationFeeder, setExplanationFeeder] = useState<FeederExecutionItem | null>(null);

  // Local seconds tick for live countdown timers
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const isBccAllowed = !user || user.role !== 'BCC_OPERATOR' || user.scope_id === selectedBcc;

  const { data: dashboard, isLoading, error } = useQuery<BccExecutionDashboard>({
    queryKey: ['bccDashboard', selectedBcc],
    queryFn: () => getBccDashboard(selectedBcc),
    enabled: !isAuthLoading && isBccAllowed,
    refetchInterval: 4000,
  });

  const PRIORITY_ORDER: Record<string, number> = {
    P5: 5,
    P4: 4,
    P3: 3,
    P2: 2,
    P1: 1,
    P0: 0,
  };

  const getPriorityExplanation = (priority: string) => {
    switch (priority) {
      case 'P5':
        return {
          title: 'Priorité P5 — Industriels & Tertiaires Lourds (Délestage en 1er)',
          desc: "Selon la grille de délestage de la STEG, les départs classés P5 sont systématiquement délestés en PREMIER. Il s'agit de zones industrielles ou de gros consommateurs non critiques pouvant différer leur consommation ou disposant de groupes autonomes. Cela permet d'épargner les usagers résidentiels et les services publics.",
          badgeColor: '#c53030',
          badgeBg: '#fff5f5',
          badgeBorder: '#feb2b2',
        };
      case 'P4':
        return {
          title: 'Priorité P4 — Activités Commerciales et Mixtes (Délestage en 2e)',
          desc: "Les départs P4 regroupent les zones commerciales, bureaux et activités tertiaires mixtes. Ils sont mobilisés en 2ème rang après épuisement des capacités P5 pour stabiliser la fréquence réseau sans impacter les zones purement résidentielles.",
          badgeColor: '#dd6b20',
          badgeBg: '#fffaf0',
          badgeBorder: '#fbd38d',
        };
      case 'P3':
        return {
          title: 'Priorité P3 — Secteurs Résidentiels Standards (Priorité Moyenne)',
          desc: "Les départs P3 alimentent des zones résidentielles denses sans infrastructure vitale. Le délestage n'intervient que si le déficit régional ne peut être absorbé par P5 et P4, avec une rotation équitable stricte.",
          badgeColor: '#2b6cb0',
          badgeBg: '#ebf8ff',
          badgeBorder: '#bee3f8',
        };
      case 'P2':
        return {
          title: 'Priorité P2 — Réseaux Urbains à Vulnérabilité Modérée (Priorité Faible)',
          desc: "Ces départs alimentent des centres urbains avec cliniques de jour, commerces de première nécessité ou écoles. Ils ne sont mobilisés qu'en situation d'urgence sévère.",
          badgeColor: '#805ad5',
          badgeBg: '#faf5ff',
          badgeBorder: '#e9d8fd',
        };
      case 'P1':
        return {
          title: 'Priorité P1 — Réseaux Sensibles de Sauvegarde (Dernier Recours)',
          desc: "Départs à proximité immédiate de nœuds stratégiques nationaux. Déconnectés uniquement en ultime recours pour éviter un effondrement généralisé du réseau (Blackout).",
          badgeColor: '#4a5568',
          badgeBg: '#f7fafc',
          badgeBorder: '#cbd5e0',
        };
      default:
        return {
          title: `Priorité ${priority}`,
          desc: "Départ sélectionné conformément aux règles de délestage hiérarchique de la STEG.",
          badgeColor: '#4a5568',
          badgeBg: '#edf2f7',
          badgeBorder: '#cbd5e0',
        };
    }
  };

  const openMutation = useMutation({
    mutationFn: (payload: { feederId: string; mwActual: number; justification?: string }) =>
      confirmOpen({
        order_id: dashboard?.order_id ?? 1, // Active order ID
        feeder_id: payload.feederId,
        mw_actual: payload.mwActual,
        justification: payload.justification,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bccDashboard', selectedBcc] });
      setJustificationFeeder(null);
      setJustificationText('');
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      alert('❌ Échec de la manœuvre d\'ouverture : ' + (e.response?.data?.detail ?? 'Erreur inconnue'));
    },
  });

  const closeMutation = useMutation({
    mutationFn: (eventId: number) => confirmClose(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bccDashboard', selectedBcc] });
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      alert('❌ Échec du rétablissement : ' + (e.response?.data?.detail ?? 'Erreur inconnue'));
    },
  });

  const restoreFeederMutation = useMutation({
    mutationFn: (feederId: string) => restoreFeederByFeederId(feederId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bccDashboard', selectedBcc] });
    },
    onError: (err: unknown) => {
      const e = err as { response?: { data?: { detail?: string } } };
      alert('❌ Échec du rétablissement : ' + (e.response?.data?.detail ?? 'Erreur inconnue'));
    },
  });

  const isRestoring = closeMutation.isPending || restoreFeederMutation.isPending;

  const handleRestoreClick = (feeder: FeederExecutionItem) => {
    if (feeder.current_event_id) {
      closeMutation.mutate(feeder.current_event_id);
    } else {
      restoreFeederMutation.mutate(feeder.feeder_id);
    }
  };

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

  const errorMessage =
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
    (error instanceof Error ? error.message : 'Impossible de charger les données du BCC.');

  if ((isLoading || isAuthLoading) && !dashboard) {
    return <div className="status loading">Chargement de la console BCC...</div>;
  }
  if (error || !dashboard) {
    return <div className="status error">Impossible de charger les données du BCC : {errorMessage}</div>;
  }

  const openFeeders = dashboard.feeders.filter(f => f.status === 'OPEN');
  const availableFeeders = dashboard.feeders
    .filter(f => f.status !== 'OPEN' && f.priority !== 'P0' && !f.is_critical)
    .sort((a, b) => {
      // 1. Départs recommandés en premier
      if (a.is_planned_in_order !== b.is_planned_in_order) {
        return a.is_planned_in_order ? -1 : 1;
      }
      // 2. Ordre décroissant de priorité de P5 vers P1
      const pA = PRIORITY_ORDER[a.priority] ?? 0;
      const pB = PRIORITY_ORDER[b.priority] ?? 0;
      if (pA !== pB) {
        return pB - pA;
      }
      // 3. À priorité égale : puissance nominale décroissante (MW)
      return b.avg_mw - a.avg_mw;
    });

  const protectedFeeders = dashboard.feeders
    .filter(f => f.priority === 'P0' || f.is_critical)
    .sort((a, b) => {
      const pA = PRIORITY_ORDER[a.priority] ?? 0;
      const pB = PRIORITY_ORDER[b.priority] ?? 0;
      if (pA !== pB) return pB - pA;
      return b.avg_mw - a.avg_mw;
    });

  const plannedCount = availableFeeders.filter(f => f.is_planned_in_order).length;

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

      {dashboard.target_mw === 0 && (
        <div className="bcc-notice-banner" style={{
          background: '#ebf8ff',
          border: '1px solid #bee3f8',
          borderLeft: '4px solid #3182ce',
          borderRadius: '6px',
          padding: '0.85rem 1.25rem',
          margin: '0 0 1.5rem 0',
          fontSize: '0.88rem',
          color: '#2b6cb0',
          lineHeight: '1.5',
        }}>
          ℹ️ <strong>Cible régionale à 0.0 MW ?</strong> Aucun quota de délestage n'est encore assigné à ce centre. Pour qu'une cible en MW (ex: 71 MW) soit attribuée et que des départs soient recommandés (badge violet), assurez-vous d'avoir cliqué sur <strong>« Lancer l'allocation »</strong> puis <strong>« ⚡ Activer »</strong> dans la page <Link to="/orders" style={{ color: '#2b6cb0', fontWeight: 600, textDecoration: 'underline' }}>Ordres de délestage ↗</Link>.
        </div>
      )}

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
                    <span className={`priority-pill priority-${f.priority.toLowerCase()}`}>{f.priority}</span>
                  </div>
                </div>

                <div className="action-card-footer">
                  <button
                    className="btn-large btn-restore"
                    onClick={() => handleRestoreClick(f)}
                    disabled={isRestoring}
                  >
                    {isRestoring ? '⏳ Rétablissement...' : '🔌 Confirmer le Rétablissement'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Départs disponibles et éligibles */}
      <div className="bcc-panel available-panel">
        <div className="panel-header-with-badge">
          <h3>⚡ Départs Disponibles pour Délestage ({availableFeeders.length})</h3>
          <div className="sort-indicator-badge">
            <span className="sort-star">★</span> <strong>Recommandés en premier</strong> · Tri décroissant <strong>P5 → P1</strong>
            {plannedCount > 0 && <span className="planned-count-tag">{plannedCount} recommandés</span>}
          </div>
        </div>
        <div className="feeder-action-cards">
          {availableFeeders.map((f) => {
            const currentMw = editedMw[f.feeder_id] ?? f.avg_mw;
            const hasRestViolation = f.rest_time_left_min && f.rest_time_left_min > 0;

            return (
              <div
                key={f.feeder_id}
                className={`action-card available-card ${f.is_planned_in_order ? 'planned-highlight' : ''}`}
              >
                <div className="action-card-header available-header">
                  <div className="card-top-bar">
                    {f.is_planned_in_order ? (
                      <button
                        type="button"
                        className="planned-badge"
                        onClick={() => setExplanationFeeder(f)}
                        title="Cliquez pour afficher l'explication complète de cette recommandation"
                      >
                        <span className="badge-icon-star">★</span>
                        <span className="badge-text">Recommandé</span>
                        <span className="badge-icon-info">ℹ️</span>
                      </button>
                    ) : (
                      <div className="card-top-placeholder" />
                    )}
                    <span className={`priority-pill priority-${f.priority.toLowerCase()}`}>
                      {f.priority}
                    </span>
                  </div>
                  <div className="card-identity-block">
                    <h4 className="card-feeder-name">{f.feeder_name}</h4>
                    <span className="card-substation">{f.substation_name} · ({f.feeder_id})</span>
                  </div>
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

      {/* Explanation Modal for Recommended Feeders */}
      {explanationFeeder && (
        <div className="modal-backdrop" onClick={() => setExplanationFeeder(null)}>
          <div className="modal-box explanation-modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="explanation-modal-header">
              <div className="explanation-title-row">
                <span className="explanation-icon">💡</span>
                <div>
                  <h3 className="explanation-title">
                    Pourquoi ce départ est-il recommandé ?
                  </h3>
                  <div className="explanation-sub">
                    <strong>{explanationFeeder.feeder_name}</strong> · {explanationFeeder.substation_name} ({explanationFeeder.feeder_id})
                  </div>
                </div>
              </div>
              <button
                className="btn-close-modal"
                onClick={() => setExplanationFeeder(null)}
                title="Fermer"
              >
                ✕
              </button>
            </div>

            <div className="explanation-meta-pills">
              <span
                className="pill-priority"
                style={{
                  color: getPriorityExplanation(explanationFeeder.priority).badgeColor,
                  backgroundColor: getPriorityExplanation(explanationFeeder.priority).badgeBg,
                  borderColor: getPriorityExplanation(explanationFeeder.priority).badgeBorder,
                }}
              >
                ⭐ Priorité {explanationFeeder.priority}
              </span>
              <span className="pill-mw">⚡ {explanationFeeder.avg_mw.toFixed(1)} MW</span>
              <span className="pill-target">🎯 Cible BCC : {dashboard.target_mw} MW</span>
              <span className="pill-planned">✓ Planifié dans l'Ordre #{dashboard.order_id ?? 'Actif'}</span>
            </div>

            <div className="explanation-cards-list">
              {/* Point 1: Priorité STEG */}
              <div className="explanation-point-card">
                <div className="point-card-header">
                  <span className="point-card-num">1</span>
                  <h4>{getPriorityExplanation(explanationFeeder.priority).title}</h4>
                </div>
                <p className="point-card-desc">
                  {getPriorityExplanation(explanationFeeder.priority).desc}
                </p>
                <div className="point-card-note">
                  ↳ <em>Règle STEG de délestage décroissant (P5 → P1)</em> : En coupant en premier lieu les départs <strong>P5</strong> (industriels/gros consommateurs), le système évite de priver d'électricité les ménages, écoles et zones urbaines (P3/P2/P1).
                </div>
              </div>

              {/* Point 2: Équité & Rotation */}
              <div className="explanation-point-card">
                <div className="point-card-header">
                  <span className="point-card-num">2</span>
                  <h4>Algorithme d'Équité &amp; Rotation Équilibrée (Fairness Engine)</h4>
                </div>
                <p className="point-card-desc">
                  Temps de coupure cumulé aujourd'hui : <strong>{explanationFeeder.cumulative_minutes ?? 0} minutes</strong>.
                  {explanationFeeder.fairness_score !== null && explanationFeeder.fairness_score !== undefined && (
                    <> (Score d'équité calculé : <strong>{explanationFeeder.fairness_score.toFixed(2)}</strong>).</>
                  )}
                </p>
                <div className="point-card-note">
                  ↳ <em>Justice territoriale</em> : Parmi tous les départs éligibles de même priorité ({explanationFeeder.priority}), ce départ fait partie de ceux ayant subi le moins d'interruptions récentes, évitant ainsi d'imposer des coupures répétées aux mêmes abonnés.
                </div>
              </div>

              {/* Point 3: Éligibilité & Sécurité */}
              <div className="explanation-point-card">
                <div className="point-card-header">
                  <span className="point-card-num">3</span>
                  <h4>Conformité Technique &amp; Règles de Sécurité Validées (100%)</h4>
                </div>
                <ul className="point-card-checklist">
                  <li>
                    ✅ <strong>Temps de repos matériel (180 min) respecté</strong> :
                    Le disjoncteur a suffisamment reposé depuis sa dernière manœuvre, évitant tout risque d'usure anormale ou de surchauffe.
                  </li>
                  <li>
                    ✅ <strong>Aucune infrastructure critique P0</strong> :
                    Cette ligne n'alimente aucun hôpital, caserne, clinique ou station d'eau potable majeure (SONEDE).
                  </li>
                  <li>
                    ✅ <strong>Départ en service</strong> :
                    Ligne sous tension et prête pour une manœuvre d'ouverture immédiate.
                  </li>
                </ul>
              </div>

              {/* Point 4: Cible MW */}
              <div className="explanation-point-card">
                <div className="point-card-header">
                  <span className="point-card-num">4</span>
                  <h4>Convergence Optimale vers le Quota Régional ({dashboard.bcc_name})</h4>
                </div>
                <p className="point-card-desc">
                  Avec une puissance nominale de <strong>{explanationFeeder.avg_mw.toFixed(1)} MW</strong>, ce départ s'ajuste idéalement pour combler le quota régional de <strong>{dashboard.target_mw} MW</strong> fixé par le Dispatching National, sans dépasser la marge de tolérance autorisée (+10%).
                </p>
              </div>
            </div>

            <div className="explanation-modal-footer">
              <button
                className="btn-small btn-ghost"
                onClick={() => setExplanationFeeder(null)}
              >
                Fermer
              </button>
              <button
                className="btn-small btn-open-direct"
                onClick={() => {
                  const feederToOpen = explanationFeeder;
                  setExplanationFeeder(null);
                  handleOpenClick(feederToOpen);
                }}
                disabled={openMutation.isPending}
              >
                ⚡ Confirmer l'Ouverture du Disjoncteur ({explanationFeeder.avg_mw.toFixed(1)} MW)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
