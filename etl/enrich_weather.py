
"""
Enrich weather_forecast.geojson with numeric fields using Open-Meteo (no API key).
Adds/overwrites: temp_min, temp_max, rain_chance, wind_speed, wind_dir, humidity.


"""

import json
import math
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IN_GEOJSON = DATA_DIR / "weather_forecast.geojson"
OUT_GEOJSON = DATA_DIR / "weather_forecast.geojson"      
CACHE_FILE = DATA_DIR / "openmeteo_cache.json"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def dump_json(path: Path, obj: Any):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def safe_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%-m/%-d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    # try fromisoformat without tz
    try:
        return datetime.fromisoformat(s.replace("Z","")).date()
    except Exception:
        return None

def round_key(x: float, nd=2) -> float:
    return float(f"{x:.{nd}f}")

def cache_key(lat: float, lon: float, d: date) -> str:
    return f"{round_key(lat,3)},{round_key(lon,3)},{d.isoformat()}"

def kmh(val) -> Optional[float]:
    try:
        return None if val is None else float(val)
    except Exception:
        return None

def pct(val) -> Optional[float]:
    try:
        v = float(val)
        if math.isnan(v):
            return None
        return max(0.0, min(100.0, v))
    except Exception:
        return None

def fetch_open_meteo(lat: float, lon: float, day: date) -> Optional[Dict[str, Any]]:
    """
    Get daily min/max temp, precip prob max, windspeed max, wind direction dominant,
    and hourly humidity (we'll use 12:00 local as representative).
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "windspeed_10m_max",
            "winddirection_10m_dominant",
        ]),
        "hourly": "relative_humidity_2m",
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def summarize_open_meteo(j: Dict[str, Any]) -> Dict[str, Any]:
    out = {"temp_min": None, "temp_max": None, "rain_chance": None, "wind_speed": None, "wind_dir": None, "humidity": None}
    daily = j.get("daily") or {}
    # daily arrays are length 1 for start=end
    if daily:
        tmin = daily.get("temperature_2m_min", [None])[0]
        tmax = daily.get("temperature_2m_max", [None])[0]
        rain = daily.get("precipitation_probability_max", [None])[0]
        wspd = daily.get("windspeed_10m_max", [None])[0]      # already km/h
        wdir = daily.get("winddirection_10m_dominant", [None])[0]
        out["temp_min"] = None if tmin is None else float(tmin)
        out["temp_max"] = None if tmax is None else float(tmax)
        out["rain_chance"] = pct(rain)
        out["wind_speed"] = kmh(wspd)
        out["wind_dir"] = None if wdir is None else float(wdir)

    # humidity from hourly: take 12:00 local if present, else mean
    hourly = j.get("hourly") or {}
    rh_list = hourly.get("relative_humidity_2m")
    times = hourly.get("time")
    if rh_list and times and len(rh_list) == len(times):
        # find 12:00 index (local). If not found, average.
        idx12 = next((i for i,t in enumerate(times) if t.endswith("12:00")), None)
        if idx12 is not None:
            out["humidity"] = pct(rh_list[idx12])
        else:
            try:
                vals = [float(x) for x in rh_list if x is not None]
                out["humidity"] = pct(sum(vals)/len(vals)) if vals else None
            except Exception:
                out["humidity"] = None
    return out


def main():
    if not IN_GEOJSON.exists():
        print(f"[ERROR] Missing {IN_GEOJSON}")
        return

    g = load_json(IN_GEOJSON)
    if g.get("type") != "FeatureCollection":
        print("[ERROR] weather_forecast.geojson is not a FeatureCollection")
        return

    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = load_json(CACHE_FILE)
        except Exception:
            cache = {}

    features = g.get("features", [])
    if not features:
        print("[WARN] No features in weather_forecast.geojson")
        return

    updated = 0
    total = len(features)
    for i, feat in enumerate(features, 1):
        geom = feat.get("geometry") or {}
        props = feat.setdefault("properties", {})
        coords = geom.get("coordinates")
        if not coords or geom.get("type") != "Point":
            continue

        lon, lat = float(coords[0]), float(coords[1])
        
        d = None
        for key in ("date","datetime","timestamp"):
            d = safe_date(props.get(key)) or d
        if not d:
            # cannot query time-based daily; skip
            continue

        # Only fill when missing
        needs = any(props.get(k) in (None, "", "null") for k in ("temp_min","temp_max","rain_chance","wind_speed","wind_dir","humidity"))
        if not needs:
            continue

        key = cache_key(lat, lon, d)
        data = cache.get(key)
        if not data:
            try:
                j = fetch_open_meteo(lat, lon, d)
                data = summarize_open_meteo(j)
                cache[key] = data
              
                time.sleep(0.2)
            except Exception as e:
                print(f"[WARN] Open-Meteo fetch failed @ {lat},{lon} {d}: {e}")
                continue

        for k, v in data.items():
            if props.get(k) in (None, "", "null") and v is not None:
                props[k] = v

        updated += 1
        if i % 50 == 0 or i == total:
            print(f"[INFO] processed {i}/{total} (updated {updated})")

    dump_json(CACHE_FILE, cache)
    dump_json(OUT_GEOJSON, g)
    print(f"[OK] Enriched {updated} feature(s). Wrote {OUT_GEOJSON}")
    print(f"[OK] Cache saved -> {CACHE_FILE}")

if __name__ == "__main__":
    main()
