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


async def get_citizen_view(db: AsyncSession) -> dict:
    """
    Return a public-safe snapshot of current and upcoming shedding.

    Returns:
        {
          "generated_at": ISO timestamp,
          "total_zones": int,
          "currently_shedding": int,   # number of zones with OPEN event
          "zones": [
            {
              "zone_id": "BCC1",
              "display_name": "Centre de Conduite BCC1",
              "status": "SHEDDING" | "NORMAL",
              "events": [
                {
                  "started_at": ISO | None,
                  "estimated_end": ISO | None,
                  "alarm_level": "GREEN" | "AMBER" | "RED",
                  "duration_min": int,
                  "feeders_affected": int   # count only, not IDs
                }
              ]
            }
          ]
        }
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=24)

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
        if zone not in zones:
            zones[zone] = {
                "zone_id": zone,
                "display_name": f"Zone {zone}",
                "status": "SHEDDING",
                "events": [],
            }
        duration = event.compute_duration(now) if event.open_time else 0.0
        estimated_end = None
        if event.open_time:
            # Estimate based on default 45-min cap if no planned end
            estimated_end = (event.open_time + timedelta(minutes=45)).isoformat()

        zones[zone]["events"].append({
            "started_at": event.open_time.isoformat() if event.open_time else None,
            "estimated_end": estimated_end,
            "alarm_level": event.get_alarm_level(45.0, now).value,
            "duration_min": int(duration),
            "feeders_affected": 1,  # aggregated per event
        })

    # Merge feeder counts: if same zone has multiple events, sum them
    zone_list = []
    for zone_id in sorted(zones.keys()):
        z = zones[zone_id]
        # Consolidate: count total feeders affected in this zone
        total_feeders = len(z["events"])
        z["feeders_affected"] = total_feeders
        zone_list.append(z)

    # Add zones that are currently NORMAL (no active events)
    # We list all known BCC zones
    all_bcc_ids = {"BCC1", "BCC2", "BCC3", "BCC4", "BCC5", "BCC6", "BCC7"}
    for bcc in sorted(all_bcc_ids):
        if bcc not in zones:
            zone_list.append({
                "zone_id": bcc,
                "display_name": f"Zone {bcc}",
                "status": "NORMAL",
                "events": [],
                "feeders_affected": 0,
            })

    # Sort: shedding zones first, then alphabetically
    zone_list.sort(key=lambda z: (0 if z["status"] == "SHEDDING" else 1, z["zone_id"]))

    return {
        "generated_at": now.isoformat(),
        "total_zones": len(all_bcc_ids),
        "currently_shedding": len(zones),
        "zones": zone_list,
    }
