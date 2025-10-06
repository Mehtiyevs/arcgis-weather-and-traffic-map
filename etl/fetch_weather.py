
import os, json
import requests
import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

FORECAST_URL = "https://api.data.gov.my/weather/forecast?limit=500"
WARNINGS_URL = "https://api.data.gov.my/weather/warning?limit=200"

def load_location_lookup(path):
    # expects CSV: location_id,location_name,lat,lon
    d = {}
    if not os.path.exists(path):
        return d
    with open(path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            d[r['location_id']] = (float(r['lon']), float(r['lat']))
    return d

def fetch_forecast():
    r = requests.get(FORECAST_URL, timeout=20)
    r.raise_for_status()
    payload = r.json()
    records = payload if isinstance(payload, list) else payload.get('data') or payload.get('result') or payload.get('records') or payload

    locations = load_location_lookup(DATA_DIR / "locations.csv")
    features = []
    for rec in records:
        loc = rec.get('location', {})
        loc_id = loc.get('location_id') or rec.get('location__location_id')
        loc_name = loc.get('location_name') or rec.get('location__location_name')
        coords = locations.get(loc_id)
        if not coords:
            continue
        lon, lat = coords
        props = {
            'location_id': loc_id,
            'location_name': loc_name,
            'date': rec.get('date'),
            'summary_forecast': rec.get('summary_forecast'),
            'morning_forecast': rec.get('morning_forecast'),
            'afternoon_forecast': rec.get('afternoon_forecast'),
            'night_forecast': rec.get('night_forecast'),
            'min_temp': rec.get('min_temp'),
            'max_temp': rec.get('max_temp')
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props
        })
    out = {"type": "FeatureCollection", "features": features}
    outpath = DATA_DIR / "weather_forecast.geojson"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("Wrote", outpath)

def fetch_warnings():
    r = requests.get(WARNINGS_URL, timeout=20)
    r.raise_for_status()
    payload = r.json()
    recs = payload if isinstance(payload, list) else payload.get('data') or payload.get('result') or payload
    outpath = DATA_DIR / "weather_warnings.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False)
    print("Wrote", outpath)

if __name__ == '__main__':
    fetch_forecast()
    fetch_warnings()
