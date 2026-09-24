/**
 * Central geographic + camera configuration for the public network map.
 *
 * Everything that positions or constrains the Tunisia map lives here so the map
 * component stays free of scattered magic coordinates. Bounds are derived from
 * the real national extent (see backend/data/build_tunisia_border.py), padded
 * with a small margin so navigation stays Tunisia-focused without feeling caged.
 */

export type LatLng = { lat: number; lng: number };
export type LatLngBounds = { north: number; south: number; east: number; west: number };

// Real dissolved extent of Tunisia: lat 30.23–37.54, lng 7.52–11.60.
// Geographic centre used as the camera anchor.
export const TUNISIA_CENTER: LatLng = { lat: 33.9, lng: 9.55 };

// Tight framing bounds — used with fitBounds() so the country fills the viewport
// on load regardless of container size (Tunisia is tall and narrow).
export const TUNISIA_FIT_BOUNDS: LatLngBounds = {
  north: 37.7,
  south: 30.0,
  east: 11.9,
  west: 7.3,
};

// Pan/zoom restriction bounds — a modest margin around the country so the user
// can explore Tunisia but not wander across North Africa.
export const TUNISIA_MAP_BOUNDS: LatLngBounds = {
  north: 38.4,
  south: 29.3,
  east: 12.9,
  west: 6.3,
};

// Camera defaults. Tilt is deliberately subtle: at national altitude the map
// should read as a GIS surface with depth, not a dramatic fly-through.
export const TUNISIA_CAMERA = {
  defaultZoom: 6.4,
  minZoom: 6,
  maxZoom: 15,
  localityZoom: 11,
  defaultTilt: 42.5,
  defaultHeading: 0,
} as const;

// Operational status model shown on the public map and in panels. Colour is a
// support for the label, never the only signal (see accessibility requirements).
export type NetworkStatus = 'NORMAL' | 'ACTIVE' | 'SCHEDULED' | 'UNAVAILABLE';

export interface StatusMeta {
  key: NetworkStatus;
  /** Short French label shown to citizens. */
  label: string;
  /** Solid brand colour for dots, borders, panel accents. */
  color: string;
  /** Polygon fill opacity when idle / when hovered or selected. */
  fillOpacity: number;
  fillOpacityActive: number;
}

export const STATUS_META: Record<NetworkStatus, StatusMeta> = {
  NORMAL: {
    key: 'NORMAL',
    label: 'Alimenté',
    color: '#1f9d57',
    fillOpacity: 0.1,
    fillOpacityActive: 0.28,
  },
  ACTIVE: {
    key: 'ACTIVE',
    label: 'Délestage en cours',
    color: '#d1372b',
    fillOpacity: 0.3,
    fillOpacityActive: 0.5,
  },
  SCHEDULED: {
    key: 'SCHEDULED',
    label: 'Délestage programmé',
    color: '#d98324',
    fillOpacity: 0.24,
    fillOpacityActive: 0.44,
  },
  UNAVAILABLE: {
    key: 'UNAVAILABLE',
    label: 'Données indisponibles',
    color: '#93a1b0',
    fillOpacity: 0.08,
    fillOpacityActive: 0.2,
  },
};

// Restrained basemap: light neutral land, muted water, no POIs, minimal roads —
// the electricity choropleth and national border stay the focal point.
export const MAP_STYLE: google.maps.MapTypeStyle[] = [
  { elementType: 'geometry', stylers: [{ color: '#eef1f4' }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#7c8896' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#ffffff' }, { weight: 2 }] },
  { featureType: 'administrative', elementType: 'geometry', stylers: [{ visibility: 'off' }] },
  { featureType: 'administrative.country', elementType: 'geometry.stroke', stylers: [{ color: '#c3ccd6' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#5b6b7f' }] },
  { featureType: 'administrative.province', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#e7ebef' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#dfe4e9' }] },
  { featureType: 'road', elementType: 'labels', stylers: [{ visibility: 'off' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#d4dae0' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#c5d4e2' }] },
  { featureType: 'water', elementType: 'labels', stylers: [{ visibility: 'off' }] },
];
