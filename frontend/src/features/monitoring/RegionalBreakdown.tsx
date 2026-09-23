import type { RegionalSummary } from '../../api/client';

interface RegionalBreakdownProps {
  crcs: RegionalSummary[];
  bccs: RegionalSummary[];
}

export default function RegionalBreakdown({ crcs, bccs }: RegionalBreakdownProps) {
  const getProgressPct = (actual: number, target: number) => {
    if (target <= 0) return actual > 0 ? 100 : 0;
    return Math.min(100, Math.round((actual / target) * 100));
  };

  return (
    <div className="regional-breakdown-container">
      <div className="crc-section">
        <h3>Répartition par CRC (Centres Régionaux de Conduite)</h3>
        <div className="crc-cards-grid">
          {crcs.map(c => {
            const pct = getProgressPct(c.actual_mw, c.target_mw);
            return (
              <div key={c.entity_id} className="crc-card">
                <div className="crc-header">
                  <span className="crc-name">{c.name}</span>
                  <span className="crc-ratio">
                    <strong>{c.actual_mw.toFixed(1)}</strong> / {c.target_mw.toFixed(1)} MW
                  </span>
                </div>
                <div className="progress-bar-track">
                  <div
                    className={`progress-bar-fill ${pct >= 90 && pct <= 110 ? 'fill-ok' : 'fill-warning'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="crc-footer">
                  <span>Écart: {c.gap_mw > 0 ? `+${c.gap_mw.toFixed(1)}` : c.gap_mw.toFixed(1)} MW</span>
                  <span>{c.open_feeders} départs ouverts</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="bcc-section">
        <h3>Répartition par BCC (7 Régions STEG)</h3>
        <div className="bcc-grid">
          {bccs.map(b => {
            const pct = getProgressPct(b.actual_mw, b.target_mw);
            return (
              <div key={b.entity_id} className="bcc-mini-card">
                <div className="bcc-header">
                  <span className="bcc-title">{b.name}</span>
                  <span className="bcc-values">
                    {b.actual_mw.toFixed(1)} / {b.target_mw.toFixed(1)} MW
                  </span>
                </div>
                <div className="progress-bar-track-small">
                  <div
                    className={`progress-bar-fill ${pct >= 90 ? 'fill-ok' : 'fill-warning'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="bcc-subtext">
                  {b.open_feeders} départs ({pct}%)
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
