// Approximate city-center coordinates for Tunisia's governorates (plus a couple of
// named places used by BCC_METADATA on the backend, e.g. Djerba). Static reference
// data — the citizen platform never has per-city grid data, only per-BCC-zone status,
// so each governorate is plotted as one point colored by its zone's status.
export const GOVERNORATE_COORDINATES: Record<string, [number, number]> = {
  'Tunis': [36.8065, 10.1815],
  'Ariana': [36.8625, 10.1956],
  'Ben Arous': [36.7533, 10.2189],
  'Manouba': [36.8081, 10.0972],
  'Nabeul': [36.4561, 10.7376],
  'Zaghouan': [36.4028, 10.1428],
  'Sousse': [35.8256, 10.6411],
  'Monastir': [35.7780, 10.8262],
  'Mahdia': [35.5047, 11.0622],
  'Kairouan': [35.6784, 10.0963],
  'Bizerte': [37.2744, 9.8739],
  'Béja': [36.7256, 9.1817],
  'Jendouba': [36.5011, 8.7803],
  'Le Kef': [36.1826, 8.7148],
  'Siliana': [36.0844, 9.3708],
  'Sfax': [34.7406, 10.7603],
  'Sidi Bouzid': [35.0381, 9.4858],
  'Kasserine': [35.1675, 8.8362],
  'Gabès': [33.8815, 10.0982],
  'Médenine': [33.3549, 10.5055],
  'Tataouine': [32.9297, 10.4518],
  'Djerba': [33.8076, 10.8451],
  'Gafsa': [34.4250, 8.7842],
  'Tozeur': [33.9197, 8.1335],
  'Kébili': [33.7044, 8.9690],
};

// Geographic center used to frame the initial map view over Tunisia.
export const TUNISIA_CENTER: [number, number] = [34.4, 9.6];
export const TUNISIA_DEFAULT_ZOOM = 7;
