"""
AgroSmart Andino — Parte 5: Cargar datos en Apache Cassandra
=============================================================
Lee los CSVs Gold (generados por PySpark en EMR) y los inserta
en las tablas del keyspace agrosmart_andino.

Pre-requisitos:
  1. Docker con Cassandra corriendo en Cloud9:
       docker run -d --name cassandra -p 9042:9042 cassandra:4.1
  2. Esquema creado:
       docker exec -i cassandra cqlsh -f /tmp/07_create_schema.cql
  3. CSVs Gold descargados en data/gold/ (desde S3 o scp desde EMR)

Uso:
  python scripts/cassandra/08_load_data.py [--host 127.0.0.1] [--dry-run]
"""

import os
import sys
import csv
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, date
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Python 3.12+ eliminó asyncore; usar asyncio reactor explícitamente
try:
    from cassandra.io.asyncioreactor import AsyncioConnection  # noqa: F401
    from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
    from cassandra.policies import DCAwareRoundRobinPolicy, RetryPolicy
    from cassandra.query import SimpleStatement
    from cassandra import ConsistencyLevel
    _CASSANDRA_OK = True
except Exception:
    _CASSANDRA_OK = False

# ══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════

BASE_DIR    = Path(__file__).resolve().parents[2]
GOLD_DIR    = BASE_DIR / "data" / "gold"
KEYSPACE    = "agrosmart_andino"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agrosmart.cassandra")

# Definición de tablas: archivo CSV → tabla Cassandra
TABLAS = {
    "lecturas_climaticas": {
        "csv":   GOLD_DIR / "lecturas_climaticas.csv",
        "tabla": "lecturas_climaticas_por_dia",
        "batch": 50,
    },
    "alertas_activas": {
        "csv":   GOLD_DIR / "alertas_activas.csv",
        "tabla": "alertas_activas",
        "batch": 100,
    },
    "recomendaciones_riego": {
        "csv":   GOLD_DIR / "recomendaciones_riego.csv",
        "tabla": "recomendaciones_riego",
        "batch": 100,
    },
    "predicciones_rendimiento": {
        "csv":   GOLD_DIR / "predicciones_rendimiento.csv",
        "tabla": "predicciones_rendimiento",
        "batch": 50,
    },
}


# ══════════════════════════════════════════════════════════════════
# CONEXIÓN
# ══════════════════════════════════════════════════════════════════

def crear_sesion(host: str, port: int = 9042):
    """Crea sesión Cassandra con asyncio reactor (compatible Python 3.12+)."""
    if not _CASSANDRA_OK:
        raise RuntimeError("cassandra-driver no disponible")
    from cassandra.io.asyncioreactor import AsyncioConnection
    profile = ExecutionProfile(
        load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="datacenter1"),
        retry_policy=RetryPolicy(),
        consistency_level=ConsistencyLevel.LOCAL_QUORUM,
        request_timeout=60,
    )
    cluster = Cluster(
        contact_points=[host],
        port=port,
        execution_profiles={EXEC_PROFILE_DEFAULT: profile},
        protocol_version=4,
        connection_class=AsyncioConnection,
    )
    session = cluster.connect()
    session.execute(f"USE {KEYSPACE}")
    log.info("Conectado a Cassandra %s:%d  → keyspace '%s'", host, port, KEYSPACE)
    return cluster, session


# ══════════════════════════════════════════════════════════════════
# HELPERS DE TIPO
# ══════════════════════════════════════════════════════════════════

def _float(val: str) -> Optional[float]:
    try:
        v = float(val)
        return None if v != v else v   # NaN → None
    except (ValueError, TypeError):
        return None


def _int(val: str) -> Optional[int]:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _date(val: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None


def _ts(val: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None


def _bool(val: str) -> bool:
    return str(val).strip().lower() in ("1", "true", "yes")


def _str(val: str) -> Optional[str]:
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None


# ══════════════════════════════════════════════════════════════════
# CARGA POR TABLA
# ══════════════════════════════════════════════════════════════════

def cargar_lecturas_climaticas(session, rows: list[dict], dry_run: bool) -> int:
    cql = """
    INSERT INTO lecturas_climaticas_por_dia
        (estacion, fecha, temp_max_c, temp_min_c, temp_media_c,
         precipitacion_mm, humedad_relativa_pct, radiacion_solar_mj,
         viento_ms, riesgo_helada, anio, mes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    stmt = session.prepare(cql) if not dry_run else None
    ok = 0
    for r in rows:
        try:
            params = (
                _str(r["estacion"]),
                _date(r["fecha"]),
                _float(r["temp_max_c"]),
                _float(r["temp_min_c"]),
                _float(r["temp_media_c"]),
                _float(r["precipitacion_mm"]),
                _float(r["humedad_relativa_pct"]),
                _float(r["radiacion_solar_mj"]),
                _float(r["viento_ms"]),
                _int(r["riesgo_helada"]),
                _int(r["anio"]),
                _int(r["mes"]),
            )
            if not dry_run and params[0] and params[1]:
                session.execute(stmt, params)
            ok += 1
        except Exception as e:
            log.debug("Error fila lecturas: %s", e)
    return ok


def cargar_alertas_activas(session, rows: list[dict], dry_run: bool) -> int:
    cql = """
    INSERT INTO alertas_activas
        (nodo_id, fecha, tipo_alerta, parcela, ihb, itt, ieh,
         nivel_alerta, alerta_critica, temp_min_c,
         humedad_relativa_pct, humedad_suelo_media)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    stmt = session.prepare(cql) if not dry_run else None
    ok = 0
    for r in rows:
        try:
            params = (
                _str(r["nodo_id"]),
                _date(r["fecha"]),
                _str(r["tipo_alerta"]),
                _str(r["parcela"]),
                _int(r["ihb"]),
                _int(r["itt"]),
                _int(r["ieh"]),
                _int(r["nivel_alerta"]),
                _int(r["alerta_critica"]),
                _float(r["temp_min_c"]),
                _float(r["humedad_relativa_pct"]),
                _float(r["humedad_suelo_media"]),
            )
            if not dry_run and params[0] and params[1] and params[2]:
                session.execute(stmt, params)
            ok += 1
        except Exception as e:
            log.debug("Error fila alerta: %s", e)
    return ok


def cargar_recomendaciones_riego(session, rows: list[dict], dry_run: bool) -> int:
    cql = """
    INSERT INTO recomendaciones_riego
        (nodo_id, fecha, parcela, altitud_m, et0_mm, precipitacion_mm,
         humedad_suelo_pct, vol_riego_aplicado_l, deficit_hidrico_mm,
         recomendacion, horas_riego)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    stmt = session.prepare(cql) if not dry_run else None
    ok = 0
    for r in rows:
        try:
            params = (
                _str(r["nodo_id"]),
                _date(r["fecha"]),
                _str(r["parcela"]),
                _int(r.get("altitud_m", "0")),
                _float(r["et0_mm"]),
                _float(r["precipitacion_mm"]),
                _float(r["humedad_suelo_pct"]),
                _float(r["vol_riego_aplicado_l"]),
                _float(r["deficit_hidrico_mm"]),
                _str(r["recomendacion"]),
                _int(r.get("horas_riego", "0")),
            )
            if not dry_run and params[0] and params[1]:
                session.execute(stmt, params)
            ok += 1
        except Exception as e:
            log.debug("Error fila riego: %s", e)
    return ok


def cargar_predicciones_rendimiento(session, rows: list[dict], dry_run: bool) -> int:
    cql = """
    INSERT INTO predicciones_rendimiento
        (anio, distrito, variedad, evento_climatico, sup_sembrada_ha,
         rendimiento_pred_tm_ha, produccion_estimada_tm, fecha_prediccion)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    stmt = session.prepare(cql) if not dry_run else None
    ok = 0
    for r in rows:
        try:
            params = (
                _int(r["anio"]),
                _str(r["distrito"]),
                _str(r["variedad"]),
                _str(r.get("evento_climatico", "normal")),
                _float(r.get("sup_sembrada_ha", "0")),
                _float(r["rendimiento_pred_tm_ha"]),
                _float(r.get("produccion_estimada_tm", "0")),
                _ts(r.get("fecha_prediccion", str(datetime.now()))),
            )
            if not dry_run and params[0] and params[1] and params[2]:
                session.execute(stmt, params)
            ok += 1
        except Exception as e:
            log.debug("Error fila prediccion: %s", e)
    return ok


# ══════════════════════════════════════════════════════════════════
# ACTUALIZAR ESTADO DE NODOS
# ══════════════════════════════════════════════════════════════════

def actualizar_estado_nodos(session, dry_run: bool):
    """Construye y actualiza la tabla estado_nodos con los últimos datos."""
    log.info("Actualizando tabla estado_nodos...")

    # Leer últimas alertas por nodo
    alertas_csv = GOLD_DIR / "alertas_activas.csv"
    riego_csv   = GOLD_DIR / "recomendaciones_riego.csv"

    if not alertas_csv.exists() or not riego_csv.exists():
        log.warning("No se encontraron CSVs para estado_nodos")
        return

    # Agrupar por nodo (última fila = fecha más reciente, CSV ya ordenado DESC)
    def leer_ultimo_por_nodo(csv_path: Path) -> dict:
        ultimos = {}
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                nodo = row.get("nodo_id", "")
                if nodo and nodo not in ultimos:
                    ultimos[nodo] = row
        return ultimos

    ultimas_alertas = leer_ultimo_por_nodo(alertas_csv)
    ultimas_riego   = leer_ultimo_por_nodo(riego_csv)

    # Todos los nodos conocidos
    nodos = {
        "NODO-001": {"parcela": "Parcela Baja",  "altitud_m": 3000},
        "NODO-002": {"parcela": "Parcela Media", "altitud_m": 3200},
        "NODO-003": {"parcela": "Parcela Alta",  "altitud_m": 3500},
    }

    cql = """
    INSERT INTO estado_nodos
        (nodo_id, parcela, altitud_m, ultima_lectura,
         temp_suelo_c, humedad_suelo_pct, bateria_pct, estado_bateria,
         alerta_activa, tipo_alerta_actual, nivel_alerta_actual,
         recomendacion_riego, actualizado_en)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    stmt = session.prepare(cql) if not dry_run else None
    now  = datetime.utcnow()

    for nodo_id, info in nodos.items():
        alerta = ultimas_alertas.get(nodo_id, {})
        riego  = ultimas_riego.get(nodo_id, {})

        humedad = _float(riego.get("humedad_suelo_pct", "55"))
        bateria = 85.0  # dato simulado (en producción vendría del IoT)
        estado_bat = "CRITICO" if bateria < 20 else "BAJO" if bateria < 40 else "OK"

        nivel = _int(alerta.get("nivel_alerta", "0")) or 0

        params = (
            nodo_id,
            info["parcela"],
            info["altitud_m"],
            _ts(alerta.get("fecha", str(now.date()))) or now,
            _float(riego.get("humedad_suelo_pct", "10")) or 10.0,  # temp_suelo aprox
            humedad or 55.0,
            bateria,
            estado_bat,
            nivel > 0,
            _str(alerta.get("tipo_alerta", "NINGUNA")),
            nivel,
            _str(riego.get("recomendacion", "NORMAL")),
            now,
        )
        if not dry_run:
            session.execute(stmt, params)
        log.info("  %s → alerta=%s nivel=%d riego=%s",
                 nodo_id,
                 params[10] or "NINGUNA",
                 nivel,
                 params[11] or "NORMAL")

    log.info("✓ estado_nodos actualizado (%d nodos)", len(nodos))


# ══════════════════════════════════════════════════════════════════
# DISPATCHER
# ══════════════════════════════════════════════════════════════════

LOADERS = {
    "lecturas_climaticas":    cargar_lecturas_climaticas,
    "alertas_activas":        cargar_alertas_activas,
    "recomendaciones_riego":  cargar_recomendaciones_riego,
    "predicciones_rendimiento": cargar_predicciones_rendimiento,
}


def cargar_tabla(session, nombre: str, config: dict, dry_run: bool) -> dict:
    """Lee el CSV y ejecuta la función de carga correspondiente."""
    csv_path: Path = config["csv"]
    tabla    = config["tabla"]

    if not csv_path.exists():
        log.warning("CSV no encontrado: %s", csv_path)
        return {"nombre": nombre, "estado": "FALTANTE", "total": 0, "ok": 0}

    # Leer CSV
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    log.info("Cargando %-30s  (%d filas → %s)", nombre, total, tabla)

    t0 = time.time()
    ok = LOADERS[nombre](session, rows, dry_run)
    elapsed = time.time() - t0

    log.info("  ✓ %d/%d filas en %.1fs (%.0f filas/s)",
             ok, total, elapsed, ok / elapsed if elapsed > 0 else 0)

    return {"nombre": nombre, "estado": "OK", "total": total, "ok": ok,
            "elapsed": elapsed}


# ══════════════════════════════════════════════════════════════════
# VERIFICACIÓN
# ══════════════════════════════════════════════════════════════════

def verificar_carga(session):
    """Cuenta filas en cada tabla y muestra resumen."""
    tablas_cql = [
        "lecturas_climaticas_por_dia",
        "alertas_activas",
        "recomendaciones_riego",
        "predicciones_rendimiento",
        "estado_nodos",
    ]
    print("\n" + "=" * 60)
    print("  Verificación — Conteo de filas en Cassandra")
    print("=" * 60)
    for tabla in tablas_cql:
        try:
            # ALLOW FILTERING es aceptable en demo single-node
            row = session.execute(
                f"SELECT COUNT(*) FROM {tabla}"   # noqa: S608
            ).one()
            n = row[0] if row else 0
            print(f"  {tabla:<40s}: {n:>6,} filas")
        except Exception as e:
            print(f"  {tabla:<40s}: ERROR — {e}")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="Carga datos en Apache Cassandra")
    p.add_argument("--host",    default=os.getenv("CASSANDRA_HOST", "127.0.0.1"),
                   help="Host de Cassandra (default: 127.0.0.1)")
    p.add_argument("--port",    type=int, default=9042)
    p.add_argument("--dry-run", action="store_true",
                   help="Parsea los CSVs sin insertar en Cassandra")
    p.add_argument("--tabla",   default=None,
                   help="Cargar solo esta tabla (nombre sin extensión)")
    return p.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  AgroSmart Andino — Carga en Apache Cassandra")
    print("  Parte 5 — Capa de Servicio NoSQL")
    print("=" * 60)
    print(f"  Host     : {args.host}:{args.port}")
    print(f"  Keyspace : {KEYSPACE}")
    print(f"  Gold dir : {GOLD_DIR}")
    print(f"  Modo     : {'DRY-RUN (sin insertar)' if args.dry_run else 'PRODUCCION'}")
    print("=" * 60)

    # Verificar CSVs
    tablas_a_cargar = (
        {args.tabla: TABLAS[args.tabla]} if args.tabla and args.tabla in TABLAS
        else TABLAS
    )
    faltantes = [n for n, c in tablas_a_cargar.items() if not c["csv"].exists()]
    if faltantes:
        print(f"\n  AVISO — CSVs no encontrados: {', '.join(faltantes)}")
        print(f"  Directorio esperado: {GOLD_DIR}/")
        print("  → Descarga los CSVs Gold desde S3 o cópialos desde el EMR")
        if not args.dry_run:
            print("\n  Comandos para descargar desde S3:")
            for n, c in tablas_a_cargar.items():
                bucket = os.getenv("S3_BUCKET_NAME", "agrosmart-andino-demo")
                print(f"    aws s3 cp s3://{bucket}/gold/csv/{n}/ {GOLD_DIR}/ --recursive")
            sys.exit(1)

    # Conectar
    if not args.dry_run:
        if not _CASSANDRA_OK:
            print("\n  ERROR: cassandra-driver no disponible o incompatible.")
            print("  En Cloud9 (Python 3.9): pip install cassandra-driver")
            sys.exit(1)
        try:
            cluster, session = crear_sesion(args.host, args.port)
        except Exception as e:
            print(f"\n  ERROR conectando a Cassandra: {e}")
            print("\n  ¿Está Cassandra corriendo?")
            print("  En Cloud9 con Docker:")
            print("    docker run -d --name cassandra -p 9042:9042 cassandra:4.1")
            print("    docker exec -i cassandra cqlsh < /tmp/07_create_schema.cql")
            sys.exit(1)
    else:
        cluster, session = None, None
        log.info("Modo DRY-RUN — sin conexión a Cassandra")

    # Cargar tablas
    t_total = time.time()
    resultados = []
    for nombre, config in tablas_a_cargar.items():
        res = cargar_tabla(session, nombre, config, args.dry_run)
        resultados.append(res)

    # Actualizar estado de nodos
    if not args.dry_run and session:
        actualizar_estado_nodos(session, args.dry_run)

    # Verificar
    if not args.dry_run and session:
        verificar_carga(session)

    # Resumen final
    elapsed_total = time.time() - t_total
    total_filas   = sum(r["total"] for r in resultados)
    total_ok      = sum(r["ok"] for r in resultados)

    print("\n" + "=" * 60)
    print("  RESUMEN DE CARGA")
    print("=" * 60)
    for r in resultados:
        est = r["estado"]
        print(f"  {'✓' if est == 'OK' else '⚠'} {r['nombre']:<35s}: "
              f"{r.get('ok', 0):>6,} / {r.get('total', 0):>6,} filas")
    print(f"\n  Total filas procesadas : {total_ok:>6,} / {total_filas:>6,}")
    print(f"  Tiempo total           : {elapsed_total:.1f}s")

    if not args.dry_run:
        print()
        print("  ✓ Cassandra listo para el dashboard Streamlit")
        print()
        print("  Próximo paso — PARTE 6: Dashboard Streamlit")
        print("    python dashboard/app.py")
    print("=" * 60)

    if cluster:
        cluster.shutdown()


if __name__ == "__main__":
    main()
