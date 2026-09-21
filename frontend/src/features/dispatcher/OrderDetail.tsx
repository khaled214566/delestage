import { useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getOrder, allocateOrder, validateOrder, cancelOrder, activateOrder, completeOrder, getPlan } from '../../api/client';
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
      <div className="order-detail-header">
        <button className="btn-small btn-ghost" onClick={() => navigate('/orders')}>
          ← Retour aux ordres
        </button>
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

        {user?.role === 'DISPATCHER' && (
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
            orderId={order.id}
            orderStatus={order.status}
          />
        </div>
      )}
    </div>
  );
}
