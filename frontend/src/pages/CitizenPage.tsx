import { useState, useEffect, useCallback } from 'react';
import { getCitizenStatus, type CitizenStatusResponse } from '../api/client';
import { Link } from 'react-router-dom';

export default function CitizenPage() {
  const [data, setData] = useState<CitizenStatusResponse | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<string>('');

  const load = useCallback(async () => {
    try {
      const res = await getCitizenStatus();
      setData(res);
      setLastRefreshed(new Date().toLocaleTimeString('fr-FR'));
    } catch (err) {
      console.error('Erreur chargement portail citoyen:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [load]);

  const filteredZones = data?.zones.filter(z =>
    z.display_name.toLowerCase().includes(search.toLowerCase()) ||
    z.zone_id.toLowerCase().includes(search.toLowerCase())
  ) ?? [];

  return (
    <div className="citizen-portal">
      <header className="citizen-header">
        <div className="citizen-brand">
          <span className="brand-logo">⚡ STEG</span>
          <div>
            <h1>Portail d'Information Citoyen</h1>
            <p className="subtitle">État du réseau électrique &amp; Transparence des délestages tournants</p>
          </div>
        </div>
        <div className="citizen-actions">
          <span className="live-badge">● Direct</span>
          <Link to="/login" className="btn-operator-login">Accès Opérateur</Link>
        </div>
      </header>

      <div className="citizen-hero">
        <div className="hero-stat-card">
          <span className="hero-stat-label">Statut National</span>
          <span className={`hero-stat-val ${data && data.currently_shedding > 0 ? 'text-amber' : 'text-green'}`}>
            {loading ? '…' : data && data.currently_shedding > 0 ? 'Délestage en cours' : 'Réseau Normal'}
          </span>
          <span className="hero-stat-sub">
            {data?.currently_shedding ?? 0} zone(s) activement délestée(s)
          </span>
        </div>

        <div className="hero-stat-card">
          <span className="hero-stat-label">Zones Surveillées</span>
          <span className="hero-stat-val text-blue">{data?.total_zones ?? 7}</span>
          <span className="hero-stat-sub">Couverture nationale Nord &amp; Sud</span>
        </div>

        <div className="hero-stat-card">
          <span className="hero-stat-label">Dernière Mise à Jour</span>
          <span className="hero-stat-val text-dark">{lastRefreshed || '…'}</span>
          <span className="hero-stat-sub">Actualisation auto (10s)</span>
        </div>
      </div>

      <div className="citizen-search-bar">
        <input
          type="text"
          placeholder="🔍 Rechercher votre zone (ex: BCC1, Zone Tunis, Sousse...)"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <button onClick={load} className="btn-refresh" title="Rafraîchir">🔄 Actualiser</button>
      </div>

      <div className="citizen-zones-grid">
        {filteredZones.map(zone => {
          const isShedding = zone.status === 'SHEDDING';
          return (
            <div key={zone.zone_id} className={`zone-card ${isShedding ? 'zone-shedding' : 'zone-normal'}`}>
              <div className="zone-card-header">
                <h3>{zone.display_name}</h3>
                <span className={`status-pill ${isShedding ? 'pill-shedding' : 'pill-normal'}`}>
                  {isShedding ? '⚡ Coupure Temporaire' : '✅ Alimentation Normale'}
                </span>
              </div>

              {isShedding ? (
                <div className="zone-details">
                  <div className="zone-metric">
                    <span className="metric-label">Lignes en coupure :</span>
                    <span className="metric-value font-bold">{zone.feeders_affected} départ(s)</span>
                  </div>
                  {zone.events.map((ev, idx) => (
                    <div key={idx} className="event-info-box">
                      <div>
                        <strong>Début :</strong> {ev.started_at ? new Date(ev.started_at).toLocaleTimeString('fr-FR') : 'N/A'}
                      </div>
                      <div>
                        <strong>Fin estimée :</strong> {ev.estimated_end ? new Date(ev.estimated_end).toLocaleTimeString('fr-FR') : 'Sous 45 min'}
                      </div>
                      <div className="duration-tag">
                        Durée en cours : {ev.duration_min} min (Max autorisé : 45 min)
                      </div>
                    </div>
                  ))}
                  <p className="zone-note">
                    ℹ️ Les infrastructures sensibles (hôpitaux, stations d'eau) restent protégées en permanence.
                  </p>
                </div>
              ) : (
                <div className="zone-details">
                  <p className="text-muted">Aucune coupure planifiée ni en cours dans cette région.</p>
                  <span className="security-tag">🛡️ Réseau sous tension stable</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <footer className="citizen-footer">
        <p>Société Tunisienne de l'Électricité et du Gaz (STEG) — Plateforme Nationale de Gestion Intelligente des Délestages Tournants</p>
        <p className="footer-sub">Conforme aux règles d'équité territoriale et de protection prioritaire des services vitaux.</p>
      </footer>
    </div>
  );
}
