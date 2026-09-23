"""
Generates realistic electrical load (MW) data for all 264 Tunisian delegations
based on the 2024 INS census and governorate sectoral profiles (industrial, urban, tourism).
"""
import csv
import json
import unicodedata

# 2024 INS Census Population by Governorate (RGPH 2024)
GOV_POPULATION_2024 = {
    "Tunis": 1075306,
    "Ariana": 668552,
    "Ben Arous": 722828,
    "Manouba": 418354,
    "Nabeul": 863172,
    "Zaghouan": 201065,
    "Bizerte": 607388,
    "Béja": 311417,
    "Jendouba": 404352,
    "Le Kef": 237686,
    "Siliana": 216242,
    "Sousse": 762281,
    "Monastir": 599769,
    "Mahdia": 449985,
    "Kairouan": 600803,
    "Sfax": 1047468,
    "Sidi Bouzid": 489991,
    "Kasserine": 492741,
    "Gabès": 410847,
    "Médenine": 537255,
    "Tataouine": 162654,
    "Gafsa": 388776,
    "Tozeur": 120036,
    "Kébili": 183201,
}

# Sectoral weight factor per governorate (urban, industrial, tourism)
GOV_WEIGHTS = {
    "Tunis": 1.30,       # Capital, extreme density, services, institutions
    "Ariana": 1.15,      # Dense urban, commercial centres (Technopole)
    "Ben Arous": 1.25,   # Major industrial zone (Mégrine, Radès port, Ben Arous)
    "Manouba": 1.00,     # Semi-urban, academic, residential
    "Nabeul": 1.10,      # Tourism, agro-industry, Cap Bon
    "Zaghouan": 0.90,    # Light industry, semi-rural
    "Bizerte": 1.10,     # Industrial hub, port, metallurgy (Menzel Bourguiba)
    "Béja": 0.85,        # Agricultural
    "Jendouba": 0.85,    # Forest/agricultural, Tabarka tourism
    "Le Kef": 0.80,      # Interior, agricultural
    "Siliana": 0.80,     # Interior, agricultural
    "Sousse": 1.20,      # Major tourism, textile, university
    "Monastir": 1.15,    # Heavy textile, university, coastal tourism
    "Mahdia": 0.95,      # Fishing, olive oil, tourism
    "Kairouan": 0.90,    # Commercial, agricultural, historical
    "Sfax": 1.35,        # 2nd economic hub, heavy industry, oil & gas
    "Sidi Bouzid": 0.85, # Major agricultural basin
    "Kasserine": 0.85,   # Paper industry (SNCPA), interior
    "Gabès": 1.30,       # Chemical cluster (GCT), port, cement
    "Médenine": 1.10,    # Djerba tourism hub, commercial trade
    "Tataouine": 0.75,   # Desert, low density, oil exploration
    "Gafsa": 1.15,       # Phosphate mining (CPG), chemical
    "Tozeur": 0.90,      # Saharan tourism, date palm irrigation
    "Kébili": 0.80,      # Saharan, agricultural
}

# Regional BCC distribution
GOV_TO_BCC = {
    "Tunis": "BCC1", "Ariana": "BCC1", "Ben Arous": "BCC1", "Manouba": "BCC1", "Manubah": "BCC1",
    "Nabeul": "BCC2", "Zaghouan": "BCC2",
    "Sousse": "BCC3", "Monastir": "BCC3", "Mahdia": "BCC3", "Kairouan": "BCC3",
    "Bizerte": "BCC4", "Béja": "BCC4", "Beja": "BCC4", "Jendouba": "BCC4", "Le Kef": "BCC4", "Siliana": "BCC4",
    "Sfax": "BCC5",
    "Gabès": "BCC6", "Médenine": "BCC6", "Medenine": "BCC6", "Tataouine": "BCC6",
    "Gafsa": "BCC7", "Tozeur": "BCC7", "Kébili": "BCC7", "Kebili": "BCC7",
    "Kassérine": "BCC7", "Kasserine": "BCC7", "Sidi Bou Zid": "BCC7", "Sidi Bouzid": "BCC7",
}

def norm_name(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip()

def main():
    # Load 264 delegations from GeoJSON
    with open("frontend/public/data/tunisia_zones.geojson", "r", encoding="utf-8") as f:
        geojson = json.load(f)

    # Group delegations by governorate
    delegations_by_gov = {}
    for feat in geojson["features"]:
        props = feat["properties"]
        gov = props["governorate"]
        # Normalize governorate name
        for k in GOV_POPULATION_2024:
            if norm_name(k).lower() == norm_name(gov).lower():
                gov = k
                break
        if gov not in delegations_by_gov:
            delegations_by_gov[gov] = []
        delegations_by_gov[gov].append(feat)

    TOTAL_MANAGED_MW = 1830.0
    TOTAL_PEAK_MW = 4888.0

    # Calculate weighted governorate population
    gov_weighted_pop = {}
    for gov, pop in GOV_POPULATION_2024.items():
        w = GOV_WEIGHTS.get(gov, 1.0)
        gov_weighted_pop[gov] = pop * w

    total_weighted = sum(gov_weighted_pop.values())

    # Calculate each governorate's load
    gov_managed_mw = {gov: (wpop / total_weighted) * TOTAL_MANAGED_MW for gov, wpop in gov_weighted_pop.items()}
    gov_peak_mw = {gov: (wpop / total_weighted) * TOTAL_PEAK_MW for gov, wpop in gov_weighted_pop.items()}

    # Assign delegation MW
    rows = []
    for gov, feats in delegations_by_gov.items():
        n = len(feats)
        pop_gov = GOV_POPULATION_2024.get(gov, 300000)
        managed_gov = gov_managed_mw.get(gov, 50.0)
        peak_gov = gov_peak_mw.get(gov, 130.0)

        # Baseline per delegation: average with slight realistic variation
        for i, feat in enumerate(feats):
            p = feat["properties"]
            name = p["name"]
            is_center = any(kw in name.lower() for kw in ["ville", "centre", "medina", "médina", "nord", "sud", "ouest", "est", "carthage", "marsa", "lac"])
            factor = 1.30 if is_center else 0.85
            
            # Estimated delegation population
            del_pop = round((pop_gov / n) * factor)
            
            # Delegation MW share
            del_managed_mw = round((managed_gov / n) * factor, 1)
            del_peak_mw = round((peak_gov / n) * factor, 1)
            
            bcc_id = p.get("bcc_id", GOV_TO_BCC.get(gov, "BCC1"))

            rows.append({
                "pcode": p["id"],
                "name_fr": p["name"],
                "name_ar": p.get("name_ar", ""),
                "governorate": gov,
                "bcc_id": bcc_id,
                "population_2024": del_pop,
                "managed_load_mw": del_managed_mw,
                "peak_load_mw": del_peak_mw,
            })

    # Sort by governorate, name
    rows.sort(key=lambda r: (r["governorate"], r["name_fr"]))

    # Save to CSV
    csv_path = "backend/data/tunisia_load_data.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "pcode", "name_fr", "name_ar", "governorate", "bcc_id",
            "population_2024", "managed_load_mw", "peak_load_mw"
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} delegation load rows in {csv_path}")

    # Summary by BCC
    bcc_totals = {}
    for r in rows:
        b = r["bcc_id"]
        bcc_totals[b] = bcc_totals.get(b, 0.0) + r["managed_load_mw"]

    for b in sorted(bcc_totals):
        print(f"  {b}: {bcc_totals[b]:.1f} MW")

if __name__ == "__main__":
    main()
