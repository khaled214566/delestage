import { useState, useEffect, useCallback, useMemo } from 'react';
import { getCitizenStatus, type CitizenStatusResponse, type CitizenZone } from '../api/client';
import { Link } from 'react-router-dom';
import CitizenMap from '../components/CitizenMap';

type FilterType = 'ALL' | 'SHEDDING' | 'NORMAL' | 'NORD' | 'SUD';

function normalizeText(str: string): string {
  return (str || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

export default function CitizenPage() {
  const [data, setData] = useState<CitizenStatusResponse | null>(null);
  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState<FilterType>('ALL');
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

  const filteredZones = useMemo(() => {
    if (!data?.zones) return [];

    const query = normalizeText(search);

    return data.zones.filter((z: CitizenZone) => {
      // 1. Status and Region Filter
      if (activeFilter === 'SHEDDING' && z.status !== 'SHEDDING') return false;
      if (activeFilter === 'NORMAL' && z.status !== 'NORMAL') return false;
      if (activeFilter === 'NORD' && normalizeText(z.region || '') !== 'nord') return false;
      if (activeFilter === 'SUD' && normalizeText(z.region || '') !== 'sud') return false;

      // 2. Search Text Query (fuzzy across all fields)
      if (!query) return true;

      const searchableString = normalizeText(
        `${z.zone_id} ${z.display_name} ${z.region || ''} ${z.governorates || ''} ${
          z.status === 'SHEDDING' ? 'coupure delestage panne arret' : 'normal alimente stable sous tension'
        }`
      );

      // Check if all tokens in search query are found in searchableString
      const tokens = query.split(/\s+/).filter(Boolean);
      return tokens.every(token => searchableString.includes(token));
    });
  }, [data, search, activeFilter]);

  const sheddingCount = data?.zones.filter(z => z.status === 'SHEDDING').length ?? 0;
  const normalCount = data?.zones.filter(z => z.status === 'NORMAL').length ?? 0;

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
          <span className={`hero-stat-val ${sheddingCount > 0 ? 'text-amber' : 'text-green'}`}>
            {loading ? '…' : sheddingCount > 0 ? 'Délestage en cours' : 'Réseau Normal'}
          </span>
          <span className="hero-stat-sub">
            {sheddingCount} zone(s) activement délestée(s)
          </span>
        </div>

        <div className="hero-stat-card">
          <span className="hero-stat-label">Centres Surveillés</span>
          <span className="hero-stat-val text-blue">{data?.total_zones ?? 7}</span>
          <span className="hero-stat-sub">Couverture intégrale des 24 gouvernorats</span>
        </div>

        <div className="hero-stat-card">
          <span className="hero-stat-label">Dernière Mise à Jour</span>
          <span className="hero-stat-val text-dark">{lastRefreshed || '…'}</span>
          <span className="hero-stat-sub">Actualisation automatique toutes les 10s</span>
        </div>
      </div>

      {/* Enhanced Search and Filter Bar */}
      <div className="citizen-search-section">
        <div className="citizen-search-bar">
          <div className="search-input-wrapper">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              placeholder="Rechercher votre ville ou gouvernorat (ex: Tunis, Nabeul, Sousse, Sfax, Ariana...)"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button
                className="btn-clear-search"
                onClick={() => setSearch('')}
                title="Effacer la recherche"
              >
                ✖
              </button>
            )}
          </div>
          <button onClick={load} className="btn-refresh" title="Actualiser les données immédiatement">
            🔄 Actualiser
          </button>
        </div>

        {/* Quick Filter Chips */}
        <div className="citizen-filter-chips">
          <button
            className={`chip ${activeFilter === 'ALL' ? 'chip-active' : ''}`}
            onClick={() => setActiveFilter('ALL')}
          >
            Tous ({data?.zones.length ?? 7})
          </button>
          <button
            className={`chip chip-shedding ${activeFilter === 'SHEDDING' ? 'chip-active' : ''}`}
            onClick={() => setActiveFilter('SHEDDING')}
          >
            ⚡ En coupure ({sheddingCount})
          </button>
          <button
            className={`chip chip-normal ${activeFilter === 'NORMAL' ? 'chip-active' : ''}`}
            onClick={() => setActiveFilter('NORMAL')}
          >
            ✅ Normal ({normalCount})
          </button>
          <button
            className={`chip ${activeFilter === 'NORD' ? 'chip-active' : ''}`}
            onClick={() => setActiveFilter('NORD')}
          >
            Nord (4)
          </button>
          <button
            className={`chip ${activeFilter === 'SUD' ? 'chip-active' : ''}`}
            onClick={() => setActiveFilter('SUD')}
          >
            Sud (3)
          </button>
        </div>
      </div>

      {/* Network Map */}
      <div className="citizen-map-section">
        <h2 className="citizen-section-title">Carte du réseau</h2>
        <CitizenMap zones={data?.zones ?? []} />
      </div>

      {/* Zones Grid */}
      <div className="citizen-zones-grid">
        {filteredZones.length === 0 ? (
          <div className="search-empty-card">
            <div className="empty-icon">🔎</div>
            <h3>Aucun centre trouvé pour « {search} »</h3>
            <p>Vérifiez l'orthographe ou essayez un nom de ville voisin (ex: Tunis, Sfax, Bizerte, Nabeul, Gabès...).</p>
            <button
              className="btn-reset-search"
              onClick={() => {
                setSearch('');
                setActiveFilter('ALL');
              }}
            >
              🔄 Réinitialiser la recherche
            </button>
          </div>
        ) : (
          filteredZones.map(zone => {
            const isShedding = zone.status === 'SHEDDING';
            return (
              <div key={zone.zone_id} className={`zone-card ${isShedding ? 'zone-shedding' : 'zone-normal'}`}>
                <div className="zone-card-header">
                  <div>
                    <h3>{zone.display_name}</h3>
                    <span className="zone-code">{zone.zone_id} · Région {zone.region || 'National'}</span>
                  </div>
                  <span className={`status-pill ${isShedding ? 'pill-shedding' : 'pill-normal'}`}>
                    {isShedding ? '⚡ Coupure Temporaire' : '✅ Alimentation Normale'}
                  </span>
                </div>

                <div className="governorates-tag">
                  📍 <strong>Gouvernorats :</strong> {zone.governorates || 'Secteur régional'}
                </div>

                {isShedding ? (
                  <div className="zone-details">
                    <div className="zone-metric">
                      <span className="metric-label">Départs concernés :</span>
                      <span className="metric-value font-bold">{zone.feeders_affected} ligne(s) MT</span>
                    </div>
                    {zone.events.map((ev, idx) => (
                      <div key={idx} className="event-info-box">
                        <div>
                          <strong>Début coupure :</strong> {ev.started_at ? new Date(ev.started_at).toLocaleTimeString('fr-FR') : 'N/A'}
                        </div>
                        <div>
                          <strong>Rétablissement estimé :</strong> {ev.estimated_end ? new Date(ev.estimated_end).toLocaleTimeString('fr-FR') : 'Sous 45 min'}
                        </div>
                        <div className="duration-tag">
                          ⏱ Durée écoulée : {ev.duration_min} min (Plafond réglementaire : 45 min)
                        </div>
                      </div>
                    ))}
                    <p className="zone-note">
                      🛡️ <em>Les services vitaux (hôpitaux, santé, stations d'eau potable) sont sous protection prioritaire stricte.</em>
                    </p>
                  </div>
                ) : (
                  <div className="zone-details">
                    <p className="text-muted">Aucun délestage n'est en cours ni programmé sur ce secteur.</p>
                    <span className="security-tag">🛡️ Tension normale et stable</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <footer className="citizen-footer">
        <p>Société Tunisienne de l'Électricité et du Gaz (STEG) — Plateforme Nationale de Gestion Intelligente des Délestages Tournants</p>
        <p className="footer-sub">Conformité stricte aux règles de rotation de 45 minutes et de protection des infrastructures de santé publique.</p>
      </footer>
    </div>
  );
}
