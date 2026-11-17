import os
import json
import time
import socket
from datetime import datetime
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import gdown
import urllib3.util.connection as urllib3_cn

urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

# ==============================================================================
# PEGÁ ENTRE COMILLAS LOS DOS ENLACES DE GOOGLE DRIVE QUE COMPARTISTE RECIÉN:
URL_DRIVE_RADIOS = "https://drive.google.com/file/d/1KiOw4aettgbjLZJIwms86yVp-lPXcBXQ/view?usp=drivesdk"
URL_DRIVE_DEPTOS = "https://drive.google.com/file/d/1_BthlwEU2QMKtUlzwDv1AEsF4mB6SB9E/view?usp=drivesdk"
# ==============================================================================

URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

RUTA_RADIOS = "datos_censales/radios_2022.gpkg"
RUTA_DEPTOS = "datos_censales/deptos_2022.gpkg"
RUTA_CACHE_OSM = "datos_censales/pois_osm.json"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def cargar_locales():
    df = pd.read_csv(URL_DATOS_MERCADO_CSV)
    df = df[["slug_local", "latitud", "longitud"]].dropna().copy()
    df["latitud"] = pd.to_numeric(df["latitud"].astype(str).str.replace(",", "."), errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"].astype(str).str.replace(",", "."), errors="coerce")
    return df.dropna(subset=["latitud", "longitud"]).drop_duplicates(subset=["slug_local"])


def descargar_desde_drive(url_drive, ruta_destino):
    if not url_drive.startswith("http"):
        return False
    os.makedirs(os.path.dirname(ruta_destino), exist_ok=True)
    if not os.path.exists(ruta_destino):
        print(f"Descargando capa censal en la nube -> {ruta_destino}...")
        gdown.download(url_drive, ruta_destino, quiet=False, fuzzy=True)
    return os.path.exists(ruta_destino)


def detectar_columna_poblacion(columnas):
    prioridad = [
        "pob_2022", "poblacion_2022", "personas_2022", "p2022",
        "poblacion", "tot_pob", "pob_tot", "personas", "pob"
    ]
    cols_lower = {c.lower(): c for c in columnas}
    for candidato in prioridad:
        if candidato in cols_lower:
            return cols_lower[candidato]
    for c in columnas:
        cl = c.lower()
        if ("pob" in cl or "pers" in cl) and "2022" in cl and "dens" not in cl and "var" not in cl:
            return c
    for c in columnas:
        cl = c.lower()
        if "pob" in cl and "dens" not in cl and "var" not in cl and "pct" not in cl:
            return c
    return None


def detectar_columna_hogares(columnas):
    cols_lower = {c.lower(): c for c in columnas}
    for candidato in ["hog_2022", "hogares_2022", "h2022", "hogares", "hog"]:
        if candidato in cols_lower:
            return cols_lower[candidato]
    return None


def calcular_censo_500m(gdf_buffers_3857, ruta_gpkg):
    """Intersecta los círculos de 500m con los polígonos de poblaciones.org."""
    gdf_c = gpd.read_file(ruta_gpkg).to_crs(epsg=3857)
    print(f"Columnas detectadas en {ruta_gpkg}: {list(gdf_c.columns)}")

    col_pob = detectar_columna_poblacion(gdf_c.columns)
    col_hog = detectar_columna_hogares(gdf_c.columns)

    if not col_pob:
        print(f"No se encontró columna de población en {ruta_gpkg}")
        return {}, {}

    gdf_c["area_poligono"] = gdf_c.geometry.area.replace(0, np.nan)
    inter = gpd.overlay(gdf_buffers_3857, gdf_c, how="intersection")
    if inter.empty:
        return {}, {}

    inter["factor_area"] = (inter.geometry.area / inter["area_poligono"]).clip(0, 1)
    inter["pob_prop"] = pd.to_numeric(inter[col_pob], errors="coerce").fillna(0) * inter["factor_area"]
    pob_dict = inter.groupby("slug_local")["pob_prop"].sum().round().astype(int).to_dict()

    hog_dict = {}
    if col_hog:
        inter["hog_prop"] = pd.to_numeric(inter[col_hog], errors="coerce").fillna(0) * inter["factor_area"]
        hog_dict = inter.groupby("slug_local")["hog_prop"].sum().round().astype(int).to_dict()

    return pob_dict, hog_dict


def obtener_atractores_osm(df_locales):
    pois = {}
    if os.path.exists(RUTA_CACHE_OSM):
        with open(RUTA_CACHE_OSM, "r", encoding="utf-8") as f:
            pois = json.load(f)

    grillas = df_locales.assign(
        lat_g=df_locales["latitud"].round(0),
        lon_g=df_locales["longitud"].round(0),
    )[["lat_g", "lon_g"]].drop_duplicates()

    for _, row in grillas.iterrows():
        s, w = row["lat_g"] - 0.55, row["lon_g"] - 0.55
        n, e = row["lat_g"] + 0.55, row["lon_g"] + 0.55
        query = f"""
        [out:json][timeout:12];
        (
          node["railway"~"station|subway_entrance"]({s},{w},{n},{e});
          node["amenity"~"university|college|coworking_space|hospital"]({s},{w},{n},{e});
          way["amenity"~"university|college|hospital"]({s},{w},{n},{e});
          node["leisure"="fitness_centre"]({s},{w},{n},{e});
        );
        out center qt;
        """
        for url in OVERPASS_URLS:
            try:
                resp = requests.post(url, data={"data": query}, timeout=14)
                if resp.status_code == 200:
                    for el in resp.json().get("elements", []):
                        lat = el.get("lat") or el.get("center", {}).get("lat")
                        lon = el.get("lon") or el.get("center", {}).get("lon")
                        if lat and lon:
                            pois[f"{el['type']}_{el['id']}"] = {"lat": lat, "lon": lon}
                    break
            except Exception:
                continue
        time.sleep(0.3)

    if pois:
        os.makedirs("datos_censales", exist_ok=True)
        with open(RUTA_CACHE_OSM, "w", encoding="utf-8") as f:
            json.dump(pois, f)
        df_pois = pd.DataFrame(list(pois.values()))
        return gpd.GeoDataFrame(
            df_pois,
            geometry=gpd.points_from_xy(df_pois["lon"], df_pois["lat"]),
            crs="EPSG:4326",
        ).to_crs(epsg=3857)

    return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:3857")


def calcular_perfil_socioeconomico(row):
    pob = row["poblacion_500m"]
    hog = row["hogares_500m"]
    atr = row["atractores_500m"]
    comp = row["competidores_500m"]

    # Hogares unipersonales/chicos (< 2.4 pers/hogar) suelen correlacionar con PEA joven/activa alta
    pers_por_hogar = (pob / hog) if hog > 0 else 2.8
    bonus_hogar = max(0.0, (3.0 - pers_por_hogar) * 5.0)
    pea_est = round(min(76.0, max(54.0, 56.0 + bonus_hogar + (atr * 0.7))), 1)

    score_urbano = (pob / 1000.0) + (atr * 2.5) + (comp * 1.5) + bonus_hogar
    if score_urbano >= 24:
        nse = "Alto"
    elif score_urbano >= 13:
        nse = "Medio-Alto"
    elif score_urbano >= 5:
        nse = "Medio"
    else:
        nse = "Emergente"
    return pd.Series([pea_est, nse])


def main():
    df_locales = cargar_locales()
    gdf_locales = gpd.GeoDataFrame(
        df_locales,
        geometry=gpd.points_from_xy(df_locales["longitud"], df_locales["latitud"]),
        crs="EPSG:4326",
    ).to_crs(epsg=3857)

    gdf_buffers = gdf_locales[["slug_local", "geometry"]].copy()
    gdf_buffers["geometry"] = gdf_buffers.geometry.buffer(500)

    # 1. Competencia en 500m
    cruce_comp = gpd.sjoin(gdf_buffers, gdf_locales[["slug_local", "geometry"]], how="left", predicate="intersects")
    conteo_comp = (cruce_comp.groupby("slug_local_left").size() - 1).clip(lower=0)

    # 2. Atractores diurnos (OpenStreetMap)
    gdf_pois = obtener_atractores_osm(df_locales)
    if not gdf_pois.empty:
        cruce_pois = gpd.sjoin(gdf_buffers, gdf_pois, how="inner", predicate="intersects")
        conteo_pois = cruce_pois.groupby("slug_local").size()
    else:
        conteo_pois = pd.Series(dtype=int)

    # 3. Censo 2022 (Radios urbanos como principal, Departamentos como respaldo)
    pob_radios, hog_radios = {}, {}
    if descargar_desde_drive(URL_DRIVE_RADIOS, RUTA_RADIOS):
        pob_radios, hog_radios = calcular_censo_500m(gdf_buffers, RUTA_RADIOS)

    pob_deptos, hog_deptos = {}, {}
    if descargar_desde_drive(URL_DRIVE_DEPTOS, RUTA_DEPTOS):
        pob_deptos, hog_deptos = calcular_censo_500m(gdf_buffers, RUTA_DEPTOS)

    res = df_locales[["slug_local", "latitud", "longitud"]].copy()
    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["atractores_500m"] = res["slug_local"].map(conteo_pois).fillna(0).astype(int)

    res["poblacion_500m"] = res["slug_local"].apply(
        lambda s: pob_radios[s] if pob_radios.get(s, 0) > 0 else pob_deptos.get(s, 0)
    ).astype(int)

    res["hogares_500m"] = res["slug_local"].apply(
        lambda s: hog_radios[s] if hog_radios.get(s, 0) > 0 else hog_deptos.get(s, 0)
    ).astype(int)

    perfiles = res.apply(calcular_perfil_socioeconomico, axis=1)
    res["pea_porcentaje"] = perfiles[0]
    res["nivel_socioeconomico"] = perfiles[1]

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
    print(f"Cruce censal 2022 finalizado: {len(res)} locales procesados.")


if __name__ == "__main__":
    main()
