"""Deterministic synthetic national grid (module M1).

Usage (from ``backend/``, or ``docker compose exec api ...``)::

    python -m seed.generate                  # (re)seed the database
    python -m seed.generate --fingerprint    # build in memory, print summary + fingerprint, no DB

The generator is split in two on purpose:

* ``build_network()``  is *pure*: same seed -> byte-identical data. It never
  touches the database or the clock, so it is trivial to unit-test.
* ``write_network()``  replaces the grid tables in ONE transaction.

Determinism rules: fixed NumPy seed, fixed ``REFERENCE_TIME`` (never ``now()``),
contiguous/balanced assignments instead of random ones wherever possible, and
exact quotas (largest remainder) instead of independent random draws, so a
small BCC can never end up with zero P0 feeders by bad luck.

WARNING: seeding TRUNCATEs the grid tables (crc, bcc, substation, feeder,
feeder_history, parameters) and everything that references them. Dev only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import csv
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

DEFAULT_SEED = 42

# "Now" of the synthetic world. Histories are generated relative to this
# instant, which is what makes the dataset reproducible. It is the evening of
# the demo scenario in the project documentation (19 Sept 2026).
REFERENCE_TIME = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Static topology (from the project documentation, section 8.1)
# ---------------------------------------------------------------------------
CRCS = [
    {"id": "CRC_N", "name": "CRC Nord", "share_key": 0.67},
    {"id": "CRC_S", "name": "CRC Sud", "share_key": 0.33},
]

BCCS = [
    {"id": "BCC1", "name": "BCC Tunis (Grand Tunis)", "crc_id": "CRC_N", "managed_load_mw": 420.0, "area_km2": 1200.0},
    {"id": "BCC2", "name": "BCC Nabeul (Cap Bon)", "crc_id": "CRC_N", "managed_load_mw": 360.0, "area_km2": 3100.0},
    {"id": "BCC3", "name": "BCC Sousse (Sahel)", "crc_id": "CRC_N", "managed_load_mw": 240.0, "area_km2": 2800.0},
    {"id": "BCC4", "name": "BCC Bizerte (Nord-Ouest)", "crc_id": "CRC_N", "managed_load_mw": 180.0, "area_km2": 3500.0},
    {"id": "BCC5", "name": "BCC Sfax (Sfax)", "crc_id": "CRC_S", "managed_load_mw": 310.0, "area_km2": 4800.0},
    {"id": "BCC6", "name": "BCC Gabès (Sud-Est)", "crc_id": "CRC_S", "managed_load_mw": 190.0, "area_km2": 6200.0},
    {"id": "BCC7", "name": "BCC Gafsa (Sud-Ouest)", "crc_id": "CRC_S", "managed_load_mw": 130.0, "area_km2": 7100.0},
]

# Three substations per BCC: (zone code, substation name, local label).
# Zone codes are globally unique because zone_id = "Z-<CODE>-<n>" is what the
# citizen platform (M10) will search on.
SUBSTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "BCC1": [("LAC", "Poste Source Lac", "Lac"), ("ARI", "Poste Ariana", "Ariana"), ("BEN", "Poste Ben Arous", "Ben Arous")],
    "BCC2": [("NAB", "Poste Nabeul", "Nabeul"), ("HAM", "Poste Hammamet", "Hammamet"), ("KEL", "Poste Kélibia", "Kélibia")],
    "BCC3": [("SOU", "Poste Sousse", "Sousse"), ("MON", "Poste Monastir", "Monastir"), ("MHD", "Poste Mahdia", "Mahdia")],
    "BCC4": [("BIZ", "Poste Bizerte", "Bizerte"), ("MBO", "Poste Menzel Bourguiba", "Menzel Bourguiba"), ("BEJ", "Poste Béja", "Béja")],
    "BCC5": [("SFX", "Poste Sfax Centre", "Sfax Centre"), ("SKZ", "Poste Sakiet Ezzit", "Sakiet Ezzit"), ("MHR", "Poste Mahrès", "Mahrès")],
    "BCC6": [("GAB", "Poste Gabès", "Gabès"), ("MED", "Poste Médenine", "Médenine"), ("ZAR", "Poste Zarzis", "Zarzis")],
    "BCC7": [("GAF", "Poste Gafsa", "Gafsa"), ("TOZ", "Poste Tozeur", "Tozeur"), ("KEB", "Poste Kébili", "Kébili")],
}

# ---------------------------------------------------------------------------
# Generation parameters
# ---------------------------------------------------------------------------
TARGET_AVG_FEEDER_MW = 10.8      # 1830 MW / 10.8 ~ 170 feeders (plan: 150-190)
MW_JITTER = (0.6, 1.4)           # per-feeder size multiplier before normalisation
P0_SHARE = 0.08                  # ~8% of feeders never shed (hospitals, water, airports)
# Mix of the NON-P0 feeders, in percent. Most are P3-P5 as required by the plan.
NON_P0_MIX = {"P1": 5, "P2": 10, "P3": 33, "P4": 30, "P5": 14}
NEVER_SHED_SHARE = 0.25          # share of non-P0 feeders with no shedding history
RECENTLY_SHED_SHARE = 0.06       # of the shed ones: cut < 3 h ago -> inside rest time (demo of the rule)
SPECIAL_STATUS = {"BCC4": "MAINTENANCE", "BCC5": "UNAVAILABLE"}  # exercises v_sheddable_feeders
                                 # (BCC4 maintenance also matches use case 3 in the documentation)

DEFAULT_PARAMETERS = {
    "id": 1,
    "max_duration_min": 45,
    "rest_time_min": 180,
    "slot_size_min": 30,
    "rotation_warn_pct": 80,
    "regional_key": {"CRC_N": 0.67, "CRC_S": 0.33},
}


@dataclass(frozen=True)
class Network:
    crcs: list[dict]
    bccs: list[dict]
    substations: list[dict]
    feeders: list[dict]
    histories: list[dict]
    parameters: dict

    def fingerprint(self) -> str:
        """Stable SHA-256 of the whole dataset. Equal fingerprints == identical data."""
        blob = json.dumps(asdict(self), sort_keys=True, default=lambda o: o.isoformat())
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def apportion(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Largest-remainder apportionment: integer shares that sum EXACTLY to ``total``.

    Same technique the allocator (M5) will use for MW, so it is defined once here
    and covered by tests.
    """
    wsum = sum(weights.values())
    exact = {k: total * w / wsum for k, w in weights.items()}
    shares = {k: int(v) for k, v in exact.items()}
    leftover = total - sum(shares.values())
    by_remainder = sorted(exact, key=lambda k: (-(exact[k] - shares[k]), k))
    for k in by_remainder[:leftover]:
        shares[k] += 1
    return shares


def feeder_count(managed_load_mw: float) -> int:
    return max(3, round(managed_load_mw / TARGET_AVG_FEEDER_MW))


def size_feeders(rng: np.random.Generator, n: int, target_mw: float) -> list[float]:
    """n feeder sizes (0.1 MW resolution) that sum to ``target_mw``."""
    weights = rng.uniform(MW_JITTER[0], MW_JITTER[1], size=n)
    sizes = np.round(weights / weights.sum() * target_mw, 1)
    residual = round(target_mw - float(sizes.sum()), 1)   # rounding drift, at most a couple of MW
    sizes[int(np.argmax(sizes))] += residual              # absorbed by the largest feeder
    return [round(float(s), 1) for s in sizes]


def make_history(rng: np.random.Generator, priority: str, ref: datetime) -> dict:
    empty = {"cumulative_minutes": 0, "rotations": 0, "last_shed_start": None, "last_shed_end": None}
    if priority == "P0" or rng.random() < NEVER_SHED_SHARE:
        return empty
    rotations = int(rng.integers(1, 9))                    # 1..8 past cuts
    durations = rng.integers(15, 46, size=rotations)       # each 15..45 min
    minutes_ago = (
        int(rng.integers(20, 180)) if rng.random() < RECENTLY_SHED_SHARE
        else int(rng.integers(180, 7 * 24 * 60))
    )
    end = ref - timedelta(minutes=minutes_ago)
    start = end - timedelta(minutes=int(durations[-1]))
    return {
        "cumulative_minutes": int(durations.sum()),        # consistent with rotations
        "rotations": rotations,
        "last_shed_start": start,
        "last_shed_end": end,
    }


# Load real Tunisian delegation data if available
DELEGATIONS_BY_BCC: dict[str, list[dict]] = {}
try:
    _csv_file = Path(__file__).resolve().parent.parent / "data" / "tunisia_load_data.csv"
    if _csv_file.exists():
        with open(_csv_file, mode="r", encoding="utf-8") as _f:
            for _row in csv.DictReader(_f):
                DELEGATIONS_BY_BCC.setdefault(_row["bcc_id"], []).append(_row)
        for _b in DELEGATIONS_BY_BCC:
            DELEGATIONS_BY_BCC[_b].sort(key=lambda x: -int(x.get("population_2024", 0)))
except Exception:
    pass


def build_network(seed: int = DEFAULT_SEED, ref: datetime = REFERENCE_TIME) -> Network:
    rng = np.random.default_rng(seed)
    substations: list[dict] = []
    feeders: list[dict] = []
    histories: list[dict] = []

    for bcc in BCCS:
        bcc_id = bcc["id"]
        num = int(bcc_id.removeprefix("BCC"))
        subs = SUBSTATIONS[bcc_id]
        n = feeder_count(bcc["managed_load_mw"])

        for k, (_, name, _) in enumerate(subs, start=1):
            substations.append({"id": f"SS-{num}{k:02d}", "name": name, "bcc_id": bcc_id})

        # Exact priority quotas per BCC, then shuffled: every BCC gets >= 1 P0.
        n_p0 = max(1, round(P0_SHARE * n))
        quotas = apportion(n - n_p0, {p: float(w) for p, w in NON_P0_MIX.items()})
        quotas["P0"] = n_p0
        priorities = [p for p, q in sorted(quotas.items()) for _ in range(q)]
        priorities = [str(p) for p in rng.permutation(priorities)]

        sizes = size_feeders(rng, n, bcc["managed_load_mw"])

        # Optional special status on one non-P0 feeder of this BCC.
        special_idx = None
        if bcc_id in SPECIAL_STATUS:
            candidates = [i for i, p in enumerate(priorities) if p != "P0"]
            special_idx = candidates[int(rng.integers(0, len(candidates)))]

        dels = DELEGATIONS_BY_BCC.get(bcc_id, [])
        per_sub_count: dict[int, int] = {}
        for i in range(n):
            s_idx = i * len(subs) // n                       # contiguous, balanced blocks
            per_sub_count[s_idx] = per_sub_count.get(s_idx, 0) + 1
            j = per_sub_count[s_idx]                         # 1-based position in the substation
            zone_code, _, label = subs[s_idx]
            fid = f"F-{num}{i + 1:02d}"
            priority = priorities[i]

            # Assign real delegation if available, fallback to label + counter
            if dels:
                d = dels[i % len(dels)]
                suffix = f" {i // len(dels) + 1}" if n > len(dels) else ""
                feeder_name = f"Départ {d['name_fr']}{suffix}"
                zone_id = f"Z-{d['pcode']}"
            else:
                feeder_name = f"Départ {label} {j}"
                zone_id = f"Z-{zone_code}-{(j - 1) // 2 + 1}"

            feeders.append({
                "id": fid,
                "name": feeder_name,
                "substation_id": f"SS-{num}{s_idx + 1:02d}",
                "bcc_id": bcc_id,
                "priority": priority,
                "critical": priority == "P0",
                "avg_mw": sizes[i],
                "zone_id": zone_id,
                "status": SPECIAL_STATUS[bcc_id] if i == special_idx else "CLOSED",
                "created_at": ref - timedelta(days=90),
            })
            histories.append({"feeder_id": fid, **make_history(rng, priority, ref)})

    return Network(
        crcs=[dict(c) for c in CRCS],
        bccs=[dict(b) for b in BCCS],
        substations=substations,
        feeders=feeders,
        histories=histories,
        parameters=dict(DEFAULT_PARAMETERS, regional_key=dict(DEFAULT_PARAMETERS["regional_key"])),
    )


def summarize(net: Network) -> str:
    """Human-readable report, computed from the in-memory dataset."""
    sheddable = [f for f in net.feeders if f["priority"] != "P0" and not f["critical"]
                 and f["status"] not in ("MAINTENANCE", "UNAVAILABLE")]
    lines = ["", "--- SEED SUMMARY ---",
             f"{'BCC':<6}{'feeders':>8}{'P0':>4}{'feeder MW':>11}{'managed MW':>12}{'sheddable MW':>14}"]
    for b in net.bccs:
        fs = [f for f in net.feeders if f["bcc_id"] == b["id"]]
        lines.append(
            f"{b['id']:<6}{len(fs):>8}{sum(f['priority'] == 'P0' for f in fs):>4}"
            f"{sum(f['avg_mw'] for f in fs):>11.1f}{b['managed_load_mw']:>12.1f}"
            f"{sum(f['avg_mw'] for f in sheddable if f['bcc_id'] == b['id']):>14.1f}"
        )
    p0 = sum(f["priority"] == "P0" for f in net.feeders)
    mix = {p: sum(f["priority"] == p for f in net.feeders) for p in ("P0", "P1", "P2", "P3", "P4", "P5")}
    lines += [
        f"Total feeders     : {len(net.feeders)}  (P0: {p0} = {100 * p0 / len(net.feeders):.1f}%)",
        f"Priority mix      : {mix}",
        f"Non-P0 feeder MW  : {sum(f['avg_mw'] for f in net.feeders if f['priority'] != 'P0'):.1f} MW",
        f"Sheddable (view)  : {len(sheddable)} feeders, {sum(f['avg_mw'] for f in sheddable):.1f} MW",
        f"Not CLOSED        : {[(f['id'], f['status']) for f in net.feeders if f['status'] != 'CLOSED']}",
        f"Fingerprint       : {net.fingerprint()[:16]}  (must be identical on every run)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Database writer
# ---------------------------------------------------------------------------
def write_network(session, net: Network) -> None:
    """Replace the grid tables with ``net``. Caller owns the transaction."""
    from sqlalchemy import insert, text

    from app.models import Bcc, Crc, Feeder, FeederHistory, Parameters, Substation
    from app.models.enums import FeederStatus, PriorityLevel

    session.execute(text(
        "TRUNCATE TABLE feeder_history, feeder, substation, bcc, crc, parameters RESTART IDENTITY CASCADE"
    ))
    session.execute(insert(Parameters), [net.parameters])
    session.execute(insert(Crc), net.crcs)
    session.execute(insert(Bcc), net.bccs)
    session.execute(insert(Substation), net.substations)
    session.execute(insert(Feeder), [
        {**f, "priority": PriorityLevel(f["priority"]), "status": FeederStatus(f["status"])}
        for f in net.feeders
    ])
    session.execute(insert(FeederHistory), net.histories)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the synthetic national grid (M1).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="NumPy seed (default 42)")
    parser.add_argument("--fingerprint", action="store_true",
                        help="build in memory and print the summary/fingerprint; do not touch the database")
    args = parser.parse_args(argv)

    net = build_network(seed=args.seed)
    if args.fingerprint:
        print(summarize(net))
        return 0

    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    from app.core.config import settings

    if settings.app_env.lower() == "production":
        print("Refusing to seed: APP_ENV=production (seeding TRUNCATEs the grid tables).", file=sys.stderr)
        return 1

    engine = create_engine(settings.database_url_sync, echo=False)
    try:
        with engine.connect() as conn:
            if conn.execute(text("SELECT to_regclass('public.v_sheddable_feeders')")).scalar() is None:
                print("Schema not found. Run migrations first:  alembic upgrade head", file=sys.stderr)
                return 2
        with Session(engine) as session, session.begin():   # one transaction: all or nothing
            write_network(session, net)
            in_db = session.execute(text(
                "SELECT count(*), COALESCE(sum(avg_mw), 0) FROM v_sheddable_feeders"
            )).one()
    except SQLAlchemyError as exc:
        print(f"Database error: {exc.__class__.__name__}: {getattr(exc, 'orig', exc)}", file=sys.stderr)
        return 3

    print(summarize(net))
    print(f"Verified in DB    : v_sheddable_feeders = {in_db[0]} feeders, {float(in_db[1]):.1f} MW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
