import os
import re
import json
import zipfile
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
URL_GEOFABRIK_AR = "https://download.geofabrik.de/south-america/argentina-latest-free.shp.zip"

URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

RUTA_RADIOS = "datos_censales/radios_2022.gpkg"
RUTA_DEPTOS = "datos_censales/deptos_2022.gpkg"
RUTA_CACHE_OSM = "datos_censales/pois_osm_v2.json"

CLASES_TURISMO = {
    "hotel", "hostel", "guest_house", "motel", "chalet", "alpine_hut",
    "camp_site", "caravan_site", "museum", "attraction", "viewpoint",
    "theme_park", "zoo", "monument", "memorial", "castle", "ruins",
    "arts_centre", "tourist_info", "beach",
}

CLASES_COMERCIO = {
    "restaurant", "bar", "pub", "fast_food", "ice_cream", "food_court",
    "biergarten", "bakery", "supermarket", "convenience", "mall",
    "department_store", "clothes", "shoes", "boutique", "bookshop",
    "gift", "jeweller", "beauty_shop", "hairdresser", "chemist",
    "pharmacy", "florist", "greengrocer", "butcher", "beverages",
    "optician", "mobile_phone_shop", "electronics", "furniture_shop",
    "sports_shop", "toy_shop", "stationery", "kiosk",
}

CLASES_TRANSPORTE = {
    "bus_stop", "bus_station", "railway_station", "railway_halt",
    "subway_entrance", "tram_stop", "ferry_terminal", "taxi",
    "university", "college", "school", "hospital", "clinic",
    "bank", "courthouse", "town_hall", "post_office", "library",
    "theatre", "cinema", "nightclub", "stadium", "sports_centre", "park",
}


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


def obtener_circulacion_geofabrik(gdf_buffers_3857):
    log("3/5 Cargando capa comercial, turística y transporte de Argentina...")
    if os.path.exists(RUTA_CACHE_OSM) and os.path.getsize(RUTA_CACHE_OSM) > 10000:
        with open(RUTA_CACHE_OSM, "r", encoding="utf-8") as f:
            registros = json.load(f)
        if registros:
            log(f"    -> Caché cargada: {len(registros)} polos cercanos.")
            df_pois = pd.DataFrame(registros)
            return gpd.GeoDataFrame(
                df_pois[["cat"]],
                geometry=gpd.points_from_xy(df_pois["lon"], df_pois["lat"]),
                crs="EPSG:4326",
            ).to_crs(epsg=3857)

    ruta_zip = "/tmp/argentina_osm.zip"
    log("    -> Descargando capa OpenStreetMap Argentina (Geofabrik)...")
    try:
        with requests.get(URL_GEOFABRIK_AR, stream=True, timeout=(10, 90)) as r:
            r.raise_for_status()
            with open(ruta_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        log(f"    -> Error descargando Geofabrik: {e}")
        return gpd.GeoDataFrame(columns=["cat", "geometry"], crs="EPSG:3857")

    mb = os.path.getsize(ruta_zip) / (1024 * 1024)
    log(f"    -> Paquete descargado ({mb:.1f} MB). Extrayendo comercios, turismo y transporte...")

    capas_validas = []
    with zipfile.ZipFile(ruta_zip, "r") as zf:
        shps = [
            n for n in zf.namelist()
            if n.endswith(".shp") and ("pois" in n or "transport" in n)
        ]

    for shp in shps:
        try:
            gdf_capa = gpd.read_file(f"zip://{ruta_zip}!{shp}")
            if "fclass" not in gdf_capa.columns or gdf_capa.empty:
                continue

            gdf_capa["fclass"] = gdf_capa["fclass"].astype(str).str.lower()
            gdf_capa["cat"] = np.select(
                [
                    gdf_capa["fclass"].isin(CLASES_TURISMO),
                    gdf_capa["fclass"].isin(CLASES_COMERCIO),
                    gdf_capa["fclass"].isin(CLASES_TRANSPORTE),
                ],
                ["turismo", "comercio", "transporte"],
                default="",
            )
            gdf_capa = gdf_capa[gdf_capa["cat"] != ""][["cat", "geometry"]].copy()
            if gdf_capa.empty:
                continue

            gdf_capa = gdf_capa.to_crs(epsg=3857)
            gdf_capa["geometry"] = gdf_capa.geometry.centroid
            capas_validas.append(gdf_capa)
            log(f"    -> {shp}: {len(gdf_capa)} puntos relevantes.")
        except Exception as e:
            log(f"    -> Aviso leyendo {shp}: {e}")

    if os.path.exists(ruta_zip):
        os.remove(ruta_zip)

    if not capas_validas:
        return gpd.GeoDataFrame(columns=["cat", "geometry"], crs="EPSG:3857")

    gdf_todos = pd.concat(capas_validas, ignore_index=True)

    # Filtra únicamente los POIs que caen dentro de algún radio de 500m para guardar una caché liviana
    cruce_filtrado = gpd.sjoin(gdf_todos, gdf_buffers_3857[["geometry"]], how="inner", predicate="intersects")
    gdf_relevantes = gdf_todos.loc[cruce_filtrado.index.unique()].copy()

    gdf_4326 = gdf_relevantes.to_crs(epsg=4326)
    registros = [
        {"lat": round(geom.y, 6), "lon": round(geom.x, 6), "cat": cat}
        for geom, cat in zip(gdf_4326.geometry, gdf_4326["cat"])
    ]
    os.makedirs("datos_censales", exist_ok=True)
    with open(RUTA_CACHE_OSM, "w", encoding="utf-8") as f:
        json.dump(registros, f)

    log(f"    -> {len(gdf_relevantes)} polos guardados en caché para futuras actualizaciones.")
    return gdf_relevantes


def evaluar_entorno_y_circulacion(row):
    pob = row["poblacion_500m"]
    com = row["comercios_500m"]
    tur = row["turismo_500m"]
    tra = row["transporte_500m"]
    comp = row["competidores_500m"]

    flujo_score = com + (tur * 4) + (tra * 2)
    if flujo_score >= 120:
        circulacion = "Muy Alta"
    elif flujo_score >= 45:
        circulacion = "Alta"
    elif flujo_score >= 15:
        circulacion = "Media"
    else:
        circulacion = "Baja"

    pea_est = round(min(76.0, max(55.0, 56.0 + (tra * 0.4) + (com * 0.08))), 1)

    score_urbano = (pob / 1000.0) + (com * 0.15) + (tur * 0.6) + (comp * 1.2)
    if score_urbano >= 24:
        nse = "Alto"
    elif score_urbano >= 13:
        nse = "Medio-Alto"
    elif score_urbano >= 5:
        nse = "Medio"
    else:
        nse = "Emergente"

    # Combina residentes estables + masa crítica de circulación comercial y turística
    demanda_total = (pob / 100.0) + (flujo_score * 0.85)
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

    gdf_pois = obtener_circulacion_geofabrik(gdf_buffers)
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
    log(f"¡COMPLETADO! {len(res)} locales con datos censales y circulación real.")


if __name__ == "__main__":
    main()
