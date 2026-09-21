import { useEffect, useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getMonitoringSummary, simulateToggle, type MonitoringSummary, type LiveTelemetryPoint } from '../../api/client';
import FeederStatusTable from './FeederStatusTable';
import RegionalBreakdown from './RegionalBreakdown';
import RotationPanel from '../execution/RotationPanel';
import LiveGridTelemetry from './LiveGridTelemetry';

export default function MonitoringDashboard() {
  const queryClient = useQueryClient();
  const [liveData, setLiveData] = useState<MonitoringSummary | null>(null);
  const [latestTick, setLatestTick] = useState<LiveTelemetryPoint | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [simFeederId, setSimFeederId] = useState('F-101');
  const wsRef = useRef<WebSocket | null>(null);

  // Initial fetch using React Query
  const { data: initialData, isLoading, error } = useQuery<MonitoringSummary>({
    queryKey: ['monitoringSummary'],
    queryFn: getMonitoringSummary,
    refetchInterval: wsConnected ? false : 3000, // Poll only if WebSocket disconnected
  });

  // Keep liveData synced with query or WebSocket
  const summary = liveData || initialData;

  // Setup WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/monitoring/ws`;

    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'MONITORING_SUMMARY' && msg.data) {
              setLiveData(msg.data);
            } else if (msg.type === 'LIVE_TELEMETRY_TICK' && msg.data) {
              setLatestTick(msg.data);
            } else if (!msg.type && msg.target_mw !== undefined) {
              setLiveData(msg as MonitoringSummary);
            }
          } catch (err) {
            console.error('Failed to parse monitoring telemetry message:', err);
          }
        };

        ws.onerror = () => {
          setWsConnected(false);
        };

        ws.onclose = () => {
          setWsConnected(false);
          // Try reconnecting after 3 seconds
          reconnectTimer = setTimeout(connect, 3000);
        };
      } catch (e) {
        console.warn('WebSocket connection attempt failed:', e);
        reconnectTimer = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const toggleMutation = useMutation({
    mutationFn: ({ feederId, openState }: { feederId: string; openState: boolean }) =>
      simulateToggle(feederId, openState),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitoringSummary'] });
    },
  });

  if (isLoading && !summary) {
    return <div className="status loading">Connexion au flux de monitoring...</div>;
  }

  if (error && !summary) {
    return <div className="status error">Impossible de charger les données de monitoring en direct.</div>;
  }

  if (!summary) return null;

  return (
    <div className="monitoring-dashboard">
      <div className="monitoring-topbar">
        <div>
          <h2>📡 Tableau de Bord de Conduite &amp; Télémesure en Temps Réel</h2>
          <p className="monitoring-subtitle">
            Supervision nationale des manœuvres de délestage STEG (UC4 - Monitor Status)
          </p>
        </div>
        <div className="telemetry-pill">
          {wsConnected ? (
            <span className="pill-live">● Flux WebSocket Actif</span>
          ) : (
            <span className="pill-polling">○ Mode Polling (HTTP 3s)</span>
          )}
        </div>
      </div>

      {/* High-frequency 1 Hz Live Grid Telemetry Strip */}
      <LiveGridTelemetry latestTick={latestTick} />

      {/* KPI Cards Row */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <span className="kpi-title">Puissance Requise</span>
          <span className="kpi-value highlight-blue">{(summary.target_mw ?? 0).toLocaleString('fr-FR')} MW</span>
          <span className="kpi-subtext">Ordre National actif</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-title">Puissance Réalisée</span>
          <span className="kpi-value highlight-green">{(summary.actual_mw ?? 0).toLocaleString('fr-FR')} MW</span>
          <span className="kpi-subtext">Coupure effective</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-title">Écart National</span>
          <span className={`kpi-value ${(summary.gap_mw ?? 0) > 0 ? 'highlight-orange' : 'highlight-green'}`}>
            {(summary.gap_mw ?? 0) > 0 ? `+${(summary.gap_mw ?? 0).toLocaleString('fr-FR')}` : (summary.gap_mw ?? 0).toLocaleString('fr-FR')} MW
          </span>
          <span className="kpi-subtext">Cible - Réalisé</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-title">Départs Déconnectés</span>
          <span className="kpi-value">{summary.open_feeders_count ?? 0}</span>
          <span className="kpi-subtext">sur {summary.active_bccs_count ?? 0} BCCs actifs</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-title">Durée Max. Coupure</span>
          <span className={`kpi-value ${(summary.max_duration_min ?? 0) >= 36 ? 'highlight-red' : ''}`}>
            {summary.max_duration_min ?? 0} min
          </span>
          <span className="kpi-subtext">Limite max: 45 min</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-title">Énergie Non Distribuée</span>
          <span className="kpi-value">{(summary.total_ens_mwh ?? 0).toLocaleString('fr-FR')} MWh</span>
          <span className="kpi-subtext">ENS cumulée totale</span>
        </div>

        <div className="kpi-card">
          <span className="kpi-title">Alarmes Actives</span>
          <div className="alarms-summary-pill">
            <span className="badge-amber">{summary.amber_alarms_count ?? 0} rot.</span>
            <span className="badge-red">{summary.red_alarms_count ?? 0} crit.</span>
          </div>
          <span className="kpi-subtext">Surveillance seuils</span>
        </div>
      </div>

      {/* Rotation Alerts (UC6) */}
      <RotationPanel />

      {/* Regional breakdown */}
      <RegionalBreakdown crcs={summary.crc_breakdown || []} bccs={summary.bcc_breakdown || []} />

      {/* Active feeders table */}
      <div className="active-feeders-section">
        <h3>Départs Actuellement Déconnectés ({(summary.active_events || []).length})</h3>
        <FeederStatusTable
          events={summary.active_events || []}
          onToggleRestore={(fId) => toggleMutation.mutate({ feederId: fId, openState: false })}
        />
      </div>

      {/* Live Simulation Console */}
      <div className="simulation-console">
        <h3>🕹️ Banc d'Essai &amp; Simulation de Télémesure (Démonstrateur)</h3>
        <p className="sim-help-text">
          Permet de simuler l'ouverture ou le rétablissement d'un disjoncteur sur le terrain pour observer la mise à jour
          immédiate des compteurs, du gap national et des alarmes via WebSocket.
        </p>
        <div className="sim-controls">
          <input
            type="text"
            className="sim-input"
            value={simFeederId}
            onChange={(e) => setSimFeederId(e.target.value)}
            placeholder="Ex: F-101"
          />
          <button
            className="btn-small btn-primary"
            onClick={() => toggleMutation.mutate({ feederId: simFeederId, openState: true })}
            disabled={toggleMutation.isPending}
          >
            ⚡ Simuler Ouverture (Coupure)
          </button>
          <button
            className="btn-small btn-ghost"
            onClick={() => toggleMutation.mutate({ feederId: simFeederId, openState: false })}
            disabled={toggleMutation.isPending}
          >
            🔌 Simuler Rétablissement
          </button>
          <div className="quick-sim-buttons">
            <span>Raccourcis démo :</span>
            {['F-101', 'F-125', 'F-144'].map((f) => (
              <button
                key={f}
                className="btn-small btn-link"
                onClick={() => {
                  setSimFeederId(f);
                  toggleMutation.mutate({ feederId: f, openState: true });
                }}
              >
                + Couper {f}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
