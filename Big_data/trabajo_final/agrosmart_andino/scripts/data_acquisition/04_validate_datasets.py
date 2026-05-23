"""
Script 04: Validación de datasets — AgroSmart Andino
═════════════════════════════════════════════════════
Verifica integridad, completitud y consistencia de los 3 CSVs
generados antes de subirlos a AWS S3.

Uso:
    python scripts/data_acquisition/04_validate_datasets.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

DATASETS = {
    "NASA POWER (clima)":     RAW_DIR / "nasa_power_yauyos.csv",
    "Sensores IoT":           RAW_DIR / "sensores_iot.csv",
    "Producción MIDAGRI":     RAW_DIR / "produccion_papa_yauyos.csv",
}

CHECKS = {
    "NASA POWER (clima)": {
        "min_filas": 15000,
        "columnas_requeridas": [
            "fecha", "estacion", "latitud", "longitud", "altitud_m",
            "temp_max_c", "temp_min_c", "temp_media_c",
            "precipitacion_mm", "humedad_relativa_pct",
            "radiacion_solar_mj", "viento_ms",
            "riesgo_helada", "dia_lluvioso",
        ],
        "rango": {"temp_media_c": (-10, 30), "precipitacion_mm": (0, 100)},
    },
    "Sensores IoT": {
        "min_filas": 50000,
        "columnas_requeridas": [
            "timestamp", "nodo_id", "parcela", "altitud_m",
            "temp_suelo_c", "humedad_suelo_pct",
            "caudal_riego_lmin", "bateria_pct",
            "alerta_helada_suelo", "alerta_sequia",
        ],
        "rango": {"temp_suelo_c": (-5, 30), "humedad_suelo_pct": (0, 100)},
    },
    "Producción MIDAGRI": {
        "min_filas": 200,
        "columnas_requeridas": [
            "anio", "region", "provincia", "distrito", "cultivo",
            "variedad", "sup_sembrada_ha", "sup_cosechada_ha",
            "produccion_tm", "rendimiento_tm_ha",
        ],
        "rango": {"rendimiento_tm_ha": (1, 30), "produccion_tm": (0, 50000)},
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def seccion(titulo: str):
    print(f"\n{'═' * 65}")
    print(f"  {titulo}")
    print(f"{'═' * 65}")

def ok(msg: str):   print(f"  ✓  {msg}")
def warn(msg: str): print(f"  ⚠  {msg}")
def err(msg: str):  print(f"  ✗  {msg}")

# ── Validación principal ───────────────────────────────────────────────────────

def validar_dataset(nombre: str, path: Path, checks: dict) -> bool:
    seccion(nombre)

    # 1. Existencia del archivo
    if not path.exists():
        err(f"Archivo no encontrado: {path}")
        err("Ejecuta primero el script de adquisición correspondiente.")
        return False
    ok(f"Archivo encontrado: {path.name}  ({path.stat().st_size / 1024:.1f} KB)")

    # 2. Carga
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as e:
        err(f"Error al leer el CSV: {e}")
        return False

    ok(f"Cargado correctamente: {len(df):,} filas × {len(df.columns)} columnas")

    # 3. Mínimo de filas
    if len(df) < checks["min_filas"]:
        err(f"Pocas filas: {len(df):,} < {checks['min_filas']:,} esperadas")
        return False
    ok(f"Volumen suficiente: {len(df):,} filas (mínimo: {checks['min_filas']:,})")

    # 4. Columnas requeridas
    faltantes = [c for c in checks["columnas_requeridas"] if c not in df.columns]
    if faltantes:
        err(f"Columnas faltantes: {faltantes}")
        return False
    ok(f"Todas las columnas requeridas presentes ({len(checks['columnas_requeridas'])})")

    # 5. Valores nulos
    nulos = df[checks["columnas_requeridas"]].isnull().sum()
    nulos_total = nulos.sum()
    if nulos_total == 0:
        ok("Sin valores nulos en columnas clave")
    else:
        pct = nulos_total / (len(df) * len(checks["columnas_requeridas"])) * 100
        if pct < 5:
            warn(f"Valores nulos: {nulos_total:,} ({pct:.1f}%) — aceptable para datos históricos")
        else:
            err(f"Demasiados nulos: {nulos_total:,} ({pct:.1f}%)")
            return False

    # 6. Rangos lógicos
    for col, (vmin, vmax) in checks.get("rango", {}).items():
        if col in df.columns:
            col_num = pd.to_numeric(df[col], errors="coerce")
            fuera   = col_num.dropna()
            fuera   = fuera[(fuera < vmin) | (fuera > vmax)]
            pct_fuera = len(fuera) / len(col_num.dropna()) * 100
            if pct_fuera < 1:
                ok(f"Rango {col}: [{vmin}, {vmax}]  — {pct_fuera:.2f}% fuera del rango (OK)")
            else:
                warn(f"Rango {col}: {pct_fuera:.1f}% de valores fuera de [{vmin}, {vmax}]")

    # 7. Duplicados
    dups = df.duplicated().sum()
    if dups == 0:
        ok("Sin filas duplicadas")
    else:
        warn(f"{dups:,} filas duplicadas detectadas")

    # 8. Estadísticas rápidas
    num_cols = df.select_dtypes(include="number").columns.tolist()[:5]
    print(f"\n  Estadísticas descriptivas (primeras {len(num_cols)} variables numéricas):")
    print(df[num_cols].describe().round(2).to_string())

    return True


def main():
    print("=" * 65)
    print("  AgroSmart Andino — Validación de Datasets")
    print("  Parte 2 — Sección 2.4")
    print("=" * 65)

    resultados = {}
    for nombre, path in DATASETS.items():
        checks = CHECKS[nombre]
        ok_flag = validar_dataset(nombre, path, checks)
        resultados[nombre] = "✓ OK" if ok_flag else "✗ FALLO"

    # Resumen final
    print("\n" + "=" * 65)
    print("  RESUMEN DE VALIDACIÓN")
    print("=" * 65)
    todos_ok = True
    for nombre, resultado in resultados.items():
        print(f"  {resultado}  {nombre}")
        if "FALLO" in resultado:
            todos_ok = False

    if todos_ok:
        total_filas = sum(
            len(pd.read_csv(p, low_memory=False))
            for p in DATASETS.values() if p.exists()
        )
        print(f"\n  Total registros listos para S3: {total_filas:,}")
        print("  ✓  Todos los datasets validados — listos para PARTE 3 (AWS S3)")
    else:
        print("\n  Corrige los errores antes de subir a S3.")
        sys.exit(1)

    print("=" * 65)


if __name__ == "__main__":
    main()
