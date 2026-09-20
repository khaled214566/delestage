import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listOrders, createOrder, listPlans } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export default function OrdersPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<number | ''>('');

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

  const validatedPlansWithoutOrders = plans.filter(
    (p) => p.status === 'VALIDATED' && !orders.some((o) => o.plan_id === p.id)
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
                <h3>Ordre #{order.id}</h3>
                <span className={`order-status-badge ${getStatusColor(order.status)}`}>
                  {order.status}
                </span>
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
    </div>
  );
}
