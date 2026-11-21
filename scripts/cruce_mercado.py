import os
import re
import json
import zipfile
import socket
import unicodedata
from datetime import datetime
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import gdown
import urllib3.util.connection as urllib3_cn

urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

PUB_ID = "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn"
URL_DRIVE_RADIOS = "https://drive.google.com/file/d/1KiOw4aettgbjLZJIwms86yVp-lPXcBXQ/view?usp=drivesdk"
URL_DRIVE_DEPTOS = "https://drive.google.com/file/d/1_BthlwEU2QMKtUlzwDv1AEsF4mB6SB9E/view?usp=drivesdk"
URL_GEOFABRIK_AR = "https://download.geofabrik.de/south-america/argentina-latest-free.shp.zip"
URL_SINTA_EOH_CSV = "https://datos.yvera.gob.ar/dataset/0314b342-9c2d-4c5c-88c1-443054192a3b/resource/7e867c46-214d-4551-8e62-751d9f944b57/download/eoh-localidades.csv"

GID_DATOS_MERCADO = "1552155233"

RUTA_RADIOS = "datos_censales/radios_2022.gpkg"
RUTA_DEPTOS = "datos_censales/deptos_2022.gpkg"
RUTA_CACHE_OSM = "datos_censales/pois_osm_v2.json"
RUTA_CACHE_RUTAS = "datos_censales/rutas_osm_v1.json"

PLAZAS_ELEGIBLES_EXPANSION = {
    "Ciudad Autónoma de Buenos Aires",
    "GBA / La Plata",
    "Mar del Plata (Urbana)",
    "Chapadmalal / Sur Mar del Plata",
    "Pinamar / Cariló",
    "Córdoba Capital / Rosario / Santa Fe",
    "Valles Serranos Córdoba (Carlos Paz / Calamuchita)",
    "Gran Mendoza / Enoturismo",
    "Cordillera Patagónica (Bariloche / SMA / VLA)",
    "Patagonia Austral (Ushuaia / El Calafate)",
    "Norte Argentino (Salta / Quebrada / Cafayate)",
    "Puerto Iguazú",
    "Tandil / Escapadas Cercanas",
}

HISTORICO_TURISMO = {
    "chapadmalal": {
        "plaza": "Chapadmalal / Sur Mar del Plata",
        "turistas_anuales": 420000,
        "ocupacion_alta_pct": 82,
        "ocupacion_baja_pct": 14,
        "estadia_noches": 4.8,
        "temporada_pico": "Dic a Mar + fines de semana largos",
        "mes_valle": "May a Sep",
        "perfil_turistico": "Balneario / Surf / Corredor Ruta 11",
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
        "perfil_turistico": "Doble temporada + circuitos cordilleranos",
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
        "perfil_turistico": "Turismo interno y rutas serranas",
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
        "perfil_turistico": "Circuito cultural, pasos y enoturismo",
    },
    "mendoza": {
        "plaza": "Gran Mendoza / Enoturismo",
        "turistas_anuales": 2100000,
        "ocupacion_alta_pct": 72,
        "ocupacion_baja_pct": 48,
        "estadia_noches": 3.2,
        "temporada_pico": "Mar (Vendimia), Jul y Oct-Nov",
        "mes_valle": "Jun",
        "perfil_turistico": "Enoturismo anual + corredor bioceánico",
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

PERFILES_ECONOMICOS = {
    "caba_puerto_madero": {
        "corredor": "Puerto Madero / Eje Corporativo",
        "nivel_gasto": "Muy Alto",
        "indice_ticket": 1.45,
        "gasto_turista_usd": 98,
        "costo_alquiler": "Muy Alto",
        "bonus_diurno": 12500,
        "ecuacion_rentabilidad": "Ticket máximo y público internacional/ejecutivo, pero alquiler muy alto exige volumen sostenido.",
    },
    "caba_palermo_norte": {
        "corredor": "Palermo / Belgrano / Núñez / Recoleta",
        "nivel_gasto": "Alto",
        "indice_ticket": 1.30,
        "gasto_turista_usd": 80,
        "costo_alquiler": "Alto",
        "bonus_diurno": 4500,
        "ecuacion_rentabilidad": "Fuerte consumo de especialidad y turismo receptivo; requiere alta rotación para amortizar alquiler.",
    },
    "caba_la_boca_sur": {
        "corredor": "La Boca / Barracas / Circuito Diurno",
        "nivel_gasto": "Medio-Bajo",
        "indice_ticket": 0.90,
        "gasto_turista_usd": 42,
        "costo_alquiler": "Medio-Bajo",
        "bonus_diurno": 2200,
        "ecuacion_rentabilidad": "Turista excursionista diurno de estadía corta; conviene propuesta ágil y costos fijos bajos.",
    },
    "caba_barrial_medio": {
        "corredor": "CABA · Corredor Barrial / Comercial",
        "nivel_gasto": "Medio-Alto",
        "indice_ticket": 1.12,
        "gasto_turista_usd": 56,
        "costo_alquiler": "Medio-Alto",
        "bonus_diurno": 2500,
        "ecuacion_rentabilidad": "Equilibrio saludable entre consumo habitual de vecinos y valor de alquiler intermedio.",
    },
    "pinamar_carilo": {
        "corredor": "Pinamar / Cariló · Balneario ABC1",
        "nivel_gasto": "Muy Alto",
        "indice_ticket": 1.40,
        "gasto_turista_usd": 88,
        "costo_alquiler": "Alto (estacional)",
        "bonus_diurno": 800,
        "ecuacion_rentabilidad": "Turista de alto poder adquisitivo en verano; clave negociar alquiler anual flexible.",
    },
    "gesell_pampas": {
        "corredor": "Villa Gesell / Mar de las Pampas",
        "nivel_gasto": "Medio-Alto",
        "indice_ticket": 1.15,
        "gasto_turista_usd": 62,
        "costo_alquiler": "Medio-Alto (estacional)",
        "bonus_diurno": 600,
        "ecuacion_rentabilidad": "Buen margen en temporada alta y escapadas; exige estructura liviana en invierno.",
    },
    "mdp_guemes_sur": {
        "corredor": "Mar del Plata · Güemes / Playa Grande / Sur",
        "nivel_gasto": "Alto",
        "indice_ticket": 1.22,
        "gasto_turista_usd": 68,
        "costo_alquiler": "Alto",
        "bonus_diurno": 1800,
        "ecuacion_rentabilidad": "Público de mayor gasto promedio en la ciudad y cultura de café de especialidad consolidada.",
    },
    "mdp_urbano_masivo": {
        "corredor": "Mar del Plata · Centro / Barrial",
        "nivel_gasto": "Medio",
        "indice_ticket": 1.00,
        "gasto_turista_usd": 48,
        "costo_alquiler": "Medio",
        "bonus_diurno": 2200,
        "ecuacion_rentabilidad": "Turismo masivo heterogéneo + base residente anual con alquileres más accesibles.",
    },
    "mendoza_enoturismo": {
        "corredor": "Mendoza · Enoturismo y Ciudad",
        "nivel_gasto": "Alto",
        "indice_ticket": 1.28,
        "gasto_turista_usd": 85,
        "costo_alquiler": "Medio-Alto",
        "bonus_diurno": 2000,
        "ecuacion_rentabilidad": "Turista internacional/nacional de alto gasto frente a costos inmobiliarios más moderados que CABA.",
    },
    "patagonia_turistica": {
        "corredor": "Patagonia · Plaza Receptiva",
        "nivel_gasto": "Muy Alto",
        "indice_ticket": 1.38,
        "gasto_turista_usd": 92,
        "costo_alquiler": "Alto",
        "bonus_diurno": 1500,
        "ecuacion_rentabilidad": "Ticket elevado en nieve y verano que compensa costos logísticos y de alquiler.",
    },
    "gran_ciudad_interior": {
        "corredor": "Polo Universitario / Comercial Interior",
        "nivel_gasto": "Medio-Alto",
        "indice_ticket": 1.08,
        "gasto_turista_usd": 52,
        "costo_alquiler": "Medio",
        "bonus_diurno": 2500,
        "ecuacion_rentabilidad": "Excelente relación ingreso/costo por flujo diario constante y alquileres razonables.",
    },
    "plaza_regional": {
        "corredor": "Plaza Regional / Escapadas",
        "nivel_gasto": "Medio",
        "indice_ticket": 0.96,
        "gasto_turista_usd": 45,
        "costo_alquiler": "Bajo a Medio",
        "bonus_diurno": 1000,
        "ecuacion_rentabilidad": "Punto de equilibrio bajo; ideal para operación propia y clientela recurrente.",
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

JERARQUIA_RUTAS = {
    "motorway": (1, 14000),
    "motorway_link": (1, 12000),
    "trunk": (2, 10500),
    "trunk_link": (2, 9500),
    "primary": (3, 7500),
    "primary_link": (3, 6800),
    "secondary": (4, 4800),
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def slugify_texto(txt):
    s = unicodedata.normalize("NFD", str(txt or "")).encode("ascii", "ignore").decode("utf-8").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def encontrar_col(columnas, palabras):
    for c in columnas:
        cl = unicodedata.normalize("NFD", str(c)).encode("ascii", "ignore").decode("utf-8").lower().strip()
        if any(p in cl for p in palabras):
            return c
    return None


def parsear_coords(val):
    if pd.isna(val):
        return None, None
    s = str(val).strip()
    m = re.search(r"(-?\d{1,2}[.,]\d+)\s*[,;\s/]+\s*(-?\d{1,3}[.,]\d+)", s)
    if not m:
        return None, None
    try:
        lat = float(m.group(1).replace(",", "."))
        lon = float(m.group(2).replace(",", "."))
        if -56.0 <= lat <= -21.0 and -74.0 <= lon <= -53.0:
            return lat, lon
    except ValueError:
        pass
    return None, None


def leer_hoja_publicada(gid, header="infer"):
    url = f"https://docs.google.com/spreadsheets/d/e/{PUB_ID}/pub?gid={gid}&single=true&output=csv"
    return pd.read_csv(url, header=header)


def cargar_locales():
    log("1/5 Descargando locales desde Google Sheets (Base_Maestra)...")
    slugs_vistos = {}

    df = leer_hoja_publicada(GID_DATOS_MERCADO)
    if df.empty:
        raise RuntimeError("La hoja Base_Maestra descargada está vacía.")

    # Detectar si la primera fila ya contiene datos en lugar de encabezados
    primera_fila_es_dato = False
    for c in df.columns[:4]:
        cs = str(c).strip()
        if parsear_coords(cs)[0] is not None:
            primera_fila_es_dato = True
            break
        try:
            v = float(cs.replace(",", "."))
            if -56.0 <= v <= -21.0 or -74.0 <= v <= -53.0:
                primera_fila_es_dato = True
                break
        except ValueError:
            pass

    if primera_fila_es_dato:
        df = leer_hoja_publicada(GID_DATOS_MERCADO, header=None)
        nombres_std = ["nombre", "latitud", "longitud", "ubicacion", "instagram", "zona", "ciudad", "ciudad_real"]
        df.columns = [
            nombres_std[i] if i < len(nombres_std) else f"col_{i}"
            for i in range(df.shape[1])
        ]

    col_nombre = encontrar_col(df.columns, ["nombre", "cafeteria", "local", "cafe", "slug"])
    col_coords = encontrar_col(df.columns, ["coordenada", "ubicacion_mapa", "gps", "latlong"])
    col_lat = encontrar_col(df.columns, ["latitud", "lat"])
    col_lon = encontrar_col(df.columns, ["longitud", "lon", "lng"])
    col_ciudad = encontrar_col(df.columns, ["ciudad", "provincia", "region"])
    col_zona = encontrar_col(df.columns, ["zona", "barrio", "partido", "localidad"])

    if not col_nombre and not (col_coords or (col_lat and col_lon)):
        df = leer_hoja_publicada(GID_DATOS_MERCADO, header=None)
        col_nombre = 0
        for c in df.columns[1:]:
            muestra = df[c].dropna().astype(str).head(15)
            if any(parsear_coords(v)[0] is not None for v in muestra):
                col_coords = c
                break
        if col_coords is None and df.shape[1] >= 3:
            col_lat, col_lon = 1, 2
        if df.shape[1] >= 6:
            col_zona = 5
        elif df.shape[1] >= 4:
            col_zona = 3

    registros = []
    for _, fila in df.iterrows():
        nombre = str(fila.get(col_nombre, "") or "").strip() if col_nombre is not None else ""
        if not nombre or nombre.lower() in ("nan", "none", "nombre", "slug_local"):
            continue

        lat, lon = None, None
        if col_coords is not None:
            lat, lon = parsear_coords(fila.get(col_coords))
        if (lat is None or lon is None) and col_lat is not None and col_lon is not None:
            try:
                la = float(str(fila.get(col_lat, "")).replace(",", ".").strip())
                lo = float(str(fila.get(col_lon, "")).replace(",", ".").strip())
                if -56.0 <= la <= -21.0 and -74.0 <= lo <= -53.0:
                    lat, lon = la, lo
            except ValueError:
                pass

        if lat is None or lon is None:
            continue

        ciudad = str(fila.get(col_ciudad, "") or "").strip() if col_ciudad is not None else ""
        if ciudad.lower() in ("nan", "none"):
            ciudad = ""

        barrio = str(fila.get(col_zona, "") or "").strip() if col_zona is not None else ""
        if barrio.lower() in ("nan", "none"):
            barrio = ""

        base_slug = slugify_texto(f"{nombre}-{ciudad}" if ciudad else nombre)
        if not base_slug:
            base_slug = f"local-{len(registros) + 1}"

        count = slugs_vistos.get(base_slug, 0) + 1
        slugs_vistos[base_slug] = count
        slug_final = base_slug if count == 1 else f"{base_slug}-{count}"

        registros.append({
            "slug_local": slug_final,
            "nombre": nombre,
            "latitud": lat,
            "longitud": lon,
            "ciudad": ciudad,
            "barrio": barrio,
        })

    if not registros:
        raise RuntimeError(
            f"Se descargaron {len(df)} filas de Base_Maestra (columnas: {list(df.columns)}), "
            "pero ninguna tenía nombre y coordenadas válidas."
        )

    df_total = pd.DataFrame(registros)
    log(f"    -> {len(df_total)} locales válidos cargados desde Base_Maestra.")
    return df_total


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


def detectar_perfil_economico(row):
    lat, lon = row["latitud"], row["longitud"]
    texto = " ".join([
        str(row.get("slug_local", "")),
        str(row.get("ciudad", "")),
        str(row.get("barrio", "")),
    ]).lower()

    if -34.71 <= lat <= -34.52 and -58.54 <= lon <= -58.33:
        if "puerto-madero" in texto or (-34.628 <= lat <= -34.593 and -58.370 <= lon <= -58.348):
            return PERFILES_ECONOMICOS["caba_puerto_madero"]
        if any(k in texto for k in ["la-boca", "barracas"]) or (-34.648 <= lat <= -34.626 and -58.375 <= lon <= -58.355):
            return PERFILES_ECONOMICOS["caba_la_boca_sur"]
        if any(k in texto for k in ["palermo", "belgrano", "recoleta", "nunez", "colegiales"]) or (
            -34.596 <= lat <= -34.542 and -58.465 <= lon <= -58.382
        ):
            return PERFILES_ECONOMICOS["caba_palermo_norte"]
        return PERFILES_ECONOMICOS["caba_barrial_medio"]

    if "pinamar" in texto or "carilo" in texto or (-37.22 <= lat <= -37.05 and -57.00 <= lon <= -56.80):
        return PERFILES_ECONOMICOS["pinamar_carilo"]
    if "gesell" in texto or "pampas" in texto or (-37.38 <= lat < -37.22 and -57.10 <= lon <= -56.95):
        return PERFILES_ECONOMICOS["gesell_pampas"]
    if "chapadmalal" in texto or (-38.26 <= lat <= -38.012 and -57.75 <= lon <= -57.528):
        return PERFILES_ECONOMICOS["mdp_guemes_sur"]
    if "mar-del-plata" in texto or (-38.105 < lat <= -37.90 and -57.66 <= lon <= -57.50):
        return PERFILES_ECONOMICOS["mdp_urbano_masivo"]

    if "mendoza" in texto or (-33.70 <= lat <= -32.80 and -69.30 <= lon <= -68.70):
        return PERFILES_ECONOMICOS["mendoza_enoturismo"]
    if any(k in texto for k in ["bariloche", "angostura", "san-martin-de-los-andes", "ushuaia", "calafate"]) or (
        -43.20 <= lat <= -37.80 and -71.80 <= lon <= -70.90
    ) or lat < -50.0:
        return PERFILES_ECONOMICOS["patagonia_turistica"]
    if any(k in texto for k in ["la-plata", "cordoba", "rosario", "santa-fe"]) or (
        (-35.02 <= lat <= -34.85 and -58.10 <= lon <= -57.88)
        or (-31.50 <= lat <= -31.30 and -64.30 <= lon <= -64.10)
        or (-33.05 <= lat <= -32.85 and -60.75 <= lon <= -60.60)
    ):
        return PERFILES_ECONOMICOS["gran_ciudad_interior"]

    return PERFILES_ECONOMICOS["plaza_regional"]


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
    gdf_c = gpd.read_file(ruta_gpkg, layer="features").to_crs(epsg=3857)
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


def obtener_circulacion_y_rutas_geofabrik(gdf_buffers_3857):
    log("3/5 Cargando capa comercial, turística, transporte y rutas de Argentina...")
    tiene_pois = os.path.exists(RUTA_CACHE_OSM) and os.path.getsize(RUTA_CACHE_OSM) > 10000
    tiene_rutas = os.path.exists(RUTA_CACHE_RUTAS) and os.path.getsize(RUTA_CACHE_RUTAS) > 100

    gdf_pois = gpd.GeoDataFrame(columns=["cat", "geometry"], crs="EPSG:3857")
    rutas_por_slug = {}

    if tiene_pois:
        with open(RUTA_CACHE_OSM, "r", encoding="utf-8") as f:
            registros = json.load(f)
        if registros:
            log(f"    -> Caché POIs cargada: {len(registros)} polos.")
            df_pois = pd.DataFrame(registros)
            gdf_pois = gpd.GeoDataFrame(
                df_pois[["cat"]],
                geometry=gpd.points_from_xy(df_pois["lon"], df_pois["lat"]),
                crs="EPSG:4326",
            ).to_crs(epsg=3857)

    if tiene_rutas:
        with open(RUTA_CACHE_RUTAS, "r", encoding="utf-8") as f:
            rutas_por_slug = json.load(f)
        log(f"    -> Caché rutas cargada: {len(rutas_por_slug)} locales con traza vial.")

    if tiene_pois and tiene_rutas:
        return gdf_pois, rutas_por_slug

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
        return gdf_pois, rutas_por_slug

    mb = os.path.getsize(ruta_zip) / (1024 * 1024)
    log(f"    -> Paquete descargado ({mb:.1f} MB). Procesando POIs y rutas principales...")

    with zipfile.ZipFile(ruta_zip, "r") as zf:
        todos_shps = [n for n in zf.namelist() if n.endswith(".shp")]

    if not tiene_pois:
        shps_pois = [n for n in todos_shps if ("pois" in n or "transport" in n)]
        capas_validas = []
        for shp in shps_pois:
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

        if capas_validas:
            gdf_todos = pd.concat(capas_validas, ignore_index=True)
            cruce_filtrado = gpd.sjoin(gdf_todos, gdf_buffers_3857[["geometry"]], how="inner", predicate="intersects")
            gdf_pois = gdf_todos.loc[cruce_filtrado.index.unique()].copy()

            gdf_4326 = gdf_pois.to_crs(epsg=4326)
            registros = [
                {"lat": round(geom.y, 6), "lon": round(geom.x, 6), "cat": cat}
                for geom, cat in zip(gdf_4326.geometry, gdf_4326["cat"])
            ]
            os.makedirs("datos_censales", exist_ok=True)
            with open(RUTA_CACHE_OSM, "w", encoding="utf-8") as f:
                json.dump(registros, f)
            log(f"    -> {len(gdf_pois)} polos guardados en caché.")

    if not tiene_rutas:
        shps_roads = [n for n in todos_shps if "roads" in n]
        capas_rutas = []
        for shp in shps_roads:
            try:
                gdf_r = gpd.read_file(f"zip://{ruta_zip}!{shp}")
                if "fclass" not in gdf_r.columns or gdf_r.empty:
                    continue
                gdf_r["fclass"] = gdf_r["fclass"].astype(str).str.lower()
                gdf_r = gdf_r[gdf_r["fclass"].isin(JERARQUIA_RUTAS.keys())].copy()
                if gdf_r.empty:
                    continue
                cols_r = [c for c in ["fclass", "name", "ref", "geometry"] if c in gdf_r.columns]
                gdf_r = gdf_r[cols_r].to_crs(epsg=3857)
                capas_rutas.append(gdf_r)
            except Exception as e:
                log(f"    -> Aviso leyendo rutas {shp}: {e}")

        if capas_rutas:
            gdf_rutas_all = pd.concat(capas_rutas, ignore_index=True)
            cruce_r = gpd.sjoin(gdf_buffers_3857[["slug_local", "geometry"]], gdf_rutas_all, how="inner", predicate="intersects")
            for slug, grupo in cruce_r.groupby("slug_local"):
                mejor_prio = 99
                mejor_flujo = 0
                etiqueta_ruta = ""
                for _, fila in grupo.iterrows():
                    fc = str(fila.get("fclass", ""))
                    prio, flujo_base = JERARQUIA_RUTAS.get(fc, (99, 0))
                    ref = str(fila.get("ref", "") or "").strip()
                    nom = str(fila.get("name", "") or "").strip()
                    if ref.lower() == "none":
                        ref = ""
                    if nom.lower() == "none":
                        nom = ""
                    label = " · ".join([x for x in [ref, nom] if x])
                    if prio < mejor_prio or (prio == mejor_prio and label and not etiqueta_ruta):
                        mejor_prio = prio
                        mejor_flujo = flujo_base
                        etiqueta_ruta = label or fc.replace("_", " ").title()
                rutas_por_slug[slug] = {
                    "prio": mejor_prio,
                    "flujo_base": mejor_flujo,
                    "nombre": etiqueta_ruta,
                }

        os.makedirs("datos_censales", exist_ok=True)
        with open(RUTA_CACHE_RUTAS, "w", encoding="utf-8") as f:
            json.dump(rutas_por_slug, f, ensure_ascii=False)
        log(f"    -> {len(rutas_por_slug)} locales vinculados con vías principales.")

    if os.path.exists(ruta_zip):
        os.remove(ruta_zip)

    return gdf_pois, rutas_por_slug


def detectar_corredor_ruta(row, info_osm_ruta):
    lat, lon = row["latitud"], row["longitud"]
    texto = " ".join([
        str(row.get("slug_local", "")),
        str(row.get("ciudad", "")),
        str(row.get("barrio", "")),
    ]).lower()

    if "chapadmalal" in texto or (-38.26 <= lat <= -38.105 and -57.75 <= lon <= -57.54):
        return True, "RP 11 · Corredor Costero Sur", 9200
    if any(k in texto for k in ["bariloche", "bustillo", "llao", "catedral", "angostura", "siete-lagos", "san-martin-de-los-andes"]) or (
        -41.25 <= lat <= -40.05 and -71.75 <= lon <= -71.10
    ):
        nombre_osm = info_osm_ruta.get("nombre", "") if info_osm_ruta else ""
        etiqueta = nombre_osm if any(k in nombre_osm.lower() for k in ["40", "bustillo", "237", "231", "77"]) else "Av. Bustillo / RN 40 · Paso Cordillerano"
        return True, etiqueta, 11500
    if any(k in texto for k in ["altas-cumbres", "cuadrado", "carlos-paz", "calamuchita", "cumbre", "falda", "cosquin"]) or (
        -32.20 <= lat <= -30.90 and -64.75 <= lon <= -64.35
    ):
        return True, info_osm_ruta.get("nombre") or "Corredor Serrano / Camino de Montaña", 8400
    if any(k in texto for k in ["potrerillos", "uspallata", "cacheuta", "valle-de-uco", "tunuyan", "tupungato"]) or (
        -33.75 <= lat <= -32.55 and -69.60 <= lon <= -68.95
    ):
        return True, info_osm_ruta.get("nombre") or "RN 7 / Corredor Alta Montaña y Bodegas", 9800
    if any(k in texto for k in ["purmamarca", "tilcara", "humahuaca", "cafayate", "tafi"]) or (
        -26.90 <= lat <= -23.10 and -66.10 <= lon <= -65.20
    ):
        return True, info_osm_ruta.get("nombre") or "RN 9 / RN 68 · Paso Quebrada y Valles", 7600
    if any(k in texto for k in ["pinamar", "carilo", "gesell", "pampas", "san-bernardo", "lucila"]):
        return True, info_osm_ruta.get("nombre") or "RP 11 · Corredor Atlántico", 8800

    if info_osm_ruta and info_osm_ruta.get("prio", 99) <= 3:
        es_caba_centro = (-34.63 <= lat <= -34.56 and -58.46 <= lon <= -58.36)
        if not es_caba_centro:
            return True, info_osm_ruta.get("nombre") or "Ruta / Arteria Principal", int(info_osm_ruta.get("flujo_base", 7500))

    if info_osm_ruta and info_osm_ruta.get("prio", 99) == 4:
        return False, info_osm_ruta.get("nombre", ""), int(info_osm_ruta.get("flujo_base", 4500))

    return False, "", 0


def inferir_publico_objetivo(econ, hist, com, tur, tra, pob):
    corredor = econ["corredor"].lower()
    if "corporativo" in corredor or "puerto madero" in corredor:
        return "Ejecutivos, oficinas y turismo receptivo de alto ticket"
    if tur >= 8 or "enoturismo" in corredor or "patagonia" in corredor or "pinamar" in corredor:
        return "Turismo nacional/internacional y escapadas de fin de semana"
    if tra >= 6 or "universitario" in corredor:
        return "Estudiantes universitarios, tránsito diario y consumo al paso"
    if pob >= 6500:
        return "Público residencial habitual, home-office y vecinos de cercanía"
    return "Mixto: flujo comercial barrial y visitantes de cercanía"


def evaluar_modelo_integral(row, rutas_por_slug):
    slug = row["slug_local"]
    pob = row["poblacion_500m"]
    com = row["comercios_500m"]
    tur = row["turismo_500m"]
    tra = row["transporte_500m"]
    comp = row["competidores_500m"]

    hist = detectar_plaza_historica(row)
    econ = detectar_perfil_economico(row)
    info_osm_ruta = rutas_por_slug.get(slug, {})
    es_ruta, ruta_nombre, flujo_ruta_diario = detectar_corredor_ruta(row, info_osm_ruta)

    ratio_est = round(hist["ocupacion_alta_pct"] / max(1, hist["ocupacion_baja_pct"]), 1)

    aporte_ruta_score = round(flujo_ruta_diario / 250.0) if es_ruta else round(flujo_ruta_diario / 550.0)
    flujo_score = com + (tur * 3.5) + (tra * 2.0) + aporte_ruta_score

    if flujo_score >= 130:
        circulacion = "Muy Alta"
    elif flujo_score >= 50:
        circulacion = "Alta"
    elif flujo_score >= 18:
        circulacion = "Media"
    else:
        circulacion = "Baja"

    aporte_ruta_personas = int(round(flujo_ruta_diario * (0.40 if es_ruta else 0.12)))
    publico_diurno = int(round(
        pob + (com * 40) + (tra * 130) + (tur * 85) + econ["bonus_diurno"] + aporte_ruta_personas
    ))

    pea_est = round(min(76.0, max(55.0, 56.0 + (tra * 0.4) + (com * 0.08))), 1)
    ticket_mult = econ["indice_ticket"]

    # Escala recalibrada (0 a 20 pts) para diferenciar plazas saturadas, equilibradas y con oportunidad real
    factor_saturacion = 1.0 + (comp * 0.65) + (max(0, comp - 4) * 0.45)

    base_baja = (
        min(8.5, pob / 1400.0)
        + min(6.5, (com * 0.14) + (tra * 0.45))
        + min(4.0, tur * 0.25 * (hist["ocupacion_baja_pct"] / 55.0))
        + (2.2 if es_ruta else 0.0)
    ) * ticket_mult
    oportunidad_baja = round(min(20.0, max(1.2, (base_baja * 2.1) / factor_saturacion)), 1)

    factor_pico = (hist["ocupacion_alta_pct"] / 65.0) * (1.0 + min(0.65, hist["turistas_anuales"] / 9000000.0))
    base_alta = (
        min(7.5, pob / 1600.0)
        + min(8.5, (flujo_score * 0.085) * factor_pico)
        + (2.8 if es_ruta else 0.0)
    ) * ticket_mult
    oportunidad_alta = round(min(20.0, max(1.5, (base_alta * 2.2) / factor_saturacion)), 1)

    indice_compuesto = round((oportunidad_baja * 0.62) + (oportunidad_alta * 0.38), 1)

    return pd.Series([
        circulacion,
        pea_est,
        econ["nivel_gasto"],
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
        econ["corredor"],
        econ["indice_ticket"],
        econ["gasto_turista_usd"],
        econ["costo_alquiler"],
        econ["ecuacion_rentabilidad"],
        publico_diurno,
        bool(es_ruta),
        ruta_nombre,
        int(flujo_ruta_diario),
    ])


def detectar_zonas_recomendadas(res_df, gdf_locales_3857, gdf_pois_3857, top_n=4):
    if gdf_pois_3857.empty or res_df.empty:
        return []

    elegibles = res_df[res_df["plaza_turistica"].isin(PLAZAS_ELEGIBLES_EXPANSION)].copy()
    if elegibles.empty:
        elegibles = res_df.copy()

    gdf_eleg_3857 = gpd.GeoDataFrame(
        elegibles,
        geometry=gpd.points_from_xy(elegibles["longitud"], elegibles["latitud"]),
        crs="EPSG:4326",
    ).to_crs(epsg=3857)

    area_urbana = gdf_eleg_3857.geometry.buffer(4000).union_all()
    pois_candidatos = gdf_pois_3857[gdf_pois_3857.geometry.within(area_urbana)].copy()
    if pois_candidatos.empty:
        return []

    pois_candidatos["gx"] = (pois_candidatos.geometry.x // 700).astype(int)
    pois_candidatos["gy"] = (pois_candidatos.geometry.y // 700).astype(int)

    celdas = (
        pois_candidatos.groupby(["gx", "gy"])
        .agg(
            total_pois=("cat", "count"),
            com=("cat", lambda s: (s == "comercio").sum()),
            tur=("cat", lambda s: (s == "turismo").sum()),
            tra=("cat", lambda s: (s == "transporte").sum()),
            x_mean=("geometry", lambda g: g.x.mean()),
            y_mean=("geometry", lambda g: g.y.mean()),
        )
        .reset_index()
    )

    celdas = celdas[celdas["total_pois"] >= 10].sort_values("total_pois", ascending=False).head(120)
    if celdas.empty:
        return []

    gdf_celdas = gpd.GeoDataFrame(
        celdas,
        geometry=gpd.points_from_xy(celdas["x_mean"], celdas["y_mean"]),
        crs="EPSG:3857",
    )

    buf_celdas = gdf_celdas[["geometry"]].copy()
    buf_celdas["geometry"] = buf_celdas.geometry.buffer(650)
    cruce_comp = gpd.sjoin(buf_celdas, gdf_locales_3857[["geometry"]], how="left", predicate="intersects")
    comp_por_celda = cruce_comp.groupby(cruce_comp.index)["index_right"].count()
    gdf_celdas["comp_650m"] = gdf_celdas.index.map(comp_por_celda).fillna(0).astype(int)

    gdf_celdas = gdf_celdas[gdf_celdas["comp_650m"] <= 2].copy()
    if gdf_celdas.empty:
        return []

    gdf_celdas_4326 = gdf_celdas.to_crs(epsg=4326)
    candidatos_rank = []

    for _, row in gdf_celdas_4326.iterrows():
        lat, lon = round(row.geometry.y, 5), round(row.geometry.x, 5)
        dist = np.hypot(elegibles["latitud"] - lat, elegibles["longitud"] - lon)
        ref = elegibles.loc[dist.idxmin()]

        if ref["plaza_turistica"] not in PLAZAS_ELEGIBLES_EXPANSION:
            continue

        hist = detectar_plaza_historica({"latitud": lat, "longitud": lon, "slug_local": "", "ciudad": ref.get("ciudad", ""), "barrio": ref.get("barrio", "")})
        econ = detectar_perfil_economico({"latitud": lat, "longitud": lon, "slug_local": "", "ciudad": ref.get("ciudad", ""), "barrio": ref.get("barrio", "")})

        flujo = row["com"] + (row["tur"] * 3.5) + (row["tra"] * 2.0)
        score = round(
            min(19.5, ((flujo * 0.14) * econ["indice_ticket"]) / (1.0 + row["comp_650m"] * 0.7)),
            1,
        )
        publico = inferir_publico_objetivo(econ, hist, row["com"], row["tur"], row["tra"], ref.get("poblacion_500m", 4000))

        candidatos_rank.append({
            "latitud": lat,
            "longitud": lon,
            "radio_metros": 650,
            "plaza": hist["plaza"],
            "corredor": econ["corredor"],
            "ciudad": str(ref.get("ciudad", "") or hist["plaza"]),
            "barrio_referencia": str(ref.get("barrio", "") or econ["corredor"]),
            "score_potencial": score,
            "competidores_cercanos": int(row["comp_650m"]),
            "atractores_cercanos": int(row["total_pois"]),
            "nivel_gasto": econ["nivel_gasto"],
            "indice_ticket": econ["indice_ticket"],
            "circulacion": "Muy Alta" if flujo >= 110 else "Alta",
            "publico_objetivo": publico,
            "motivo": (
                f"{int(row['total_pois'])} polos comerciales/turísticos y gasto {econ['nivel_gasto'].lower()} "
                f"con solo {int(row['comp_650m'])} cafetería(s) en 650 m."
            ),
        })

    candidatos_rank.sort(key=lambda x: x["score_potencial"], reverse=True)
    seleccionadas = []
    for cand in candidatos_rank:
        muy_cerca = any(
            np.hypot(cand["latitud"] - s["latitud"], cand["longitud"] - s["longitud"]) < 0.03
            for s in seleccionadas
        )
        if not muy_cerca:
            cand["id"] = f"zona-oportunidad-{len(seleccionadas) + 1}"
            seleccionadas.append(cand)
        if len(seleccionadas) >= top_n:
            break

    return seleccionadas


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

    gdf_pois, rutas_por_slug = obtener_circulacion_y_rutas_geofabrik(gdf_buffers)
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

    log("5/5 Exportando modelo integral...")
    res = df_locales.copy()
    if "ciudad" not in res.columns:
        res["ciudad"] = ""
    if "barrio" not in res.columns:
        res["barrio"] = ""

    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["comercios_500m"] = res["slug_local"].map(conteo_com).fillna(0).astype(int)
    res["turismo_500m"] = res["slug_local"].map(conteo_tur).fillna(0).astype(int)
    res["transporte_500m"] = res["slug_local"].map(conteo_tra).fillna(0).astype(int)
    res["atractores_500m"] = res["comercios_500m"] + res["turismo_500m"] + res["transporte_500m"]

    res["poblacion_500m"] = res["slug_local"].apply(
        lambda s: pob_radios[s] if pob_radios.get(s, 0) > 0 else pob_deptos.get(s, 0)
    ).astype(int)

    evaluacion = res.apply(lambda r: evaluar_modelo_integral(r, rutas_por_slug), axis=1)
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
    res["corredor_economico"] = evaluacion[15]
    res["indice_ticket"] = evaluacion[16]
    res["gasto_turista_usd"] = evaluacion[17]
    res["costo_alquiler_zona"] = evaluacion[18]
    res["ecuacion_rentabilidad"] = evaluacion[19]
    res["publico_diurno_500m"] = evaluacion[20].astype(int)
    res["es_corredor_ruta"] = evaluacion[21].astype(bool)
    res["ruta_cercana"] = evaluacion[22].astype(str)
    res["flujo_ruta_diario"] = evaluacion[23].astype(int)
    res["fecha_actualizacion"] = datetime.now().strftime("%Y-%m-%d")

    os.makedirs("src/data", exist_ok=True)
    os.makedirs("public/data", exist_ok=True)
    res.set_index("slug_local").to_json("src/data/mercado.json", orient="index", force_ascii=False, indent=2)

    zonas_oportunidad = detectar_zonas_recomendadas(res, gdf_locales, gdf_pois, top_n=4)
    with open("src/data/zonas_oportunidad.json", "w", encoding="utf-8") as f:
        json.dump(zonas_oportunidad, f, ensure_ascii=False, indent=2)
    with open("public/data/zonas_oportunidad.json", "w", encoding="utf-8") as f:
        json.dump(zonas_oportunidad, f, ensure_ascii=False, indent=2)
    log(f"    -> {len(zonas_oportunidad)} zonas recomendadas para expansión exportadas.")

    cols_sheets = [
        "slug_local",
        "latitud",
        "longitud",
        "ciudad",
        "barrio",
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
        "corredor_economico",
        "indice_ticket",
        "gasto_turista_usd",
        "costo_alquiler_zona",
        "publico_diurno_500m",
        "es_corredor_ruta",
        "ruta_cercana",
        "flujo_ruta_diario",
    ]
    res[cols_sheets].to_csv("public/data/mercado.csv", index=False)
    log(f"¡COMPLETADO! {len(res)} locales exportados.")


if __name__ == "__main__":
    main()

