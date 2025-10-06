# etl/build_warnings_geojson.py
"""
Convert MET Malaysia weather_warnings.json -> weather_warnings.geojson (points).

Placement order:
  1) exact match to data/locations.csv (location_name)
  2) built-in Malaysia state/FT centroids
  3) fuzzy match against locations.csv
If all fail, the area is skipped (with a log).


"""

from pathlib import Path
import json, csv, re, difflib

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
IN_WARN = DATA_DIR / "weather_warnings.json"
IN_LOC  = DATA_DIR / "locations.csv"
OUT_GEO = DATA_DIR / "weather_warnings.geojson"

# Malaysia states & FTs approximate centroids (lon, lat)
STATE_CENTROIDS = {
     "malaysia": (101.975766, 4.210484),
    "johor": (103.406, 1.849),
    "kedah": (100.561, 6.123),
    "kelantan": (102.238, 5.419),
    "melaka": (102.249, 2.276),
    "malacca": (102.249, 2.276),
    "negeri sembilan": (102.251, 2.718),
    "pahang": (102.350, 3.733),
    "perak": (101.091, 4.967),
    "perlis": (100.216, 6.466),
    "pulau pinang": (100.298, 5.401),
    "penang": (100.298, 5.401),
    "selangor": (101.522, 3.123),
    "terengganu": (103.119, 5.302),
    "sabah": (116.071, 5.801),
    "sarawak": (112.902, 1.553),
    "kuala lumpur": (101.6869, 3.1390),
    "putrajaya": (101.676, 2.925),
    "labuan": (115.241, 5.283),
    # Common variants
    "wilayah persekutuan kuala lumpur": (101.6869, 3.1390),
    "wilayah persekutuan labuan": (115.241, 5.283),
    "wilayah persekutuan putrajaya": (101.676, 2.925),
}

def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def load_locations():
    by_norm = {}
    names = []
    if IN_LOC.exists():
        with IN_LOC.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    name = r.get("location_name") or r.get("name") or ""
                    lat = float(r.get("lat") or r.get("latitude"))
                    lon = float(r.get("lon") or r.get("longitude"))
                except Exception:
                    continue
                key = norm(name)
                by_norm[key] = (lon, lat, name)
                names.append(name)
    return by_norm, names

def coalesce(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "null", "undefined"):
            return v
    return None

def split_areas(val):
    """
    Accept 'Johor, Melaka; Negeri Sembilan' or list [...]
    Return list of clean area strings.
    """
    if val is None:
        return []
    if isinstance(val, list):
        parts = []
        for p in val:
            for sub in re.split(r"[;,/]+", str(p)):
                sub = sub.strip()
                if sub:
                    parts.append(sub)
        return parts
    # string
    parts = []
    for p in re.split(r"[;,/]+", str(val)):
        p = p.strip()
        if p:
            parts.append(p)
    return parts

def place_area(area_raw, loc_index):
    by_norm, all_names = loc_index
    k = norm(area_raw)

    # 1) exact match to locations.csv
    if k in by_norm:
        lon, lat, _ = by_norm[k]
        return lon, lat

    # 2) state/FT centroid
    if k in STATE_CENTROIDS:
        return STATE_CENTROIDS[k]

    # 3) fuzzy match against locations.csv
    best = difflib.get_close_matches(area_raw, all_names, n=1, cutoff=0.78)
    if best:
        bk = norm(best[0])
        if bk in by_norm:
            lon, lat, _ = by_norm[bk]
            return lon, lat

    return None

def to_features(raw, loc_index, log):
    feats = []
    items = raw
    if isinstance(raw, dict):
       
        items = raw.get("warnings") or raw.get("data") or raw.get("results") or []

    total_items = len(items) if isinstance(items, list) else 0
    total_areas = 0
    placed = 0
    skipped = 0

    for w in (items or []):
        title = coalesce(w, "title", "headline", "event", "type") or "Warning"
        area_val  = coalesce(w, "area", "areas", "location", "district", "state", "zone") or ""
        desc  = coalesce(w, "description", "summary", "details", "message") or ""
        issued= coalesce(w, "issued", "time", "onset", "sent", "effective")
        start = coalesce(w, "start", "onset", "effective")
        end   = coalesce(w, "end", "expires", "until", "expiry")
        cat   = coalesce(w, "category", "level", "severity")
        src   = coalesce(w, "url", "source_url", "link")

        # If geometry already present
        if "geometry" in w and isinstance(w["geometry"], dict):
            feats.append({"type":"Feature","geometry":w["geometry"],"properties":{
                "title":title,"area":area_val,"description":desc,"issued":issued,
                "start":start,"end":end,"category":cat,"source_url":src}})
            placed += 1
            continue

        # Expand areas
        areas = split_areas(area_val) or [str(area_val)] if area_val else []
        if not areas:
            areas = ["Malaysia"]  # extremely defensive

        for a in areas:
            total_areas += 1
            pt = place_area(a, loc_index)
            if not pt:
                log.append(f"[WARN] Could not place area '{a}' for warning '{title}'")
                skipped += 1
                continue
            lon, lat = pt
            feats.append({
                "type":"Feature",
                "geometry":{"type":"Point","coordinates":[lon, lat]},
                "properties":{
                    "title": title,
                    "area": a,
                    "description": desc,
                    "issued": issued,
                    "start": start,
                    "end": end,
                    "category": cat,
                    "source_url": src
                }
            })
            placed += 1
    
    return feats, dict(total_items=total_items, total_areas=total_areas, placed=placed, skipped=skipped)

def main():
    if not IN_WARN.exists():
        print(f"[ERROR] Not found: {IN_WARN}")
        return

    try:
        raw = json.loads(IN_WARN.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to read {IN_WARN}: {e}")
        return

    loc_index = load_locations()
    if not loc_index[0]:
        print(f"[ERROR] Need locations.csv with location_name,lat,lon in {IN_LOC}")
        return

    log = []
    feats, stats = to_features(raw, loc_index, log)
    fc = {"type":"FeatureCollection","features":feats}
    OUT_GEO.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Wrote {OUT_GEO} with {len(feats)} features")
    print(f"[INFO] Stats: items={stats['total_items']} areas={stats['total_areas']} placed={stats['placed']} skipped={stats['skipped']}")
    if log:
        # show up to 20 reasons to avoid spam
        print("\n".join(log[:20]))
        if len(log) > 20:
            print(f"... (+{len(log)-20} more)")

if __name__ == "__main__":
    main()
