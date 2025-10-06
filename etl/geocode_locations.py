import os
import time
import csv
import requests
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
LOCATIONS_CSV = DATA_DIR / "locations.csv"

load_dotenv(ROOT / ".env")

GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "ackgis-weather-traffic/1.0 (contact@example.com)")
FORECAST_LIST_URL = "https://api.data.gov.my/weather/forecast?limit=1000"

HEADERS = {"User-Agent": GEOCODER_USER_AGENT}

def fetch_location_list_from_api():
    r = requests.get(FORECAST_LIST_URL, timeout=20)
    r.raise_for_status()
    j = r.json()
    records = j if isinstance(j, list) else j.get("data") or j.get("result") or j.get("records") or j.get("results") or j
    locs = {}
    for rec in records:
        loc = rec.get("location") or {}
        lid = loc.get("location_id") or rec.get("location__location_id")
        lname = loc.get("location_name") or rec.get("location__location_name")
        if lid and lname:
            locs[lid] = lname
    return locs

def load_existing_locations():
    d = {}
    if not LOCATIONS_CSV.exists():
        return d
    with open(LOCATIONS_CSV, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            d[r['location_id']] = {
                "location_name": r['location_name'],
                "lat": float(r['lat']),
                "lon": float(r['lon'])
            }
    return d

def geocode_name(n):
    # Nominatim Search API
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": n + ", Malaysia", "format": "json", "limit": 1, "addressdetails": 0}
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        return None
    return float(arr[0]['lat']), float(arr[0]['lon'])

def save_locations(d):
    # d: mapping location_id -> {location_name, lat, lon}
    with open(LOCATIONS_CSV, "w", newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=["location_id","location_name","lat","lon"])
        writer.writeheader()
        for lid, info in sorted(d.items()):
            writer.writerow({
                "location_id": lid,
                "location_name": info["location_name"],
                "lat": info["lat"],
                "lon": info["lon"]
            })

def main():
    remote = fetch_location_list_from_api()
    print("Found", len(remote), "unique location ids in MET forecast API.")
    existing = load_existing_locations()

    # Merge: prefer existing; geocode missing ones
    merged = existing.copy()
    to_geocode = []
    for lid, lname in remote.items():
        if lid not in merged:
            to_geocode.append((lid, lname))

    print("Need to geocode", len(to_geocode), "locations.")
    for lid, lname in to_geocode:
        try:
            coords = geocode_name(lname)
            if coords:
                lat, lon = coords
                merged[lid] = {"location_name": lname, "lat": lat, "lon": lon}
                print("Geocoded", lname, "->", lat, lon)
            else:
                print("No geocode result for", lname)
        except Exception as e:
            print("Error geocoding", lname, e)
        # Nominatim policy: send 1 request per second max
        time.sleep(1.1)
    save_locations(merged)
    print("Saved", LOCATIONS_CSV)

if __name__ == "__main__":
    main()
