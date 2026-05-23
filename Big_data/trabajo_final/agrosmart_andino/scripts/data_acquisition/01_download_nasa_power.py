"""
Script 01: Descarga de datos climáticos históricos — NASA POWER API
════════════════════════════════════════════════════════════════════
Proyecto : AgroSmart Andino
Grupo    : 2 — Maestría IA | Curso Big Data | UNI
Docente  : Rosa Virginia Encinas Quille

Descripción:
    Descarga datos climáticos diarios 2015-2024 para 5 puntos geográficos
    en la zona alto andina de Yauyos, Lima (Perú) usando la API pública y
    gratuita de NASA POWER (Prediction Of Worldwide Energy Resources).

    API base: https://power.larc.nasa.gov/api/temporal/daily/point
    Comunidad: AG (Agroclimatología — diseñada para agricultura)
    Sin registro ni API key requerida.

Variables descargadas:
    T2M_MAX           → Temperatura máxima a 2m (°C)
    T2M_MIN           → Temperatura mínima a 2m (°C)
    T2M               → Temperatura media a 2m (°C)
    PRECTOTCORR       → Precipitación corregida (mm/día)
    RH2M              → Humedad relativa a 2m (%)
    ALLSKY_SFC_SW_DWN → Radiación solar superficial total (MJ/m²/día)
    WS2M              → Velocidad del viento a 2m (m/s)

Puntos geográficos (zona alto andina Yauyos, Lima):
    1. Huangascar  — foco principal del sistema (3,200 m.s.n.m.)
    2. Yauyos      — capital de provincia
    3. Carania     — zona alto andina norte
    4. Tanta       — zona alto andina este
    5. Vilca       — zona alto andina sur

Output:
    data/raw/nasa_power_yauyos.csv  (~18,250 filas × 11 columnas)

Uso:
    python scripts/data_acquisition/01_download_nasa_power.py
"""

import requests
import pandas as pd
import time
import sys
from pathlib import Path
from tqdm import tqdm

# ── Configuración ──────────────────────────────────────────────────────────────

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

VARIABLES = "T2M_MAX,T2M_MIN,T2M,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN,WS2M"

# 5 puntos representativos de la zona alto andina de Yauyos
ESTACIONES = [
    {"nombre": "Huangascar", "lat": -12.94, "lon": -75.77, "altitud_m": 3200},
    {"nombre": "Yauyos",     "lat": -12.49, "lon": -75.90, "altitud_m": 2310},
    {"nombre": "Carania",    "lat": -12.36, "lon": -75.83, "altitud_m": 3850},
    {"nombre": "Tanta",      "lat": -12.11, "lon": -76.02, "altitud_m": 4200},
    {"nombre": "Vilca",      "lat": -12.04, "lon": -75.56, "altitud_m": 3600},
]

FECHA_INICIO = "20150101"
FECHA_FIN    = "20241231"

# Ruta de salida relativa al directorio del script
OUTPUT_FILE = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "nasa_power_yauyos.csv"
)

RENAME_COLS = {
    "T2M_MAX":           "temp_max_c",
    "T2M_MIN":           "temp_min_c",
    "T2M":               "temp_media_c",
    "PRECTOTCORR":       "precipitacion_mm",
    "RH2M":              "humedad_relativa_pct",
    "ALLSKY_SFC_SW_DWN": "radiacion_solar_mj",
    "WS2M":              "viento_ms",
}

# ── Funciones ──────────────────────────────────────────────────────────────────

def descargar_estacion(nombre: str, lat: float, lon: float, altitud_m: int) -> pd.DataFrame | None:
    """
    Descarga datos diarios de una estación desde NASA POWER API.
    Retorna un DataFrame limpio o None si falla.
    """
    params = {
        "parameters": VARIABLES,
        "community":  "AG",
        "longitude":  lon,
        "latitude":   lat,
        "start":      FECHA_INICIO,
        "end":        FECHA_FIN,
        "format":     "JSON",
    }

    try:
        resp = requests.get(NASA_POWER_URL, params=params, timeout=90)
        resp.raise_for_status()
        data = resp.json()

        properties = data["properties"]["parameter"]
        fechas = list(next(iter(properties.values())).keys())

        rows = []
        for fecha_str in fechas:
            row = {
                "fecha":     fecha_str,
                "estacion":  nombre,
                "latitud":   lat,
                "longitud":  lon,
                "altitud_m": altitud_m,
            }
            for var, valores in properties.items():
                row[var] = valores.get(fecha_str)
            rows.append(row)

        df = pd.DataFrame(rows)
        df["fecha"] = pd.to_datetime(df["fecha"], format="%Y%m%d")

        # Reemplazar -999 (valor NASA para datos faltantes) por NaN
        numeric_cols = df.select_dtypes(include="number").columns
        df[numeric_cols] = df[numeric_cols].replace(-999.0, float("nan"))

        # Renombrar columnas a nombres descriptivos
        df.rename(columns=RENAME_COLS, inplace=True)

        # Agregar columnas derivadas útiles
        df["anio"]      = df["fecha"].dt.year
        df["mes"]       = df["fecha"].dt.month
        df["dia"]       = df["fecha"].dt.day
        df["dia_anio"]  = df["fecha"].dt.dayofyear

        # Indicador de riesgo de helada (T_min < 2°C)
        df["riesgo_helada"] = (df["temp_min_c"] < 2.0).astype(int)

        # Indicador de día lluvioso (precipitación > 1 mm)
        df["dia_lluvioso"] = (df["precipitacion_mm"] > 1.0).astype(int)

        return df

    except requests.exceptions.Timeout:
        print(f"\n  [ERROR] Timeout en {nombre}. Reintentando en 10s...")
        time.sleep(10)
        return None
    except requests.exceptions.RequestException as e:
        print(f"\n  [ERROR] {nombre}: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"\n  [ERROR] Procesando respuesta de {nombre}: {e}")
        return None


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("  AgroSmart Andino — Descarga NASA POWER API")
    print("=" * 65)
    print(f"  Período    : {FECHA_INICIO} → {FECHA_FIN}")
    print(f"  Estaciones : {len(ESTACIONES)}")
    print(f"  Variables  : {VARIABLES}")
    print(f"  Output     : {OUTPUT_FILE}")
    print("=" * 65)

    dfs = []
    for est in tqdm(ESTACIONES, desc="Descargando estaciones", unit="est"):
        tqdm.write(f"  → {est['nombre']} ({est['lat']}, {est['lon']})...")
        df = descargar_estacion(
            est["nombre"], est["lat"], est["lon"], est["altitud_m"]
        )
        if df is not None:
            dfs.append(df)
            tqdm.write(f"     {len(df):,} registros descargados ✓")
        else:
            tqdm.write(f"     OMITIDO (error de descarga)")
        time.sleep(1.5)  # Respetar rate limit de NASA POWER API

    if not dfs:
        print("\n[FATAL] No se descargó ningún dataset. Verifica conexión a internet.")
        sys.exit(1)

    df_final = pd.concat(dfs, ignore_index=True)

    # Ordenar por estación y fecha
    df_final.sort_values(["estacion", "fecha"], inplace=True)
    df_final.reset_index(drop=True, inplace=True)

    # Guardar CSV
    df_final.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # ── Reporte final ──────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  COMPLETADO — {OUTPUT_FILE.name}")
    print("=" * 65)
    print(f"  Total registros   : {len(df_final):,}")
    print(f"  Estaciones        : {df_final['estacion'].nunique()}")
    print(f"  Rango de fechas   : {df_final['fecha'].min().date()} → {df_final['fecha'].max().date()}")
    print(f"  Columnas          : {list(df_final.columns)}")
    print(f"  Valores nulos (%) : {df_final.isnull().mean().mul(100).round(1).to_dict()}")
    print("\n  Temperatura media por estación (°C):")
    resumen = (
        df_final.groupby("estacion")["temp_media_c"]
        .agg(registros="count", media="mean", minima="min", maxima="max")
        .round(1)
    )
    print(resumen.to_string())
    print("\n  Días con riesgo de helada por estación:")
    heladas = df_final.groupby("estacion")["riesgo_helada"].sum().astype(int)
    print(heladas.to_string())
    print("=" * 65)


if __name__ == "__main__":
    main()
