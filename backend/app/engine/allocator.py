"""M5: Regional allocation — CRC split and BCC largest-remainder apportionment.

All functions are pure (no I/O, no database). They receive pre-loaded data
and return allocation dicts. This keeps the math testable in isolation.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CrcShare:
    crc_id: str
    share_key: float  # e.g. 0.67 for North


@dataclass(frozen=True) 
class BccWeight:
    bcc_id: str
    managed_load_mw: float


def allocate_to_crcs(
    deficit_mw: float,
    crcs: list[CrcShare],
) -> dict[str, float]:
    """Split national deficit to CRCs using share_key.
    
    Returns {crc_id: allocated_mw}.
    Sum of allocations equals deficit_mw exactly (last CRC absorbs rounding).
    
    Example from docs: 300 MW -> CRC_N: 201 MW, CRC_S: 99 MW
    """
    if deficit_mw <= 0:
        return {c.crc_id: 0.0 for c in crcs}
    
    result: dict[str, float] = {}
    remaining = deficit_mw
    
    for i, crc in enumerate(crcs):
        if i == len(crcs) - 1:
            # Last CRC absorbs remainder to ensure exact conservation
            result[crc.crc_id] = round(remaining, 2)
        else:
            allocated = round(deficit_mw * crc.share_key, 2)
            result[crc.crc_id] = allocated
            remaining -= allocated
    
    return result


def allocate_to_bccs(
    crc_target_mw: float,
    bccs: list[BccWeight],
) -> dict[str, int]:
    """Split CRC target to BCCs using largest-remainder (Hamilton-Hare) method.

    Returns {bcc_id: allocated_mw_integer}.
    Guarantees: sum(allocated) == round(crc_target_mw)

    Algorithm:
    1. Compute ideal quota: bcc.managed_load_mw / total_managed * crc_target
    2. Give each BCC floor(quota)
    3. Distribute remaining seats to BCCs with largest fractional remainders

    The Hamilton-Hare method ensures exact integer conservation: the sum of
    all BCC allocations equals the CRC target exactly. Ties in fractional
    remainders are broken by bcc_id for determinism.
    """
    total_mw = crc_target_mw
    total_seats = round(total_mw)  # integer MW
    
    if total_seats <= 0:
        return {b.bcc_id: 0 for b in bccs}
    
    total_managed = sum(b.managed_load_mw for b in bccs)
    if total_managed == 0:
        return {b.bcc_id: 0 for b in bccs}
    
    # Step 1: Compute ideal quotas and floors
    quotas = []
    for bcc in bccs:
        ideal = (bcc.managed_load_mw / total_managed) * total_seats
        quotas.append((bcc.bcc_id, ideal, math.floor(ideal), ideal - math.floor(ideal)))
    
    # Step 2: Assign floors
    result = {bcc_id: floor_val for bcc_id, _, floor_val, _ in quotas}
    
    # Step 3: Distribute remaining seats by largest remainder
    assigned = sum(result.values())
    remaining = total_seats - assigned
    
    # Sort by remainder descending, then by bcc_id for determinism
    sorted_by_remainder = sorted(quotas, key=lambda x: (-x[3], x[0]))
    for i in range(remaining):
        result[sorted_by_remainder[i][0]] += 1
    
    return result
