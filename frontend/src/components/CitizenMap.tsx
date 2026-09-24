import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CitizenEvent, CitizenPlannedOutage, CitizenZone } from '../api/client';
import {
  MAP_STYLE,
  STATUS_META,
  TUNISIA_CAMERA,
  TUNISIA_CENTER,
  TUNISIA_FIT_BOUNDS,
  TUNISIA_MAP_BOUNDS,
  type NetworkStatus,
} from '../config/mapConfig';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;
const GOOGLE_MAP_ID = import.meta.env.VITE_GOOGLE_MAP_ID as string | undefined;

// A vector map ID is what unlocks genuine tilt/heading. Without it the Maps JS
// API renders a raster surface that cannot tilt at national altitude, so the 3D
// control is disabled rather than shown as a no-op.
const VECTOR_3D = Boolean(GOOGLE_MAP_ID);

let scriptLoadingPromise: Promise<void> | null = null;

function loadGoogleMaps(apiKey: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  if (scriptLoadingPromise) return scriptLoadingPromise;
  scriptLoadingPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&v=beta`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Impossible de charger Google Maps.'));
    document.head.appendChild(script);
  });
  return scriptLoadingPromise;
}

// ── Identity helpers ────────────────────────────────────────────────────────
// Backend zone identifiers (feeder.zone_id without the "Z-" prefix) and the
// delegation IDs baked into the GeoJSON don't always match byte-for-byte, so we
// compare on a normalised, punctuation-free form with a lenient suffix match.
function norm(value: unknown): string {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
}

function idish(a: string, b: string): boolean {
  const x = norm(a);
  const y = norm(b);
  if (!x || !y || y.length < 2) return false;
  return x === y || x.endsWith(y) || y.endsWith(x);
}

interface ZoneFeatureMeta {
  id: string;
  name: string;
  name_ar: string;
  governorate: string;
  bcc_name: string;
  center: [number, number]; // [lat, lng]
  managed_load_mw?: number;
  estimated_peak_mw?: number;
  population_2024?: number;
}

const TUNISIA_FALLBACK_CENTER: [number, number] = [TUNISIA_CENTER.lat, TUNISIA_CENTER.lng];

function extractMeta(feature: google.maps.Data.Feature): ZoneFeatureMeta {
  const num = (key: string) => {
    const v = Number(feature.getProperty(key));
    return Number.isFinite(v) ? v : undefined;
  };
  return {
    id: String(feature.getProperty('id') ?? ''),
    name: String(feature.getProperty('name') ?? ''),
    name_ar: String(feature.getProperty('name_ar') ?? ''),
    governorate: String(feature.getProperty('governorate') ?? ''),
    bcc_name: String(feature.getProperty('bcc_name') ?? ''),
    center: (feature.getProperty('center') as [number, number]) ?? TUNISIA_FALLBACK_CENTER,
    managed_load_mw: num('managed_load_mw'),
    estimated_peak_mw: num('estimated_peak_mw'),
    population_2024: num('population_2024'),
  };
}

// ── Status resolution ───────────────────────────────────────────────────────
interface StatusCtx {
  dataAvailable: boolean;
  activeIds: string[];
  activeNames: string[];
  scheduledIds: string[];
}

function resolveStatus(id: string, name: string, ctx: StatusCtx): NetworkStatus {
  if (!ctx.dataAvailable) return 'UNAVAILABLE';
  if (ctx.activeIds.some(c => idish(id, c))) return 'ACTIVE';
  const nname = norm(name);
  if (nname.length >= 4 && ctx.activeNames.some(c => c === nname || c.includes(nname) || nname.includes(c))) {
    return 'ACTIVE';
  }
  if (ctx.scheduledIds.some(c => idish(id, c))) return 'SCHEDULED';
  return 'NORMAL';
}

// ── Time formatting ─────────────────────────────────────────────────────────
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
  return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'short' });
}

interface CitizenMapProps {
  zones: CitizenZone[];
  sheddingZoneIds?: string[];
  scheduledOutages?: CitizenPlannedOutage[];
  generatedAt?: string;
  /** When false, every zone renders as "Données indisponibles" (grey). */
  dataAvailable?: boolean;
}

export default function CitizenMap({
  zones,
  sheddingZoneIds = [],
  scheduledOutages = [],
  generatedAt,
  dataAvailable,
}: CitizenMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const is3DRef = useRef<boolean>(VECTOR_3D);

  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'no-key'>('loading');
  const [zoneFeatures, setZoneFeatures] = useState<ZoneFeatureMeta[]>([]);
  const [selectedMeta, setSelectedMeta] = useState<ZoneFeatureMeta | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [is3D, setIs3D] = useState<boolean>(VECTOR_3D);
  const [legendOpen, setLegendOpen] = useState(true);

  const effectiveAvailable = dataAvailable ?? zones.length > 0;

  // Normalised matching context — rebuilt only when the underlying data changes.
  const ctx = useMemo<StatusCtx>(() => {
    const activeIds = [...sheddingZoneIds];
    const activeNames: string[] = [];
    for (const z of zones) {
      if (z.status === 'SHEDDING') {
        (z.affected_zone_ids ?? []).forEach(i => activeIds.push(i));
        (z.affected_delegations ?? []).forEach(n => activeNames.push(norm(n)));
      }
    }
    return {
      dataAvailable: effectiveAvailable,
      activeIds,
      activeNames,
      scheduledIds: scheduledOutages.map(o => o.zone_id),
    };
  }, [zones, sheddingZoneIds, scheduledOutages, effectiveAvailable]);

  const findEvent = useCallback(
    (id: string, name: string): CitizenEvent | undefined => {
      for (const z of zones) {
        for (const ev of z.events) {
          if (ev.zone_id && idish(id, ev.zone_id)) return ev;
          if (ev.delegation && norm(ev.delegation) === norm(name)) return ev;
        }
      }
      return undefined;
    },
    [zones],
  );

  const findOutage = useCallback(
    (id: string): CitizenPlannedOutage | undefined => scheduledOutages.find(o => idish(id, o.zone_id)),
    [scheduledOutages],
  );

  // ── Initialise the map exactly once ───────────────────────────────────────
  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) {
      setStatus('no-key');
      return;
    }
    let cancelled = false;

    loadGoogleMaps(GOOGLE_MAPS_API_KEY)
      .then(() => {
        if (cancelled || !containerRef.current || mapRef.current) return;

        const map = new google.maps.Map(containerRef.current, {
          center: TUNISIA_CENTER,
          zoom: TUNISIA_CAMERA.defaultZoom,
          minZoom: TUNISIA_CAMERA.minZoom,
          maxZoom: TUNISIA_CAMERA.maxZoom,
          mapId: GOOGLE_MAP_ID || undefined,
          tilt: VECTOR_3D ? TUNISIA_CAMERA.defaultTilt : 0,
          heading: TUNISIA_CAMERA.defaultHeading,
          disableDefaultUI: true,
          gestureHandling: 'cooperative',
          backgroundColor: '#eef1f4',
          restriction: { latLngBounds: TUNISIA_MAP_BOUNDS, strictBounds: false },
          // Vector maps are styled in the Cloud console via the mapId; inline
          // styles only apply (and are only needed) on the raster fallback.
          ...(VECTOR_3D ? {} : { styles: MAP_STYLE }),
        });
        mapRef.current = map;

        frameTunisia(map);

        map.data.addListener('mouseover', (e: google.maps.Data.MouseEvent) =>
          e.feature.setProperty('__hover', true),
        );
        map.data.addListener('mouseout', (e: google.maps.Data.MouseEvent) =>
          e.feature.setProperty('__hover', false),
        );
        map.data.addListener('click', (e: google.maps.Data.MouseEvent) => {
          const id = String(e.feature.getProperty('id') ?? '');
          if (!id) return; // border/mask features carry no id
          setSelectedMeta(extractMeta(e.feature));
          if (e.latLng) map.panTo(e.latLng);
        });

        void loadLayers(map, () => cancelled);
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadLayers = async (map: google.maps.Map, isCancelled: () => boolean) => {
    try {
      const [zonesGeo, borderGeo] = await Promise.all([
        fetch('/data/tunisia_zones.geojson').then(r => r.json()),
        fetch('/data/tunisia_border.geojson')
          .then(r => r.json())
          .catch(() => null),
      ]);
      if (isCancelled()) return;

      const parsed = map.data.addGeoJson(zonesGeo);
      setZoneFeatures(parsed.map(extractMeta).filter(m => m.id));

      if (borderGeo) addBorderAndMask(map, borderGeo);
      setStatus('ready');
    } catch {
      // The base map is still useful even if the overlays fail to load.
      if (!isCancelled()) setStatus('ready');
    }
  };

  // ── Re-style the choropleth whenever status data changes ───────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || status !== 'ready') return;
    const selectedId = selectedMeta?.id ?? null;

    map.data.setStyle((feature: google.maps.Data.Feature): google.maps.Data.StyleOptions => {
      const role = feature.getProperty('role');
      if (role === 'mask') {
        return { fillColor: '#f3f5f8', fillOpacity: 0.62, strokeWeight: 0, clickable: false, zIndex: 1 };
      }
      if (role === 'border') {
        return { fillOpacity: 0, strokeColor: '#33465c', strokeWeight: 1.6, clickable: false, zIndex: 40 };
      }

      const id = String(feature.getProperty('id') ?? '');
      const name = String(feature.getProperty('name') ?? '');
      const st = resolveStatus(id, name, ctx);
      const meta = STATUS_META[st];
      const hovered = Boolean(feature.getProperty('__hover'));
      const selected = selectedId === id;
      const emphasised = hovered || selected;

      return {
        fillColor: meta.color,
        fillOpacity: emphasised ? meta.fillOpacityActive : meta.fillOpacity,
        strokeColor: selected ? '#1b2733' : meta.color,
        strokeWeight: selected ? 2.4 : hovered ? 1.6 : 0.6,
        zIndex: selected ? 30 : hovered ? 20 : st === 'ACTIVE' ? 6 : 4,
        cursor: 'pointer',
      };
    });
  }, [ctx, status, selectedMeta]);

  useEffect(() => {
    is3DRef.current = is3D;
  }, [is3D]);

  // ── Camera helpers ────────────────────────────────────────────────────────
  const frameTunisia = (map: google.maps.Map) => {
    map.fitBounds(TUNISIA_FIT_BOUNDS, 24);
    if (VECTOR_3D) {
      google.maps.event.addListenerOnce(map, 'idle', () => {
        map.setTilt(is3DRef.current ? TUNISIA_CAMERA.defaultTilt : 0);
        map.setHeading(TUNISIA_CAMERA.defaultHeading);
      });
    }
  };

  const recenter = () => {
    const map = mapRef.current;
    if (!map) return;
    setSelectedMeta(null);
    frameTunisia(map);
  };

  const zoomBy = (delta: number) => {
    const map = mapRef.current;
    if (!map) return;
    map.setZoom((map.getZoom() ?? TUNISIA_CAMERA.defaultZoom) + delta);
  };

  const toggle3D = () => {
    const map = mapRef.current;
    if (!map || !VECTOR_3D) return;
    const next = !is3D;
    setIs3D(next);
    map.setTilt(next ? TUNISIA_CAMERA.defaultTilt : 0);
    map.setHeading(TUNISIA_CAMERA.defaultHeading);
  };

  const selectMeta = (meta: ZoneFeatureMeta) => {
    setSelectedMeta(meta);
    setSearchQuery('');
    const map = mapRef.current;
    if (map && meta.center) {
      const target = { lat: meta.center[0], lng: meta.center[1] };
      if (typeof map.moveCamera === 'function') {
        map.moveCamera({
          center: target,
          zoom: TUNISIA_CAMERA.localityZoom,
        });
      } else {
        map.setCenter(target);
        map.setZoom(TUNISIA_CAMERA.localityZoom);
      }
    }
  };

  // ── Derived view data ─────────────────────────────────────────────────────
  const counts = useMemo(() => {
    const c: Record<NetworkStatus, number> = { NORMAL: 0, ACTIVE: 0, SCHEDULED: 0, UNAVAILABLE: 0 };
    for (const f of zoneFeatures) c[resolveStatus(f.id, f.name, ctx)]++;
    return c;
  }, [zoneFeatures, ctx]);

  const searchResults = useMemo(() => {
    const q = norm(searchQuery);
    if (q.length < 2 || zoneFeatures.length === 0) return [];
    return zoneFeatures
      .filter(z => norm(z.name).includes(q) || norm(z.governorate).includes(q) || z.name_ar.includes(searchQuery.trim()))
      .slice(0, 6);
  }, [searchQuery, zoneFeatures]);

  const selectedInfo = useMemo(() => {
    if (!selectedMeta) return null;
    const st = resolveStatus(selectedMeta.id, selectedMeta.name, ctx);
    return {
      meta: selectedMeta,
      status: st,
      event: st === 'ACTIVE' ? findEvent(selectedMeta.id, selectedMeta.name) : undefined,
      outage: st === 'SCHEDULED' ? findOutage(selectedMeta.id) : undefined,
    };
  }, [selectedMeta, ctx, findEvent, findOutage]);

  // ── Non-map states ────────────────────────────────────────────────────────
  if (status === 'no-key') {
    return (
      <div className="pc-map-wrap">
        <div className="pc-map-placeholder">
          Carte indisponible — la clé Google&nbsp;Maps n'est pas configurée (<code>VITE_GOOGLE_MAPS_API_KEY</code>).
        </div>
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className="pc-map-wrap">
        <div className="pc-map-placeholder">Impossible de charger la carte pour le moment.</div>
      </div>
    );
  }

  const legendRows: NetworkStatus[] = effectiveAvailable
    ? ['NORMAL', 'SCHEDULED', 'ACTIVE']
    : ['UNAVAILABLE'];

  return (
    <div className="pc-map-wrap">
      <div ref={containerRef} className="pc-map-canvas" aria-label="Carte de l'état du réseau électrique en Tunisie" />

      {status === 'loading' && (
        <div className="pc-map-placeholder" style={{ position: 'absolute', inset: 0, background: 'var(--pc-surface-2)' }}>
          Chargement du fond cartographique…
        </div>
      )}

      {/* Locality search */}
      <div className="pc-map-search">
        <input
          type="text"
          className="pc-map-search-input"
          placeholder="Rechercher une localité (ex. La Marsa, Sfax, Gabès)…"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          aria-label="Rechercher une localité"
        />
        {searchResults.length > 0 && (
          <div className="pc-suggest" role="listbox">
            {searchResults.map(z => {
              const st = resolveStatus(z.id, z.name, ctx);
              const meta = STATUS_META[st];
              return (
                <button type="button" key={z.id} className="pc-suggest-item" onClick={() => selectMeta(z)}>
                  <span>
                    <span className="pc-suggest-name">{z.name}</span>{' '}
                    <span className="pc-suggest-sub">{z.governorate}</span>
                  </span>
                  <span className="pc-suggest-status" style={{ color: meta.color }}>
                    <span className="pc-dot" style={{ background: meta.color }} />
                    {meta.label}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="pc-map-controls">
        <div className="pc-ctrl-group">
          <button type="button" className="pc-ctrl" onClick={() => zoomBy(1)} aria-label="Zoomer">
            +
          </button>
          <button type="button" className="pc-ctrl" onClick={() => zoomBy(-1)} aria-label="Dézoomer">
            −
          </button>
        </div>
        <div className="pc-ctrl-group pc-ctrl-row" role="group" aria-label="Mode d'affichage">
          <button
            type="button"
            className={`pc-ctrl ${!is3D ? 'is-active' : ''}`}
            onClick={() => is3D && toggle3D()}
            disabled={!VECTOR_3D}
          >
            2D
          </button>
          <button
            type="button"
            className={`pc-ctrl ${is3D ? 'is-active' : ''}`}
            onClick={() => !is3D && toggle3D()}
            disabled={!VECTOR_3D}
            title={VECTOR_3D ? undefined : 'Vue 3D indisponible (VITE_GOOGLE_MAP_ID requis)'}
          >
            3D
          </button>
        </div>
        <div className="pc-ctrl-group">
          <button type="button" className="pc-ctrl" onClick={recenter}>
            Recentrer
          </button>
        </div>
        <div className="pc-ctrl-group">
          <button
            type="button"
            className={`pc-ctrl ${legendOpen ? 'is-active' : ''}`}
            onClick={() => setLegendOpen(o => !o)}
            aria-pressed={legendOpen}
          >
            Légende
          </button>
        </div>
      </div>

      {/* Legend */}
      {legendOpen && (
        <div className="pc-legend">
          <div className="pc-legend-title">État du réseau</div>
          {legendRows.map(key => {
            const meta = STATUS_META[key];
            return (
              <div className="pc-legend-row" key={key}>
                <span className="pc-dot" style={{ background: meta.color }} />
                <span>{meta.label}</span>
                <span className="pc-count">{counts[key]}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Info panel */}
      {selectedInfo && (
        <InfoPanel info={selectedInfo} generatedAt={generatedAt} onClose={() => setSelectedMeta(null)} />
      )}
    </div>
  );
}

// ── Info panel ──────────────────────────────────────────────────────────────
interface SelectedInfo {
  meta: ZoneFeatureMeta;
  status: NetworkStatus;
  event?: CitizenEvent;
  outage?: CitizenPlannedOutage;
}

function InfoPanel({
  info,
  generatedAt,
  onClose,
}: {
  info: SelectedInfo;
  generatedAt?: string;
  onClose: () => void;
}) {
  const { meta, status, event, outage } = info;
  const sm = STATUS_META[status];
  const peak = meta.estimated_peak_mw && meta.estimated_peak_mw > 0 ? meta.estimated_peak_mw : meta.managed_load_mw;

  return (
    <div className="pc-map-panel" role="dialog" aria-label={`État de ${meta.name}`}>
      <div className="pc-panel-accent" style={{ background: sm.color }} />
      <div className="pc-panel-body">
        <div className="pc-panel-head">
          <div>
            <h3 className="pc-panel-title">{meta.name}</h3>
            <div className="pc-panel-sub">
              {meta.governorate}
              {meta.bcc_name ? ` · ${meta.bcc_name}` : ''}
            </div>
          </div>
          <button type="button" className="pc-panel-close" onClick={onClose} aria-label="Fermer">
            ×
          </button>
        </div>

        <div className="pc-panel-status" style={{ color: sm.color }}>
          <span className="pc-dot" style={{ background: sm.color }} />
          {sm.label}
        </div>

        <div className="pc-panel-rows">
          {status === 'ACTIVE' && (
            <>
              <div className="pc-panel-row">
                <span className="k">Depuis</span>
                <span className="v">{hhmm(event?.started_at)}</span>
              </div>
              <div className="pc-panel-row">
                <span className="k">Durée actuelle</span>
                <span className="v">{event ? `${event.duration_min} min` : '—'}</span>
              </div>
              {event?.mw != null && (
                <div className="pc-panel-row">
                  <span className="k">Puissance concernée</span>
                  <span className="v">{event.mw.toLocaleString('fr-FR')} MW</span>
                </div>
              )}
              <div className="pc-panel-row">
                <span className="k">Dernière mise à jour</span>
                <span className="v">{hhmm(generatedAt)}</span>
              </div>
            </>
          )}

          {status === 'SCHEDULED' && outage && (
            <>
              <div className="pc-panel-row">
                <span className="k">Prochain délestage confirmé</span>
                <span className="v">
                  {dayLabel(outage.starts_at)} · {hhmm(outage.starts_at)}–{hhmm(outage.ends_at)}
                </span>
              </div>
              <div className="pc-panel-row">
                <span className="k">Durée prévue</span>
                <span className="v">{outage.duration_min} min</span>
              </div>
              <div className="pc-panel-row">
                <span className="k">Puissance prévue</span>
                <span className="v">{outage.planned_mw.toLocaleString('fr-FR')} MW</span>
              </div>
            </>
          )}

          {status === 'NORMAL' && (
            <>
              <div className="pc-panel-row">
                <span className="k">Aucun délestage actif</span>
                <span className="v" style={{ color: sm.color }}>
                  Alimenté
                </span>
              </div>
              {peak != null && peak > 0 && (
                <div className="pc-panel-row">
                  <span className="k">Puissance estimée</span>
                  <span className="v">{peak.toLocaleString('fr-FR')} MW</span>
                </div>
              )}
            </>
          )}

          {status === 'UNAVAILABLE' && (
            <div className="pc-panel-row">
              <span className="k">Statut électrique momentanément indisponible.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Border outline + neighbour de-emphasis mask ─────────────────────────────
// The mask is a world-sized polygon with Tunisia's coastline rings punched out
// as holes, filled with a soft page-coloured veil so neighbouring countries
// recede and Tunisia reads as the subject of the map.
function addBorderAndMask(map: google.maps.Map, borderGeo: unknown) {
  const feature = extractBorderFeature(borderGeo);
  const geom = feature?.geometry;
  if (!geom) return;

  map.data.addGeoJson({ type: 'Feature', geometry: geom, properties: { role: 'border' } });

  const outerRings: google.maps.LatLngLiteral[][] = [];
  const toRing = (ring: number[][]) => ring.map(([lng, lat]) => ({ lat, lng }));
  if (geom.type === 'Polygon') {
    outerRings.push(toRing((geom.coordinates as number[][][])[0]));
  } else if (geom.type === 'MultiPolygon') {
    (geom.coordinates as number[][][][]).forEach(poly => outerRings.push(toRing(poly[0])));
  }
  if (outerRings.length === 0) return;

  const world: google.maps.LatLngLiteral[] = [
    { lat: 85, lng: -179.9 },
    { lat: 85, lng: 179.9 },
    { lat: -85, lng: 179.9 },
    { lat: -85, lng: -179.9 },
  ];
  const maskGeom = new google.maps.Data.Polygon([world, ...outerRings]);
  map.data.add({ geometry: maskGeom, properties: { role: 'mask' } });
}

interface BorderGeometry {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: unknown;
}
interface BorderFeature {
  geometry: BorderGeometry;
}

function extractBorderFeature(geo: unknown): BorderFeature | null {
  if (!geo || typeof geo !== 'object') return null;
  const g = geo as { type?: string; features?: BorderFeature[]; geometry?: BorderGeometry };
  if (g.type === 'FeatureCollection' && g.features?.length) return g.features[0];
  if (g.geometry) return { geometry: g.geometry };
  return null;
}
