import os
import glob
import json
import time
import socket
from datetime import datetime
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
import rasterio
from rasterio.mask import mask
import urllib3.util.connection as urllib3_cn

urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

URL_DATOS_MERCADO_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vSFR6-_mxHeIRopuVzI4bskv8hSyqvnjjy0pRdJ8cNCI2vtsQlcLCDzJD5m8StLzceZL3Zn3Pmh_bbn/"
    "pub?gid=802012693&single=true&output=csv"
)

# Grilla poblacional 100m Argentina (descarga directa en la nube, ~25 MB)
URL_GRILLA_POB = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/"
    "2020/BSGM/ARG/arg_ppp_2020_UNadj_constrained.tif"
)
RUTA_GRILLA_POB = "datos_censales/arg_pob_100m.tif"
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


def calcular_poblacion_grilla(gdf_buffers_4326):
    """Calcula habitantes en 500m usando la grilla de 100m sin descargar nada a tu tablet."""
    os.makedirs("datos_censales", exist_ok=True)
    if not os.path.exists(RUTA_GRILLA_POB):
        print("Descargando grilla demográfica de Argentina (100m)...")
        try:
            with requests.get(URL_GRILLA_POB, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(RUTA_GRILLA_POB, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        f.write(chunk)
        except Exception as e:
            print(f"No se pudo descargar la grilla remota: {e}")
            return {}

    poblaciones = {}
    try:
        with rasterio.open(RUTA_GRILLA_POB) as src:
            for _, row in gdf_buffers_4326.iterrows():
                try:
                    out_img, _ = mask(src, [row["geometry"]], crop=True, filled=True, nodata=0.0)
                    valores = np.where(out_img > 0, out_img, 0.0)
                    poblaciones[row["slug_local"]] = int(round(float(np.sum(valores))))
                except Exception:
                    poblaciones[row["slug_local"]] = 0
    except Exception as e:
        print(f"Error leyendo raster poblacional: {e}")
    return poblaciones


def cruzar_capas_indec_locales(gdf_buffers_3857):
    """Lee cualquier archivo GeoJSON / GeoPackage / ZIP de INDEC o poblaciones.org en datos_censales/."""
    archivos = (
        glob.glob("datos_censales/*.geojson")
        + glob.glob("datos_censales/*.gpkg")
        + glob.glob("datos_censales/*.zip")
    )
    if not archivos:
        return {}, {}, {}

    pob_indec, pea_indec, nse_indec = {}, {}, {}
    for ruta in archivos:
        try:
            gdf_c = gpd.read_file(ruta).to_crs(epsg=3857)
            gdf_c["area_radio"] = gdf_c.geometry.area.replace(0, np.nan)

            col_pob = next((c for c in gdf_c.columns if c.upper() in ["POBLACION", "TOT_POB", "POB_TOT", "PERSONAS", "P_TOTAL", "POB"]), None)
            col_pea = next((c for c in gdf_c.columns if c.upper() in ["PEA", "PEA_PCT", "POB_15_64", "EDAD_20_59"]), None)
            col_edu = next((c for c in gdf_c.columns if c.upper() in ["UNIV", "SUP_COMP", "EDUC_SUP", "UNIVERSITARIO"]), None)

            inter = gpd.overlay(gdf_buffers_3857, gdf_c, how="intersection")
            if inter.empty:
                continue
            inter["factor_area"] = (inter.geometry.area / inter["area_radio"]).clip(0, 1)

            if col_pob:
                inter["pob_prop"] = pd.to_numeric(inter[col_pob], errors="coerce").fillna(0) * inter["factor_area"]
                for slug, val in inter.groupby("slug_local")["pob_prop"].sum().items():
                    pob_indec[slug] = pob_indec.get(slug, 0) + int(round(val))

            if col_pea and col_pob:
                inter["pea_prop"] = pd.to_numeric(inter[col_pea], errors="coerce").fillna(0) * inter["factor_area"]
                for slug, grp in inter.groupby("slug_local"):
                    tot_p = grp["pob_prop"].sum()
                    if tot_p > 0:
                        pea_indec[slug] = round((grp["pea_prop"].sum() / tot_p) * 100, 1)

            if col_edu and col_pob:
                inter["edu_prop"] = pd.to_numeric(inter[col_edu], errors="coerce").fillna(0) * inter["factor_area"]
                for slug, grp in inter.groupby("slug_local"):
                    tot_p = grp["pob_prop"].sum()
                    if tot_p > 0:
                        pct_univ = (grp["edu_prop"].sum() / tot_p) * 100
                        if pct_univ >= 28:
                            nse_indec[slug] = "Alto"
                        elif pct_univ >= 16:
                            nse_indec[slug] = "Medio-Alto"
                        elif pct_univ >= 8:
                            nse_indec[slug] = "Medio"
                        else:
                            nse_indec[slug] = "Emergente"
        except Exception as e:
            print(f"Aviso leyendo {ruta}: {e}")

    return pob_indec, pea_indec, nse_indec


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


def estimar_nse_y_pea(row):
    """Estimación de respaldo cuando aún no se subió el archivo provincial de INDEC."""
    pob = row["poblacion_500m"]
    atr = row["atractores_500m"]
    comp = row["competidores_500m"]

    pea_est = round(min(74.0, max(54.0, 56.0 + (atr * 0.8) + (pob / 2500.0))), 1)

    score_urbano = (pob / 1000.0) + (atr * 2.5) + (comp * 1.5)
    if score_urbano >= 22:
        nse = "Alto"
    elif score_urbano >= 12:
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
    gdf_buffers_4326 = gdf_buffers.to_crs(epsg=4326)

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

    # 3. Población en 500m (Grilla 100m + Capas INDEC si existen)
    pob_grilla = calcular_poblacion_grilla(gdf_buffers_4326)
    pob_indec, pea_indec, nse_indec = cruzar_capas_indec_locales(gdf_buffers)

    res = df_locales[["slug_local", "latitud", "longitud"]].copy()
    res["competidores_500m"] = res["slug_local"].map(conteo_comp).fillna(0).astype(int)
    res["atractores_500m"] = res["slug_local"].map(conteo_pois).fillna(0).astype(int)
    res["poblacion_500m"] = res["slug_local"].apply(
        lambda s: pob_indec.get(s, pob_grilla.get(s, 0))
    ).astype(int)

    estimados = res.apply(estimar_nse_y_pea, axis=1)
    res["pea_porcentaje"] = res["slug_local"].map(pea_indec).fillna(estimados[0])
    res["nivel_socioeconomico"] = res["slug_local"].map(nse_indec).fillna(estimados[1])

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
    print(f"Cruce demográfico completado: {len(res)} locales.")


if __name__ == "__main__":
    main()
