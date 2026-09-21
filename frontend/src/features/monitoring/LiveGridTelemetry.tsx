import { useState, useEffect, useMemo } from 'react';
import { getLiveTelemetry, type LiveTelemetryPoint } from '../../api/client';

interface LiveGridTelemetryProps {
  latestTick?: LiveTelemetryPoint | null;
}

export default function LiveGridTelemetry({ latestTick }: LiveGridTelemetryProps) {
  const [history, setHistory] = useState<LiveTelemetryPoint[]>([]);
  const [isPaused, setIsPaused] = useState(false);

  // Initial fetch: load 60s history so the sparkline renders immediately
  useEffect(() => {
    getLiveTelemetry()
      .then((snap) => {
        if (snap && Array.isArray(snap.history) && snap.history.length > 0) {
          setHistory(snap.history);
        }
      })
      .catch(() => {});
  }, []);

  // Sync new 1 Hz ticks from the parent's unified WebSocket
  useEffect(() => {
    if (!latestTick || isPaused) return;
    setHistory((prev) => {
      const base = prev.length > 0 ? prev : [latestTick];
      return [...base.slice(-59), latestTick];
    });
  }, [latestTick, isPaused]);

  const current = history[history.length - 1];

  const svgPath = useMemo(() => {
    if (history.length < 2) return '';
    const vals = history.map((h) => h.demand_mw ?? 0);
    const min = Math.min(...vals) - 5;
    const max = Math.max(...vals) + 5;
    const range = max - min || 1;
    const pts = history.map((h, i) => {
      const x = (i / (history.length - 1)) * 400;
      const y = 50 - (((h.demand_mw ?? 0) - min) / range) * 45;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return `M ${pts.join(' L ')}`;
  }, [history]);

  if (!current) return null;

  const demand = current.demand_mw ?? 0;
  const delta = current.delta_demand_mw ?? 0;
  const imports = current.imports_mw ?? 0;
  const deficit = current.deficit_mw ?? 0;
  const freq = current.frequency_hz ?? 50.0;

  return (
    <div
      className="live-telemetry-banner"
      style={{
        background: '#0f172a',
        borderRadius: '12px',
        padding: '16px',
        color: '#fff',
        marginBottom: '20px',
        border: '1px solid #1e293b',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: isPaused ? '#eab308' : '#22c55e',
              display: 'inline-block',
              boxShadow: isPaused ? 'none' : '0 0 8px #22c55e',
            }}
          />
          <strong style={{ fontSize: '0.95rem', letterSpacing: '0.02em' }}>📡 Télémétrie Réseau en Direct (1 Hz)</strong>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
            · Fréquence nominale 50.00 Hz (régulation primaire ±0.01 Hz)
          </span>
        </div>
        <button
          onClick={() => setIsPaused(!isPaused)}
          className="btn-small btn-ghost"
          style={{ color: '#94a3b8', borderColor: '#334155', padding: '2px 10px', fontSize: '0.8rem' }}
        >
          {isPaused ? '▶ Reprendre' : '⏸ Pause'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', marginBottom: '12px' }}>
        <div style={{ background: '#1e293b', padding: '8px 12px', borderRadius: '8px', borderLeft: '3px solid #38bdf8' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>Demande</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc' }}>
            {demand.toLocaleString('fr-FR')} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>MW</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: delta >= 0 ? '#f87171' : '#4ade80' }}>
            {delta >= 0 ? `▲ +${delta}` : `▼ ${delta}`} MW/s
          </div>
        </div>

        <div style={{ background: '#1e293b', padding: '8px 12px', borderRadius: '8px', borderLeft: '3px solid #818cf8' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>Imports Internat.</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc' }}>
            {imports.toLocaleString('fr-FR')} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>MW</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Interconnexions</div>
        </div>

        <div style={{ background: '#1e293b', padding: '8px 12px', borderRadius: '8px', borderLeft: `3px solid ${deficit > 0 ? '#f97316' : '#22c55e'}` }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>Déficit Instantané</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: deficit > 0 ? '#fb923c' : '#4ade80' }}>
            {deficit.toLocaleString('fr-FR')} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>MW</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: deficit > 0 ? '#fb923c' : '#4ade80' }}>
            {deficit > 0 ? 'Délestage requis' : 'Équilibre atteint'}
          </div>
        </div>

        <div style={{ background: '#1e293b', padding: '8px 12px', borderRadius: '8px', borderLeft: '3px solid #22c55e' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>Fréquence Réseau</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#4ade80', fontFamily: 'monospace' }}>
            {freq.toFixed(3)} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>Hz</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Stable (50.00 Hz)</div>
        </div>
      </div>

      <div style={{ background: '#0b1120', borderRadius: '6px', padding: '6px 8px', border: '1px solid #1e293b' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: '#64748b', marginBottom: '2px' }}>
          <span>Évolution de la demande nationale (dernières 60 secondes)</span>
          <span>{current.time_label ?? ''}</span>
        </div>
        <svg viewBox="0 0 400 55" style={{ width: '100%', height: '40px', overflow: 'visible' }}>
          <defs>
            <linearGradient id="gradDemand" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.0" />
            </linearGradient>
          </defs>
          {svgPath && (
            <>
              <path d={`${svgPath} L 400,55 L 0,55 Z`} fill="url(#gradDemand)" />
              <path d={svgPath} fill="none" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" />
            </>
          )}
        </svg>
      </div>
    </div>
  );
}
