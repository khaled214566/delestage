import { useState, useMemo, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { addFeederOverride, removeFeederOverride, type AllocationNode, type DeficitSlot } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';

interface AllocationTreeProps {
  nodes: AllocationNode[];
  slots?: DeficitSlot[];
  orderId: number;
  orderStatus: string;
}

interface MapZoneFeature {
  properties?: {
    id?: string;
    bcc_id?: string;
    name?: string;
  };
}

interface ZoneInfo {
  id: string;
  name: string;
}

interface CitizenStatusPayload {
  shedding_zone_ids?: string[];
}

function slotLabel(slot: DeficitSlot | { slot_start: string; slot_end: string }) {
  const opts: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' };
  const start = new Date(slot.slot_start).toLocaleTimeString('fr-FR', opts);
  const end = new Date(slot.slot_end).toLocaleTimeString('fr-FR', opts);
  return `${start}–${end}`;
}

const BCC_DISTRICT_NAMES: Record<string, string> = {
  BCC1: 'BCC1 — Tunis & Grand Tunis',
  BCC2: 'BCC2 — Nabeul & Cap Bon',
  BCC3: 'BCC3 — Sousse & Sahel',
  BCC4: 'BCC4 — Bizerte & Nord-Ouest',
  BCC5: 'BCC5 — Sfax & Centre-Sud',
  BCC6: 'BCC6 — Gabès & Sud-Est',
  BCC7: 'BCC7 — Gafsa & Sud-Ouest',
  CRC_N: 'CRC Nord (Nord & Sahel)',
  CRC_S: 'CRC Sud (Sud & Centre)',
};

export default function AllocationTree({ nodes, slots = [], orderId, orderStatus }: AllocationTreeProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [allExpanded, setAllExpanded] = useState(false);
  const [zonesByBcc, setZonesByBcc] = useState<Record<string, ZoneInfo[]>>({});
  const [liveSheddingZones, setLiveSheddingZones] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/data/tunisia_zones.geojson').then((response) => response.json() as Promise<{ features?: MapZoneFeature[] }>),
      fetch('/api/public/status').then((response) => response.json() as Promise<CitizenStatusPayload>),
    ])
      .then(([geojson, citizenStatus]) => {
        if (cancelled) return;
        const grouped: Record<string, ZoneInfo[]> = {};
        for (const feature of geojson.features || []) {
          const bccId = feature.properties?.bcc_id;
          const zoneId = feature.properties?.id;
          const zoneName = feature.properties?.name;
          if (!bccId || !zoneId || !zoneName) continue;
          (grouped[bccId] ||= []).push({ id: zoneId, name: zoneName });
        }
        for (const zones of Object.values(grouped)) zones.sort((left, right) => left.name.localeCompare(right.name, 'fr'));
        setZonesByBcc(grouped);
        setLiveSheddingZones(new Set((citizenStatus.shedding_zone_ids || []).map((zoneId) => zoneId.toUpperCase())));
      })
      .catch(() => {
        if (!cancelled) setZonesByBcc({});
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const addOverride = useMutation({
    mutationFn: ({ nodeId, feederId }: { nodeId: number; feederId: string }) => addFeederOverride(orderId, nodeId, feederId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  const removeOverride = useMutation({
    mutationFn: (assignmentId: number) => removeFeederOverride(orderId, assignmentId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['order', orderId] }),
  });

  // Map each national root node to its deficit slot
  const slotTabs = useMemo(() => {
    return nodes.map((node, index) => {
      const matchedSlot = slots.find((s) => s.id === node.slot_id);
      const label = matchedSlot ? slotLabel(matchedSlot) : `Créneau #${index + 1}`;
      return {
        nodeId: node.id,
        slotId: node.slot_id,
        slot: matchedSlot,
        nationalNode: node,
        label,
      };
    });
  }, [nodes, slots]);

  const currentTab = slotTabs[activeTabIndex] || slotTabs[0];
  const activeNode = currentTab?.nationalNode;
  const activeSlot = currentTab?.slot;

  // Open down to BCC level by default on tab switch
  useEffect(() => {
    if (!activeNode) return;
    const defaultExp: Record<number, boolean> = { [activeNode.id]: true };
    for (const crc of activeNode.children || []) {
      defaultExp[crc.id] = true;
    }
    setExpanded(defaultExp);
    setAllExpanded(false);
  }, [activeNode?.id]);

  const toggleExpand = (id: number) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleAll = () => {
    if (!activeNode) return;
    if (allExpanded) {
      // Collapse back to just National
      setExpanded({ [activeNode.id]: true });
      setAllExpanded(false);
    } else {
      // Expand National, CRC, and BCC
      const all: Record<number, boolean> = { [activeNode.id]: true };
      for (const crc of activeNode.children || []) {
        all[crc.id] = true;
        for (const bcc of crc.children || []) {
          all[bcc.id] = true;
        }
      }
      setExpanded(all);
      setAllExpanded(true);
    }
  };

  const getProgressPct = (achieved: number, target: number) => {
    if (target <= 0) return achieved > 0 ? 100 : 0;
    return Math.min(100, Math.round((achieved / target) * 100));
  };

  const renderStatusPill = (shortfall: number, target: number) => {
    if (shortfall <= 0.01) {
      return <span className="status-pill status-pill-ok">✓ Atteint</span>;
    }
    if (shortfall >= target * 0.5) {
      return <span className="status-pill status-pill-critical">⚠️ Critique</span>;
    }
    return <span className="status-pill status-pill-partial">⏳ Partiel</span>;
  };

  const renderLevelBadge = (level: string) => {
    switch (level) {
      case 'NATIONAL':
        return <span className="level-badge level-badge-national">NAT</span>;
      case 'CRC':
        return <span className="level-badge level-badge-crc">CRC</span>;
      case 'BCC':
        return <span className="level-badge level-badge-bcc">BCC</span>;
      default:
        return <span className="level-badge level-badge-feeder">{level}</span>;
    }
  };

  const renderBccZones = (node: AllocationNode, indent: number) => {
    if (node.level !== 'BCC') return null;

    const assignedZones = new Map<string, number>();
    for (const assignment of node.feeder_assignments || []) {
      const zoneName = (assignment.feeder_name || assignment.feeder_id).replace(/^Départ\s+/, '').trim();
      assignedZones.set(zoneName, (assignedZones.get(zoneName) || 0) + assignment.assigned_mw);
    }

    const zones = zonesByBcc[node.entity_id] || [...assignedZones.keys()]
      .sort((left, right) => left.localeCompare(right, 'fr'))
      .map((name) => ({ id: name, name }));
    if (!zones.length) {
      return (
        <div className="tree-zones-summary" style={{ marginLeft: `${(indent + 1) * 22}px` }}>
          <div className="tree-zones-title">Zones sous ce BCC</div>
          <div className="tree-zones-empty">Chargement des zones administratives...</div>
        </div>
      );
    }

    return (
      <div className="tree-zones-summary" style={{ marginLeft: `${(indent + 1) * 22}px` }}>
        <div className="tree-zones-title">Zones sous ce BCC ({zones.length})</div>
        <div className="tree-zones-list">
          {zones.map((zone) => {
            const isLiveShedding = liveSheddingZones.has(zone.id.toUpperCase());
            const isPlanned = assignedZones.has(zone.name);
            const statusLabel = isLiveShedding ? 'Coupure en cours' : isPlanned ? 'Délestage planifié' : 'Alimentée';
            return (
            <span
              key={zone.id}
              className={`tree-zone-chip ${isLiveShedding ? 'tree-zone-live-shedding' : isPlanned ? 'tree-zone-assigned' : 'tree-zone-normal'}`}
              title={isLiveShedding ? 'Coupure électrique en cours' : isPlanned ? 'Prévue dans cet ordre, mais pas nécessairement coupée actuellement' : 'Aucun événement de coupure en cours'}
            >
              {zone.name} · {statusLabel}
              {isPlanned ? ` · ${assignedZones.get(zone.name)!.toLocaleString('fr-FR')} MW` : ''}
            </span>
            );
          })}
        </div>
      </div>
    );
  };

  if (!nodes || nodes.length === 0) {
    return <div className="info">Aucun nœud d'allocation disponible. Lancez l'allocation pour cet ordre.</div>;
  }

  const renderNode = (node: AllocationNode, indent: number) => {
    const isExpanded = !!expanded[node.id];
    const hasChildren = (node.children?.length > 0) || (node.feeder_assignments?.length > 0);
    const canExpand = hasChildren || node.level === 'BCC';
    const pct = getProgressPct(node.achieved_mw, node.target_mw);

    return (
      <div key={`node-${node.id}`} className="tree-node-group">
        <div className={`tree-row level-${node.level.toLowerCase()}`}>
          <div className="cell-entity" style={{ paddingLeft: `${indent * 22}px` }}>
            {canExpand ? (
              <button 
                type="button" 
                className="tree-toggle" 
                onClick={() => toggleExpand(node.id)}
                title={isExpanded ? 'Replier' : 'Déplier'}
              >
                {isExpanded ? '▼' : '▶'}
              </button>
            ) : (
              <span className="tree-toggle-spacer" />
            )}

            {renderLevelBadge(node.level)}

            <span className="entity-name">{BCC_DISTRICT_NAMES[node.entity_id] || node.entity_id}</span>

            {orderStatus === 'ALLOCATED' && user?.role === 'DISPATCHER' && node.level === 'BCC' && (
              <button 
                type="button"
                className="btn-add-feeder" 
                title="Ajouter manuellement un départ"
                onClick={() => {
                  const fId = prompt('ID du départ à ajouter (ex: F_TUNIS_10) ?');
                  if (fId) addOverride.mutate({ nodeId: node.id, feederId: fId.trim() });
                }}
              >
                + Départ
              </button>
            )}
          </div>

          <div className="cell-target">{node.target_mw.toLocaleString('fr-FR')} MW</div>
          <div className="cell-achieved">{node.achieved_mw.toLocaleString('fr-FR')} MW</div>

          <div className="cell-progress">
            <div className="progress-cell">
              <div className="progress-pct-label">{pct}%</div>
              <div className="progress-mini-track">
                <div 
                  className={`progress-mini-fill ${pct >= 100 ? 'fill-success' : 'fill-warning'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>

          <div className="cell-shortfall">
            {node.shortfall_mw > 0 ? (
              <span style={{ color: '#c53030', fontWeight: 600 }}>{node.shortfall_mw.toLocaleString('fr-FR')} MW</span>
            ) : (
              '0 MW'
            )}
          </div>

          <div className="cell-status">
            {renderStatusPill(node.shortfall_mw, node.target_mw)}
          </div>
        </div>

        {isExpanded && (
          <div className="tree-children">
            {node.children?.map((child) => renderNode(child, indent + 1))}
            {renderBccZones(node, indent)}
            {node.feeder_assignments?.map((fa) => (
              <div key={`fa-${fa.id}`} className="tree-row level-feeder">
                <div className="cell-entity" style={{ paddingLeft: `${(indent + 1) * 22}px` }}>
                  <span className="tree-toggle-spacer" />
                  <span className="level-badge level-badge-feeder">DÉPART</span>
                  <span className="entity-name">{fa.feeder_name || fa.feeder_id}</span>
                  <span className="priority-badge">{fa.priority}</span>
                  {fa.is_manual && <span className="manual-badge">Manuel</span>}
                  {orderStatus === 'ALLOCATED' && user?.role === 'DISPATCHER' && fa.is_manual && (
                    <button 
                      type="button"
                      className="btn-remove-override" 
                      title="Supprimer l'override manuel"
                      onClick={() => removeOverride.mutate(fa.id)}
                    >
                      ✕
                    </button>
                  )}
                </div>
                <div className="cell-target">-</div>
                <div className="cell-achieved">{fa.assigned_mw.toLocaleString('fr-FR')} MW</div>
                <div className="cell-progress">
                  <span className="priority-badge">{fa.priority}</span>
                </div>
                <div className="cell-shortfall">-</div>
                <div className="cell-status">
                  <span className="status-pill status-pill-ok">✓ Assigné</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="allocation-section">
      {/* ── Créneaux Tabs Bar ── */}
      {slotTabs.length > 1 && (
        <div className="creneaux-tabs-bar">
          {slotTabs.map((tab, idx) => {
            const isSelected = idx === activeTabIndex;
            const deficitMw = tab.nationalNode.target_mw;
            const achievedMw = tab.nationalNode.achieved_mw;
            const isComplete = tab.nationalNode.shortfall_mw === 0 && achievedMw > 0;
            return (
              <button
                key={tab.nodeId}
                type="button"
                className={`creneau-tab-button ${isSelected ? 'active' : ''}`}
                onClick={() => setActiveTabIndex(idx)}
              >
                <span className="creneau-tab-time">⏱️ {tab.label}</span>
                <span className={`creneau-tab-badge ${isComplete ? 'badge-complete' : 'badge-deficit'}`}>
                  {deficitMw.toLocaleString('fr-FR')} MW
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Active Créneau Summary Banner (Style Calcul du Déficit) ── */}
      {activeSlot && activeNode && (
        <div className="creneau-summary-card">
          <div className="creneau-summary-header">
            <div className="creneau-summary-title">
              <span className="creneau-badge-time">⏱️ {currentTab.label}</span>
              <h4>Créneau & Calcul du Déficit</h4>
            </div>
            <div className="creneau-coverage-badge">
              Taux de couverture : <strong>{getProgressPct(activeNode.achieved_mw, activeNode.target_mw)}%</strong>
            </div>
          </div>

          <div className="creneau-metrics-grid">
            <div className="metric-pill">
              <span className="metric-label">Demande</span>
              <span className="metric-value">{activeSlot.demand_mw.toLocaleString('fr-FR')} MW</span>
            </div>
            <div className="metric-pill">
              <span className="metric-label">Production</span>
              <span className="metric-value">{activeSlot.generation_mw.toLocaleString('fr-FR')} MW</span>
            </div>
            <div className="metric-pill">
              <span className="metric-label">Imports</span>
              <span className="metric-value">{activeSlot.imports_mw.toLocaleString('fr-FR')} MW</span>
            </div>
            <div className="metric-pill">
              <span className="metric-label">Marge</span>
              <span className="metric-value">{activeSlot.margin_mw.toLocaleString('fr-FR')} MW</span>
            </div>
            <div className="metric-pill metric-pill-deficit">
              <span className="metric-label">Déficit P_déficit</span>
              <span className="metric-value deficit-val">{activeSlot.deficit_mw.toLocaleString('fr-FR')} MW</span>
            </div>
          </div>

          {(() => {
            const creneauCoveragePct = getProgressPct(activeNode.achieved_mw, activeNode.target_mw);
            return (
              <>
                <div className="creneau-progress-section">
                  <div className="progress-labels">
                    <span>Décrotage réalisé : <strong>{activeNode.achieved_mw.toLocaleString('fr-FR')} MW</strong></span>
                    <span>Cible de délestage : <strong>{activeNode.target_mw.toLocaleString('fr-FR')} MW</strong></span>
                  </div>
                  <div className="progress-track">
                    <div 
                      className={`progress-fill ${creneauCoveragePct >= 100 ? 'fill-success' : 'fill-warning'}`}
                      style={{ width: `${Math.min(100, creneauCoveragePct)}%` }}
                    />
                  </div>
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* ── Tree Toolbar ── */}
      <div className="tree-toolbar">
        <div className="tree-toolbar-info">
          <span className="tree-section-title">Répartition hiérarchique du délestage</span>
          <span className="tree-section-sub">National → CRC → BCC → Départs HTA/HTB</span>
        </div>
        <button 
          type="button" 
          className="btn-toggle-all"
          onClick={toggleAll}
        >
          {allExpanded ? '▲ Tout replier' : '▼ Tout déplier'}
        </button>
      </div>

      {/* ── Hierarchical Allocation Table ── */}
      <div className="allocation-tree">
        <div className="tree-header">
          <div className="cell-entity">Entité & Découpage</div>
          <div className="cell-target">Cible (MW)</div>
          <div className="cell-achieved">Réalisé (MW)</div>
          <div className="cell-progress">Progression</div>
          <div className="cell-shortfall">Écart (MW)</div>
          <div className="cell-status">Statut</div>
        </div>
        <div className="tree-body">
          {activeNode ? renderNode(activeNode, 0) : nodes.map((n) => renderNode(n, 0))}
        </div>
      </div>
    </div>
  );
}
