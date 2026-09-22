import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getOrder, allocateOrder, validateOrder, cancelOrder, activateOrder, completeOrder, deleteOrder, getPlan } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import AllocationTree from './AllocationTree';
import OrderExecutionSummary from './OrderExecutionSummary';

interface OrderDetailProps {
  orderId: number;
}

const LIFECYCLE_STEPS = ['DRAFT', 'ALLOCATED', 'VALIDATED', 'ACTIVE', 'COMPLETED'];

export default function OrderDetail({ orderId }: OrderDetailProps) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const { data: order, isLoading, error } = useQuery({
    queryKey: ['order', orderId],
    queryFn: () => getOrder(orderId),
  });

  const { data: plan } = useQuery({
    queryKey: ['plan', order?.plan_id],
    queryFn: () => getPlan(order!.plan_id),
    enabled: !!order?.plan_id,
  });

  const allocateMutation = useMutation({
    mutationFn: () => allocateOrder(orderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const validateMutation = useMutation({
    mutationFn: () => validateOrder(orderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const cancelMutation = useMutation({
    mutationFn: (reason: string) => cancelOrder(orderId, reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const activateMutation = useMutation({
    mutationFn: () => activateOrder(orderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeOrder(orderId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteOrder(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['plans'] });
      navigate('/orders');
    },
    onError: (err: any) => {
      alert(`Erreur lors de la suppression: ${err?.response?.data?.detail || err.message}`);
    },
  });

  if (isLoading) return <div className="status loading">Chargement de l'ordre...</div>;
  if (error || !order) return <div className="status error">Erreur lors du chargement de l'ordre</div>;

  const currentStepIndex = LIFECYCLE_STEPS.indexOf(order.status);
  const isCancelled = order.status === 'CANCELLED';

  const handleAllocate = () => allocateMutation.mutate();
  const handleValidate = () => validateMutation.mutate();
  const handleActivate = () => activateMutation.mutate();
  const handleComplete = () => {
    if (confirm('Confirmer la clôture de cet ordre ? Cette action est irréversible.')) {
      completeMutation.mutate();
    }
  };
  const handleCancel = () => {
    const reason = prompt('Raison de l\'annulation ?');
    if (reason) cancelMutation.mutate(reason);
  };

  // Find partial nodes for shortfall summary
  const partialBccNodes = order.allocation_nodes.filter(n => n.level === 'BCC' && n.is_partial);

  return (
    <div className="order-detail">
      <div className="order-detail-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button className="btn-small btn-ghost" onClick={() => navigate('/orders')}>
          ← Retour aux ordres
        </button>
        {(user?.role === 'DISPATCHER' || user?.role === 'ADMIN') && (
          <button
            type="button"
            className="btn-delete-order"
            onClick={() => setShowDeleteModal(true)}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            Supprimer l'ordre
          </button>
        )}
      </div>

      <div className="lifecycle-bar">
        {LIFECYCLE_STEPS.map((step, idx) => {
          let stateClass = 'future';
          if (isCancelled) {
            stateClass = step === order.status ? 'cancelled' : 'future'; // Wait, order.status is CANCELLED which is not in LIFECYCLE_STEPS. So index is -1.
          } else if (idx < currentStepIndex) {
            stateClass = 'completed';
          } else if (idx === currentStepIndex) {
            stateClass = 'current';
          }
          return (
            <div key={step} className={`lifecycle-step ${stateClass}`}>
              {step}
            </div>
          );
        })}
        {isCancelled && <div className="lifecycle-step cancelled">CANCELLED</div>}
      </div>

      <div className="info order-metadata">
        <h2>Détails de l'ordre #{order.id}</h2>
        <div className="metadata-grid">
          <div><strong>Plan:</strong> #{order.plan_id} {plan ? `(${plan.date} - ${plan.mode})` : ''}</div>
          <div><strong>Déficit total:</strong> {order.total_deficit_mw.toLocaleString('fr-FR')} MW</div>
          <div><strong>Statut:</strong> {order.status}</div>
          <div><strong>Créé le:</strong> {new Date(order.created_at).toLocaleString('fr-FR')}</div>
        </div>

        {(user?.role === 'DISPATCHER' || user?.role === 'ADMIN') && (
          <div className="order-actions">
            {order.status === 'DRAFT' && (
              <button 
                className="btn-small btn-primary" 
                onClick={handleAllocate}
                disabled={allocateMutation.isPending}
              >
                Lancer l'allocation
              </button>
            )}
            {order.status === 'ALLOCATED' && (
              <>
                <button 
                  className="btn-small btn-primary" 
                  onClick={handleValidate}
                  disabled={validateMutation.isPending}
                >
                  Valider l'ordre
                </button>
                <button 
                  className="btn-small btn-ghost" 
                  onClick={handleCancel}
                  disabled={cancelMutation.isPending}
                >
                  Annuler
                </button>
              </>
            )}
            {order.status === 'VALIDATED' && (
              <>
                <button 
                  className="btn-small btn-primary" 
                  onClick={handleActivate}
                  disabled={activateMutation.isPending}
                >
                  ⚡ Activer l'exécution
                </button>
                <button 
                  className="btn-small btn-ghost" 
                  onClick={handleCancel}
                  disabled={cancelMutation.isPending}
                >
                  Annuler
                </button>
              </>
            )}
            {order.status === 'ACTIVE' && (
              <button 
                className="btn-small btn-primary" 
                onClick={handleComplete}
                disabled={completeMutation.isPending}
              >
                ✅ Marquer comme terminé
              </button>
            )}
          </div>
        )}

        {(order.status === 'VALIDATED' || order.status === 'ACTIVE') && (
          <div className="bcc-link-section" style={{ marginTop: '12px' }}>
            <Link to="/bcc" className="btn-small btn-primary">
              🖥️ Ouvrir la console BCC
            </Link>
          </div>
        )}
      </div>

      {partialBccNodes.length > 0 && (
        <div className="shortfall-warning status error">
          ⚠️ Attention : {partialBccNodes.length} BCC n'atteignent pas leur cible.
        </div>
      )}

      {order.status === 'ACTIVE' && (
        <OrderExecutionSummary orderId={order.id} />
      )}

      {currentStepIndex >= LIFECYCLE_STEPS.indexOf('ALLOCATED') && (
        <div className="allocation-section">
          <h3>Arbre d'allocation</h3>
          <AllocationTree 
            nodes={order.allocation_nodes.filter(n => n.level === 'NATIONAL')} 
            slots={plan?.slots || []}
            orderId={order.id}
            orderStatus={order.status}
          />
        </div>
      )}

      {/* Confirmation & Warning Modal for Order Deletion */}
      {showDeleteModal && (
        <div className="modal-backdrop" onClick={() => !deleteMutation.isPending && setShowDeleteModal(false)}>
          <div className="modal-box delete-order-modal" onClick={(e) => e.stopPropagation()}>
            {order.status === 'COMPLETED' ? (
              <>
                <div className="modal-header-danger">
                  <div className="modal-icon-wrapper danger-subtle">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#c53030" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      <line x1="10" y1="11" x2="10" y2="17"></line>
                      <line x1="14" y1="11" x2="14" y2="17"></line>
                    </svg>
                  </div>
                  <div>
                    <h3 className="modal-title">Supprimer l'ordre #{order.id}</h3>
                    <p className="modal-subtitle">
                      Statut : <span className="order-status-badge badge-green">{order.status}</span>
                    </p>
                  </div>
                </div>

                <div className="modal-content-body">
                  <p>Êtes-vous sûr de vouloir supprimer cet ordre <strong>terminé</strong> ?</p>
                  <p className="modal-instruction">
                    Cette action supprimera définitivement l'ordre ainsi que les données d'allocation associées.
                  </p>
                </div>

                <div className="modal-actions">
                  <button 
                    type="button" 
                    className="btn-cancel" 
                    onClick={() => setShowDeleteModal(false)}
                    disabled={deleteMutation.isPending}
                  >
                    Annuler
                  </button>
                  <button 
                    type="button" 
                    className="btn-confirm-delete" 
                    onClick={() => deleteMutation.mutate()}
                    disabled={deleteMutation.isPending}
                  >
                    {deleteMutation.isPending ? 'Suppression...' : 'Supprimer'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="modal-header-danger">
                  <div className="modal-icon-wrapper warning-strong">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#c05621" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                      <line x1="12" y1="9" x2="12" y2="13"></line>
                      <line x1="12" y1="17" x2="12.01" y2="17"></line>
                    </svg>
                  </div>
                  <div>
                    <h3 className="modal-title" style={{ color: '#c05621' }}>Attention : Ordre non terminé</h3>
                    <p className="modal-subtitle">
                      Ordre #{order.id} — Statut : <span className="order-status-badge badge-orange">{order.status}</span>
                    </p>
                  </div>
                </div>

                <div className="modal-warning-box">
                  <strong>⚠️ Avertissement :</strong> Cet ordre de délestage <strong>n'est pas encore terminé</strong> (statut actuel : <strong>{order.status}</strong>).
                  <br /><br />
                  La suppression d'un ordre non terminé peut impacter les opérations de délestage en cours ou prévues sur le réseau électrique.
                </div>

                <p className="modal-instruction" style={{ marginTop: '0.75rem' }}>
                  Êtes-vous sûr de vouloir forcer la suppression de cet ordre non finalisé ? Cette action est irréversible.
                </p>

                <div className="modal-actions">
                  <button 
                    type="button" 
                    className="btn-cancel" 
                    onClick={() => setShowDeleteModal(false)}
                    disabled={deleteMutation.isPending}
                  >
                    Annuler
                  </button>
                  <button 
                    type="button" 
                    className="btn-confirm-delete btn-confirm-warning" 
                    onClick={() => deleteMutation.mutate()}
                    disabled={deleteMutation.isPending}
                  >
                    {deleteMutation.isPending ? 'Suppression...' : 'Confirmer la suppression'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
