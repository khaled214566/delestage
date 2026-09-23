import json
import csv
import unicodedata
import re
import os

def norm_ar(s):
    if not s:
        return ''
    s = s.replace('\u0640', '')
    s = s.replace('\u0623', '\u0627').replace('\u0625', '\u0627').replace('\u0622', '\u0627')
    s = s.replace('\u0629', '\u0647')
    s = s.replace('\u0649', '\u064a')
    s = s.replace('\u06cc', '\u064a')
    s = re.sub(r'[\u200e\u200f\u202a-\u202e]', '', s)
    s = s.replace('-', ' ')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.split()).strip()

def norm_fr(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower().replace('-', ' ').replace("'", ' ')
    return ' '.join(s.split()).strip()

GOV_TO_BCC = {
    'Tunis': ('BCC1', 'BCC TUNIS (Grand Tunis)'),
    'Ariana': ('BCC1', 'BCC TUNIS (Grand Tunis)'),
    'Ben Arous': ('BCC1', 'BCC TUNIS (Grand Tunis)'),
    'Manubah': ('BCC1', 'BCC TUNIS (Grand Tunis)'),
    'Manouba': ('BCC1', 'BCC TUNIS (Grand Tunis)'),
    
    'Nabeul': ('BCC2', 'BCC GROMBALIA (Nord-Est)'),
    'Zaghouan': ('BCC2', 'BCC GROMBALIA (Nord-Est)'),
    
    'Bizerte': ('BCC4', 'BCC BÉJA (Nord-Ouest)'),
    'Béja': ('BCC4', 'BCC BÉJA (Nord-Ouest)'),
    'Beja': ('BCC4', 'BCC BÉJA (Nord-Ouest)'),
    'Jendouba': ('BCC4', 'BCC BÉJA (Nord-Ouest)'),
    'Le Kef': ('BCC4', 'BCC BÉJA (Nord-Ouest)'),
    'Siliana': ('BCC4', 'BCC BÉJA (Nord-Ouest)'),
    
    'Sousse': ('BCC3', 'BCC SOUSSE (Centre)'),
    'Monastir': ('BCC3', 'BCC SOUSSE (Centre)'),
    'Mahdia': ('BCC3', 'BCC SOUSSE (Centre)'),
    'Kairouan': ('BCC3', 'BCC SOUSSE (Centre)'),
    
    'Sfax': ('BCC5', 'BCC SFAX (Sfax)'),
    
    'Gabès': ('BCC6', 'BCC GABÈS (Sud-Est)'),
    'Gabes': ('BCC6', 'BCC GABÈS (Sud-Est)'),
    'Médenine': ('BCC6', 'BCC GABÈS (Sud-Est)'),
    'Medenine': ('BCC6', 'BCC GABÈS (Sud-Est)'),
    'Tataouine': ('BCC6', 'BCC GABÈS (Sud-Est)'),
    
    'Gafsa': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
    'Tozeur': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
    'Kebili': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
    'Kassérine': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
    'Kasserine': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
    'Sidi Bou Zid': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
    'Sidi Bouzid': ('BCC7', 'BCC GAFSA (Sud-Ouest)'),
}

SYNONYMS = {
    'بن قردان': 'بنقردان',
    'بو عرقوب': 'بوعرقوب',
    'ماجل بالعباس': 'ماجل بلعباس',
    'سيدي بو علي': 'سيدي بوعلي',
    'الزاوية قصيبة الثريات': 'الزاوية - القصيبة - الثريات',
    'سيدي بوزيد الغربية': 'سيدي بوزيد الغربية',
    'صفاقس الغربية': 'صفاقس الغريبة',
    'مدنين االجنوبية': 'مدنين الجنوبية',
    'سبالة أوالد عسكر': 'سبالة أولاد عسكر',
    'سوسة سيدي عبد الحميد': 'سوسة سيدي عبد الحميد',
    'حمام الانف': 'حمام الأنف',
    'جربة حومة السوق': 'جربة حومة السوق',
    'جربة ميدون': 'جربة ميدون',
    'جربة أجيم': 'جربة أجيم',
    'حلق الوادي': 'حلق الوادي',
    'الكرم': 'الكرم',
    'المرسى': 'المرسى',
    'قرطاج': 'قرطاج',
    'El Hencha': 'Hencha',
    'Bou Salem': 'Bousalem',
    'Balta Bouawene': 'Balta Bou Aouane',
    'واد مليز': 'وادي مليز',
    'باب بحر': 'باب البحر',
    'والد شامخ': 'أولاد شامخ',
    'حمام الغزاز': 'حمام الأغزاز',
}

SUBZONES_SAMPLE = {
    "La Marsa": ["Marsa Ville", "Marsa Plage", "Marsa Cube", "Gammarth", "Les Citrons", "Sidi Dhrif", "Gammarth Supérieur"],
    "Carthage": ["Carthage Byrsa", "Carthage Dermech", "Carthage Amilcar", "Carthage Présidence", "Yasmina"],
    "Le Kram": ["Le Kram Est", "Le Kram Ouest", "Salammbô", "Khereddine"],
    "La Goulette": ["La Goulette Casino", "Cité El Habib", "Taher Sfar", "Quartier du Port"],
    "El Menzah": ["El Menzah 1", "El Menzah 4", "El Menzah 5", "El Menzah 6", "El Menzah 7", "El Menzah 8", "El Menzah 9"],
    "El Manar": ["El Manar 1", "El Manar 2", "El Manar 3", "Campus Universitaire"],
    "Ariana Médina": ["Ariana Supérieur", "Cité Ennasr 1", "Cité Ennasr 2", "Cité Essaha"],
    "Soukra": ["Chotrana 1", "Chotrana 2", "Chotrana 3", "Dar Fadhal", "Borj Louzir (partie)"],
    "Raoued": ["Raoued Plage", "Ariana Essoughra", "Cité Yamama", "Raoued Ville"],
    "Ben Arous": ["Ben Arous Ville", "Cité Bougatfa", "Zone Industrielle Ben Arous"],
    "Radès": ["Radès Forêt", "Radès Plage", "Radès Méliane", "Cité Noujoom", "Cité Olympique"],
    "Mégrine": ["Mégrine Coteaux", "Mégrine Riadh", "Mégrine Chaker", "Z.I. Saint-Gobain"],
    "Hammam Lif": ["Centre-Ville", "Bou Kornine", "Cité Mohamed Ali", "Casino"],
    "El Mourouj": ["El Mourouj 1", "El Mourouj 2", "El Mourouj 3", "El Mourouj 4", "El Mourouj 5", "El Mourouj 6"],
    "Fouchana": ["Fouchana Centre", "Cité El Mghira", "Zone Industrielle El Mghira 1 & 2"],
    "Hammamet": ["Hammamet Centre", "Hammamet Nord", "Yasmine Hammamet", "Barraket Essahel", "Bir Bouregba"],
    "Nabeul": ["Nabeul Centre", "Les Vergers", "Cité Wafa", "Zone Touristique", "Sidi Mahersi"],
    "Sousse Médina": ["Médina", "Bouhsina", "Khézama Est", "Khézama Ouest", "Corniche", "Port de Sousse"],
    "Hammam Sousse": ["Hammam Sousse Centre", "El Kantaoui", "Port El Kantaoui", "Cité Menchia"],
    "Sfax Médina": ["Bab Bhar", "Picville", "100 Mètres", "Moulinville", "Poudrière 1", "Poudrière 2"],
    "Bizerte Nord": ["Bizerte Nord", "Zarzouna", "Corniche", "Vieux Port", "Rimel"],
    "Houmt Souk": ["Houmt Souk Centre", "Erriadh (Hara Sghira)", "Taourit", "Mellita"],
    "Djerba Midoun": ["Midoun Centre", "Zone Touristique Djerba", "Aghir", "Mahboubine", "Arkou"],
    "Tozeur": ["Tozeur Centre", "Palmeraie", "Cité El Hdar", "Zone Touristique"],
    "Kairouan Nord": ["Kairouan Nord", "Médina", "Cité Mohamed Ali", "Mansoura", "Cité Okba"],
}

def main():
    # Load CSV
    delegations = []
    with open('backend/data/tunisia_admin_pcode.csv', 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['admin_level'] == '3':
                delegations.append(row)

    print(f"Loaded {len(delegations)} delegations from CSV.")

    ar_to_csv = {norm_ar(d['name1']): d for d in delegations}
    fr_to_csv = {norm_fr(d['name']): d for d in delegations}

    # Load ADM2 GeoJSON
    with open('backend/data/geoBoundaries_ADM2.geojson', 'r', encoding='utf-8') as f:
        adm2 = json.load(f)

    output_features = []
    matched_count = 0

    for f in adm2['features']:
        raw_name = f['properties'].get('shapeName', '').strip()
        name_ar = norm_ar(raw_name)
        name_fr = norm_fr(raw_name)

        row = fr_to_csv.get(name_fr)
        if not row:
            row = ar_to_csv.get(name_ar)
        if not row and raw_name in SYNONYMS:
            syn = SYNONYMS[raw_name]
            row = ar_to_csv.get(norm_ar(syn)) or fr_to_csv.get(norm_fr(syn))
        if not row:
            for k, v in ar_to_csv.items():
                if name_ar and (name_ar == k or name_ar in k or k in name_ar):
                    row = v
                    break

        if row:
            matched_count += 1
            gov_name = row['adm2_name']
            gov_name_ar = row['adm2_name1']
            zone_fr = row['name']
            zone_ar = row['name1']
            pcode = row['adm3_pcode']
            center_x = float(row['x_coord'])
            center_y = float(row['y_coord'])
        else:
            gov_name = "Tunisie"
            gov_name_ar = "تونس"
            zone_fr = raw_name
            zone_ar = raw_name
            pcode = f['properties'].get('shapeID', '')
            center_x = 10.0
            center_y = 35.0

        bcc_id, bcc_name = GOV_TO_BCC.get(gov_name, ('BCC1', 'BCC TUNIS'))
        subzones = SUBZONES_SAMPLE.get(zone_fr, [f"{zone_fr} Centre", f"Secteur {zone_fr}"])

        new_props = {
            "id": pcode,
            "name": zone_fr,
            "name_ar": zone_ar,
            "governorate": gov_name,
            "governorate_ar": gov_name_ar,
            "bcc_id": bcc_id,
            "bcc_name": bcc_name,
            "center": [center_y, center_x],
            "subzones": subzones,
            "shape_id": f['properties'].get('shapeID', '')
        }

        output_features.append({
            "type": "Feature",
            "geometry": f['geometry'],
            "properties": new_props
        })

    print(f"Total features packaged: {len(output_features)} (Matched: {matched_count}/264)")

    out_geojson = {
        "type": "FeatureCollection",
        "features": output_features
    }

    os.makedirs('frontend/public/data', exist_ok=True)
    out_path = 'frontend/public/data/tunisia_zones.geojson'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out_geojson, f, ensure_ascii=False)

    print(f"Successfully generated {out_path} ({os.path.getsize(out_path) / 1024:.1f} KB)")

if __name__ == '__main__':
    main()
