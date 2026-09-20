import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { addFeederOverride, removeFeederOverride, type AllocationNode } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';

interface AllocationTreeProps {
  nodes: AllocationNode[];
  orderId: number;
  orderStatus: string;
}

export default function AllocationTree({ nodes, orderId, orderStatus }: AllocationTreeProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const addOverride = useMutation({
    mutationFn: ({ nodeId, feederId }: { nodeId: number; feederId: string }) => addFeederOverride(orderId, nodeId, feederId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const removeOverride = useMutation({
    mutationFn: (assignmentId: number) => removeFeederOverride(orderId, assignmentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const toggleExpand = (id: number) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const getStatusClass = (node: AllocationNode) => {
    if (node.shortfall_mw === 0) return 'status-ok';
    if (node.shortfall_mw >= node.target_mw * 0.5) return 'status-critical';
    return 'status-partial';
  };

  const renderNode = (node: AllocationNode, indent: number) => {
    const isExpanded = expanded[node.id];
    const hasChildren = node.children.length > 0 || node.feeder_assignments.length > 0;
    
    return (
      <div key={`node-${node.id}`} className="tree-node-group">
        <div className={`tree-row level-${node.level.toLowerCase()}`}>
          <div className="cell-entity" style={{ paddingLeft: `${indent * 20}px` }}>
            {hasChildren && (
              <button className="tree-toggle" onClick={() => toggleExpand(node.id)}>
                {isExpanded ? '▼' : '▶'}
              </button>
            )}
            {!hasChildren && <span className="tree-toggle-spacer" />}
            <span className="entity-name">{node.level} {node.entity_id}</span>
            {orderStatus === 'ALLOCATED' && user?.role === 'DISPATCHER' && node.level === 'BCC' && (
              <button 
                className="btn-small btn-ghost" 
                onClick={() => {
                  const fId = prompt('ID du départ à ajouter ?');
                  if (fId) addOverride.mutate({ nodeId: node.id, feederId: fId });
                }}
              >
                + Ajouter
              </button>
            )}
          </div>
          <div className="cell-target">{node.target_mw.toLocaleString('fr-FR')}</div>
          <div className="cell-achieved">{node.achieved_mw.toLocaleString('fr-FR')}</div>
          <div className="cell-shortfall">{node.shortfall_mw.toLocaleString('fr-FR')}</div>
          <div className="cell-status">
            <div className={`status-indicator ${getStatusClass(node)}`} />
          </div>
        </div>
        
        {isExpanded && (
          <div className="tree-children">
            {node.children.map(child => renderNode(child, indent + 1))}
            {node.feeder_assignments.map(fa => (
              <div key={`fa-${fa.id}`} className="tree-row level-feeder">
                <div className="cell-entity" style={{ paddingLeft: `${(indent + 1) * 20}px` }}>
                  <span className="tree-toggle-spacer" />
                  <span className="entity-name">Départ {fa.feeder_name || fa.feeder_id}</span>
                  <span className="priority-badge">{fa.priority}</span>
                  {fa.is_manual && <span className="manual-badge">Manuel</span>}
                  {orderStatus === 'ALLOCATED' && user?.role === 'DISPATCHER' && fa.is_manual && (
                    <button 
                      className="btn-small btn-ghost" 
                      onClick={() => removeOverride.mutate(fa.id)}
                    >
                      ✕
                    </button>
                  )}
                </div>
                <div className="cell-target">-</div>
                <div className="cell-achieved">{fa.assigned_mw.toLocaleString('fr-FR')}</div>
                <div className="cell-shortfall">-</div>
                <div className="cell-status">
                  <div className="status-indicator status-ok" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="allocation-tree">
      <div className="tree-header">
        <div className="cell-entity">Entité</div>
        <div className="cell-target">Cible (MW)</div>
        <div className="cell-achieved">Réalisé (MW)</div>
        <div className="cell-shortfall">Écart (MW)</div>
        <div className="cell-status">Statut</div>
      </div>
      <div className="tree-body">
        {nodes.map(node => renderNode(node, 0))}
      </div>
    </div>
  );
}
