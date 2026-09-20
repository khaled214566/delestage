import { useEffect, useState } from 'react';
import type { ShedEventOut } from '../../api/client';

interface FeederStatusTableProps {
  events: ShedEventOut[];
  onToggleRestore: (feederId: string) => void;
}

export default function FeederStatusTable({ events, onToggleRestore }: FeederStatusTableProps) {
  // Local timer tick every second for smooth timer display
  const [, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatElapsed = (openTimeStr: string) => {
    const start = new Date(openTimeStr).getTime();
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - start) / 1000));
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    return `${mins}m ${secs < 10 ? '0' : ''}${secs}s`;
  };

  const getAlarmBadge = (alarmLevel: string) => {
    switch (alarmLevel) {
      case 'RED':
        return <span className="alarm-badge badge-red">🚨 CRITIQUE (&gt;45m)</span>;
      case 'AMBER':
        return <span className="alarm-badge badge-amber">⚠️ ROTATION (&gt;36m)</span>;
      default:
        return <span className="alarm-badge badge-green">NORMAL (&lt;36m)</span>;
    }
  };

  if (events.length === 0) {
    return (
      <div className="empty-events-banner">
        Aucun départ actuellement coupé. Le réseau est à l'équilibre nominal.
      </div>
    );
  }

  return (
    <div className="feeder-status-container">
      <table className="feeder-status-table">
        <thead>
          <tr>
            <th>Départ</th>
            <th>BCC</th>
            <th>MW Coupés</th>
            <th>Début coupure</th>
            <th>Durée écoulée</th>
            <th>Statut Alarme</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {events.map(ev => (
            <tr key={ev.id} className={`feeder-row alarm-${ev.alarm_level.toLowerCase()}`}>
              <td className="feeder-name">
                <strong>{ev.feeder_name}</strong>
                <span className="feeder-code">({ev.feeder_id})</span>
              </td>
              <td><span className="bcc-tag">{ev.bcc_id}</span></td>
              <td className="feeder-mw">{ev.mw_actual.toFixed(1)} MW</td>
              <td>{new Date(ev.open_time).toLocaleTimeString('fr-FR')}</td>
              <td className="elapsed-timer">{formatElapsed(ev.open_time)}</td>
              <td>{getAlarmBadge(ev.alarm_level)}</td>
              <td>
                <button
                  className="btn-small btn-ghost"
                  onClick={() => onToggleRestore(ev.feeder_id)}
                  title="Simuler le rétablissement de ce départ"
                >
                  Rétablir
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
