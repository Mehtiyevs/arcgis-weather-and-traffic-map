# ArcGIS Weather & Traffic Project

This project collects, processes, and publishes **weather and traffic data** into **ArcGIS Online**, providing datasets and interactive maps for Malaysia.  

---

## Project Setup & User Guide

### Download & Setup

1. Download the provided **ZIP file**.  
2. Extract/unzip the folder.  
3. Open the project folder in **VS Code** (or any IDE).  
4. Locate the `.env` file in the root folder: `arcgis_weather_traffic`.  

Update the `.env` file with your **ArcGIS credentials**:

```env
ARCGIS_USERNAME=your_arcgis_username
ARCGIS_PASSWORD=your_arcgis_password
```

---

### Activate Virtual Environment

1. Create a virtual environment
## Windows (PowerShell / CMD)

```bat
python -m venv .venv

2. Open a terminal in **VS Code**.  
3. Move into the `.venv` folder step by step:

```bash
cd .venv
cd Scripts
activate
pip install -r requirements.txt # or install one by one
```

**Important:**  
Do **not** use `cd .venv/Scripts` directly. Always navigate step by step.  

3. Once activated, you’ll see the terminal change to a **`.venv` environment**.

---

### Run ETL Scripts

Navigate back to the `etl` folder:

```bash
cd ..
cd ..
cd etl
```

Run the scripts in **this exact order**:

```bash
python etl\geocode_locations.py
python etl\scrape_mrt_simple.py
python etl\build_mrt_geojson.py
python etl\scrape_traffic_feeds.py   # (It’s okay if you see warnings.)
python etl\fetch_weather.py
python etl\enrich_weather.py
python etl\build_warnings_geojson.py # (If Malaysia warnings are missing, continue.)
python etl\compute_hotspots.py --hex_m 1000
python etl\publish_to_arcgis.py      # Publishes all processed data to ArcGIS
```

---

### Verify in ArcGIS

1. Log in to [ArcGIS Online](https://www.arcgis.com/).  
2. Go to **Content → My Content**.  
3. You should now see **3 new datasets**:

- **MET Forecasts**  
- **Traffic Hotspots (Hex)**  
- **Traffic Incidents (MRT)**  

---

### Local Testing (Example Website)

1. In the terminal (still inside `.venv`), return to the root folder:

```bash
cd ..
```

2. Start a local server:

```bash
python -m http.server 8080
```

3. Open your browser and visit:

```
http://localhost:8080/web/index.html
```

This opens an **example interactive map** built with the **ArcGIS API**.  
You can view:  
- Weather data  
- Traffic data  
- Hotspots  

---

### Create ArcGIS Map (Client Workflow)

To build your own map inside **ArcGIS Online**:

1. Go to [ArcGIS Online](https://www.arcgis.com/).  
2. In **My Content**, locate:
   - **MET Forecasts**  
   - **Traffic Hotspots (Hex)**  
   - **Traffic Incidents (MRT)**  
3. For each dataset:
   - Click **Open in Map Viewer**.  
   - Add the layer to your map.  

Once all 3 layers are added:
- Save your map with a title and description.  
- Adjust **layer style** (e.g., colors, symbols, hex size).  
- Click on points/hexagons to view details.  

4. To share the map:
   - Click **Share**.  
   - Choose whether to keep it private, share with your organization, or make it public.  

---

## Notes

- The ETL scripts fetch data from:
  - **Met Malaysia API** (weather forecasts).  
  - **MRT API** (traffic incidents for Johor).  
  - **Traffic feeds** (scraped sources).  
- Example warnings (if unavailable) will not block other data.  
- If you want me to build the ArcGIS map inside your account, you can provide credentials securely via Fiverr.  
