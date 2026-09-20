import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getRotationProposals,
  executeRotation,
  type RotationProposal,
  type ReplacementCandidate,
} from '../../api/client';

interface RotationPanelProps {
  bccId?: string;
  showEmptyNotice?: boolean;
}

export default function RotationPanel({ bccId, showEmptyNotice = false }: RotationPanelProps) {
  const queryClient = useQueryClient();

  // Selected replacement per proposal: proposal.outgoing_event_id -> feeder_id
  const [selectedReplacements, setSelectedReplacements] = useState<Record<number, string>>({});

  // Justification modal state
  const [activeJustification, setActiveJustification] = useState<{
    proposal: RotationProposal;
    candidate: ReplacementCandidate;
  } | null>(null);
  const [justificationText, setJustificationText] = useState('');

  // 1-sec tick for live elapsed time rendering
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const { data: proposals = [], isLoading } = useQuery<RotationProposal[]>({
    queryKey: ['rotationProposals', bccId],
    queryFn: () => getRotationProposals(bccId),
    refetchInterval: 3000,
  });

  const rotationMutation = useMutation({
    mutationFn: (payload: { outgoingEventId: number; replacementFeederId: string; justification?: string }) =>
      executeRotation({
        outgoing_event_id: payload.outgoingEventId,
        replacement_feeder_id: payload.replacementFeederId,
        justification: payload.justification,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rotationProposals'] });
      queryClient.invalidateQueries({ queryKey: ['bccDashboard'] });
      queryClient.invalidateQueries({ queryKey: ['monitoringSummary'] });
      setActiveJustification(null);
      setJustificationText('');
    },
  });

  const formatElapsed = (openTimeStr: string) => {
    const diffSec = Math.max(0, Math.floor((Date.now() - new Date(openTimeStr).getTime()) / 1000));
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    return `${mins}m ${secs < 10 ? '0' : ''}${secs}s`;
  };

  const handleExecuteClick = (proposal: RotationProposal) => {
    const chosenFeederId =
      selectedReplacements[proposal.outgoing_event_id] ??
      proposal.recommended_replacement?.feeder_id;

    if (!chosenFeederId) return;

    // Find candidate object
    const candidate =
      proposal.recommended_replacement?.feeder_id === chosenFeederId
        ? proposal.recommended_replacement
        : proposal.alternatives.find((a) => a.feeder_id === chosenFeederId);

    if (candidate && !candidate.is_eligible && candidate.rest_time_left_min) {
      setActiveJustification({ proposal, candidate });
      return;
    }

    rotationMutation.mutate({
      outgoingEventId: proposal.outgoing_event_id,
      replacementFeederId: chosenFeederId,
    });
  };

  const handleJustificationSubmit = () => {
    if (!activeJustification || !justificationText.trim()) return;
    rotationMutation.mutate({
      outgoingEventId: activeJustification.proposal.outgoing_event_id,
      replacementFeederId: activeJustification.candidate.feeder_id,
      justification: justificationText,
    });
  };

  if (isLoading && proposals.length === 0) {
    return null;
  }

  if (proposals.length === 0) {
    if (!showEmptyNotice) return null;
    return (
      <div className="rotation-empty-notice">
        <span className="check-icon">✓</span> Aucune rotation requise : aucun départ ne dépasse 80% (36 min).
      </div>
    );
  }

  return (
    <div className="rotation-panel-container">
      <div className="rotation-alert-header">
        <div className="rotation-title-area">
          <span className="alert-badge-pulse">⚠️ ALERTE ROTATION (UC6)</span>
          <h3>
            {proposals.length} départ{proposals.length > 1 ? 's ont' : ' a'} atteint le seuil de rotation (&ge; 36 min)
          </h3>
        </div>
        <p className="rotation-subtitle">
          Pour respecter la limite réglementaire de 45 minutes et préserver l'équité, basculez la coupure vers un départ
          équivalent en 1 clic (conservation stricte des MW).
        </p>
      </div>

      <div className="rotation-cards-list">
        {proposals.map((p) => {
          const chosenId =
            selectedReplacements[p.outgoing_event_id] ?? p.recommended_replacement?.feeder_id;
          const allOptions: ReplacementCandidate[] = [];
          if (p.recommended_replacement) allOptions.push(p.recommended_replacement);
          allOptions.push(...p.alternatives);

          const currentCandidate = allOptions.find((c) => c.feeder_id === chosenId);

          return (
            <div
              key={p.outgoing_event_id}
              className={`rotation-card ${p.alarm_level === 'RED' ? 'card-crit-red' : 'card-warn-amber'}`}
            >
              {/* Left Column: Outgoing Feeder */}
              <div className="rotation-section outgoing-box">
                <span className="section-label">DÉPART ACTUELLEMENT COUPÉ</span>
                <div className="feeder-identity">
                  <h4 className="feeder-name-highlight">{p.outgoing_feeder_name}</h4>
                  <span className="feeder-meta">
                    {p.substation_name} · ({p.outgoing_feeder_id}) · {p.bcc_name}
                  </span>
                </div>
                <div className="rotation-metrics">
                  <div className="metric-item">
                    <span>Temps écoulé :</span>
                    <strong className="timer-danger">{formatElapsed(p.open_time)}</strong>
                    <span className="limit-target">/ {p.max_duration_minutes} min max</span>
                  </div>
                  <div className="metric-item">
                    <span>Puissance délestée :</span>
                    <strong>{p.outgoing_mw.toFixed(1)} MW</strong>
                  </div>
                </div>
              </div>

              {/* Center divider: Swap symbol */}
              <div className="rotation-swap-divider">
                <span className="swap-icon">🔄</span>
                <span className="swap-text">Bascule</span>
              </div>

              {/* Right Column: Recommended Replacement */}
              <div className="rotation-section incoming-box">
                <div className="incoming-header-row">
                  <span className="section-label">REMPLAÇANT RECOMMANDÉ</span>
                  {allOptions.length > 1 && (
                    <select
                      className="candidate-selector"
                      value={chosenId}
                      onChange={(e) =>
                        setSelectedReplacements({
                          ...selectedReplacements,
                          [p.outgoing_event_id]: e.target.value,
                        })
                      }
                    >
                      {allOptions.map((opt) => (
                        <option key={opt.feeder_id} value={opt.feeder_id}>
                          {opt.feeder_name} ({opt.avg_mw} MW)
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {currentCandidate ? (
                  <>
                    <div className="feeder-identity">
                      <h4 className="feeder-name-candidate">{currentCandidate.feeder_name}</h4>
                      <span className="feeder-meta">
                        {currentCandidate.substation_name} · ({currentCandidate.feeder_id}) · {currentCandidate.priority}
                      </span>
                    </div>

                    <div className="rotation-metrics">
                      <div className="metric-item">
                        <span>Puissance reprise :</span>
                        <strong>{currentCandidate.avg_mw.toFixed(1)} MW</strong>
                        <span className={`delta-tag ${currentCandidate.delta_mw === 0 ? 'delta-zero' : 'delta-diff'}`}>
                          {currentCandidate.delta_mw > 0 ? `+${currentCandidate.delta_mw}` : currentCandidate.delta_mw} MW
                        </span>
                      </div>
                      <div className="metric-item">
                        <span>Score d'équité :</span>
                        <span className="fairness-tag">{currentCandidate.fairness_score}</span>
                        <span className="cum-mins">({currentCandidate.cumulative_minutes}m cumulées)</span>
                      </div>
                    </div>

                    {currentCandidate.rest_time_left_min && currentCandidate.rest_time_left_min > 0 && (
                      <div className="rotation-rest-warning">
                        ⚠️ En repos ({currentCandidate.rest_time_left_min} min). Dérogation requise.
                      </div>
                    )}
                  </>
                ) : (
                  <div className="no-candidate-warning">
                    ⚠️ Aucun départ de remplacement éligible disponible dans ce BCC.
                  </div>
                )}
              </div>

              {/* Action Column: 1-Click Rotation Button */}
              <div className="rotation-action-column">
                <button
                  className="btn-rotate-1click"
                  onClick={() => handleExecuteClick(p)}
                  disabled={!currentCandidate || rotationMutation.isPending}
                >
                  ⚡ Exécuter la Rotation
                  <span className="btn-subtext">Ouverture puis Rétablissement</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Justification Modal for Rest Time Override */}
      {activeJustification && (
        <div className="modal-backdrop">
          <div className="modal-box">
            <h3>⚠️ Dérogation de Temps de Repos - Rotation</h3>
            <p>
              Le départ de remplacement <strong>{activeJustification.candidate.feeder_name}</strong> est encore en
              période de repos obligatoire (<strong>{activeJustification.candidate.rest_time_left_min} min</strong> restantes).
            </p>
            <p className="modal-instruction">
              Veuillez saisir le motif impérieux de rotation avec ce départ (scellé dans la chaîne d'audit) :
            </p>
            <textarea
              className="modal-textarea"
              placeholder="Ex: Absence d'autre départ disponible de puissance équivalente dans le secteur..."
              value={justificationText}
              onChange={(e) => setJustificationText(e.target.value)}
              rows={3}
            />
            <div className="modal-actions">
              <button className="btn-small btn-ghost" onClick={() => setActiveJustification(null)}>
                Annuler
              </button>
              <button
                className="btn-small btn-primary"
                onClick={handleJustificationSubmit}
                disabled={!justificationText.trim() || rotationMutation.isPending}
              >
                Confirmer la rotation avec dérogation
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
