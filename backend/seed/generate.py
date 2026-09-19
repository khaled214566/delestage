"""Deterministic seed data generator for the national grid.

Usage:
    cd backend
    python -m seed.generate

Uses NumPy with fixed seed=42 for reproducibility.
"""
import numpy as np
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import Crc, Bcc, Substation, Feeder, FeederHistory, Parameters
from app.models.enums import PriorityLevel, FeederStatus

rng = np.random.default_rng(42)

CRCS = [
    {"id": "CRC_N", "name": "CRC Nord", "share_key": 0.67},
    {"id": "CRC_S", "name": "CRC Sud", "share_key": 0.33},
]

BCCS = [
    {"id": "BCC1", "name": "BCC Tunis", "crc_id": "CRC_N", "managed_load_mw": 420.0, "area_km2": 1200.0},
    {"id": "BCC2", "name": "BCC Nabeul", "crc_id": "CRC_N", "managed_load_mw": 360.0, "area_km2": 3100.0},
    {"id": "BCC3", "name": "BCC Sousse", "crc_id": "CRC_N", "managed_load_mw": 240.0, "area_km2": 2800.0},
    {"id": "BCC4", "name": "BCC Bizerte", "crc_id": "CRC_N", "managed_load_mw": 180.0, "area_km2": 3500.0},
    {"id": "BCC5", "name": "BCC Sfax", "crc_id": "CRC_S", "managed_load_mw": 310.0, "area_km2": 4800.0},
    {"id": "BCC6", "name": "BCC Gabès", "crc_id": "CRC_S", "managed_load_mw": 190.0, "area_km2": 6200.0},
    {"id": "BCC7", "name": "BCC Gafsa", "crc_id": "CRC_S", "managed_load_mw": 130.0, "area_km2": 7100.0},
]

PRIORITY_DIST = {
    PriorityLevel.P0: 0.08,
    PriorityLevel.P1: 0.05,
    PriorityLevel.P2: 0.10,
    PriorityLevel.P3: 0.35,
    PriorityLevel.P4: 0.30,
    PriorityLevel.P5: 0.12,
}
PRIORITIES = list(PRIORITY_DIST.keys())
PRIORITY_PROBS = list(PRIORITY_DIST.values())


def generate_feeders(bcc_id, managed_load_mw):
    feeders = []
    current_mw = 0.0
    f_num = 1
    
    # 3 substations per BCC
    substations = []
    for s_idx in range(1, 4):
        sub_id = f"SS-{bcc_id}-{s_idx}"
        substations.append(Substation(id=sub_id, name=f"Poste {bcc_id} - {s_idx}", bcc_id=bcc_id))
    
    while current_mw < managed_load_mw:
        avg_mw = round(rng.uniform(5.0, 20.0), 1)
        if current_mw + avg_mw > managed_load_mw * 1.05:
            break
            
        priority = rng.choice(PRIORITIES, p=PRIORITY_PROBS)
        critical = priority == PriorityLevel.P0
        
        feeder = Feeder(
            id=f"F-{bcc_id}-{f_num}",
            name=f"Depart {f_num} {bcc_id}",
            substation_id=rng.choice([s.id for s in substations]),
            bcc_id=bcc_id,
            priority=priority,
            critical=bool(critical),
            avg_mw=float(avg_mw),
            zone_id=f"Z-{bcc_id}-{f_num}",
            status=FeederStatus.CLOSED,
        )
        feeders.append(feeder)
        current_mw += avg_mw
        f_num += 1
        
    return substations, feeders


def generate_history(feeder):
    if feeder.critical:
        return FeederHistory(
            feeder_id=feeder.id,
            cumulative_minutes=0,
            rotations=0,
            last_shed_start=None,
            last_shed_end=None,
        )
    
    has_history = rng.random() > 0.3
    if has_history:
        cumulative_minutes = int(rng.integers(0, 301))
        rotations = int(rng.integers(0, 9))
        days_ago = rng.uniform(0.1, 7.0)
        end_time = datetime.now(timezone.utc) - timedelta(days=days_ago)
        start_time = end_time - timedelta(minutes=int(rng.integers(15, 46)))
        return FeederHistory(
            feeder_id=feeder.id,
            cumulative_minutes=cumulative_minutes,
            rotations=rotations,
            last_shed_start=start_time,
            last_shed_end=end_time,
        )
    else:
        return FeederHistory(
            feeder_id=feeder.id,
            cumulative_minutes=0,
            rotations=0,
            last_shed_start=None,
            last_shed_end=None,
        )


def main():
    engine = create_engine(settings.database_url_sync, echo=False)
    with Session(engine) as session:
        print("Clearing existing data...")
        session.execute(text("TRUNCATE TABLE crc CASCADE"))
        session.execute(text("TRUNCATE TABLE parameters CASCADE"))
        session.commit()
        
        print("Inserting Parameters...")
        session.add(Parameters())
        
        print("Inserting CRCs...")
        for c in CRCS:
            session.add(Crc(**c))
            
        print("Inserting BCCs, Substations, and Feeders...")
        total_feeders = 0
        p0_count = 0
        sheddable_mw = 0.0
        
        for b in BCCS:
            session.add(Bcc(**b))
            substations, feeders = generate_feeders(b["id"], b["managed_load_mw"])
            session.add_all(substations)
            session.commit()
            
            for feeder in feeders:
                session.add(feeder)
                session.add(generate_history(feeder))
                total_feeders += 1
                if feeder.critical:
                    p0_count += 1
                else:
                    sheddable_mw += feeder.avg_mw
            session.commit()
            
        print("Creating view v_sheddable_feeders...")
        view_sql = """
        CREATE OR REPLACE VIEW v_sheddable_feeders AS
        SELECT f.*, fh.cumulative_minutes, fh.rotations, fh.last_shed_end
        FROM feeder f
        JOIN feeder_history fh ON fh.feeder_id = f.id
        WHERE f.priority != 'P0'
          AND f.critical = false
          AND f.status NOT IN ('MAINTENANCE', 'UNAVAILABLE');
        """
        session.execute(text(view_sql))
        session.commit()
        
        print("\n--- SEED SUMMARY ---")
        print(f"Total feeders: {total_feeders}")
        print(f"P0 (critical) count: {p0_count}")
        print(f"Non-P0 sheddable load: {sheddable_mw:.1f} MW")

if __name__ == "__main__":
    main()
