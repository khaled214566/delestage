import { useEffect, useRef, useState } from 'react';
import type { CitizenZone } from '../api/client';
import { GOVERNORATE_COORDINATES, TUNISIA_CENTER, TUNISIA_DEFAULT_ZOOM } from '../data/governorateCoordinates';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;

const COLOR_NORMAL = '#38a169';   // matches the existing "Alimentation Normale" green
const COLOR_SHEDDING = '#e53e3e'; // matches the existing live/alert red

// Muted, low-contrast basemap so the red/green status dots stay the focal point.
const MAP_STYLE: google.maps.MapTypeStyle[] = [
  { elementType: 'geometry', stylers: [{ color: '#f5f7fa' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#718096' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#ffffff' }] },
  { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#cbd5e0' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#bee3f8' }] },
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
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&loading=async`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Impossible de charger Google Maps.'));
    document.head.appendChild(script);
  });
  return scriptLoadingPromise;
}

interface MapPoint {
  governorate: string;
  position: [number, number];
  zone: CitizenZone;
}

function buildPoints(zones: CitizenZone[]): MapPoint[] {
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

// Small fixed-size colored dot — stays a "pixel" at any zoom level instead of
// scaling with the map's geographic distance (which a Circle overlay would do).
function dotIcon(color: string): google.maps.Symbol {
  return {
    path: google.maps.SymbolPath.CIRCLE,
    fillColor: color,
    fillOpacity: 1,
    strokeColor: '#ffffff',
    strokeWeight: 1.5,
    scale: 7,
  };
}

export default function CitizenMap({ zones }: { zones: CitizenZone[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const infoWindowRef = useRef<google.maps.InfoWindow | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'no-key'>('loading');

  // Load the script and create the map once.
  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) {
      setStatus('no-key');
      return;
    }
    let cancelled = false;
    loadGoogleMaps(GOOGLE_MAPS_API_KEY)
      .then(() => {
        if (cancelled || !containerRef.current) return;
        mapRef.current = new google.maps.Map(containerRef.current, {
          center: { lat: TUNISIA_CENTER[0], lng: TUNISIA_CENTER[1] },
          zoom: TUNISIA_DEFAULT_ZOOM,
          minZoom: 6,
          maxZoom: 14,
          styles: MAP_STYLE,
          streetViewControl: false,
          mapTypeControl: false,
          fullscreenControl: true,
          restriction: {
            latLngBounds: { north: 38.2, south: 30.0, east: 12.5, west: 6.5 },
            strictBounds: false,
          },
        });
        infoWindowRef.current = new google.maps.InfoWindow();
        setStatus('ready');
      })
      .catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, []);

  // Redraw markers whenever zone statuses change (e.g. the 10s auto-refresh).
  useEffect(() => {
    if (status !== 'ready' || !mapRef.current) return;

    markersRef.current.forEach(m => m.setMap(null));
    markersRef.current = buildPoints(zones).map(point => {
      const isShedding = point.zone.status === 'SHEDDING';
      const marker = new google.maps.Marker({
        position: { lat: point.position[0], lng: point.position[1] },
        map: mapRef.current!,
        icon: dotIcon(isShedding ? COLOR_SHEDDING : COLOR_NORMAL),
        title: point.governorate,
      });
      marker.addListener('click', () => {
        const ev = point.zone.events[0];
        const html = `
          <div style="font-family:inherit;min-width:200px">
            <strong style="font-size:0.95rem">${point.governorate}</strong>
            <div style="font-size:0.8rem;color:#718096;margin-bottom:0.4rem">${point.zone.display_name}</div>
            <div style="font-size:0.85rem;font-weight:600;color:${isShedding ? COLOR_SHEDDING : COLOR_NORMAL}">
              ${isShedding ? '⚡ Coupure en cours' : '✅ Alimentation normale'}
            </div>
            ${isShedding && ev ? `
              <div style="font-size:0.78rem;color:#4a5568;margin-top:0.35rem">
                Rétablissement estimé : ${ev.estimated_end ? new Date(ev.estimated_end).toLocaleTimeString('fr-FR') : 'Sous 45 min'}
              </div>` : ''}
          </div>`;
        infoWindowRef.current?.setContent(html);
        infoWindowRef.current?.open({ map: mapRef.current!, anchor: marker });
      });
      return marker;
    });
  }, [zones, status]);

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
      {status === 'loading' && <div className="citizen-map-placeholder">🗺️ Chargement de la carte…</div>}
      <div ref={containerRef} className="citizen-map" style={{ display: status === 'ready' ? 'block' : 'none' }} />
      {status === 'ready' && (
        <div className="citizen-map-legend">
          <span><i className="dot dot-green" /> Alimentation normale</span>
          <span><i className="dot dot-red" /> Coupure en cours</span>
        </div>
      )}
    </div>
  );
}
