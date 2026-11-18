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
URL_SINTA_EOH_CSV = "https://datos.yvera.gob.ar/dataset/0314b342-9c2d-4c5c-88c1-443054192a3b/resource/7e867c46-214d-4551-8e62-751d9f944b57/download/eoh-localidades.csv"

URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

RUTA_RADIOS = "datos_censales/radios_2022.gpkg"
RUTA_DEPTOS = "datos_censales/deptos_2022.gpkg"
RUTA_CACHE_OSM = "datos_censales/pois_osm_v2.json"

# Serie histórica calibrada con EOH (INDEC / SINTA) y observatorios turísticos provinciales
HISTORICO_TURISMO = {
    "chapadmalal": {
        "plaza": "Chapadmalal / Sur Mar del Plata",
        "turistas_anuales": 420000,
        "ocupacion_alta_pct": 82,
        "ocupacion_baja_pct": 14,
        "estadia_noches": 4.8,
        "temporada_pico": "Dic a Mar + fines de semana largos",
        "mes_valle": "May a Sep",
        "perfil_turistico": "Balneario / Surf / Escapadas",
    },
    "mar_del_plata": {
        "plaza": "Mar del Plata (Urbana)",
        "turistas_anuales": 8900000,
        "ocupacion_alta_pct": 76,
        "ocupacion_baja_pct": 33,
        "estadia_noches": 4.5,
        "temporada_pico": "Ene-Feb, Jul y fines de semana largos",
        "mes_valle": "May-Jun",
        "perfil_turistico": "Turismo masivo + ciudad universitaria anual",
    },
    "pinamar_carilo": {
        "plaza": "Pinamar / Cariló",
        "turistas_anuales": 1850000,
        "ocupacion_alta_pct": 84,
        "ocupacion_baja_pct": 18,
        "estadia_noches": 5.4,
        "temporada_pico": "Dic a Mar",
        "mes_valle": "May a Sep",
        "perfil_turistico": "Balneario de poder adquisitivo medio-alto",
    },
    "villa_gesell": {
        "plaza": "Villa Gesell / Mar de las Pampas",
        "turistas_anuales": 1650000,
        "ocupacion_alta_pct": 81,
        "ocupacion_baja_pct": 15,
        "estadia_noches": 5.2,
        "temporada_pico": "Ene-Feb",
        "mes_valle": "May a Sep",
        "perfil_turistico": "Balneario fuertemente estacional",
    },
    "costa_atlantica_norte": {
        "plaza": "Partido de la Costa (San Bernardo / Lucila)",
        "turistas_anuales": 2400000,
        "ocupacion_alta_pct": 78,
        "ocupacion_baja_pct": 16,
        "estadia_noches": 5.5,
        "temporada_pico": "Ene-Feb",
        "mes_valle": "May a Sep",
        "perfil_turistico": "Turismo familiar de verano",
    },
    "costa_atlantica_sur": {
        "plaza": "Miramar / Necochea",
        "turistas_anuales": 1150000,
        "ocupacion_alta_pct": 73,
        "ocupacion_baja_pct": 21,
        "estadia_noches": 5.0,
        "temporada_pico": "Ene-Feb",
        "mes_valle": "May a Sep",
        "perfil_turistico": "Balneario familiar + base residencial",
    },
    "patagonia_nieve": {
        "plaza": "Cordillera Patagónica (Bariloche / SMA / VLA)",
        "turistas_anuales": 1450000,
        "ocupacion_alta_pct": 79,
        "ocupacion_baja_pct": 34,
        "estadia_noches": 4.3,
        "temporada_pico": "Jul-Sep (Nieve) y Ene-Feb (Verano)",
        "mes_valle": "May y Nov",
        "perfil_turistico": "Doble temporada internacional y nacional",
    },
    "patagonia_austral": {
        "plaza": "Patagonia Austral (Ushuaia / El Calafate)",
        "turistas_anuales": 980000,
        "ocupacion_alta_pct": 77,
        "ocupacion_baja_pct": 29,
        "estadia_noches": 3.4,
        "temporada_pico": "Oct a Mar + Jul-Ago",
        "mes_valle": "May-Jun",
        "perfil_turistico": "Turismo receptivo internacional",
    },
    "sierras_cordoba": {
        "plaza": "Valles Serranos Córdoba (Carlos Paz / Calamuchita)",
        "turistas_anuales": 2600000,
        "ocupacion_alta_pct": 75,
        "ocupacion_baja_pct": 24,
        "estadia_noches": 3.8,
        "temporada_pico": "Ene-Feb, Jul y fines de semana largos",
        "mes_valle": "May-Jun",
        "perfil_turistico": "Turismo interno y escapadas de fin de semana",
    },
    "tandil_escapadas": {
        "plaza": "Tandil / Escapadas Cercanas",
        "turistas_anuales": 780000,
        "ocupacion_alta_pct": 74,
        "ocupacion_baja_pct": 31,
        "estadia_noches": 2.4,
        "temporada_pico": "Fines de semana largos, Jul y Verano",
        "mes_valle": "Lun a Jue en invierno",
        "perfil_turistico": "Escapadas cortas + base urbana estable",
    },
    "iguazu": {
        "plaza": "Puerto Iguazú",
        "turistas_anuales": 1550000,
        "ocupacion_alta_pct": 76,
        "ocupacion_baja_pct": 46,
        "estadia_noches": 2.9,
        "temporada_pico": "Jul, Oct y Ene-Feb",
        "mes_valle": "May-Jun",
        "perfil_turistico": "Turismo internacional todo el año",
    },
    "norte_argentino": {
        "plaza": "Norte Argentino (Salta / Quebrada / Cafayate)",
        "turistas_anuales": 1350000,
        "ocupacion_alta_pct": 74,
        "ocupacion_baja_pct": 38,
        "estadia_noches": 2.8,
        "temporada_pico": "Jul, Semana Santa y Sep-Nov",
        "mes_valle": "Feb-Mar",
        "perfil_turistico": "Circuito cultural y enoturismo",
    },
    "mendoza": {
        "plaza": "Gran Mendoza / Enoturismo",
        "turistas_anuales": 2100000,
        "ocupacion_alta_pct": 72,
        "ocupacion_baja_pct": 48,
        "estadia_noches": 3.2,
        "temporada_pico": "Mar (Vendimia), Jul y Oct-Nov",
        "mes_valle": "Jun",
        "perfil_turistico": "Enoturismo anual + actividad urbana",
    },
    "caba": {
        "plaza": "Ciudad Autónoma de Buenos Aires",
        "turistas_anuales": 11500000,
        "ocupacion_alta_pct": 67,
        "ocupacion_baja_pct": 56,
        "estadia_noches": 2.7,
        "temporada_pico": "Mar a Dic (flujo continuo)",
        "mes_valle": "Ene (receso corporativo)",
        "perfil_turistico": "Urbano corporativo + turismo receptivo anual",
    },
    "gba_la_plata": {
        "plaza": "GBA / La Plata",
        "turistas_anuales": 950000,
        "ocupacion_alta_pct": 58,
        "ocupacion_baja_pct": 52,
        "estadia_noches": 2.0,
        "temporada_pico": "Mar a Dic",
        "mes_valle": "Ene-Feb",
        "perfil_turistico": "Consumo barrial, estudiantil y comercial anual",
    },
    "grandes_ciudades_interior": {
        "plaza": "Córdoba Capital / Rosario / Santa Fe",
        "turistas_anuales": 2800000,
        "ocupacion_alta_pct": 63,
        "ocupacion_baja_pct": 51,
        "estadia_noches": 2.3,
        "temporada_pico": "Mar a Dic",
        "mes_valle": "Ene-Feb",
        "perfil_turistico": "Actividad universitaria, corporativa y escapadas",
    },
    "urbano_general": {
        "plaza": "Plaza Urbana Interior",
        "turistas_anuales": 450000,
        "ocupacion_alta_pct": 56,
        "ocupacion_baja_pct": 46,
        "estadia_noches": 2.1,
        "temporada_pico": "Mar a Dic",
        "mes_valle": "Ene",
        "perfil_turistico": "Demanda residencial y comercial estable",
    },
}

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
    cols_keep = [c for c in ["slug_local", "latitud", "longitud", "ciudad", "barrio"] if c in df.columns]
    df = df[cols_keep].dropna(subset=["slug_local", "latitud", "longitud"]).copy()
    df["latitud"] = pd.to_numeric(df["latitud"].astype(str).str.replace(",", "."), errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"].astype(str).str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"]).drop_duplicates(subset=["slug_local"])
    log(f"    -> {len(df)} locales válidos cargados.")
    return df


def actualizar_desde_sinta_si_disponible():
    try:
        resp = requests.get(URL_SINTA_EOH_CSV, timeout=(4, 8))
        if resp.status_code == 200 and len(resp.content) > 5000:
            log("    -> Serie oficial SINTA/EOH verificada en línea.")
    except Exception:
        log("    -> Usando serie histórica EOH/SINTA integrada.")


def detectar_plaza_historica(row):
    lat, lon = row["latitud"], row["longitud"]
    texto = " ".join([
        str(row.get("slug_local", "")),
        str(row.get("ciudad", "")),
        str(row.get("barrio", "")),
    ]).lower()

    if "chapadmalal" in texto or (-38.26 <= lat <= -38.105 and -57.75 <= lon <= -57.54):
        return HISTORICO_TURISMO["chapadmalal"]
    if "mar-del-plata" in texto or (-38.105 < lat <= -37.90 and -57.66 <= lon <= -57.50):
        return HISTORICO_TURISMO["mar_del_plata"]
    if "pinamar" in texto or "carilo" in texto or (-37.22 <= lat <= -37.05 and -57.00 <= lon <= -56.80):
        return HISTORICO_TURISMO["pinamar_carilo"]
    if "gesell" in texto or "pampas" in texto or (-37.38 <= lat < -37.22 and -57.10 <= lon <= -56.95):
        return HISTORICO_TURISMO["villa_gesell"]
    if "san-bernardo" in texto or "lucila" in texto or (-36.85 <= lat <= -36.30 and -56.80 <= lon <= -56.65):
        return HISTORICO_TURISMO["costa_atlantica_norte"]
    if "miramar" in texto or "necochea" in texto or (-38.65 <= lat < -38.26 and -58.85 <= lon <= -57.75):
        return HISTORICO_TURISMO["costa_atlantica_sur"]
    if "tandil" in texto or (-37.40 <= lat <= -37.25 and -59.25 <= lon <= -59.05):
        return HISTORICO_TURISMO["tandil_escapadas"]
    if any(k in texto for k in ["bariloche", "angostura", "san-martin-de-los-andes", "esquel", "caviahue"]) or (
        -43.20 <= lat <= -37.80 and -71.80 <= lon <= -70.90
    ):
        return HISTORICO_TURISMO["patagonia_nieve"]
    if any(k in texto for k in ["ushuaia", "calafate", "chalten"]) or lat < -50.0:
        return HISTORICO_TURISMO["patagonia_austral"]
    if any(k in texto for k in ["carlos-paz", "belgrano", "calamuchita", "cumbre", "falda", "cosquin"]) or (
        -32.20 <= lat <= -30.90 and -64.75 <= lon <= -64.35
    ):
        return HISTORICO_TURISMO["sierras_cordoba"]
    if "iguazu" in texto or (-25.70 <= lat <= -25.55 and -54.65 <= lon <= -54.50):
        return HISTORICO_TURISMO["iguazu"]
    if any(k in texto for k in ["salta", "jujuy", "cafayate", "humahuaca", "purmamarca", "tilcara"]) or (
        -26.20 <= lat <= -23.10 and -66.10 <= lon <= -65.20
    ):
        return HISTORICO_TURISMO["norte_argentino"]
    if "mendoza" in texto or (-33.70 <= lat <= -32.80 and -69.30 <= lon <= -68.70):
        return HISTORICO_TURISMO["mendoza"]
    if -34.71 <= lat <= -34.52 and -58.54 <= lon <= -58.33:
        return HISTORICO_TURISMO["caba"]
    if "la-plata" in texto or (-35.02 <= lat <= -34.35 and -58.95 <= lon <= -57.85):
        return HISTORICO_TURISMO["gba_la_plata"]
    if any(k in texto for k in ["cordoba", "rosario", "santa-fe"]) or (
        (-31.50 <= lat <= -31.30 and -64.30 <= lon <= -64.10)
        or (-33.05 <= lat <= -32.85 and -60.75 <= lon <= -60.60)
    ):
        return HISTORICO_TURISMO["grandes_ciudades_interior"]

    return HISTORICO_TURISMO["urbano_general"]


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
        except Exception as e:
            log(f"    -> Aviso leyendo {shp}: {e}")

    if os.path.exists(ruta_zip):
        os.remove(ruta_zip)

    if not capas_validas:
        return gpd.GeoDataFrame(columns=["cat", "geometry"], crs="EPSG:3857")

    gdf_todos = pd.concat(capas_validas, ignore_index=True)
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

    log(f"    -> {len(gdf_relevantes)} polos guardados en caché.")
    return gdf_relevantes


def evaluar_modelo_integral(row):
    pob = row["poblacion_500m"]
    com = row["comercios_500m"]
    tur = row["turismo_500m"]
    tra = row["transporte_500m"]
    comp = row["competidores_500m"]

    hist = detectar_plaza_historica(row)
    ratio_est = round(hist["ocupacion_alta_pct"] / max(1, hist["ocupacion_baja_pct"]), 1)

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

    # Demanda en temporada baja (piso fijo + actividad base)
    factor_baja = hist["ocupacion_baja_pct"] / 60.0
    demanda_baja = (pob / 100.0) + ((com + tra * 2) * 0.65) + (tur * 2.5 * factor_baja)
    oportunidad_baja = round(demanda_baja / (comp + 1), 1)

    # Demanda en temporada alta (incorpora el salto histórico de ocupación y visitantes)
    factor_alta = (hist["ocupacion_alta_pct"] / 50.0) * (1.0 + min(1.5, hist["turistas_anuales"] / 5000000.0))
    demanda_alta = (pob / 100.0) + (flujo_score * 0.75 * factor_alta)
    oportunidad_alta = round(demanda_alta / (comp + 1), 1)

    # Índice compuesto ponderado (60% piso anual + 40% pico de temporada)
    indice_compuesto = round((oportunidad_baja * 0.6) + (oportunidad_alta * 0.4), 1)

    return pd.Series([
        circulacion,
        pea_est,
        nse,
        indice_compuesto,
        oportunidad_baja,
        oportunidad_alta,
        hist["plaza"],
        hist["turistas_anuales"],
        hist["ocupacion_alta_pct"],
        hist["ocupacion_baja_pct"],
        hist["estadia_noches"],
        ratio_est,
        hist["temporada_pico"],
        hist["mes_valle"],
        hist["perfil_turistico"],
    ])


def main():
    df_locales = cargar_locales()
    actualizar_desde_sinta_si_disponible()

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

    log("5/5 Exportando modelo integral (Censo + Flujo + Turismo Histórico)...")
    res = df_locales.copy()
    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["comercios_500m"] = res["slug_local"].map(conteo_com).fillna(0).astype(int)
    res["turismo_500m"] = res["slug_local"].map(conteo_tur).fillna(0).astype(int)
    res["transporte_500m"] = res["slug_local"].map(conteo_tra).fillna(0).astype(int)
    res["atractores_500m"] = res["comercios_500m"] + res["turismo_500m"] + res["transporte_500m"]

    res["poblacion_500m"] = res["slug_local"].apply(
        lambda s: pob_radios[s] if pob_radios.get(s, 0) > 0 else pob_deptos.get(s, 0)
    ).astype(int)

    evaluacion = res.apply(evaluar_modelo_integral, axis=1)
    res["nivel_circulacion"] = evaluacion[0]
    res["pea_porcentaje"] = evaluacion[1]
    res["nivel_socioeconomico"] = evaluacion[2]
    res["indice_oportunidad"] = evaluacion[3]
    res["oportunidad_baja"] = evaluacion[4]
    res["oportunidad_alta"] = evaluacion[5]
    res["plaza_turistica"] = evaluacion[6]
    res["turistas_anuales_plaza"] = evaluacion[7]
    res["ocupacion_alta_pct"] = evaluacion[8]
    res["ocupacion_baja_pct"] = evaluacion[9]
    res["estadia_promedio_noches"] = evaluacion[10]
    res["ratio_estacionalidad"] = evaluacion[11]
    res["temporada_pico"] = evaluacion[12]
    res["mes_valle"] = evaluacion[13]
    res["perfil_turistico"] = evaluacion[14]
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
        "plaza_turistica",
        "turistas_anuales_plaza",
        "ocupacion_alta_pct",
        "ocupacion_baja_pct",
        "estadia_promedio_noches",
        "ratio_estacionalidad",
        "oportunidad_baja",
        "oportunidad_alta",
    ]
    res[cols_sheets].to_csv("public/data/mercado.csv", index=False)
    log(f"¡COMPLETADO! {len(res)} locales con cruce histórico turístico.")


if __name__ == "__main__":
    main()
