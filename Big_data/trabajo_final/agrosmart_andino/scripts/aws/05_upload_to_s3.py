"""
AgroSmart Andino — Parte 3: Subida de datos crudos a AWS S3
============================================================
Sube los 3 datasets validados al bucket S3 como Data Lake.

Estructura en S3:
  s3://agrosmart-andino-demo/raw/clima/nasa_power_yauyos.csv
  s3://agrosmart-andino-demo/raw/sensores/sensores_iot.csv
  s3://agrosmart-andino-demo/raw/produccion/produccion_papa_yauyos.csv

Pre-requisitos:
  1. Crear bucket S3 "agrosmart-andino-demo" en AWS Console (ver instrucciones abajo)
  2. Configurar credenciales en .env (copiar de AWS Academy Learner Lab)
  3. Tener los 3 archivos CSV en data/raw/

Uso:
  python scripts/aws/05_upload_to_s3.py
"""

import os
import sys
import time
from pathlib import Path

# ── Credenciales desde .env ────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Si no hay dotenv, se usan variables de entorno del sistema

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_RAW = BASE_DIR / "data" / "raw"

BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "agrosmart-andino-demo")
AWS_REGION  = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Mapeo: archivo local → prefijo (carpeta) en S3
UPLOAD_PLAN = [
    {
        "local":  DATA_RAW / "nasa_power_yauyos.csv",
        "s3_key": "raw/clima/nasa_power_yauyos.csv",
        "desc":   "Clima histórico NASA POWER (18,265 registros)",
    },
    {
        "local":  DATA_RAW / "sensores_iot.csv",
        "s3_key": "raw/sensores/sensores_iot.csv",
        "desc":   "Sensores IoT simulados (52,632 registros)",
    },
    {
        "local":  DATA_RAW / "produccion_papa_yauyos.csv",
        "s3_key": "raw/produccion/produccion_papa_yauyos.csv",
        "desc":   "Producción MIDAGRI (1,500 registros)",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_bytes(nb: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nb < 1024:
            return f"{nb:.1f} {unit}"
        nb /= 1024
    return f"{nb:.1f} GB"


class ProgressCallback:
    """Muestra progreso de carga en tiempo real."""

    def __init__(self, filename: str, total: int):
        self.filename = filename
        self.total    = total
        self.seen     = 0
        self.start    = time.time()

    def __call__(self, bytes_amount: int):
        self.seen += bytes_amount
        pct  = self.seen / self.total * 100 if self.total else 0
        elapsed = time.time() - self.start
        speed = self.seen / elapsed if elapsed > 0 else 0
        bar  = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(
            f"\r     [{bar}] {pct:5.1f}%  "
            f"{_fmt_bytes(self.seen)}/{_fmt_bytes(self.total)}  "
            f"({_fmt_bytes(speed)}/s)   ",
            end="",
            flush=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PRINCIPALES
# ══════════════════════════════════════════════════════════════════════════════

def crear_cliente_s3():
    """Crea cliente boto3 con credenciales del entorno."""
    kwargs = {"region_name": AWS_REGION}
    access_key   = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key   = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("AWS_SESSION_TOKEN")

    if access_key and secret_key:
        kwargs.update(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        if session_token:
            kwargs["aws_session_token"] = session_token

    return boto3.client("s3", **kwargs)


def verificar_bucket(s3, bucket: str) -> bool:
    """Verifica que el bucket exista y sea accesible."""
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            print(f"\n  ✗  Bucket '{bucket}' no encontrado.")
            print(     "     → Créalo en AWS Console (ver instrucciones al final).")
        elif code == "403":
            print(f"\n  ✗  Sin permisos para acceder al bucket '{bucket}'.")
            print(     "     → Verifica las credenciales en .env")
        else:
            print(f"\n  ✗  Error verificando bucket: {e}")
        return False


def subir_archivo(s3, item: dict) -> bool:
    """Sube un archivo a S3 con barra de progreso."""
    local_path: Path = item["local"]
    s3_key: str      = item["s3_key"]
    desc: str        = item["desc"]

    if not local_path.exists():
        print(f"  ✗  Archivo no encontrado: {local_path.name}")
        print(  "     → Ejecuta primero los scripts de data_acquisition/")
        return False

    file_size = local_path.stat().st_size
    print(f"\n  → {local_path.name}  ({_fmt_bytes(file_size)})")
    print(f"     {desc}")
    print(f"     Destino: s3://{BUCKET_NAME}/{s3_key}")

    callback = ProgressCallback(local_path.name, file_size)
    try:
        s3.upload_file(
            Filename=str(local_path),
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Callback=callback,
            ExtraArgs={"ContentType": "text/csv"},
        )
        print(f"\n     ✓  Subido en {time.time() - callback.start:.1f}s")
        return True
    except ClientError as e:
        print(f"\n     ✗  Error S3: {e}")
        return False


def verificar_subida(s3, items: list) -> None:
    """Lista los objetos subidos y confirma tamaños."""
    print("\n" + "═" * 65)
    print("  Verificación en S3")
    print("═" * 65)
    total_bytes = 0
    for item in items:
        try:
            resp = s3.head_object(Bucket=BUCKET_NAME, Key=item["s3_key"])
            size = resp["ContentLength"]
            total_bytes += size
            ts   = resp["LastModified"].strftime("%Y-%m-%d %H:%M UTC")
            print(f"  ✓  {item['s3_key']}")
            print(f"       Tamaño: {_fmt_bytes(size)}  |  Subido: {ts}")
        except ClientError:
            print(f"  ✗  No encontrado: {item['s3_key']}")
    print(f"\n  Total almacenado en S3: {_fmt_bytes(total_bytes)}")


# ══════════════════════════════════════════════════════════════════════════════
# INSTRUCCIONES AWS CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

INSTRUCCIONES_AWS = """
╔═══════════════════════════════════════════════════════════════════╗
║  INSTRUCCIONES — Crear bucket S3 en AWS Academy                  ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  PASO 1 — Iniciar sesión en AWS Academy                          ║
║    1. Ve a: https://awsacademy.instructure.com                   ║
║    2. Abre tu curso → "Learner Lab" → [Start Lab]                ║
║    3. Espera que el indicador se ponga en VERDE                   ║
║    4. Clic en [AWS] → se abre la consola AWS                     ║
║                                                                   ║
║  PASO 2 — Copiar credenciales temporales                         ║
║    1. En Learner Lab, clic en "AWS Details"                      ║
║    2. Copia los 3 valores:                                        ║
║         AWS_ACCESS_KEY_ID = ASIA...                              ║
║         AWS_SECRET_ACCESS_KEY = ...                              ║
║         AWS_SESSION_TOKEN = ...                                   ║
║    3. Pégalos en el archivo .env del proyecto                    ║
║       (copia .env.example → .env y reemplaza los valores)        ║
║                                                                   ║
║  PASO 3 — Crear bucket S3                                        ║
║    1. En AWS Console → busca "S3" → [Create bucket]              ║
║    2. Bucket name: agrosmart-andino-demo                         ║
║    3. AWS Region: US East (N. Virginia) us-east-1                ║
║    4. Block Public Access: ACTIVADO (dejar por defecto)          ║
║    5. Versioning: Disabled                                        ║
║    6. Clic en [Create bucket]                                    ║
║                                                                   ║
║  PASO 4 — Ejecutar este script                                   ║
║    Desde la carpeta agrosmart_andino/:                           ║
║    > python scripts/aws/05_upload_to_s3.py                      ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
"""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  AgroSmart Andino — Subida a AWS S3 (Data Lake)")
    print("  Parte 3 — Ingesta de datos crudos")
    print("=" * 65)
    print(f"  Bucket destino : s3://{BUCKET_NAME}/")
    print(f"  Región         : {AWS_REGION}")
    print(f"  Archivos       : {len(UPLOAD_PLAN)} datasets")
    print("=" * 65)

    # Verificar archivos locales antes de conectar
    faltantes = [i for i in UPLOAD_PLAN if not i["local"].exists()]
    if faltantes:
        print("\n  ✗  Archivos faltantes:")
        for i in faltantes:
            print(f"     - {i['local'].name}")
        print("\n  → Ejecuta primero los scripts de data_acquisition/")
        sys.exit(1)

    # Crear cliente S3
    print("\n  Conectando a AWS S3...")
    try:
        s3 = crear_cliente_s3()
        # Prueba simple de conectividad
        s3.list_buckets()
        print("  ✓  Conexión exitosa")
    except NoCredentialsError:
        print("\n  ✗  Credenciales AWS no encontradas.")
        print(     "     → Configura AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY en .env")
        print(INSTRUCCIONES_AWS)
        sys.exit(1)
    except Exception as e:
        print(f"\n  ✗  Error de conexión: {e}")
        print(INSTRUCCIONES_AWS)
        sys.exit(1)

    # Verificar bucket
    print(f"\n  Verificando bucket '{BUCKET_NAME}'...")
    if not verificar_bucket(s3, BUCKET_NAME):
        print(INSTRUCCIONES_AWS)
        sys.exit(1)
    print(f"  ✓  Bucket accesible")

    # Subir archivos
    print("\n" + "═" * 65)
    print("  Subiendo datasets")
    print("═" * 65)
    resultados = []
    for item in UPLOAD_PLAN:
        ok = subir_archivo(s3, item)
        resultados.append(ok)

    # Resumen
    exitosos = sum(resultados)
    fallidos  = len(resultados) - exitosos

    if exitosos > 0:
        verificar_subida(s3, [i for i, ok in zip(UPLOAD_PLAN, resultados) if ok])

    print("\n" + "=" * 65)
    print("  RESUMEN")
    print("=" * 65)
    print(f"  ✓  Archivos subidos    : {exitosos}/{len(UPLOAD_PLAN)}")
    if fallidos:
        print(f"  ✗  Archivos fallidos   : {fallidos}")

    if exitosos == len(UPLOAD_PLAN):
        print()
        print("  ✓  Data Lake listo en S3")
        print()
        print("  Próximo paso — PARTE 4: EMR + PySpark")
        print("  Ejecutar: notebooks/agrosmart_pipeline.ipynb en JupyterHub")
        print()
        print("  Estructura del Data Lake:")
        for item in UPLOAD_PLAN:
            print(f"    s3://{BUCKET_NAME}/{item['s3_key']}")
    else:
        print()
        print("  Algunos archivos no se subieron. Revisa los errores anteriores.")
        sys.exit(1)


if __name__ == "__main__":
    main()
