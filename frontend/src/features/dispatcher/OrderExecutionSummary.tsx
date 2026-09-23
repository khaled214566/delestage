import { useQuery } from '@tanstack/react-query';
import { getMonitoringSummary, type MonitoringSummary } from '../../api/client';

interface Props {
  orderId: number;
}

function alarmBadge(level: string) {
  switch (level) {
    case 'RED': return '🔴';
    case 'AMBER': return '🟠';
    default: return '🟢';
  }
}

function fmtDuration(minutes: number) {
  const m = Math.floor(minutes);
  const s = Math.round((minutes - m) * 60);
  return `${m}m${s.toString().padStart(2, '0')}s`;
}

export default function OrderExecutionSummary({ orderId }: Props) {
  const { data, isLoading, error } = useQuery<MonitoringSummary>({
    queryKey: ['monitoring-summary', orderId],
    queryFn: getMonitoringSummary,
    refetchInterval: 5000,
  });

  if (isLoading) return <div className="status loading">Chargement du suivi en temps réel...</div>;
  if (error || !data) return <div className="status error">❌ Impossible de charger le monitoring</div>;

  const activeEvents = data.active_events || [];

  return (
    <div className="execution-summary">
      <h3>📡 Suivi d'exécution en temps réel</h3>

      <div className="grid-stats">
        <div className="stat-card">
          <span className="stat-value">{data.target_mw.toLocaleString('fr-FR')}</span>
          <span className="stat-label">Cible (MW)</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.actual_mw.toLocaleString('fr-FR')}</span>
          <span className="stat-label">Réalisé (MW)</span>
        </div>
        <div className={`stat-card ${data.gap_mw > 0 ? 'stat-bad' : 'stat-good'}`}>
          <span className="stat-value">{data.gap_mw.toLocaleString('fr-FR')}</span>
          <span className="stat-label">Écart (MW)</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.open_feeders_count}</span>
          <span className="stat-label">Départs ouverts</span>
        </div>
      </div>

      {(data.amber_alarms_count > 0 || data.red_alarms_count > 0) && (
        <div className="alarm-counters">
          {data.amber_alarms_count > 0 && (
            <span className="alarm-badge amber">⚠️ {data.amber_alarms_count} alarme(s) AMBER</span>
          )}
          {data.red_alarms_count > 0 && (
            <span className="alarm-badge red">🔴 {data.red_alarms_count} alarme(s) RED</span>
          )}
        </div>
      )}

      {activeEvents.length > 0 && (
        <div className="active-events-section">
          <h4>Départs actuellement coupés</h4>
          <div className="allocation-tree">
            <div className="tree-header">
              <div className="cell-entity">Départ</div>
              <div className="cell-target">BCC</div>
              <div className="cell-achieved">MW</div>
              <div className="cell-shortfall">Durée</div>
              <div className="cell-status">Alarme</div>
            </div>
            <div className="tree-body">
              {activeEvents.map(evt => (
                <div key={evt.id} className="tree-row level-feeder">
                  <div className="cell-entity">
                    <span className="entity-name">{evt.feeder_name}</span>
                  </div>
                  <div className="cell-target">{evt.bcc_id}</div>
                  <div className="cell-achieved">{evt.mw_actual.toLocaleString('fr-FR')}</div>
                  <div className="cell-shortfall">{fmtDuration(evt.duration_min)}</div>
                  <div className="cell-status">
                    <span>{alarmBadge(evt.alarm_level)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeEvents.length === 0 && (
        <div className="empty-state info" style={{ marginTop: '12px' }}>
          Aucun départ actuellement coupé. Les opérateurs BCC peuvent démarrer les manœuvres.
        </div>
      )}

      <div className="execution-totals" style={{ marginTop: '12px', fontSize: '0.9em', color: '#888' }}>
        ENS totale : {data.total_ens_mwh.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} MWh
        &nbsp;·&nbsp;
        Durée max : {fmtDuration(data.max_duration_min)}
        &nbsp;·&nbsp;
        BCC actifs : {data.active_bccs_count}
      </div>
    </div>
  );
}
