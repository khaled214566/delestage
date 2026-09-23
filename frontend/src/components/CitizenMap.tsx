import { useEffect, useRef, useState, useMemo } from 'react';
import type { CitizenZone } from '../api/client';
import { GOVERNORATE_COORDINATES, TUNISIA_CENTER, TUNISIA_DEFAULT_ZOOM } from '../data/governorateCoordinates';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;

const COLOR_NORMAL = '#38a169';       // "Alimentation Normale" green
const COLOR_SHEDDING = '#e53e3e';     // Live alert red
const COLOR_BORDER_NORMAL = '#276749';
const COLOR_BORDER_SHED = '#9b2c2c';
const COLOR_HOVER = '#2b6cb0';        // Vibrant blue on hover/select

// Low-contrast clean basemap so borders and colors remain the focal point
const MAP_STYLE: google.maps.MapTypeStyle[] = [
  { elementType: 'geometry', stylers: [{ color: '#f8fafc' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#64748b' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#ffffff' }] },
  { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#cbd5e1' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#bae6fd' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#e2e8f0' }] },
  { featureType: 'road', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
];

let scriptLoadingPromise: Promise<void> | null = null;

function loadGoogleMaps(apiKey: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  if (scriptLoadingPromise) return scriptLoadingPromise;

  scriptLoadingPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Impossible de charger Google Maps.'));
    document.head.appendChild(script);
  });
  return scriptLoadingPromise;
}

interface ZoneFeatureMeta {
  id: string;
  name: string;
  name_ar: string;
  governorate: string;
  governorate_ar: string;
  bcc_id: string;
  bcc_name: string;
  center: [number, number]; // [lat, lng]
  subzones: string[];
  managed_load_mw?: number;
  estimated_peak_mw?: number;
  population_2024?: number;
}

interface MapPoint {
  governorate: string;
  position: [number, number];
  zone: CitizenZone;
}

function buildGovernoratePoints(zones: CitizenZone[]): MapPoint[] {
  const points: MapPoint[] = [];
  for (const zone of zones) {
    const names = (zone.governorates || '').split(',').map(s => s.trim()).filter(Boolean);
    for (const name of names) {
      const position = GOVERNORATE_COORDINATES[name];
      if (position) points.push({ governorate: name, position, zone });
    }
  }
  return points;
}

function dotIcon(color: string): google.maps.Symbol {
  return {
    path: google.maps.SymbolPath.CIRCLE,
    fillColor: color,
    fillOpacity: 1,
    strokeColor: '#ffffff',
    strokeWeight: 1.5,
    scale: 6,
  };
}

interface CitizenMapProps {
  zones: CitizenZone[];
  sheddingZoneIds?: string[];
}

export default function CitizenMap({ zones, sheddingZoneIds = [] }: CitizenMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);
  const featuresRef = useRef<Map<string, google.maps.Data.Feature>>(new Map());

  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'no-key'>('loading');
  const [zoneFeatures, setZoneFeatures] = useState<ZoneFeatureMeta[]>([]);
  const [showBorders, setShowBorders] = useState<boolean>(true);
  const [showMarkers, setShowMarkers] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);

  // Helper to determine if an exact delegation is currently in shedding
  const isZoneShedding = (meta: ZoneFeatureMeta): boolean => {
    // 1. Direct match with active shedding zone IDs (from API)
    if (sheddingZoneIds && sheddingZoneIds.length > 0) {
      const cleanId = meta.id.toUpperCase();
      const cleanName = meta.name.toLowerCase();
      const match = sheddingZoneIds.some(zid => {
        const z = zid.toUpperCase();
        return z === cleanId || z.endsWith(cleanId) || cleanId.endsWith(z) || cleanName === zid.toLowerCase();
      });
      if (match) return true;
    }

    // 2. Check if any BCC zone lists this delegation as affected
    for (const z of zones) {
      if (z.status === 'SHEDDING') {
        if (z.affected_zone_ids?.some(zid => zid.toUpperCase() === meta.id.toUpperCase())) {
          return true;
        }
        if (z.affected_delegations?.some(d => d.toLowerCase().includes(meta.name.toLowerCase()) || meta.name.toLowerCase().includes(d.toLowerCase()))) {
          return true;
        }
      }
    }

    return false;
  };

  // 1. Initialize Map
  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) {
      setStatus('no-key');
      return;
    }
    let cancelled = false;

    loadGoogleMaps(GOOGLE_MAPS_API_KEY)
      .then(() => {
        if (cancelled || !containerRef.current) return;

        const map = new google.maps.Map(containerRef.current, {
          center: { lat: TUNISIA_CENTER[0], lng: TUNISIA_CENTER[1] },
          zoom: TUNISIA_DEFAULT_ZOOM,
          minZoom: 6,
          maxZoom: 16,
          styles: MAP_STYLE,
          streetViewControl: false,
          mapTypeControl: false,
          fullscreenControl: true,
          restriction: {
            latLngBounds: { north: 38.2, south: 30.0, east: 12.5, west: 6.5 },
            strictBounds: false,
          },
        });

        const infoWindow = new google.maps.InfoWindow();
        mapRef.current = map;
        infoWindowRef.current = infoWindow;

        // Load 264 Tunisian Zone Boundaries GeoJSON
        fetch('/data/tunisia_zones.geojson')
          .then(res => res.json())
          .then(geojson => {
            if (cancelled) return;
            const parsedFeatures = map.data.addGeoJson(geojson);
            const metas: ZoneFeatureMeta[] = [];

            parsedFeatures.forEach((feat: google.maps.Data.Feature) => {
              const id = feat.getProperty('id') as string;
              const name = feat.getProperty('name') as string;
              const name_ar = feat.getProperty('name_ar') as string;
              const governorate = feat.getProperty('governorate') as string;
              const governorate_ar = feat.getProperty('governorate_ar') as string;
              const bcc_id = feat.getProperty('bcc_id') as string;
              const bcc_name = feat.getProperty('bcc_name') as string;
              const center = feat.getProperty('center') as [number, number];
              const subzones = (feat.getProperty('subzones') as string[]) || [];

              const meta: ZoneFeatureMeta = {
                id,
                name,
                name_ar,
                governorate,
                governorate_ar,
                bcc_id,
                bcc_name,
                center,
                subzones,
              };

              metas.push(meta);
              featuresRef.current.set(id, feat);
            });

            setZoneFeatures(metas);
            setStatus('ready');
          })
          .catch(err => {
            console.error('Failed to load tunisia_zones.geojson', err);
            setStatus('ready'); // Still show base map even if geojson fails
          });

        // Hover events
        map.data.addListener('mouseover', (event: google.maps.Data.MouseEvent) => {
          event.feature.setProperty('isHovered', true);
        });

        map.data.addListener('mouseout', (event: google.maps.Data.MouseEvent) => {
          event.feature.setProperty('isHovered', false);
        });

        // Click event on zone polygon
        map.data.addListener('click', (event: google.maps.Data.MouseEvent) => {
          const id = String(event.feature.getProperty('id') || '');
          const name = String(event.feature.getProperty('name') || '');
          const name_ar = String(event.feature.getProperty('name_ar') || '');
          const gov = String(event.feature.getProperty('governorate') || '');
          const bcc = String(event.feature.getProperty('bcc_name') || '');
          const subzones = (event.feature.getProperty('subzones') as string[]) || [];
          const center = (event.feature.getProperty('center') as [number, number]) || [35.0, 10.0];

          const managedMw = Number(event.feature.getProperty('managed_load_mw') || 0);
          const peakMw = Number(event.feature.getProperty('estimated_peak_mw') || 0);
          const pop = Number(event.feature.getProperty('population_2024') || 0);

          const meta: ZoneFeatureMeta = {
            id,
            name,
            name_ar,
            governorate: gov,
            governorate_ar: '',
            bcc_id: '',
            bcc_name: bcc,
            center,
            subzones,
            managed_load_mw: managedMw,
            estimated_peak_mw: peakMw,
            population_2024: pop,
          };

          const isShedding = isZoneShedding(meta);
          setSelectedZoneId(id);

          const subzonesHtml = subzones.length > 0
            ? `<div style="margin-top:0.5rem;font-size:0.75rem;color:#4a5568;line-height:1.35;">
                 <strong>Secteurs & Quartiers :</strong><br/>
                 <span style="color:#718096">${subzones.join(', ')}</span>
               </div>`
            : '';

          const html = `
            <div style="font-family:inherit;min-width:240px;max-width:320px;padding:2px;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                <div>
                  <h3 style="margin:0;font-size:1.05rem;font-weight:700;color:#1a202c;">
                    ${name} <span style="font-size:0.9rem;font-weight:500;color:#718096">(${name_ar || ''})</span>
                  </h3>
                  <div style="font-size:0.78rem;color:#718096;margin-top:2px;">
                    District : <strong>${gov}</strong> • ${bcc}
                  </div>
                </div>
              </div>

              <div style="font-size:0.78rem;color:#4a5568;margin-top:6px;padding:5px 8px;border-radius:6px;background:#f8fafc;border:1px solid #e2e8f0;display:flex;justify-content:space-between;">
                <span>⚡ Puissance estimée : <strong>${peakMw > 0 ? peakMw.toFixed(1) : managedMw.toFixed(1)} MW</strong></span>
                ${pop > 0 ? `<span>👥 <strong>${pop.toLocaleString('fr-FR')}</strong> hab.</span>` : ''}
              </div>
              
              <div style="margin-top:0.6rem;padding:0.4rem 0.6rem;border-radius:6px;font-size:0.82rem;font-weight:600;display:flex;align-items:center;gap:6px;background:${isShedding ? '#fff5f5' : '#f0fff4'};color:${isShedding ? COLOR_SHEDDING : COLOR_NORMAL};border:1px solid ${isShedding ? '#feb2b2' : '#9ae6b4'}">
                <span>${isShedding ? '⚡ Coupure en cours (Délestage)' : '✅ Alimentation électrique normale'}</span>
              </div>

              ${isShedding ? `
                <div style="font-size:0.78rem;color:#742a2a;margin-top:0.4rem;background:#fffaf0;padding:5px 8px;border-radius:4px;border-left:3px solid #dd6b20;">
                  ⏱️ Rétablissement estimé : <strong>Sous 45 minutes</strong> (rotation tournante)
                </div>` : ''}

              ${subzonesHtml}
            </div>
          `;

          infoWindow.setContent(html);
          infoWindow.setPosition(event.latLng);
          infoWindow.open(map);
        });
      })
      .catch(err => {
        console.error('CitizenMap: failed to load/init Google Maps.', err);
        if (!cancelled) setStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [sheddingZoneIds]);

  // 2. Dynamic styling for Zone Border Polygons
  useEffect(() => {
    if (status !== 'ready' || !mapRef.current) return;

    mapRef.current.data.setStyle((feature: google.maps.Data.Feature) => {
      if (!showBorders) {
        return { visible: false };
      }

      const id = feature.getProperty('id') as string;
      const gov = feature.getProperty('governorate') as string;
      const bccId = feature.getProperty('bcc_id') as string;
      const isHovered = feature.getProperty('isHovered');
      const isSelected = selectedZoneId === id;

      const meta: ZoneFeatureMeta = {
        id,
        name: String(feature.getProperty('name') || ''),
        name_ar: String(feature.getProperty('name_ar') || ''),
        governorate: gov,
        governorate_ar: '',
        bcc_id: bccId,
        bcc_name: String(feature.getProperty('bcc_name') || ''),
        center: [0, 0],
        subzones: [],
      };

      const isShedding = isZoneShedding(meta);

      if (isSelected) {
        return {
          fillColor: isShedding ? COLOR_SHEDDING : COLOR_HOVER,
          fillOpacity: 0.5,
          strokeColor: '#1a365d',
          strokeWeight: 3.5,
          zIndex: 20,
          cursor: 'pointer',
        };
      }

      if (isShedding) {
        return {
          fillColor: COLOR_SHEDDING,
          fillOpacity: isHovered ? 0.45 : 0.28,
          strokeColor: isHovered ? '#742a2a' : COLOR_BORDER_SHED,
          strokeWeight: isHovered ? 2.5 : 1.2,
          zIndex: isHovered ? 15 : 2,
          cursor: 'pointer',
        };
      }

      return {
        fillColor: isHovered ? '#319795' : COLOR_NORMAL,
        fillOpacity: isHovered ? 0.3 : 0.12,
        strokeColor: isHovered ? COLOR_HOVER : COLOR_BORDER_NORMAL,
        strokeWeight: isHovered ? 2.5 : 0.8,
        zIndex: isHovered ? 10 : 1,
        cursor: 'pointer',
      };
    });
  }, [zones, sheddingZoneIds, status, showBorders, selectedZoneId]);

  // 3. Optional Regional Markers
  useEffect(() => {
    if (status !== 'ready' || !mapRef.current) return;

    markersRef.current.forEach(m => m.setMap(null));
    if (!showMarkers) {
      markersRef.current = [];
      return;
    }

    markersRef.current = buildGovernoratePoints(zones).map(point => {
      const isShedding = point.zone.status === 'SHEDDING';
      const marker = new google.maps.Marker({
        position: { lat: point.position[0], lng: point.position[1] },
        map: mapRef.current!,
        icon: dotIcon(isShedding ? COLOR_SHEDDING : COLOR_NORMAL),
        title: point.governorate,
      });

      marker.addListener('click', () => {
        const html = `
          <div style="font-family:inherit;min-width:200px">
            <strong style="font-size:0.95rem">${point.governorate}</strong>
            <div style="font-size:0.8rem;color:#718096;margin-bottom:0.4rem">${point.zone.display_name}</div>
            <div style="font-size:0.85rem;font-weight:600;color:${isShedding ? COLOR_SHEDDING : COLOR_NORMAL}">
              ${isShedding ? '⚡ Coupure en cours' : '✅ Alimentation normale'}
            </div>
          </div>`;
        infoWindowRef.current?.setContent(html);
        infoWindowRef.current?.open({ map: mapRef.current!, anchor: marker });
      });

      return marker;
    });
  }, [zones, status, showMarkers]);

  // Filtered search suggestions
  const searchResults = useMemo(() => {
    if (!searchQuery.trim() || zoneFeatures.length === 0) return [];
    const q = searchQuery.toLowerCase().trim();
    return zoneFeatures
      .filter(z =>
        z.name.toLowerCase().includes(q) ||
        z.name_ar.includes(q) ||
        z.governorate.toLowerCase().includes(q) ||
        z.subzones.some(s => s.toLowerCase().includes(q))
      )
      .slice(0, 6);
  }, [searchQuery, zoneFeatures]);

  // Zoom to a selected zone
  const handleSelectZone = (meta: ZoneFeatureMeta) => {
    setSelectedZoneId(meta.id);
    setSearchQuery('');

    if (mapRef.current && meta.center) {
      mapRef.current.panTo({ lat: meta.center[0], lng: meta.center[1] });
      mapRef.current.setZoom(12);

      const isShedding = isZoneShedding(meta);
      const html = `
        <div style="font-family:inherit;min-width:240px;padding:2px;">
          <h3 style="margin:0;font-size:1.05rem;font-weight:700;">${meta.name} (${meta.name_ar})</h3>
          <div style="font-size:0.8rem;color:#718096;margin:3px 0 6px;">
            District : <strong>${meta.governorate}</strong> • ${meta.bcc_name}
          </div>
          <div style="padding:4px 8px;border-radius:4px;font-size:0.82rem;font-weight:600;background:${isShedding ? '#fff5f5' : '#f0fff4'};color:${isShedding ? COLOR_SHEDDING : COLOR_NORMAL};border:1px solid ${isShedding ? '#feb2b2' : '#9ae6b4'}">
            ${isShedding ? '⚡ Coupure en cours' : '✅ Alimentation normale'}
          </div>
          ${meta.subzones.length > 0 ? `
            <div style="margin-top:6px;font-size:0.75rem;color:#718096;">
              <strong>Secteurs :</strong> ${meta.subzones.slice(0, 5).join(', ')}...
            </div>` : ''}
        </div>
      `;
      infoWindowRef.current?.setContent(html);
      infoWindowRef.current?.setPosition({ lat: meta.center[0], lng: meta.center[1] });
      infoWindowRef.current?.open(mapRef.current);
    }
  };

  const sheddingCount = zoneFeatures.filter(z => isZoneShedding(z)).length;
  const normalCount = zoneFeatures.length - sheddingCount;

  if (status === 'no-key') {
    return (
      <div className="citizen-map-placeholder">
        🗺️ Carte indisponible — clé Google Maps non configurée (<code>VITE_GOOGLE_MAPS_API_KEY</code>).
      </div>
    );
  }
  if (status === 'error') {
    return <div className="citizen-map-placeholder">🗺️ Impossible de charger la carte Google Maps.</div>;
  }

  return (
    <div className="citizen-map-wrapper">
      {/* Search & Layer Toolbar */}
      <div style={{
        padding: '0.75rem 1rem',
        background: '#ffffff',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '0.75rem',
      }}>
        {/* Search input with live suggestion dropdown */}
        <div style={{ position: 'relative', flex: '1 1 280px', maxWidth: '420px' }}>
          <input
            type="text"
            placeholder="🔍 Trouver une zone (ex: La Marsa, Carthage, Sfax, Sousse...)"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '0.45rem 0.85rem',
              fontSize: '0.88rem',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              outline: 'none',
            }}
          />
          {searchResults.length > 0 && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              marginTop: '4px',
              background: '#fff',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              zIndex: 100,
              maxHeight: '260px',
              overflowY: 'auto',
            }}>
              {searchResults.map(z => {
                const shedding = isZoneShedding(z);
                return (
                  <div
                    key={z.id}
                    onClick={() => handleSelectZone(z)}
                    style={{
                      padding: '0.5rem 0.8rem',
                      cursor: 'pointer',
                      borderBottom: '1px solid #f1f5f9',
                      fontSize: '0.85rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#f8fafc')}
                    onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <div>
                      <strong>{z.name}</strong> <span style={{ color: '#64748b' }}>({z.name_ar})</span>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{z.governorate} • {z.bcc_name}</div>
                    </div>
                    <span style={{
                      fontSize: '0.75rem',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: shedding ? '#fee2e2' : '#dcfce7',
                      color: shedding ? '#991b1b' : '#166534',
                      fontWeight: 600,
                    }}>
                      {shedding ? '⚡ Coupure' : '✅ Normal'}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Layer Toggles & Stats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <label style={{ fontSize: '0.82rem', color: '#475569', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showBorders}
              onChange={e => setShowBorders(e.target.checked)}
            />
            <span>Délimitations frontalières (264 zones)</span>
          </label>
          <label style={{ fontSize: '0.82rem', color: '#475569', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showMarkers}
              onChange={e => setShowMarkers(e.target.checked)}
            />
            <span>Repères chefs-lieux</span>
          </label>
        </div>
      </div>

      {status === 'loading' && <div className="citizen-map-placeholder">🗺️ Chargement du découpage territorial tunisien…</div>}

      <div
        ref={containerRef}
        className="citizen-map"
        style={{ display: status === 'ready' ? 'block' : 'none', height: '480px' }}
      />

      {status === 'ready' && (
        <div className="citizen-map-legend" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <span><i className="dot dot-green" /> Alimentation normale ({normalCount})</span>
          <span><i className="dot dot-red" /> Zone en coupure ({sheddingCount})</span>
          <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
            💡 Cliquez sur n'importe quelle zone pour voir ses quartiers et son statut
          </span>
        </div>
      )}
    </div>
  );
}
