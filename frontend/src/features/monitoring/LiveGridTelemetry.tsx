import { useState, useEffect, useMemo } from 'react';
import { getLiveTelemetry, setTelemetryScenario, type LiveTelemetryPoint } from '../../api/client';

interface LiveGridTelemetryProps {
  latestTick?: LiveTelemetryPoint | null;
}

export default function LiveGridTelemetry({ latestTick }: LiveGridTelemetryProps) {
  const [history, setHistory] = useState<LiveTelemetryPoint[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [activeScenario, setActiveScenario] = useState<string>('AUTO');

  // Initial fetch: load 60s history so the sparkline renders immediately
  useEffect(() => {
    getLiveTelemetry()
      .then((snap) => {
        if (snap && Array.isArray(snap.history) && snap.history.length > 0) {
          setHistory(snap.history);
          if (snap.scenario_mode) setActiveScenario(snap.scenario_mode);
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

  const handleScenarioChange = async (mode: string) => {
    setActiveScenario(mode);
    try {
      await setTelemetryScenario(mode);
    } catch (e) {
      console.error('Failed to change scenario', e);
    }
  };

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

  // Deficit badge styling
  let deficitBorder = '#22c55e';
  let deficitColor = '#4ade80';
  let deficitLabel = 'Équilibre atteint (0 MW)';
  if (deficit > 500) {
    deficitBorder = '#ef4444';
    deficitColor = '#f87171';
    deficitLabel = 'Pic de délestage critique';
  } else if (deficit > 0) {
    deficitBorder = '#f97316';
    deficitColor = '#fb923c';
    deficitLabel = 'Délestage requis';
  }

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
      {/* Top row: Status, current scenario & controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
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
          <span style={{ fontSize: '0.75rem', background: '#1e293b', padding: '2px 8px', borderRadius: '4px', color: '#38bdf8' }}>
            {current.scenario || 'Actif'}
          </span>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>· Fréquence ±0.01 Hz</span>
        </div>

        {/* Scenario selection buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Scénarios :</span>
          <button
            onClick={() => handleScenarioChange('AUTO')}
            className="btn-small"
            style={{
              padding: '2px 8px',
              fontSize: '0.75rem',
              background: activeScenario === 'AUTO' ? '#38bdf8' : '#1e293b',
              color: activeScenario === 'AUTO' ? '#0f172a' : '#94a3b8',
              border: '1px solid #334155',
              borderRadius: '4px',
              fontWeight: 600,
            }}
          >
            🔄 Cycle Auto (0 ↔ 800 MW)
          </button>
          <button
            onClick={() => handleScenarioChange('BALANCED')}
            className="btn-small"
            style={{
              padding: '2px 8px',
              fontSize: '0.75rem',
              background: activeScenario === 'BALANCED' ? '#22c55e' : '#1e293b',
              color: activeScenario === 'BALANCED' ? '#0f172a' : '#94a3b8',
              border: '1px solid #334155',
              borderRadius: '4px',
              fontWeight: 600,
            }}
          >
            🟢 0 MW (Équilibre)
          </button>
          <button
            onClick={() => handleScenarioChange('PEAK')}
            className="btn-small"
            style={{
              padding: '2px 8px',
              fontSize: '0.75rem',
              background: activeScenario === 'PEAK' ? '#ef4444' : '#1e293b',
              color: activeScenario === 'PEAK' ? '#fff' : '#94a3b8',
              border: '1px solid #334155',
              borderRadius: '4px',
              fontWeight: 600,
            }}
          >
            ⚡ ~800 MW (Pic)
          </button>
          <button
            onClick={() => setIsPaused(!isPaused)}
            className="btn-small btn-ghost"
            style={{ color: '#94a3b8', borderColor: '#334155', padding: '2px 8px', fontSize: '0.75rem' }}
          >
            {isPaused ? '▶ Reprendre' : '⏸ Pause'}
          </button>
        </div>
      </div>

      {/* 4 Metric Cards */}
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

        <div style={{ background: '#1e293b', padding: '8px 12px', borderRadius: '8px', borderLeft: `3px solid ${deficitBorder}` }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>Déficit Instantané</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: deficitColor }}>
            {deficit.toLocaleString('fr-FR')} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>MW</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: deficitColor }}>
            {deficitLabel}
          </div>
        </div>

        <div style={{ background: '#1e293b', padding: '8px 12px', borderRadius: '8px', borderLeft: '3px solid #22c55e' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'uppercase' }}>Fréquence Réseau</div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#4ade80', fontFamily: 'monospace' }}>
            {freq.toFixed(3)} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>Hz</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Régulée (50.00 Hz)</div>
        </div>
      </div>

      {/* SVG Sparkline */}
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
