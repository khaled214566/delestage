import csv
import json
import urllib.request
import unicodedata
import os

def norm_ar(s):
    if not s:
        return ''
    s = s.replace('\u0640', '')  # tatweel
    s = s.replace('\u0623', '\u0627').replace('\u0625', '\u0627').replace('\u0622', '\u0627')  # alef
    s = s.replace('\u0629', '\u0647')  # teh marbuta
    s = s.replace('\u0649', '\u064a')  # alef maksura
    s = s.replace('-', ' ')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # harakat
    return ' '.join(s.split()).strip()

def norm_fr(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower().replace('-', ' ').replace("'", ' ').strip()

def main():
    # 1. Load CSV data
    csv_path = 'backend/data/tunisia_admin_pcode.csv'
    delegations = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['admin_level'] == '3':
                delegations.append(row)

    print(f"Loaded delegations from CSV: {len(delegations)}")

    # 2. Load ADM2 GeoJSON
    cache_file = 'backend/data/geoBoundaries_ADM2.geojson'
    if not os.path.exists(cache_file):
        print("Downloading ADM2 GeoJSON from geoBoundaries...")
        url = 'https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/TUN/ADM2/geoBoundaries-TUN-ADM2_simplified.geojson'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=20).read()
        with open(cache_file, 'wb') as f:
            f.write(raw)
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        adm2 = json.load(f)

    print(f"Loaded ADM2 GeoJSON features: {len(adm2['features'])}")

    csv_by_ar = {norm_ar(d['name1']): d for d in delegations}
    csv_by_fr = {norm_fr(d['name']): d for d in delegations}

    matched = 0
    unmatched = []
    for f in adm2['features']:
        ar_name = norm_ar(f['properties'].get('shapeName', ''))
        matched_row = csv_by_ar.get(ar_name)
        if not matched_row:
            # Try partial or prefix matching
            for k, row in csv_by_ar.items():
                if ar_name and (ar_name in k or k in ar_name):
                    matched_row = row
                    break
        
        if matched_row:
            matched += 1
        else:
            unmatched.append(f['properties'].get('shapeName', ''))

    print(f"Matched: {matched}/{len(adm2['features'])}")
    if unmatched:
        print("Unmatched:", [ascii(u) for u in unmatched[:15]])

if __name__ == '__main__':
    main()
