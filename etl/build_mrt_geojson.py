import os, re, json, time
from datetime import datetime
from pathlib import Path

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IN_JSON = DATA_DIR / "mrt_announcements.json"
OUT_GEOJSON = DATA_DIR / "traffic_incidents.geojson"
CACHE_FILE = DATA_DIR / "locations_cache.json"

# Johor Bahru bias box (lon/lat) W, S, E, N
JB_VIEWBOX = ((1.40, 103.60), (1.55, 103.90))

# Fallback coordinates for tough strings
GAZETTEER = {
    "JOHOR–SINGAPORE CAUSEWAY": [103.763, 1.462],
    "JOHOR CAUSEWAY": [103.763, 1.462],
    "KM0.75 JOHOR CAUSEWAY": [103.763, 1.462],
    "JALAN TUN ABDUL RAZAK, JOHOR BAHRU": [103.7617, 1.4658],
    "JALAN GEREJA, JOHOR BAHRU": [103.7630, 1.4568],
    "JALAN TEBRAU, JOHOR BAHRU": [103.7837, 1.4857],
    "JB SENTRAL": [103.7639, 1.4624],
    "JALAN SULTAN AZLAN SHAH, SUNGAI TIRAM": [103.6787, 1.6407],
    "JALAN SALLEH, KIM TENG PARK, JOHOR BAHRU": [103.7625, 1.4679],
}

def norm(s: str) -> str:
    if not s: return ""
    return " ".join(s.replace("–","-").replace("—","-").upper().split())

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def clean_location_for_search(text: str) -> str:
    if not text: return ""
    t = text
    # remove parenthetical clutter
    t = re.sub(r"\((?:BOTH BOUNDS|BOTH DIRECTIONS)\)", "", t, flags=re.I)
    t = re.sub(r"\(NEAR [^)]+\)", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    # title-case but keep all-uppercase tokens
    return " ".join([w if w.isupper() else w.title() for w in t.split()])

def location_from_title(title: str) -> str:
    if not title: return ""
    return title.split(" AT ", 1)[1].strip() if " AT " in title else title.strip()

def best_date_iso(*cands):
    fmts = ("%d %b %Y", "%d %B %Y", "%d %b, %Y", "%d %B, %Y")
    for s in cands:
        if not s: continue
        s = str(s).strip()
        for fmt in fmts:
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                pass
        # already ISO?
        try:
            return datetime.fromisoformat(s).date().isoformat()
        except Exception:
            pass
    return None

def geocode_one(raw_text: str, geocode, cache: dict):
    """Gazetteer -> cache -> limited candidate queries. No loops/retries beyond this list."""
    if not raw_text: return None

    key = norm(raw_text)

    # gazetteer
    if key in GAZETTEER:
        return GAZETTEER[key]
    for k, v in GAZETTEER.items():
        if k in key:
            return v

    # cache
    if key in cache:
        return cache[key]

    cleaned = clean_location_for_search(raw_text)
    candidates = [
        f"{cleaned}, Johor Bahru, Malaysia",
        f"{cleaned}, Johor, Malaysia",
        f"{cleaned}, Malaysia",
    ]
    if "CAUSEWAY" in key:
        candidates.insert(0, "Johor–Singapore Causeway, Johor Bahru, Malaysia")

    for q in candidates:
        try:
            loc = geocode(q, country_codes="my", viewbox=JB_VIEWBOX, bounded=True, exactly_one=True)
            if loc:
                coords = [float(loc.longitude), float(loc.latitude)]
                cache[key] = coords
                save_cache(cache)
                return coords
        except Exception as e:
            # swallow and move on to next candidate
            print(f"[WARN] geocode failed for '{q}': {e}")
            continue
    return None

def main():
    # env for proper UA (Nominatim policy requires contact)
    load_dotenv = load_dotenv = __import__("dotenv").load_dotenv
    load_dotenv(ROOT / ".env")
    ua = os.getenv("GEOCODER_USER_AGENT", "ackgis-traffic/1.0 (contact@example.com)")

    if not IN_JSON.exists():
        print(f"[ERROR] Missing {IN_JSON}")
        return

    try:
        items = json.loads(IN_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Could not read JSON: {e}")
        return

    if not isinstance(items, list) or not items:
        print(f"[ERROR] No announcements in {IN_JSON}")
        return

    geolocator = Nominatim(user_agent=ua, timeout=20)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1, max_retries=1, swallow_exceptions=True)
    cache = load_cache()

    features = []
    total = len(items)
    for i, it in enumerate(items, 1):
        title = (it.get("title") or "").strip()
        start_date = it.get("start_date")
        end_date = it.get("end_date")
        activity_time = it.get("activity_time")
        description = it.get("description")
        activity = it.get("activity")
        media_release = it.get("media_release")
        post_url = it.get("post_url")
        scraped_at = it.get("scraped_at")

        # pick timestamp in priority order
        timestamp = best_date_iso(start_date, end_date, scraped_at) or datetime.utcnow().date().isoformat()
        ts_ms = int(datetime.fromisoformat(timestamp).timestamp() * 1000)


        loc_text = location_from_title(title)
        coords = geocode_one(loc_text, geocode, cache)
        if not coords:
            print(f"[SKIP] No coords for: {loc_text}")
            continue

        props = {
            "title": title,
            "start_date": best_date_iso(start_date),
            "end_date": best_date_iso(end_date),
            "activity_time": activity_time,
            "description": description,
            "activity": activity,
            "media_release": media_release,
            "post_url": post_url,
            "location_text": loc_text,
            "timestamp": timestamp,
            "timestamp_ms": ts_ms,
            "source": post_url or "https://www.mymrt.com.my/traffic-announcement/",
            "scraped_at": scraped_at,
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": props
        })

        if i % 10 == 0 or i == total:
            print(f"[INFO] processed {i}/{total}")

    if not features:
        print("[ERROR] 0 features geocoded. Check your titles/locations.")
        return

    fc = {"type": "FeatureCollection", "features": features}
    OUT_GEOJSON.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote {OUT_GEOJSON} with {len(features)} features")

if __name__ == "__main__":
    main()
