import os
import re
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

URL_DRIVE_RADIOS = "https://drive.google.com/file/d/1KiOw4aettgbjLZJIwms86yVp-lPXcBXQ/view?usp=drivesdk"
URL_DRIVE_DEPTOS = "https://drive.google.com/file/d/1_BthlwEU2QMKtUlzwDv1AEsF4mB6SB9E/view?usp=drivesdk"

URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

RUTA_RADIOS = "datos_censales/radios_2022.gpkg"
RUTA_DEPTOS = "datos_censales/deptos_2022.gpkg"
RUTA_CACHE_OSM = "datos_censales/pois_osm_v2.json"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def cargar_locales():
    log("1/5 Descargando locales desde Google Sheets...")
    df = pd.read_csv(URL_DATOS_MERCADO_CSV)
    df = df[["slug_local", "latitud", "longitud"]].dropna().copy()
    df["latitud"] = pd.to_numeric(df["latitud"].astype(str).str.replace(",", "."), errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"].astype(str).str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"]).drop_duplicates(subset=["slug_local"])
    log(f"    -> {len(df)} locales válidos cargados.")
    return df


def descargar_desde_drive(url_drive, ruta_destino):
    os.makedirs(os.path.dirname(ruta_destino), exist_ok=True)
    if os.path.exists(ruta_destino) and os.path.getsize(ruta_destino) > 50000:
        log(f"    -> Archivo ya disponible en caché: {ruta_destino}")
        return True

    match = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]+)", url_drive)
    if not match:
        return False

    file_id = match.group(1)
    url_uc = f"https://drive.google.com/uc?id={file_id}"
    log(f"    -> Descargando {ruta_destino} desde Google Drive...")
    try:
        gdown.download(url_uc, ruta_destino, quiet=True)
    except Exception as e:
        log(f"    -> Aviso gdown: {e}")

    return os.path.exists(ruta_destino) and os.path.getsize(ruta_destino) > 50000


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


def calcular_censo_500m(gdf_buffers_3857, ruta_gpkg):
    if gdf_buffers_3857.empty:
        return {}

    log(f"    -> Leyendo polígonos de {ruta_gpkg}...")
    gdf_c = gpd.read_file(ruta_gpkg).to_crs(epsg=3857)
    col_pob = detectar_columna_poblacion(gdf_c.columns)
    if not col_pob:
        return {}

    gdf_c = gdf_c[gdf_c.geometry.notnull() & ~gdf_c.geometry.is_empty].copy()
    gdf_c["area_poligono"] = gdf_c.geometry.area.replace(0, np.nan)

    pares = gpd.sjoin(gdf_buffers_3857, gdf_c, how="inner", predicate="intersects")
    if pares.empty:
        return {}

    geom_buf = gpd.GeoSeries(gdf_buffers_3857.loc[pares.index, "geometry"].values, crs="EPSG:3857")
    geom_pol = gpd.GeoSeries(gdf_c.loc[pares["index_right"], "geometry"].values, crs="EPSG:3857")
    area_inter = geom_buf.intersection(geom_pol).area.values

    factor_area = np.nan_to_num(np.clip(area_inter / pares["area_poligono"].values, 0.0, 1.0), nan=0.0)
    pares["pob_prop"] = pd.to_numeric(pares[col_pob], errors="coerce").fillna(0).values * factor_area
    return pares.groupby("slug_local")["pob_prop"].sum().round().astype(int).to_dict()


def clasificar_poi_osm(tags):
    if tags.get("tourism") or tags.get("natural") == "beach":
        return "turismo"
    if tags.get("shop") or tags.get("amenity") in ("restaurant", "bar", "pub", "fast_food", "ice_cream"):
        return "comercio"
    return "transporte"


def obtener_circulacion_osm(df_locales):
    log("3/5 Consultando flujo comercial, turístico y transporte (OpenStreetMap)...")
    pois = {}
    if os.path.exists(RUTA_CACHE_OSM):
        with open(RUTA_CACHE_OSM, "r", encoding="utf-8") as f:
            pois = json.load(f)

    # Agrupa por macro-regiones (2 grados) y consulta solo el rectángulo exacto donde hay locales
    df_tmp = df_locales.copy()
    df_tmp["gx"] = (df_tmp["longitud"] // 2.0) * 2.0
    df_tmp["gy"] = (df_tmp["latitud"] // 2.0) * 2.0

    bloques = df_tmp.groupby(["gx", "gy"]).agg(
        s=("latitud", "min"),
        n=("latitud", "max"),
        w=("longitud", "min"),
        e=("longitud", "max"),
    ).reset_index()

    log(f"    -> Consultando {len(bloques)} polos regionales en bloque...")

    for _, b in bloques.iterrows():
        s, w = round(b["s"] - 0.01, 4), round(b["w"] - 0.01, 4)
        n, e = round(b["n"] + 0.01, 4), round(b["e"] + 0.01, 4)

        query = (
            f'[out:json][timeout:18];('
            f'node["shop"]({s},{w},{n},{e});'
            f'node["amenity"~"restaurant|bar|pub|fast_food|ice_cream|university|college|hospital|clinic|bank|theatre|cinema"]({s},{w},{n},{e});'
            f'node["tourism"~"hotel|hostel|guest_house|motel|apartment|museum|attraction|viewpoint|information"]({s},{w},{n},{e});'
            f'way["tourism"~"hotel|museum|attraction"]({s},{w},{n},{e});'
            f'way["natural"="beach"]({s},{w},{n},{e});'
            f'node["highway"="bus_stop"]({s},{w},{n},{e});'
            f'node["railway"~"station|subway_entrance"]({s},{w},{n},{e});'
            f'way["leisure"="park"]({s},{w},{n},{e});'
            f');out center qt;'
        )

        for url in OVERPASS_URLS:
            try:
                resp = requests.post(url, data={"data": query}, timeout=(6, 22))
                if resp.status_code == 200:
                    elementos = resp.json().get("elements", [])
                    for el in elementos:
                        lat = el.get("lat") or el.get("center", {}).get("lat")
                        lon = el.get("lon") or el.get("center", {}).get("lon")
                        if lat and lon:
                            cat = clasificar_poi_osm(el.get("tags", {}))
                            pois[f"{el['type']}_{el['id']}"] = {"lat": lat, "lon": lon, "cat": cat}
                    log(f"    -> Bloque ({s}, {w}): +{len(elementos)} puntos detectados.")
                    break
            except Exception as ex:
                log(f"    -> Reintentando espejo OSM ({ex})...")
                continue
        time.sleep(0.4)

    log(f"    -> Total acumulado en todo el país: {len(pois)} puntos de circulación.")
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

    return gpd.GeoDataFrame(columns=["cat", "geometry"], crs="EPSG:3857")


def evaluar_entorno_y_circulacion(row):
    pob = row["poblacion_500m"]
    com = row["comercios_500m"]
    tur = row["turismo_500m"]
    tra = row["transporte_500m"]
    comp = row["competidores_500m"]

    # Score de circulación peatonal y turística
    flujo_score = com + (tur * 4) + (tra * 2)
    if flujo_score >= 120:
        circulacion = "Muy Alta"
    elif flujo_score >= 50:
        circulacion = "Alta"
    elif flujo_score >= 15:
        circulacion = "Media"
    else:
        circulacion = "Baja"

    # PEA estimada según actividad diurna del entorno
    pea_est = round(min(76.0, max(55.0, 56.0 + (tra * 0.4) + (com * 0.08))), 1)

    # Perfil comercial/urbano del entorno
    score_urbano = (pob / 1000.0) + (com * 0.15) + (tur * 0.6) + (comp * 1.2)
    if score_urbano >= 24:
        nse = "Alto"
    elif score_urbano >= 13:
        nse = "Medio-Alto"
    elif score_urbano >= 5:
        nse = "Medio"
    else:
        nse = "Emergente"

    # Índice de oportunidad equilibrado: combina residentes fijos + flujo peatonal/turístico
    demanda_total = (pob / 100.0) + (flujo_score * 0.55)
    oportunidad = round(demanda_total / (comp + 1), 1)

    return pd.Series([circulacion, pea_est, nse, oportunidad])


def main():
    df_locales = cargar_locales()
    gdf_locales = gpd.GeoDataFrame(
        df_locales,
        geometry=gpd.points_from_xy(df_locales["longitud"], df_locales["latitud"]),
        crs="EPSG:4326",
    ).to_crs(epsg=3857)

    gdf_buffers = gdf_locales[["slug_local", "geometry"]].copy()
    gdf_buffers["geometry"] = gdf_buffers.geometry.buffer(500)

    log("2/5 Calculando competencia a 500 metros...")
    cruce_comp = gpd.sjoin(gdf_buffers, gdf_locales[["slug_local", "geometry"]], how="left", predicate="intersects")
    conteo_comp = (cruce_comp.groupby("slug_local_left").size() - 1).clip(lower=0)

    gdf_pois = obtener_circulacion_osm(df_locales)
    conteo_com = pd.Series(dtype=int)
    conteo_tur = pd.Series(dtype=int)
    conteo_tra = pd.Series(dtype=int)

    if not gdf_pois.empty:
        cruce_pois = gpd.sjoin(gdf_buffers, gdf_pois[["cat", "geometry"]], how="inner", predicate="intersects")
        conteo_com = cruce_pois[cruce_pois["cat"] == "comercio"].groupby("slug_local").size()
        conteo_tur = cruce_pois[cruce_pois["cat"] == "turismo"].groupby("slug_local").size()
        conteo_tra = cruce_pois[cruce_pois["cat"] == "transporte"].groupby("slug_local").size()

    log("4/5 Procesando capas censales INDEC 2022...")
    pob_radios = {}
    if descargar_desde_drive(URL_DRIVE_RADIOS, RUTA_RADIOS):
        pob_radios = calcular_censo_500m(gdf_buffers, RUTA_RADIOS)

    slugs_sin_pob = [s for s in df_locales["slug_local"] if pob_radios.get(s, 0) == 0]
    pob_deptos = {}
    if slugs_sin_pob and descargar_desde_drive(URL_DRIVE_DEPTOS, RUTA_DEPTOS):
        gdf_faltantes = gdf_buffers[gdf_buffers["slug_local"].isin(slugs_sin_pob)]
        pob_deptos = calcular_censo_500m(gdf_faltantes, RUTA_DEPTOS)

    log("5/5 Exportando datos finales para web y Google Sheets...")
    res = df_locales[["slug_local", "latitud", "longitud"]].copy()
    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["comercios_500m"] = res["slug_local"].map(conteo_com).fillna(0).astype(int)
    res["turismo_500m"] = res["slug_local"].map(conteo_tur).fillna(0).astype(int)
    res["transporte_500m"] = res["slug_local"].map(conteo_tra).fillna(0).astype(int)
    res["atractores_500m"] = res["comercios_500m"] + res["turismo_500m"] + res["transporte_500m"]

    res["poblacion_500m"] = res["slug_local"].apply(
        lambda s: pob_radios[s] if pob_radios.get(s, 0) > 0 else pob_deptos.get(s, 0)
    ).astype(int)

    evaluacion = res.apply(evaluar_entorno_y_circulacion, axis=1)
    res["nivel_circulacion"] = evaluacion[0]
    res["pea_porcentaje"] = evaluacion[1]
    res["nivel_socioeconomico"] = evaluacion[2]
    res["indice_oportunidad"] = evaluacion[3]
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
        "nivel_circulacion",
        "comercios_500m",
        "turismo_500m",
        "transporte_500m",
    ]
    res[cols_sheets].to_csv("public/data/mercado.csv", index=False)
    log(f"¡COMPLETADO! {len(res)} locales con datos censales y circulación turística.")


if __name__ == "__main__":
    main()
