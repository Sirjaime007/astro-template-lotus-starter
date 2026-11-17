import os
import time
import socket
from datetime import datetime
import pandas as pd
import geopandas as gpd
import requests
import urllib3.util.connection as urllib3_cn

# Forzar IPv4 para evitar "[Errno 101] Network is unreachable" en GitHub Actions
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

RUTA_CENSO = "datos_censales/radios_censales.geojson"


def cargar_locales():
    df = pd.read_csv(URL_DATOS_MERCADO_CSV)
    df = df[["slug_local", "latitud", "longitud"]].dropna().copy()
    df["latitud"] = pd.to_numeric(df["latitud"].astype(str).str.replace(",", "."), errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"].astype(str).str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"]).drop_duplicates(subset=["slug_local"])
    return df


def consultar_servidor_osm(query):
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, timeout=18)
            if resp.status_code == 200:
                return resp.json().get("elements", [])
        except Exception:
            continue
    return None


def obtener_atractores_osm(df_locales):
    """Agrupa locales en cuadrículas de ~55 km y usa servidores espejo con límite de 3 minutos."""
    grillas = df_locales.assign(
        lat_g=(df_locales["latitud"] * 2).round() / 2,
        lon_g=(df_locales["longitud"] * 2).round() / 2,
    )[["lat_g", "lon_g"]].drop_duplicates()

    print(f"Consultando {len(grillas)} zonas urbanas en OpenStreetMap...")
    pois = {}
    inicio = time.time()

    for _, row in grillas.iterrows():
        if time.time() - inicio > 180:
            print("Límite de tiempo OSM alcanzado, continuando con datos recolectados.")
            break

        s, w = row["lat_g"] - 0.26, row["lon_g"] - 0.26
        n, e = row["lat_g"] + 0.26, row["lon_g"] + 0.26
        query = f"""
        [out:json][timeout:15];
        (
          node["railway"~"station|subway_entrance"]({s},{w},{n},{e});
          node["amenity"~"university|college|coworking_space|hospital|bank"]({s},{w},{n},{e});
          way["amenity"~"university|college|hospital"]({s},{w},{n},{e});
          node["office"]({s},{w},{n},{e});
          node["leisure"="fitness_centre"]({s},{w},{n},{e});
        );
        out center;
        """
        elementos = consultar_servidor_osm(query)
        if elementos:
            for el in elementos:
                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat and lon:
                    pois[(el["type"], el["id"])] = {"lat": lat, "lon": lon}
        time.sleep(0.5)

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

    res = df_locales[["slug_local", "latitud", "longitud"]].copy()
    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["atractores_500m"] = res["slug_local"].map(conteo_pois).fillna(0).astype(int)
    res["poblacion_500m"] = 0
    res["pea_porcentaje"] = 0.0
    res["nivel_socioeconomico"] = "En calibración"

    if os.path.exists(RUTA_CENSO):
        gdf_censo = gpd.read_file(RUTA_CENSO).to_crs(epsg=3857)
        cruce_censo = gpd.sjoin(gdf_buffers, gdf_censo, how="inner", predicate="intersects")
        col_pob = next((c for c in gdf_censo.columns if c.upper() in ["POBLACION", "TOT_POB", "POB_TOT"]), None)
        if col_pob:
            pob_map = cruce_censo.groupby("slug_local")[col_pob].sum()
            res["poblacion_500m"] = res["slug_local"].map(pob_map).fillna(0).astype(int)

    res["indice_oportunidad"] = (
        ((res["poblacion_500m"] / 100.0) + (res["atractores_500m"] * 15.0))
        / (res["competidores_500m"] + 1)
    ).round(1)

    res["fecha_actualizacion"] = datetime.now().strftime("%Y-%m-%d")

    os.makedirs("src/data", exist_ok=True)
    os.makedirs("public/data", exist_ok=True)

    res.set_index("slug_local").to_json("src/data/mercado.json", orient="index", force_ascii=False, indent=2)

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
    print(f"Proceso completado en tiempo récord: {len(res)} locales analizados.")


if __name__ == "__main__":
    main()
