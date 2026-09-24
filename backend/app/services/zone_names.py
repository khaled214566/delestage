from __future__ import annotations

import csv
from pathlib import Path


_CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "tunisia_admin_pcode.csv"
_NAMES_BY_PCODE: dict[str, str] = {}

if _CSV_PATH.exists():
    with _CSV_PATH.open(encoding="utf-8", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            if row.get("admin_level") == "3" and row.get("adm3_pcode") and row.get("name"):
                _NAMES_BY_PCODE[row["adm3_pcode"]] = row["name"]


def feeder_display_name(feeder: object) -> str:
    """Return the canonical CSV delegation name for a feeder when available."""
    zone_id = str(getattr(feeder, "zone_id", ""))
    pcode = zone_id.removeprefix("Z-")
    delegation_name = _NAMES_BY_PCODE.get(pcode)
    if delegation_name:
        return f"Départ {delegation_name}"
    return str(getattr(feeder, "name", ""))


def delegation_display_name(feeder: object) -> str:
    """Return only the canonical delegation name for a feeder."""
    return feeder_display_name(feeder).removeprefix("Départ ")
