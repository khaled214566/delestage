"""
M11 — Demo Simulator service.

Runs a scripted 4-beat demo scenario using the existing API services:
  Beat 1 (J-1 Plan):  Overview — explains what will happen
  Beat 2 (Live +50 MW): Open 5 feeders in BCC1 via simulate_event_toggle
  Beat 3 (Rotation):  Set a feeder's open_time to 37 min ago → triggers AMBER alarm
  Beat 4 (Audit):     Verify the SHA-256 hash chain is intact

Reset: close all demo-opened events.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EventStatus, FeederStatus
from app.models.event import ShedEvent
from app.models.hierarchy import Feeder
from app.services.audit import log as audit_log, verify_chain
from app.services.monitoring import simulate_event_toggle, get_monitoring_summary
from app.core.websocket import ws_manager

DEMO_ACTOR_ID = "0"
DEMO_ACTOR_NAME = "Simulateur Démo"

# Tag demo events by a fixed bcc_id "BCC1" for cleanup
DEMO_BCC1 = "BCC1"
DEMO_BCC2 = "BCC2"

# ─── Beat 1: Info/Plan J-1 ────────────────────────────────────────────────────

async def run_beat1_j1_plan(db: AsyncSession) -> dict:
    """
    Beat 1 is informational — explain the J-1 plan context.
    No DB writes needed (plan was created at seed time if any).
    Just return the scenario description.
    """
    return {
        "beat": 1,
        "label": "📋 Plan J-1 — 300 MW de déficit",
        "status": "ok",
        "scenario": {
            "step": "J-1",
            "description": "Le Dispatching National prévoit 300 MW de déficit pour la tranche 20h-20h30. "
                           "La plateforme calcule : BCC1→90 MW, BCC2→75 MW, BCC3→50 MW…",
            "target_mw": 300,
            "slots": 2,
            "period": "20h00 – 21h00",
        },
        "message": "Scénario J-1 prêt — cliquez sur Beat 2 pour simuler la hausse du déficit en direct.",
    }


# ─── Beat 2: Live +50 MW ──────────────────────────────────────────────────────

async def run_beat2_live_increase(db: AsyncSession) -> dict:
    """Open 5 BCC1 feeders simulating a live +50 MW deficit increase."""
    now = datetime.now(timezone.utc)

    # Pick 5 CLOSED non-P0 feeders from BCC1
    from app.models.enums import PriorityLevel
    result = await db.execute(
        select(Feeder)
        .where(
            Feeder.bcc_id == DEMO_BCC1,
            Feeder.status == FeederStatus.CLOSED,
            Feeder.priority != PriorityLevel.P0,
        )
        .limit(5)
    )
    feeders = list(result.scalars().all())

    opened = []
    total_mw = 0.0
    for feeder in feeders:
        ev = await simulate_event_toggle(db, feeder.id, open_state=True)
        opened.append({"feeder_id": feeder.id, "mw": feeder.avg_mw})
        total_mw += feeder.avg_mw

    await audit_log(
        db,
        actor_id=DEMO_ACTOR_ID,
        actor_name=DEMO_ACTOR_NAME,
        action="DEMO_BEAT2",
        entity_type="simulation",
        entity_id="bcc1",
        payload={"feeders_opened": len(opened), "mw": round(total_mw, 1)},
    )
    await db.commit()

    return {
        "beat": 2,
        "label": "⚡ Hausse en direct — +50 MW",
        "status": "ok",
        "feeders_opened": opened,
        "total_mw_added": round(total_mw, 1),
        "message": f"{len(opened)} alimentateurs ouverts dans BCC1 "
                   f"(+{round(total_mw, 1)} MW). Vérifiez le Monitoring en direct.",
    }


# ─── Beat 3: Rotation ─────────────────────────────────────────────────────────

async def run_beat3_rotation(db: AsyncSession) -> dict:
    """Backdate a BCC2 open event to 37 minutes ago, triggering AMBER alarm."""
    now = datetime.now(timezone.utc)
    from app.models.enums import PriorityLevel

    # Find an existing OPEN event in BCC2, or open one
    open_result = await db.execute(
        select(ShedEvent)
        .join(Feeder, ShedEvent.feeder_id == Feeder.id)
        .where(ShedEvent.status == EventStatus.OPEN, ShedEvent.bcc_id == DEMO_BCC2)
        .limit(1)
    )
    event = open_result.scalar_one_or_none()

    if event is None:
        # Open a BCC2 feeder first
        feeder_result = await db.execute(
            select(Feeder)
            .where(
                Feeder.bcc_id == DEMO_BCC2,
                Feeder.status == FeederStatus.CLOSED,
                Feeder.priority != PriorityLevel.P0,
            )
            .limit(1)
        )
        feeder = feeder_result.scalar_one_or_none()
        if feeder is None:
            return {
                "beat": 3,
                "status": "skip",
                "message": "Aucun alimentateur disponible dans BCC2 — relancez Reset d'abord.",
            }
        ev = await simulate_event_toggle(db, feeder.id, open_state=True)
        await db.flush()
        event = ev

    # Backdate to 37 minutes ago
    event.open_time = now - timedelta(minutes=37)

    await audit_log(
        db,
        actor_id=DEMO_ACTOR_ID,
        actor_name=DEMO_ACTOR_NAME,
        action="DEMO_BEAT3",
        entity_type="simulation",
        entity_id=event.feeder_id,
        payload={"duration_min": 37, "alarm": "AMBER", "feeder_id": event.feeder_id},
    )
    await db.commit()

    # Broadcast updated monitoring
    try:
        summary = await get_monitoring_summary(db)
        await ws_manager.broadcast(summary.model_dump(mode="json"))
    except Exception:
        pass

    return {
        "beat": 3,
        "label": "🔄 Rotation — Alerte durée prolongée",
        "status": "ok",
        "feeder_id": event.feeder_id,
        "bcc_id": DEMO_BCC2,
        "duration_min": 37,
        "alarm_level": "AMBER",
        "message": f"Alimentateur {event.feeder_id} est à 37 min "
                   f"(seuil: 80% × 45 min = 36 min). "
                   f"Allez dans 'Conduite BCC' → 'Panneau de rotation' pour accepter.",
    }


# ─── Beat 4: Preuve Audit ─────────────────────────────────────────────────────

async def run_beat4_audit(db: AsyncSession) -> dict:
    """Verify SHA-256 hash chain integrity."""
    result = await verify_chain(db)

    await audit_log(
        db,
        actor_id=DEMO_ACTOR_ID,
        actor_name=DEMO_ACTOR_NAME,
        action="DEMO_BEAT4",
        entity_type="simulation",
        entity_id="audit_chain",
        payload={"chain_ok": result["ok"], "total_checked": result["total_checked"]},
    )
    await db.commit()

    return {
        "beat": 4,
        "label": "🔐 Preuve — Intégrité de la chaîne d'audit SHA-256",
        "status": "ok",
        "chain_ok": result["ok"],
        "total_checked": result["total_checked"],
        "broken_at_seq": result["broken_at_seq"],
        "message": (
            f"✅ Chaîne intacte — {result['total_checked']} enregistrements vérifiés. "
            "Allez dans Administration → Journal d'Audit → 'Vérifier la chaîne' pour voir l'interface."
            if result["ok"]
            else f"❌ Rupture détectée à seq={result['broken_at_seq']}"
        ),
    }


# ─── Reset ────────────────────────────────────────────────────────────────────

async def reset_demo(db: AsyncSession) -> dict:
    """Close all currently OPEN shed events and restore feeders."""
    now = datetime.now(timezone.utc)

    open_events_result = await db.execute(
        select(ShedEvent).where(ShedEvent.status == EventStatus.OPEN)
    )
    events = list(open_events_result.scalars().all())
    feeder_ids = []

    for ev in events:
        duration = (now - ev.open_time).total_seconds() / 60.0
        ev.close_time = now
        ev.duration_min = round(duration, 1)
        ev.ens_mwh = round(ev.mw_actual * duration / 60.0, 3)
        ev.status = EventStatus.CLOSED
        feeder_ids.append(ev.feeder_id)

    if feeder_ids:
        await db.execute(
            update(Feeder)
            .where(Feeder.id.in_(feeder_ids))
            .values(status=FeederStatus.CLOSED)
        )

    await audit_log(
        db,
        actor_id=DEMO_ACTOR_ID,
        actor_name=DEMO_ACTOR_NAME,
        action="DEMO_RESET",
        entity_type="simulation",
        entity_id="all",
        payload={"feeders_restored": len(feeder_ids), "events_closed": len(events)},
    )
    await db.commit()

    # Broadcast clean state
    try:
        summary = await get_monitoring_summary(db)
        await ws_manager.broadcast(summary.model_dump(mode="json"))
    except Exception:
        pass

    return {
        "status": "reset",
        "feeders_restored": len(feeder_ids),
        "events_closed": len(events),
        "message": f"✅ Démo réinitialisée — {len(feeder_ids)} alimentateurs restaurés",
    }
