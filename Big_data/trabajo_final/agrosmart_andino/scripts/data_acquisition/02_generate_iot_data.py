"""
Script 02: Generación de datos IoT simulados realistas
═══════════════════════════════════════════════════════
Proyecto : AgroSmart Andino
Grupo    : 2 — Maestría IA | Curso Big Data | UNI
Docente  : Rosa Virginia Encinas Quille

Descripción:
    Genera datos sintéticos realistas de sensores IoT instalados en parcelas
    de cultivo de papa nativa en Huangascar, Yauyos (3,200 m.s.n.m.).

    Los datos simulan lecturas horarias de 3 nodos sensores durante 2 años
    (2023-2024), siguiendo patrones climáticos reales de la zona andina:
    - Temporada seca: mayo–octubre (bajas lluvias, riesgo de helada nocturna)
    - Temporada húmeda: noviembre–abril (lluvias frecuentes, temperaturas templadas)

Sensores por nodo:
    temp_suelo_c         → Temperatura del suelo a 10 cm de profundidad (°C)
    humedad_suelo_pct    → Humedad volumétrica del suelo a 15 cm (%)
    caudal_riego_lmin    → Caudal del sistema de riego (L/min)
    bateria_pct          → Nivel de batería del nodo IoT (%)

Nodos:
    NODO-001 — Parcela Baja    (~3,000 m.s.n.m.)
    NODO-002 — Parcela Media   (~3,200 m.s.n.m.) — foco principal
    NODO-003 — Parcela Alta    (~3,500 m.s.n.m.)

Output:
    data/raw/sensores_iot.csv  (~52,560 filas × 9 columnas)

Nota académica:
    Estos datos son sintéticos, generados con patrones estadísticos
    representativos de la zona. En un sistema real, provendrían de sensores
    físicos (Arduino/Raspberry Pi + LoRaWAN). Se documenta explícitamente
    como datos de demostración del pipeline Big Data.

Uso:
    python scripts/data_acquisition/02_generate_iot_data.py
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ── Configuración ──────────────────────────────────────────────────────────────

SEED = 42
np.random.seed(SEED)

FECHA_INICIO = "2023-01-01 00:00:00"
FECHA_FIN    = "2024-12-31 23:00:00"
FRECUENCIA   = "1h"

NODOS = [
    {"id": "NODO-001", "parcela": "Parcela Baja",   "altitud_m": 3000, "lat": -12.942, "lon": -75.771},
    {"id": "NODO-002", "parcela": "Parcela Media",  "altitud_m": 3200, "lat": -12.940, "lon": -75.768},
    {"id": "NODO-003", "parcela": "Parcela Alta",   "altitud_m": 3500, "lat": -12.937, "lon": -75.763},
]

OUTPUT_FILE = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "sensores_iot.csv"
)

# ── Parámetros climáticos por mes (Huangascar, 3200 m.s.n.m.) ─────────────────
# Basado en climatología conocida de la sierra central peruana
#       ene  feb  mar  abr  may  jun  jul  ago  sep  oct  nov  dic
T_AMBIENTE_MEDIA   = [13,  13,  13,  12,  10,   8,   8,   9,  10,  12,  13,  13]
T_AMPLITUD_DIARIA  = [ 8,   8,   7,   9,  12,  13,  14,  14,  13,  11,   9,   8]
PROB_LLUVIA_DIARIA = [0.7, 0.7, 0.6, 0.4, 0.1, 0.02,0.02,0.03,0.1, 0.3, 0.5, 0.6]
LLUVIA_INTENSIDAD  = [5.0, 6.0, 4.0, 2.5, 0.5, 0.2, 0.1, 0.2, 0.5, 1.5, 3.0, 4.0]


# ── Funciones de simulación ────────────────────────────────────────────────────

def temperatura_horaria(fechas: pd.DatetimeIndex, altitud_m: int) -> np.ndarray:
    """
    Simula temperatura del suelo horaria.
    El suelo sigue la temperatura ambiente con:
      - Corrección por altitud (-0.65°C por 100m sobre 3200m base)
      - Inercia térmica (el suelo no cambia tan rápido como el aire)
      - Ciclo diurno sinusoidal (mínimo ~6am, máximo ~14h)
      - Ruido gaussiano pequeño
    """
    correc_altitud = (altitud_m - 3200) * (-0.0065)
    temps = np.zeros(len(fechas))

    for i, ts in enumerate(fechas):
        mes       = ts.month - 1
        hora      = ts.hour
        t_media   = T_AMBIENTE_MEDIA[mes] + correc_altitud
        amplitud  = T_AMPLITUD_DIARIA[mes]

        # Ciclo diurno: mínimo a las 6h, máximo a las 14h
        ciclo = -np.cos(2 * np.pi * (hora - 6) / 24)

        # El suelo amortigua la amplitud (factor 0.6) y tiene lag de +2h
        ciclo_suelo = -np.cos(2 * np.pi * (hora - 8) / 24)
        t_suelo = t_media + amplitud * 0.55 * ciclo_suelo

        # Ruido
        t_suelo += np.random.normal(0, 0.4)

        # Clipping: el suelo rara vez baja de 0°C o sube de 25°C en esta zona
        temps[i] = np.clip(t_suelo, 0.5, 24.0)

    # Suavizado con rolling window para mayor realismo
    return pd.Series(temps).rolling(3, center=True, min_periods=1).mean().values


def humedad_suelo_horaria(fechas: pd.DatetimeIndex, altitud_m: int) -> np.ndarray:
    """
    Simula humedad volumétrica del suelo (%).
    Modelo simple de balance hídrico:
      - Recarga por eventos de lluvia (aumenta humedad)
      - Descenso gradual por evapotranspiración (más rápido en temporada seca)
      - Riegos adicionales en temporada seca (aumento moderado)
    """
    n = len(fechas)
    humedad = np.zeros(n)
    h = 55.0  # humedad inicial (%)

    for i, ts in enumerate(fechas):
        mes       = ts.month - 1
        hora      = ts.hour

        # Determinar si es día lluvioso (una vez por día a las 00h)
        if hora == 0:
            llueve = np.random.random() < PROB_LLUVIA_DIARIA[mes]
        else:
            llueve = False

        # Recarga por lluvia (~10-20% de incremento en el día)
        if llueve and hora in [14, 15, 16]:  # lluvias típicamente tarde
            recarga = np.random.uniform(5, 20) * LLUVIA_INTENSIDAD[mes] / 5.0
            h += recarga

        # Riego programado: lunes, miércoles, viernes a las 7am en temporada seca
        es_temporada_seca = mes in [4, 5, 6, 7, 8, 9]
        es_dia_riego = ts.dayofweek in [0, 2, 4]
        if es_temporada_seca and es_dia_riego and hora == 7:
            h += np.random.uniform(8, 15)

        # Evapotranspiración horaria (mayor al mediodía, casi nula de noche)
        et_hora = 0.05 if 8 <= hora <= 18 else 0.01
        et_factor = 1.5 if es_temporada_seca else 0.8
        h -= et_hora * et_factor

        # Percolación si excede capacidad de campo
        if h > 80:
            h = 80.0 - np.random.uniform(0, 3)

        h = np.clip(h, 15.0, 80.0)
        humedad[i] = h + np.random.normal(0, 0.8)

    return np.clip(humedad, 10.0, 85.0).round(1)


def caudal_riego_horario(fechas: pd.DatetimeIndex) -> np.ndarray:
    """
    Simula el caudal del sistema de riego por goteo (L/min).
    - Riego activado lunes, miércoles y viernes a las 7am–9am (temporada seca)
    - Sin riego en temporada húmeda (nov–abr)
    - Caudal típico por gotero: 0.5–2.0 L/min
    """
    caudal = np.zeros(len(fechas))

    for i, ts in enumerate(fechas):
        mes = ts.month - 1
        hora = ts.hour
        es_temporada_seca = mes in [4, 5, 6, 7, 8, 9]
        es_dia_riego = ts.dayofweek in [0, 2, 4]

        if es_temporada_seca and es_dia_riego and 7 <= hora <= 9:
            caudal[i] = np.random.uniform(0.8, 1.8)
        else:
            caudal[i] = 0.0

    return caudal.round(2)


def bateria_horaria(n: int) -> np.ndarray:
    """
    Simula el nivel de batería del nodo IoT (%).
    Carga solar durante el día, consumo constante.
    Descarga total ~5% por día, recarga ~8% durante horas solares.
    """
    bateria = np.zeros(n)
    b = np.random.uniform(85, 95)

    for i in range(n):
        hora = i % 24
        # Carga solar (8am–18h)
        if 8 <= hora <= 18:
            b += np.random.uniform(0.3, 0.7)
        else:
            b -= np.random.uniform(0.1, 0.25)

        # Capping entre 20% y 100%
        b = np.clip(b, 20.0, 100.0)
        bateria[i] = round(b + np.random.normal(0, 0.3), 1)

    return np.clip(bateria, 20.0, 100.0)


def generar_nodo(nodo_info: dict, fechas: pd.DatetimeIndex) -> pd.DataFrame:
    """Genera el DataFrame completo de un nodo sensor."""
    n = len(fechas)
    altitud = nodo_info["altitud_m"]

    print(f"  Generando {nodo_info['id']} — {nodo_info['parcela']} "
          f"({altitud} m.s.n.m.)... ", end="", flush=True)

    df = pd.DataFrame({
        "timestamp":          fechas,
        "nodo_id":            nodo_info["id"],
        "parcela":            nodo_info["parcela"],
        "latitud":            nodo_info["lat"],
        "longitud":           nodo_info["lon"],
        "altitud_m":          altitud,
        "temp_suelo_c":       temperatura_horaria(fechas, altitud).round(1),
        "humedad_suelo_pct":  humedad_suelo_horaria(fechas, altitud),
        "caudal_riego_lmin":  caudal_riego_horario(fechas),
        "bateria_pct":        bateria_horaria(n),
    })

    # Indicadores derivados
    df["alerta_helada_suelo"]   = (df["temp_suelo_c"] < 2.0).astype(int)
    df["alerta_sequia"]         = (df["humedad_suelo_pct"] < 25.0).astype(int)
    df["alerta_exceso_agua"]    = (df["humedad_suelo_pct"] > 75.0).astype(int)
    df["riego_activo"]          = (df["caudal_riego_lmin"] > 0).astype(int)

    print(f"OK — {len(df):,} registros")
    return df


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("  AgroSmart Andino — Generación de datos IoT simulados")
    print("=" * 65)
    print(f"  Período    : {FECHA_INICIO} → {FECHA_FIN}")
    print(f"  Frecuencia : horaria")
    print(f"  Nodos      : {len(NODOS)}")
    print(f"  Output     : {OUTPUT_FILE}")
    print("=" * 65)

    fechas = pd.date_range(start=FECHA_INICIO, end=FECHA_FIN, freq=FRECUENCIA)

    dfs = [generar_nodo(nodo, fechas) for nodo in NODOS]
    df_final = pd.concat(dfs, ignore_index=True)
    df_final.sort_values(["nodo_id", "timestamp"], inplace=True)
    df_final.reset_index(drop=True, inplace=True)

    df_final.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    # ── Reporte final ──────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  COMPLETADO — {OUTPUT_FILE.name}")
    print("=" * 65)
    print(f"  Total registros    : {len(df_final):,}")
    print(f"  Nodos              : {df_final['nodo_id'].nunique()}")
    print(f"  Rango timestamps   : {df_final['timestamp'].min()} → {df_final['timestamp'].max()}")

    print("\n  Estadísticas por nodo:")
    resumen = df_final.groupby("nodo_id").agg(
        registros        = ("timestamp", "count"),
        temp_suelo_media = ("temp_suelo_c", "mean"),
        humedad_media    = ("humedad_suelo_pct", "mean"),
        horas_riego      = ("riego_activo", "sum"),
        alertas_helada   = ("alerta_helada_suelo", "sum"),
        alertas_sequia   = ("alerta_sequia", "sum"),
    ).round(1)
    print(resumen.to_string())
    print("=" * 65)


if __name__ == "__main__":
    main()
