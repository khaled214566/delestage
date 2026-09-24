"""
Dissolve the 264 delegation polygons in ``tunisia_zones.geojson`` into a single
national boundary used by the public map for country emphasis + neighbour
dimming. Output: ``frontend/public/data/tunisia_border.geojson``.

The border is intentionally simplified (~500 m tolerance): it is a visual
emphasis layer, not an analytical dataset, so a lighter geometry keeps the map
responsive without changing what the citizen sees.

Run from the repo root:  python backend/data/build_tunisia_border.py
"""
from __future__ import annotations

import json
import os

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

SRC = "frontend/public/data/tunisia_zones.geojson"
OUT = "frontend/public/data/tunisia_border.geojson"
# Douglas-Peucker tolerance in degrees (~0.006 deg ≈ 600 m at Tunisia's latitude).
SIMPLIFY_TOLERANCE = 0.006


def main() -> None:
    with open(SRC, "r", encoding="utf-8") as fh:
        collection = json.load(fh)

    geoms = [shape(feat["geometry"]) for feat in collection["features"]]
    # Dissolve every delegation into one national geometry, then buffer(0) to
    # heal the slivers left between adjacent administrative polygons.
    national = unary_union(geoms).buffer(0)
    national = national.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)

    bounds = national.bounds  # (minx, miny, maxx, maxy)
    out = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Tunisie",
                    "name_ar": "تونس",
                    "bbox": list(bounds),
                },
                "geometry": mapping(national),
            }
        ],
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)

    size_kb = os.path.getsize(OUT) / 1024
    print(f"Dissolved {len(geoms)} delegations -> {national.geom_type}")
    print(f"National bounds: {tuple(round(b, 3) for b in bounds)}")
    print(f"Wrote {OUT} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
