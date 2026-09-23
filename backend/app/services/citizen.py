"""
M10 — Citizen platform: public read-only endpoint.

Exposes current and next-24h shedding slots per zone — no auth required.
No feeder IDs, no P0 sites, no operator-sensitive data.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import ShedEvent
from app.models.hierarchy import Feeder
from app.models.enums import EventStatus, PriorityLevel


BCC_METADATA = {
    "BCC1": {
        "display_name": "Centre Tunis & Grand Tunis",
        "region": "Nord",
        "governorates": "Tunis, Ariana, Ben Arous, Manouba",
    },
    "BCC2": {
        "display_name": "Centre Nabeul & Cap Bon",
        "region": "Nord",
        "governorates": "Nabeul, Zaghouan",
    },
    "BCC3": {
        "display_name": "Centre Sousse & Sahel",
        "region": "Nord",
        "governorates": "Sousse, Monastir, Mahdia, Kairouan",
    },
    "BCC4": {
        "display_name": "Centre Bizerte & Nord-Ouest",
        "region": "Nord",
        "governorates": "Bizerte, Béja, Jendouba, Le Kef, Siliana",
    },
    "BCC5": {
        "display_name": "Centre Sfax & Centre-Ouest",
        "region": "Sud",
        "governorates": "Sfax, Sidi Bouzid, Kasserine",
    },
    "BCC6": {
        "display_name": "Centre Gabès & Sud-Est",
        "region": "Sud",
        "governorates": "Gabès, Médenine, Tataouine, Djerba",
    },
    "BCC7": {
        "display_name": "Centre Gafsa & Sud-Ouest",
        "region": "Sud",
        "governorates": "Gafsa, Tozeur, Kébili",
    },
}


async def get_citizen_view(db: AsyncSession) -> dict:
    """Return a public-safe snapshot of current and upcoming shedding."""
    now = datetime.now(timezone.utc)

    # Fetch active OPEN events (no P0 feeders — filtered by joining Feeder)
    stmt = (
        select(ShedEvent, Feeder)
        .join(Feeder, ShedEvent.feeder_id == Feeder.id)
        .where(
            and_(
                ShedEvent.status == EventStatus.OPEN,
                Feeder.priority != PriorityLevel.P0,
            )
        )
    )
    rows = (await db.execute(stmt)).all()

    # Group by BCC (zone_id)
    zones: dict[str, dict] = {}
    for event, feeder in rows:
        zone = feeder.bcc_id
        meta = BCC_METADATA.get(zone, {
            "display_name": f"Centre {zone}",
            "region": "National",
            "governorates": zone,
        })
        if zone not in zones:
            zones[zone] = {
                "zone_id": zone,
                "display_name": meta["display_name"],
                "region": meta["region"],
                "governorates": meta["governorates"],
                "status": "SHEDDING",
                "events": [],
            }
        duration = event.compute_duration(now) if event.open_time else 0.0
        estimated_end = None
        if event.open_time:
            # Estimate based on default 45-min cap
            estimated_end = (event.open_time + timedelta(minutes=45)).isoformat()

        zones[zone]["events"].append({
            "started_at": event.open_time.isoformat() if event.open_time else None,
            "estimated_end": estimated_end,
            "alarm_level": event.get_alarm_level(45.0, now).value,
            "duration_min": int(duration),
            "feeders_affected": 1,
        })

    # Consolidate zones
    zone_list = []
    for zone_id in sorted(zones.keys()):
        z = zones[zone_id]
        z["feeders_affected"] = len(z["events"])
        zone_list.append(z)

    # Add zones that are currently NORMAL
    for bcc, meta in sorted(BCC_METADATA.items()):
        if bcc not in zones:
            zone_list.append({
                "zone_id": bcc,
                "display_name": meta["display_name"],
                "region": meta["region"],
                "governorates": meta["governorates"],
                "status": "NORMAL",
                "events": [],
                "feeders_affected": 0,
            })

    # Sort: shedding zones first, then alphabetically
    zone_list.sort(key=lambda z: (0 if z["status"] == "SHEDDING" else 1, z["zone_id"]))

    return {
        "generated_at": now.isoformat(),
        "total_zones": len(BCC_METADATA),
        "currently_shedding": len(zones),
        "zones": zone_list,
    }
