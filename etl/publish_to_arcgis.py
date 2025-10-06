import os
from pathlib import Path
import json
import dotenv
from arcgis.gis import GIS

ROOT = Path(__file__).resolve().parents[1]
dotenv.load_dotenv(ROOT / ".env")

ARCGIS_URL = os.getenv("ARCGIS_URL", "https://www.arcgis.com")
ARCGIS_USERNAME = os.getenv("ARCGIS_USERNAME")
ARCGIS_PASSWORD = os.getenv("ARCGIS_PASSWORD")

# Optional: auto-share items publicly after create/publish (true/false)
SHARE_PUBLIC = os.getenv("ARCGIS_SHARE_PUBLIC", "true").lower() in ("1","true","yes")

def _delete_existing_by_title(gis: GIS, title: str, item_types):
    """Delete items owned by me with matching title and type in item_types."""
    me = gis.users.me
    for itype in item_types:
        hits = gis.content.search(query=f'title:"{title}" AND owner:{me.username}', item_type=itype, max_items=50)
        for it in hits:
            if it.title == title and it.owner == me.username:
                print(f"[INFO] Deleting existing {itype}: {it.id} ({it.title})")
                try:
                    it.delete()
                except Exception as e:
                    print(f"[WARN] Failed to delete {it.id}: {e}")

def _share_if_requested(item):
    if not SHARE_PUBLIC:
        return
    try:
        item.share(everyone=True)
        print(f"[OK] Shared publicly: {item.title}  {item.id}")
    except Exception as e:
        print(f"[WARN] Failed to share publicly: {e}")

def _upload_geojson_file_item(gis: GIS, geojson_path: Path, title: str, tags=None):
    """Upload a GeoJSON file item (no publish). Works on public accounts."""
    tags = tags or ["ackgis"]
    _delete_existing_by_title(gis, title, ["GeoJSON"])
    props = {"title": title, "tags": ",".join(tags), "type": "GeoJson"}
    print(f"[INFO] Uploading as File Item (GeoJSON): {title}")
    item = gis.content.add(item_properties=props, data=str(geojson_path))
    _share_if_requested(item)
    print(f"[OK] Uploaded file item: {item.title}  id={item.id}  (no publishing privileges)")
    return item

def _try_publish_feature_layer(gis: GIS, geojson_path: Path, title: str, tags=None, time_field=None):
    """
    Try to publish a Hosted Feature Layer.
    On privilege error, fall back to uploading GeoJSON as a file item.
    """
    tags = tags or ["ackgis"]

    # Clean old items first
    _delete_existing_by_title(gis, title, ["Feature Service", "GeoJSON"])

    print(f"[INFO] Adding GeoJSON item: {title}")
    file_item = gis.content.add(item_properties={"title": title, "tags": ",".join(tags), "type": "GeoJson"},
                                data=str(geojson_path))
    try:
        print(f"[INFO] Publishing hosted feature layer: {title}")
        fl_item = file_item.publish()
        print(f"[OK] Published: {fl_item.title}  id={fl_item.id}")
        print(f"     URL: {fl_item.url}")

        if time_field:
            try:
                lyr = fl_item.layers[0]
                lyr.manager.update_definition({"timeInfo": {"startTimeField": time_field}})
                print(f"[OK] Set timeInfo.startTimeField = {time_field}")
            except Exception as te:
                print(f"[WARN] Failed to set timeInfo: {te}")

        _share_if_requested(fl_item)
        return fl_item

    except Exception as e:
        msg = str(e)
        print(f"[WARN] Publish failed, falling back to file item. Reason: {msg}")
        _share_if_requested(file_item)
        print("[HINT] To publish in an Org account: open the uploaded GeoJSON item in ArcGIS Online and click 'Publish'.")
        return file_item

def main():
    gis = GIS(ARCGIS_URL, ARCGIS_USERNAME, ARCGIS_PASSWORD)
    me = gis.users.me
    print(f"[INFO] Signed in as: {me.username}")

    data_dir = ROOT / "data"

    targets = [
        (data_dir / "traffic_incidents.geojson", "Traffic Incidents (MRT)", ["ackgis","traffic"], "timestamp_ms"),
        (data_dir / "hotspots_hex.geojson",      "Traffic Hotspots (Hex)",  ["ackgis","traffic"], None),
        (data_dir / "weather_forecast.geojson",  "MET Forecasts",           ["ackgis","weather"], "date"),  # string date; you can add date_ms later if needed
    ]

    for path, title, tags, time_field in targets:
        if not path.exists():
            print(f"[SKIP] Not found: {path}")
            continue
        _try_publish_feature_layer(gis, path, title, tags=tags, time_field=time_field)

if __name__ == "__main__":
    main()
