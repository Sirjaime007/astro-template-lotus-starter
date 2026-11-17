import os
import time
from datetime import datetime
import pandas as pd
import geopandas as gpd
import requests

# Tu hoja Datos_Mercado publicada como CSV
URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RUTA_CENSO = "datos_censales/radios_censales.geojson"


def cargar_locales():
    df = pd.read_csv(URL_DATOS_MERCADO_CSV)
    df = df[["slug_local", "latitud", "longitud"]].dropna().copy()
    df["latitud"] = pd.to_numeric(df["latitud"].astype(str).str.replace(",", "."), errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"].astype(str).str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"]).drop_duplicates(subset=["slug_local"])
    return df


def obtener_atractores_osm(df_locales):
    """Consulta OpenStreetMap agrupando locales en grillas de ~11 km para evitar límites de API."""
    grillas = df_locales.assign(
        lat_g=df_locales["latitud"].round(1),
        lon_g=df_locales["longitud"].round(1),
    )[["lat_g", "lon_g"]].drop_duplicates()

    pois = {}
    for _, row in grillas.iterrows():
        s, w = row["lat_g"] - 0.06, row["lon_g"] - 0.06
        n, e = row["lat_g"] + 0.06, row["lon_g"] + 0.06
        query = f"""
        [out:json][timeout:25];
        (
          node["railway"~"station|subway_entrance"]({s},{w},{n},{e});
          node["amenity"~"university|college|coworking_space|hospital|bank"]({s},{w},{n},{e});
          way["amenity"~"university|college|hospital"]({s},{w},{n},{e});
          node["office"]({s},{w},{n},{e});
          node["leisure"="fitness_centre"]({s},{w},{n},{e});
        );
        out center;
        """
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
            if resp.status_code == 200:
                for el in resp.json().get("elements", []):
                    lat = el.get("lat") or el.get("center", {}).get("lat")
                    lon = el.get("lon") or el.get("center", {}).get("lon")
                    if lat and lon:
                        pois[(el["type"], el["id"])] = {"lat": lat, "lon": lon}
            time.sleep(1.5)
        except Exception as err:
            print(f"Aviso Overpass en grilla ({row['lat_g']}, {row['lon_g']}): {err}")

    if not pois:
        return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:3857")

    df_pois = pd.DataFrame(list(pois.values()))
    return gpd.GeoDataFrame(
        df_pois,
        geometry=gpd.points_from_xy(df_pois["lon"], df_pois["lat"]),
        crs="EPSG:4326",
    ).to_crs(epsg=3857)


def main():
    print("1. Descargando coordenadas actualizadas de Cofiteca...")
    df_locales = cargar_locales()

    gdf_locales = gpd.GeoDataFrame(
        df_locales,
        geometry=gpd.points_from_xy(df_locales["longitud"], df_locales["latitud"]),
        crs="EPSG:4326",
    ).to_crs(epsg=3857)

    # Círculo exacto de 500 metros alrededor de cada cafetería
    gdf_buffers = gdf_locales[["slug_local", "geometry"]].copy()
    gdf_buffers["geometry"] = gdf_buffers.geometry.buffer(500)

    print("2. Calculando saturación de competencia (radio 500 m)...")
    cruce_comp = gpd.sjoin(gdf_buffers, gdf_locales[["slug_local", "geometry"]], how="left", predicate="intersects")
    conteo_comp = (cruce_comp.groupby("slug_local_left").size() - 1).clip(lower=0)

    print("3. Consultando atractores de tráfico diurno en OpenStreetMap...")
    gdf_pois = obtener_atractores_osm(df_locales)
    if not gdf_pois.empty:
        cruce_pois = gpd.sjoin(gdf_buffers, gdf_pois, how="inner", predicate="intersects")
        conteo_pois = cruce_pois.groupby("slug_local").size()
    else:
        conteo_pois = pd.Series(dtype=int)

    # Base de resultados
    res = df_locales[["slug_local", "latitud", "longitud"]].copy()
    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["atractores_500m"] = res["slug_local"].map(conteo_pois).fillna(0).astype(int)
    res["poblacion_500m"] = 0
    res["pea_porcentaje"] = 0.0
    res["nivel_socioeconomico"] = "En calibración"

    print("4. Verificando capa censal (INDEC / poblaciones.org)...")
    if os.path.exists(RUTA_CENSO):
        gdf_censo = gpd.read_file(RUTA_CENSO).to_crs(epsg=3857)
        cruce_censo = gpd.sjoin(gdf_buffers, gdf_censo, how="inner", predicate="intersects")
        # Ajustá los nombres de columna según el GeoJSON descargado (ej. POBLACION / TOT_POB)
        col_pob = next((c for c in gdf_censo.columns if c.upper() in ["POBLACION", "TOT_POB", "POB_TOT"]), None)
        if col_pob:
            pob_map = cruce_censo.groupby("slug_local")[col_pob].sum()
            res["poblacion_500m"] = res["slug_local"].map(pob_map).fillna(0).astype(int)

    # Cálculo del Índice de Oportunidad (Demanda + Tráfico diurno vs Competencia)
    res["indice_oportunidad"] = (
        ((res["poblacion_500m"] / 100.0) + (res["atractores_500m"] * 15.0))
        / (res["competidores_500m"] + 1)
    ).round(1)

    res["fecha_actualizacion"] = datetime.now().strftime("%Y-%m-%d")

    os.makedirs("src/data", exist_ok=True)
    os.makedirs("public/data", exist_ok=True)

    # 1) JSON listo para importar directo en Astro
    res.set_index("slug_local").to_json("src/data/mercado.json", orient="index", force_ascii=False, indent=2)

    # 2) CSV limpio para sincronizar de vuelta con Google Sheets
    cols_sheets = [
        "poblacion_500m",
        "pea_porcentaje",
        "competidores_500m",
        "indice_oportunidad",
        "nivel_socioeconomico",
        "atractores_500m",
        "fecha_actualizacion",
    ]
    res[cols_sheets].to_csv("public/data/mercado.csv", index=False)
    print(f"Proceso completado: {len(res)} locales analizados.")


if __name__ == "__main__":
    main()
