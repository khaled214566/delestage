import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  getCitizenHistory,
  getCitizenSchedule,
  getCitizenStatus,
  type CitizenHistoryResponse,
  type CitizenPlannedOutage,
  type CitizenStatusResponse,
} from '../api/client';
import CitizenMap from '../components/CitizenMap';
import { STATUS_META, type NetworkStatus } from '../config/mapConfig';
import '../styles/citizen.css';

// ── Formatting helpers ──────────────────────────────────────────────────────
const nf = (n: number) => n.toLocaleString('fr-FR');

const norm = (s: string) =>
  s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();

function hhmm(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return "Aujourd'hui";
  if (d.toDateString() === tomorrow.toDateString()) return 'Demain';
  return d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' });
}

function weekday(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('fr-FR', { weekday: 'short' });
}

export default function CitizenPage() {
  const [status, setStatus] = useState<CitizenStatusResponse | null>(null);
  const [statusAvailable, setStatusAvailable] = useState(true);
  const [schedule, setSchedule] = useState<CitizenPlannedOutage[]>([]);
  const [scheduleAvailable, setScheduleAvailable] = useState(true);
  const [history, setHistory] = useState<CitizenHistoryResponse | null>(null);
  const [historyAvailable, setHistoryAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState('');
  const [plannedQuery, setPlannedQuery] = useState('');

  const load = useCallback(async () => {
    const [s, sch, hist] = await Promise.allSettled([
      getCitizenStatus(),
      getCitizenSchedule(),
      getCitizenHistory(7),
    ]);

    if (s.status === 'fulfilled') {
      setStatus(s.value);
      setStatusAvailable(true);
      setLastRefreshed(new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }));
    } else {
      setStatusAvailable(false);
    }

    if (sch.status === 'fulfilled') {
      setSchedule(sch.value.outages);
      setScheduleAvailable(true);
    } else {
      setScheduleAvailable(false);
    }

    if (hist.status === 'fulfilled') {
      setHistory(hist.value);
      setHistoryAvailable(true);
    } else {
      setHistoryAvailable(false);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 20000);
    return () => window.clearInterval(timer);
  }, [load]);

  const zones = useMemo(() => status?.zones ?? [], [status]);
  const sheddingCount = zones.filter(z => z.status === 'SHEDDING').length;
  const totalZones = status?.total_zones ?? zones.length;

  const activeEvents = useMemo(
    () =>
      zones
        .filter(z => z.status === 'SHEDDING')
        .flatMap(z => z.events.map(ev => ({ ev, zone: z })))
        .sort((a, b) => (a.ev.started_at ?? '').localeCompare(b.ev.started_at ?? '')),
    [zones],
  );

  const affectedMw = activeEvents.reduce((sum, { ev }) => sum + (ev.mw ?? 0), 0);

  const upcoming = useMemo(
    () => [...schedule].sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
    [schedule],
  );

  const affectedLocalities = useMemo(() => new Set(upcoming.map(o => o.locality)).size, [upcoming]);

  const filteredUpcoming = useMemo(() => {
    const q = norm(plannedQuery);
    if (!q) return upcoming;
    return upcoming.filter(o => norm(o.locality).includes(q) || norm(o.governorate).includes(q));
  }, [upcoming, plannedQuery]);

  const upcomingByDay = useMemo(() => {
    const groups: { day: string; items: CitizenPlannedOutage[] }[] = [];
    const byLabel = new Map<string, number>();
    for (const o of filteredUpcoming) {
      const label = dayLabel(o.starts_at);
      let gi = byLabel.get(label);
      if (gi === undefined) {
        gi = groups.length;
        byLabel.set(label, gi);
        groups.push({ day: label, items: [] });
      }
      groups[gi].items.push(o);
    }
    return groups;
  }, [filteredUpcoming]);

  const nationalStatus: NetworkStatus = !statusAvailable ? 'UNAVAILABLE' : sheddingCount > 0 ? 'ACTIVE' : 'NORMAL';
  const nationalHeadline = !statusAvailable
    ? 'État du réseau indisponible'
    : sheddingCount > 0
      ? 'Délestage en cours'
      : 'Réseau alimenté normalement';

  const maxDaily = Math.max(1, ...(history?.daily_series ?? []).map(d => d.duration_min));
  const avgDuration =
    history && history.total_events > 0 ? Math.round(history.total_duration_min / history.total_events) : 0;

  return (
    <div className="pc">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="pc-header">
        <div className="pc-header-inner">
          <div className="pc-brand">
            <img src="/steg-logo.png" alt="STEG" className="pc-brand-logo" />
            <div className="pc-brand-text">
              <h1>État du réseau électrique</h1>
              <p>Information publique sur les délestages — STEG Tunisie</p>
            </div>
          </div>
          <div className="pc-header-actions">
            <span className="pc-live">En direct</span>
            <button type="button" className="pc-btn" onClick={() => load()} disabled={loading}>
              {loading ? 'Chargement…' : 'Actualiser'}
            </button>
            <Link to="/login" className="pc-btn pc-btn-primary">
              Accès opérateur
            </Link>
          </div>
        </div>
      </header>

      <div className="pc-container">
        {/* ── National status ──────────────────────────────────── */}
        <section
          className="pc-statusbar"
          style={{ borderLeft: `4px solid ${STATUS_META[nationalStatus].color}` }}
          aria-label="État national du réseau"
        >
          <div className="pc-status-headline">
            <span className="pc-status-dot" style={{ background: STATUS_META[nationalStatus].color }} />
            <h2>{nationalHeadline}</h2>
            <span className="pc-status-sub">
              {lastRefreshed ? `Dernière mise à jour ${lastRefreshed}` : 'Mise à jour…'}
              <br />
              Actualisation automatique
            </span>
          </div>
          <div className="pc-status-metrics">
            <div className="pc-metric">
              <span className="pc-metric-label">Zones en délestage</span>
              <span className="pc-metric-value">{statusAvailable ? sheddingCount : '—'}</span>
              <span className="pc-metric-sub">sur {totalZones} centres</span>
            </div>
            <div className="pc-metric">
              <span className="pc-metric-label">Puissance concernée</span>
              <span className="pc-metric-value">{statusAvailable ? `${nf(Math.round(affectedMw))}` : '—'}</span>
              <span className="pc-metric-sub">MW — délestages en cours</span>
            </div>
            <div className="pc-metric">
              <span className="pc-metric-label">Délestages programmés</span>
              <span className="pc-metric-value">{scheduleAvailable ? upcoming.length : '—'}</span>
              <span className="pc-metric-sub">confirmés à venir</span>
            </div>
            <div className="pc-metric">
              <span className="pc-metric-label">Sur 7 jours</span>
              <span className="pc-metric-value">{historyAvailable && history ? history.total_events : '—'}</span>
              <span className="pc-metric-sub">
                {historyAvailable && history ? `${nf(history.total_duration_min)} min cumulées` : 'historique'}
              </span>
            </div>
          </div>
        </section>

        {/* ── Map (centrepiece) ────────────────────────────────── */}
        <section className="pc-map-section" aria-label="Carte nationale">
          <div className="pc-section-head">
            <div>
              <span className="pc-kicker">Carte nationale</span>
              <h2 className="pc-section-title">État du réseau par localité</h2>
            </div>
            <span className="pc-section-meta">264 délégations · 7 centres BCC</span>
          </div>
          <CitizenMap
            zones={zones}
            sheddingZoneIds={status?.shedding_zone_ids}
            scheduledOutages={upcoming}
            generatedAt={status?.generated_at}
            dataAvailable={statusAvailable}
          />
        </section>

        {/* ── Current outages (only when there are any) ────────── */}
        {activeEvents.length > 0 && (
          <section className="pc-section" aria-label="Délestages en cours">
            <div className="pc-section-head">
              <div>
                <span className="pc-kicker">En cours</span>
                <h2 className="pc-section-title">Délestages en cours</h2>
              </div>
              <span className="pc-section-meta">{activeEvents.length} localité(s)</span>
            </div>
            <div className="pc-card">
              <div className="pc-outage-list">
                {activeEvents.slice(0, 12).map(({ ev, zone }, i) => (
                  <div className="pc-outage-row" key={`${zone.zone_id}-${ev.zone_id ?? i}`}>
                    <div className="pc-outage-when">
                      {hhmm(ev.started_at)}
                      <small>depuis</small>
                    </div>
                    <div className="pc-outage-place">
                      <div className="name">{ev.delegation ?? zone.display_name}</div>
                      <div className="sub">
                        {zone.region ? `${zone.region} · ` : ''}
                        {zone.display_name}
                      </div>
                    </div>
                    <div className="pc-outage-meta">
                      <strong>{ev.duration_min} min</strong>
                      {ev.mw != null ? `${nf(ev.mw)} MW` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ── Upcoming confirmed outages ───────────────────────── */}
        <section className="pc-section" id="programmes" aria-label="Prochains délestages">
          <div className="pc-section-head">
            <div>
              <span className="pc-kicker">À venir</span>
              <h2 className="pc-section-title">Prochains délestages confirmés</h2>
            </div>
            <span className="pc-section-meta">
              {scheduleAvailable && upcoming.length > 0
                ? `${upcoming.length} créneau(x) · ${affectedLocalities} localité(s)`
                : 'Délestages validés uniquement'}
            </span>
          </div>
          <div className="pc-card pc-planned">
            <p className="pc-planned-lead">
              Vérifiez si votre localité est concernée par un délestage à venir. Seuls les délestages confirmés et
              validés par les opérateurs sont affichés.
            </p>

            <div className="pc-filter">
              <svg className="pc-filter-icon" viewBox="0 0 20 20" aria-hidden="true">
                <path d="M9 3.5a5.5 5.5 0 1 0 3.39 9.83l3.64 3.64a1 1 0 0 0 1.42-1.42l-3.64-3.64A5.5 5.5 0 0 0 9 3.5Zm-3.5 5.5a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0Z" />
              </svg>
              <input
                type="text"
                className="pc-filter-input"
                placeholder="Recherchez votre localité ou votre gouvernorat…"
                value={plannedQuery}
                onChange={e => setPlannedQuery(e.target.value)}
                aria-label="Rechercher votre localité dans les délestages programmés"
              />
              {plannedQuery && (
                <button
                  type="button"
                  className="pc-filter-clear"
                  onClick={() => setPlannedQuery('')}
                  aria-label="Effacer la recherche"
                >
                  Effacer
                </button>
              )}
            </div>

            {!scheduleAvailable ? (
              <div className="pc-empty">
                <strong>Données indisponibles</strong>
                Le calendrier des délestages confirmés est momentanément indisponible.
              </div>
            ) : upcoming.length === 0 ? (
              <div className="pc-empty pc-empty-ok">
                <strong>Aucun délestage programmé</strong>
                Aucun délestage n'est confirmé à venir. Seuls les délestages validés par les opérateurs sont affichés
                ici.
              </div>
            ) : filteredUpcoming.length === 0 ? (
              <div className="pc-empty pc-empty-ok">
                <strong>Aucun délestage prévu pour « {plannedQuery.trim()} »</strong>
                Aucun délestage confirmé ne concerne cette localité pour l'instant. Votre secteur n'est pas programmé
                pour un délestage à venir.
              </div>
            ) : (
              <div className="pc-day-groups">
                {upcomingByDay.map(group => (
                  <div className="pc-day-group" key={group.day}>
                    <div className="pc-day-head">
                      <span className="pc-day-label">{group.day}</span>
                      <span className="pc-day-count">{group.items.length} créneau(x)</span>
                    </div>
                    <div className="pc-outage-list">
                      {group.items.map((o, i) => (
                        <div className="pc-outage-row" key={`${o.zone_id}-${o.starts_at}-${i}`}>
                          <div className="pc-outage-when">
                            {hhmm(o.starts_at)}–{hhmm(o.ends_at)}
                            <small>{o.duration_min} min</small>
                          </div>
                          <div className="pc-outage-place">
                            <div className="name">{o.locality}</div>
                            <div className="sub">
                              {o.governorate}
                              {o.bcc_name ? ` · ${o.bcc_name}` : ''}
                            </div>
                          </div>
                          <div className="pc-outage-side">
                            <span className="pc-badge pc-badge-scheduled">Programmé</span>
                            <span className="pc-outage-mw">{nf(o.planned_mw)} MW</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* ── History + transparency chart ─────────────────────── */}
        <section className="pc-section" aria-label="Historique des délestages">
          <div className="pc-section-head">
            <div>
              <span className="pc-kicker">Transparence</span>
              <h2 className="pc-section-title">Historique des délestages</h2>
            </div>
            <span className="pc-section-meta">7 derniers jours</span>
          </div>

          {!historyAvailable || !history ? (
            <div className="pc-card">
              <div className="pc-empty">
                <strong>Données indisponibles</strong>
                L'historique public sera affiché dès qu'il sera disponible.
              </div>
            </div>
          ) : (
            <div className="pc-history-grid">
              <div className="pc-card pc-chart-card">
                <div className="pc-chart-head">
                  <span className="t">Durée cumulée de délestage par jour</span>
                  <span className="u">minutes</span>
                </div>
                <div className="pc-chart">
                  {history.daily_series.map(d => {
                    const pct = Math.round((d.duration_min / maxDaily) * 100);
                    return (
                      <div
                        className="pc-chart-col"
                        key={d.day}
                        title={`${shortDate(d.day)} · ${nf(d.duration_min)} min`}
                      >
                        <div
                          className={`pc-chart-bar ${d.duration_min === 0 ? 'is-zero' : ''}`}
                          style={{ height: `${d.duration_min === 0 ? 2 : Math.max(pct, 4)}%` }}
                        />
                      </div>
                    );
                  })}
                </div>
                <div className="pc-chart-axis">
                  {history.daily_series.map(d => (
                    <span key={d.day}>{weekday(d.day)}</span>
                  ))}
                </div>
              </div>

              <div className="pc-card">
                {history.events.length === 0 ? (
                  <div className="pc-empty">
                    <strong>Aucun délestage recensé</strong>
                    Aucun délestage n'a été enregistré sur les 7 derniers jours.
                  </div>
                ) : (
                  <table className="pc-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Localité</th>
                        <th className="num">Durée</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.events.slice(0, 8).map((e, i) => (
                        <tr key={`${e.locality}-${e.started_at}-${i}`}>
                          <td className="num">
                            {shortDate(e.date)}
                            <br />
                            <span style={{ color: 'var(--pc-faint)', fontSize: '11.5px' }}>
                              {hhmm(e.started_at)}–{hhmm(e.ended_at)}
                            </span>
                          </td>
                          <td className="place">
                            {e.locality}
                            <small>{e.region}</small>
                          </td>
                          <td className="num">{e.duration_min} min</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </section>

        {/* ── National transparency statistics ─────────────────── */}
        <section className="pc-section" aria-label="Statistiques nationales">
          <div className="pc-section-head">
            <div>
              <span className="pc-kicker">Statistiques nationales</span>
              <h2 className="pc-section-title">Bilan des 7 derniers jours</h2>
            </div>
          </div>
          <div className="pc-stats-grid">
            <div className="pc-card pc-stat-card">
              <div className="pc-stat-num">{historyAvailable && history ? history.total_events : '—'}</div>
              <div className="pc-stat-cap">Délestages recensés</div>
            </div>
            <div className="pc-card pc-stat-card">
              <div className="pc-stat-num">
                {historyAvailable && history ? nf(history.total_duration_min) : '—'}
              </div>
              <div className="pc-stat-cap">Minutes cumulées de délestage</div>
            </div>
            <div className="pc-card pc-stat-card">
              <div className="pc-stat-num">{historyAvailable && history ? nf(history.total_ens_mwh) : '—'}</div>
              <div className="pc-stat-cap">Énergie non distribuée (MWh)</div>
            </div>
            <div className="pc-card pc-stat-card">
              <div className="pc-stat-num">{historyAvailable && history ? avgDuration : '—'}</div>
              <div className="pc-stat-cap">Durée moyenne par délestage (min)</div>
            </div>
          </div>
          <p className="pc-stat-note">
            Indicateurs calculés à partir des délestages clôturés et validés. Les sites prioritaires (hôpitaux,
            production et distribution d'eau) sont exclus du délestage et ne figurent pas dans ces chiffres.
          </p>
        </section>
      </div>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="pc-footer">
        <div className="pc-footer-inner">
          <p>Société Tunisienne de l'Électricité et du Gaz (STEG) — état public du réseau électrique.</p>
          <p>
            Seules les informations confirmées et validées par les opérateurs sont publiées. Les données provisoires
            ou en cours d'analyse ne sont pas affichées.
          </p>
        </div>
      </footer>
    </div>
  );
}
