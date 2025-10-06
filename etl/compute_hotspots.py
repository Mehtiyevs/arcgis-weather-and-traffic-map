
import os
import json
import math
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, Point
from shapely.ops import transform
import pandas as pd
import pyproj
import argparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

DEFAULT_IN_FILES = [
    DATA_DIR / "traffic_incidents.geojson", 
 
]
OUT = DATA_DIR / "hotspots_hex.geojson"

def make_hex_grid(bounds_wgs84, hex_radius_m):
    """
    Create a hex grid (pointy-top) covering bounds in WGS84.
    hex_radius_m is the distance from center to any vertex (meters).
    """
    minx, miny, maxx, maxy = bounds_wgs84

    crs_wgs84 = pyproj.CRS("EPSG:4326")
    crs_merc  = pyproj.CRS("EPSG:3857")
    to_merc   = pyproj.Transformer.from_crs(crs_wgs84, crs_merc, always_xy=True).transform
    to_wgs    = pyproj.Transformer.from_crs(crs_merc,  crs_wgs84, always_xy=True).transform

    # Project bbox to meters 
    (minx_m, miny_m) = transform(to_merc, Point(minx, miny)).coords[0]
    (maxx_m, maxy_m) = transform(to_merc, Point(maxx, maxy)).coords[0]
    pad = hex_radius_m * 2
    minx_m -= pad; miny_m -= pad; maxx_m += pad; maxy_m += pad

    # Pointy-top hex geometry constants
    R = hex_radius_m
    dx = R * math.sqrt(3)          # horizontal spacing between centers
    dy = R * 1.5                   # vertical spacing between centers

    cols = int(math.ceil((maxx_m - minx_m) / dx)) + 1
    rows = int(math.ceil((maxy_m - miny_m) / dy)) + 1

    # Prebuild local transformer to avoid recreating in loop
    polys = []
    for r in range(rows):
        for c in range(cols):
            cx = minx_m + c * dx + (dx / 2 if r % 2 else 0)  # offset every other row
            cy = miny_m + r * dy
            # 6 vertices (pointy-top)
            verts = []
            for i in range(6):
                ang = math.pi / 3 * i
                px = cx + R * math.cos(ang)
                py = cy + R * math.sin(ang)
                vx, vy = transform(to_wgs, Point(px, py)).coords[0]
                verts.append((vx, vy))
            polys.append(Polygon(verts))
    return polys

def load_points(in_files):
    frames = []
    for f in in_files:
        f = Path(f)
        if not f.exists():
            continue
        try:
            g = gpd.read_file(f)
            if g.empty:
                continue
            # drop non-point geometries safely
            g = g[g.geometry.type == "Point"].copy()
            if g.empty:
                continue
            # ensure WGS84
            if g.crs is None:
                g.set_crs(epsg=4326, inplace=True)
            else:
                g = g.to_crs(epsg=4326)
            frames.append(g)
            print(f"[INFO] Loaded {len(g)} points from {f.name}")
        except Exception as e:
            print(f"[WARN] Failed to read {f}: {e}")
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")

def main():
    parser = argparse.ArgumentParser(description="Compute hexagon hotspots from point data.")
    parser.add_argument("--hex_m", type=int, default=2000, help="Hex radius in meters (center to vertex). Default 2000.")
    parser.add_argument("--inputs", nargs="*", default=[str(p) for p in DEFAULT_IN_FILES], help="Input point files (GeoJSON).")
    parser.add_argument("--out", default=str(OUT), help="Output GeoJSON path.")
    parser.add_argument("--weight_field", default=None, help="Optional numeric field to use as weight per point.")
    args = parser.parse_args()

    pts = load_points(args.inputs)
    if pts.empty:
        print("[ERROR] No point data found. Checked:", args.inputs)
        return

    minx, miny, maxx, maxy = pts.total_bounds
    hexes = make_hex_grid((minx, miny, maxx, maxy), args.hex_m)
    hex_gdf = gpd.GeoDataFrame(geometry=hexes, crs="EPSG:4326")

    # Spatial join: assign points to hexagon index
    hex_gdf = hex_gdf.reset_index(names="hex_id")
    joined = gpd.sjoin(pts, hex_gdf[["hex_id", "geometry"]], how="inner", predicate="within")

    # Count (or weighted sum)
    if args.weight_field and args.weight_field in joined.columns:
        agg = joined.groupby("hex_id")[args.weight_field].sum().reset_index(name="value")
    else:
        agg = joined.groupby("hex_id").size().reset_index(name="value")

    # Merge back
    hex_gdf = hex_gdf.merge(agg, on="hex_id", how="left").fillna({"value": 0})
    hex_gdf["value"] = hex_gdf["value"].astype(float)

    # Compute hex area in km2 and density
    merc = hex_gdf.to_crs(epsg=3857)
    hex_gdf["area_km2"] = merc.geometry.area / 1_000_000.0
    # Avoid division by zero
    hex_gdf["density_per_km2"] = hex_gdf.apply(
        lambda r: (r["value"] / r["area_km2"]) if r["area_km2"] > 0 else 0.0, axis=1
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
  
    export = hex_gdf[["hex_id", "value", "area_km2", "density_per_km2", "geometry"]]
    export.to_file(out_path, driver="GeoJSON")
    print(f"[OK] Wrote hotspots -> {out_path}  (hex_m={args.hex_m}, features={len(export)})")

if __name__ == "__main__":
    main()

