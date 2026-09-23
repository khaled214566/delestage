import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listOrders, createOrder, listPlans, deleteOrder, type OrderListItem } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export default function OrdersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<number | ''>('');
  const [orderToDelete, setOrderToDelete] = useState<OrderListItem | null>(null);

  const { data: orders = [], isLoading: isLoadingOrders } = useQuery({
    queryKey: ['orders'],
    queryFn: listOrders,
  });

  const { data: plans = [] } = useQuery({
    queryKey: ['plans'],
    queryFn: listPlans,
    enabled: showCreate,
  });

  const createMutation = useMutation({
    mutationFn: createOrder,
    onSuccess: (newOrder) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      navigate(`/orders/${newOrder.id}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['plans'] });
      queryClient.invalidateQueries({ queryKey: ['deficit-plans'] });
      setOrderToDelete(null);
    },
    onError: (err: any) => {
      alert(`Erreur lors de la suppression: ${err?.response?.data?.detail || err.message}`);
    },
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'DRAFT': return 'badge-gray';
      case 'ALLOCATED': return 'badge-blue';
      case 'VALIDATED': return 'badge-green';
      case 'ACTIVE': return 'badge-orange';
      case 'COMPLETED': return 'badge-green';
      case 'CANCELLED': return 'badge-red';
      default: return 'badge-gray';
    }
  };

  const handleCreate = () => {
    if (selectedPlanId) {
      createMutation.mutate(Number(selectedPlanId));
    }
  };

  const todayStr = new Date().toISOString().slice(0, 10);
  const validatedPlansWithoutOrders = plans.filter(
    (p) => p.status === 'VALIDATED' && !orders.some((o) => o.plan_id === p.id) && p.date >= todayStr
  );

  return (
    <div className="orders-page">
      <div className="page-header">
        <h2>Ordres de délestage</h2>
        {user?.role === 'DISPATCHER' && (
          <button className="btn-small btn-primary" onClick={() => setShowCreate(!showCreate)}>
            Créer un ordre
          </button>
        )}
      </div>

      {showCreate && (
        <div className="create-order-panel info">
          <select 
            value={selectedPlanId} 
            onChange={(e) => setSelectedPlanId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">-- Sélectionner un plan validé --</option>
            {validatedPlansWithoutOrders.map(p => (
              <option key={p.id} value={p.id}>Plan #{p.id} - {p.date} ({p.mode})</option>
            ))}
          </select>
          <button 
            className="btn-small btn-primary" 
            onClick={handleCreate}
            disabled={!selectedPlanId || createMutation.isPending}
          >
            Créer
          </button>
        </div>
      )}

      {isLoadingOrders ? (
        <div className="status loading">Chargement des ordres...</div>
      ) : orders.length === 0 ? (
        <div className="empty-state info">Aucun ordre de délestage trouvé.</div>
      ) : (
        <div className="order-list">
          {orders.map(order => (
            <div 
              key={order.id} 
              className="order-card"
              onClick={() => navigate(`/orders/${order.id}`)}
            >
              <div className="order-card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <h3>Ordre #{order.id}</h3>
                  <span className={`order-status-badge ${getStatusColor(order.status)}`}>
                    {order.status}
                  </span>
                </div>
                {(user?.role === 'DISPATCHER' || user?.role === 'ADMIN') && (
                  <button
                    type="button"
                    className="btn-delete-order"
                    title="Supprimer cet ordre"
                    onClick={(e) => {
                      e.stopPropagation();
                      setOrderToDelete(order);
                    }}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                    Supprimer
                  </button>
                )}
              </div>
              <div className="order-card-body">
                <div>Date: {order.plan_date}</div>
                <div>Mode: {order.plan_mode}</div>
                <div>Déficit total: {order.total_deficit_mw.toLocaleString('fr-FR')} MW</div>
                {order.shortfall_count > 0 && (
                  <div className="shortfall-indicator">⚠️ {order.shortfall_count} écart(s)</div>
                )}
                <div className="order-date-created">Créé le {new Date(order.created_at).toLocaleString('fr-FR')}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Confirmation & Warning Modal for Order Deletion */}
      {orderToDelete && (
        <div className="modal-backdrop" onClick={() => !deleteMutation.isPending && setOrderToDelete(null)}>
          <div className="modal-box delete-order-modal" onClick={(e) => e.stopPropagation()}>
            {orderToDelete.status === 'COMPLETED' ? (
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
                    <h3 className="modal-title">Supprimer l'ordre #{orderToDelete.id}</h3>
                    <p className="modal-subtitle">
                      Statut : <span className={`order-status-badge ${getStatusColor(orderToDelete.status)}`}>{orderToDelete.status}</span>
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
                    onClick={() => setOrderToDelete(null)}
                    disabled={deleteMutation.isPending}
                  >
                    Annuler
                  </button>
                  <button 
                    type="button" 
                    className="btn-confirm-delete" 
                    onClick={() => deleteMutation.mutate(orderToDelete.id)}
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
                      Ordre #{orderToDelete.id} — Statut : <span className={`order-status-badge ${getStatusColor(orderToDelete.status)}`}>{orderToDelete.status}</span>
                    </p>
                  </div>
                </div>

                <div className="modal-warning-box">
                  <strong>⚠️ Avertissement :</strong> Cet ordre de délestage <strong>n'est pas encore terminé</strong> (statut actuel : <strong>{orderToDelete.status}</strong>).
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
                    onClick={() => setOrderToDelete(null)}
                    disabled={deleteMutation.isPending}
                  >
                    Annuler
                  </button>
                  <button 
                    type="button" 
                    className="btn-confirm-delete btn-confirm-warning" 
                    onClick={() => deleteMutation.mutate(orderToDelete.id)}
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
