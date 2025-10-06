import os
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG = ROOT / "etl" / "traffic_feeds.json"
OUT = DATA_DIR / "traffic_feeds.geojson"
LOCATIONS_CSV = DATA_DIR / "locations.csv"

load_dotenv(ROOT / ".env")
HEADERS = {"User-Agent": os.getenv("GEOCODER_USER_AGENT", "ackgis-weather-traffic/1.0 (contact@example.com)")}

# --- simple geocode helper (uses Nominatim)
def geocode_address(q):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"{q}, Malaysia", "format": "json", "limit": 1}
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    arr = r.json()
    if not arr: return None
    return float(arr[0]['lat']), float(arr[0]['lon'])

def parse_feed_entry(page_url, entry_selector, lat_selector=None, lon_selector=None, text_selector=None):
    r = requests.get(page_url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select(entry_selector)
    out = []
    for el in items:
        lat = None; lon = None; text = None
        if lat_selector and lon_selector:
            lat_tag = el.select_one(lat_selector)
            lon_tag = el.select_one(lon_selector)
            if lat_tag and lon_tag:
                try:
                    lat = float(lat_tag.get_text(strip=True))
                    lon = float(lon_tag.get_text(strip=True))
                except:
                    lat = lon = None
        if text_selector:
            t = el.select_one(text_selector)
            if t:
                text = t.get_text(separator=" ", strip=True)
        out.append({"lat":lat,"lon":lon,"text":text})
    return out

def run():
    if not CONFIG.exists():
        print("No config file found at", CONFIG)
        return
    with open(CONFIG, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    features = []
    for feed in cfg.get("feeds", []):
        url = feed["url"]
        print("Fetching feed", url)
        try:
            entries = parse_feed_entry(url,
                                      entry_selector=feed["entry_selector"],
                                      lat_selector=feed.get("lat_selector"),
                                      lon_selector=feed.get("lon_selector"),
                                      text_selector=feed.get("text_selector"))
        except Exception as e:
            print("Failed to fetch/parse", url, e)
            continue

        for e in entries:
            lat = e.get("lat"); lon = e.get("lon"); txt = e.get("text")
            if not lat or not lon:
                if txt:
                    try:
                        coords = geocode_address(txt)
                        if coords:
                            lat, lon = coords
                            time.sleep(1.1)  # nominatim rate limit
                    except Exception as ge:
                        print("Geocode error:", ge)
            if not lat or not lon:
                continue
            feat = {
                "type":"Feature",
                "geometry":{"type":"Point","coordinates":[lon,lat]},
                "properties":{"source":url,"text":txt}
            }
            features.append(feat)
        time.sleep(feed.get("delay", 1.0))

    out = {"type":"FeatureCollection","features":features}
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print("Wrote", OUT)

if __name__ == "__main__":
    run()
