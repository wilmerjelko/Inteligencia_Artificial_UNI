"""
AgroSmart Andino — Parte 3: Crear clúster EMR en AWS
=====================================================
Crea el clúster EMR con PySpark + JupyterHub para la Parte 4.

Uso:
  python scripts/aws/06_create_emr_cluster.py

Pre-requisitos:
  - Bucket S3 creado y datasets subidos (ejecutar primero 05_upload_to_s3.py)
  - Credenciales AWS configuradas en .env
  - Key pair EC2 disponible en la región (ver instrucciones)

Salida:
  - Cluster ID guardado en data/emr_cluster_id.txt
  - URL de JupyterHub mostrada en pantalla
"""

import os
import sys
import json
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR    = Path(__file__).resolve().parents[2]
BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "agrosmart-andino-demo")
AWS_REGION  = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Configuración del clúster (demo scale — AWS Academy)
CLUSTER_CONFIG = {
    "Name": "AgroSmart-Andino-Demo",
    "ReleaseLabel": "emr-6.15.0",          # Spark 3.4, Hadoop 3.3
    "Applications": [
        {"Name": "Spark"},
        {"Name": "JupyterHub"},
        {"Name": "Hadoop"},
        {"Name": "Hive"},
    ],
    "Instances": {
        "InstanceGroups": [
            {
                "Name": "Primary",
                "Market": "ON_DEMAND",
                "InstanceRole": "MASTER",
                "InstanceType": "m5.xlarge",
                "InstanceCount": 1,
            },
            {
                "Name": "Core",
                "Market": "ON_DEMAND",
                "InstanceRole": "CORE",
                "InstanceType": "m5.xlarge",
                "InstanceCount": 1,
            },
        ],
        "KeepJobFlowAliveWhenNoSteps": True,
        "TerminationProtected": False,
    },
    "Configurations": [
        {
            "Classification": "spark-defaults",
            "Properties": {
                "spark.driver.memory": "4g",
                "spark.executor.memory": "4g",
                "spark.executor.cores": "2",
                "spark.sql.adaptive.enabled": "true",
                "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
            },
        },
        {
            "Classification": "jupyter-s3-conf",
            "Properties": {
                "s3.persistence.enabled": "true",
                "s3.persistence.bucket": BUCKET_NAME,
            },
        },
    ],
    "JobFlowRole": "EMR_EC2_DefaultRole",
    "ServiceRole": "EMR_DefaultRole",
    "LogUri": f"s3://{BUCKET_NAME}/logs/emr/",
    "VisibleToAllUsers": True,
    "Tags": [
        {"Key": "Project",  "Value": "AgroSmart-Andino"},
        {"Key": "Course",   "Value": "Big-Data-UNI"},
        {"Key": "Environment", "Value": "demo"},
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES
# ══════════════════════════════════════════════════════════════════════════════

def crear_cliente(service: str):
    kwargs = {"region_name": AWS_REGION}
    for k, env in [
        ("aws_access_key_id",     "AWS_ACCESS_KEY_ID"),
        ("aws_secret_access_key", "AWS_SECRET_ACCESS_KEY"),
        ("aws_session_token",     "AWS_SESSION_TOKEN"),
    ]:
        val = os.getenv(env)
        if val:
            kwargs[k] = val
    return boto3.client(service, **kwargs)


def preparar_security_groups_emr(ec2, vpc_id: str) -> tuple:
    """
    Crea (o reutiliza) security groups limpios para EMR.
    Solo permite SSH (22) desde internet; comunicación intra-cluster
    queda abierta entre los propios SGs.
    AWS Academy rechaza SGs con acceso público en puertos != 22.
    """
    def get_o_crear_sg(name, desc):
        try:
            resp = ec2.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [name]},
                    {"Name": "vpc-id",    "Values": [vpc_id]},
                ]
            )
            if resp["SecurityGroups"]:
                sg_id = resp["SecurityGroups"][0]["GroupId"]
                print(f"  ✓  SG existente reutilizado: {name} ({sg_id})")
                return sg_id
        except ClientError:
            pass
        resp = ec2.create_security_group(
            GroupName=name, Description=desc, VpcId=vpc_id
        )
        sg_id = resp["GroupId"]
        print(f"  ✓  SG creado: {name} ({sg_id})")
        return sg_id

    master_sg_id = get_o_crear_sg(
        "agrosmart-emr-master-sg", "AgroSmart EMR Master - SSH only"
    )
    slave_sg_id = get_o_crear_sg(
        "agrosmart-emr-slave-sg", "AgroSmart EMR Slave - SSH only"
    )

    # Añadir reglas solo si aún no existen
    for sg_id, peer_id in [
        (master_sg_id, slave_sg_id),
        (slave_sg_id,  master_sg_id),
    ]:
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    # SSH público
                    {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                     "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                    # Todo el tráfico interno desde el SG del peer
                    {"IpProtocol": "-1",
                     "UserIdGroupPairs": [{"GroupId": peer_id}]},
                    # Todo el tráfico interno desde el mismo SG
                    {"IpProtocol": "-1",
                     "UserIdGroupPairs": [{"GroupId": sg_id}]},
                ],
            )
        except ClientError as e:
            if "InvalidPermission.Duplicate" not in str(e):
                print(f"  ⚠  Regla SG ya existente o error ignorado: {e}")

    return master_sg_id, slave_sg_id


def esperar_cluster(emr, cluster_id: str, timeout_min: int = 20):
    """Espera a que el clúster esté en estado WAITING (listo)."""
    estados_ok    = {"WAITING"}
    estados_error = {"TERMINATED", "TERMINATED_WITH_ERRORS"}
    print(f"\n  Esperando que el clúster esté listo (hasta {timeout_min} min)...")
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        resp   = emr.describe_cluster(ClusterId=cluster_id)
        estado = resp["Cluster"]["Status"]["State"]
        motivo = resp["Cluster"]["Status"].get("StateChangeReason", {}).get("Message", "")
        print(f"\r  Estado: {estado:30s}", end="", flush=True)
        if estado in estados_ok:
            print(f"\n  ✓  Clúster listo")
            return True
        if estado in estados_error:
            print(f"\n  ✗  Clúster terminó con error: {motivo}")
            return False
        time.sleep(30)
    print(f"\n  ✗  Timeout esperando el clúster")
    return False


def obtener_dns_master(emr, cluster_id: str) -> str:
    resp = emr.describe_cluster(ClusterId=cluster_id)
    return resp["Cluster"].get("MasterPublicDnsName", "")


def main():
    print("=" * 65)
    print("  AgroSmart Andino — Crear clúster EMR")
    print("  Parte 3 — Infraestructura de procesamiento")
    print("=" * 65)
    print(f"  Bucket S3 : s3://{BUCKET_NAME}/")
    print(f"  Región    : {AWS_REGION}")
    print(f"  Release   : {CLUSTER_CONFIG['ReleaseLabel']}")
    print(f"  Nodos     : 1 Master + 1 Core (m5.xlarge)")
    print("=" * 65)

    # Crear clientes AWS
    print("\n  Conectando a AWS...")
    try:
        emr = crear_cliente("emr")
        ec2 = crear_cliente("ec2")
        print("  ✓  Conexión exitosa")
    except NoCredentialsError:
        print("  ✗  Credenciales no encontradas. Configura .env")
        sys.exit(1)

    # Verificar/crear roles IAM necesarios
    print("\n  Verificando roles IAM...")
    iam = crear_cliente("iam")
    roles_ok = True
    for role in ["EMR_DefaultRole", "EMR_EC2_DefaultRole"]:
        try:
            iam.get_role(RoleName=role)
            print(f"  ✓  {role}")
        except ClientError:
            print(f"  ⚠  {role} no encontrado — intentando crear con aws emr create-default-roles")
            roles_ok = False

    if not roles_ok:
        print("\n  → Ejecuta en tu terminal antes de continuar:")
        print("    aws emr create-default-roles")
        print("    (o créalos manualmente en IAM Console)")
        print("\n  Luego vuelve a ejecutar este script.")
        sys.exit(1)

    # Obtener subnet y VPC por defecto
    print("\n  Obteniendo subnet por defecto...")
    vpc_id = None
    try:
        subnets = ec2.describe_subnets(
            Filters=[{"Name": "defaultForAz", "Values": ["true"]}]
        )
        if subnets["Subnets"]:
            subnet_id = subnets["Subnets"][0]["SubnetId"]
            vpc_id    = subnets["Subnets"][0]["VpcId"]
            CLUSTER_CONFIG["Instances"]["Ec2SubnetId"] = subnet_id
            print(f"  ✓  Subnet: {subnet_id}  |  VPC: {vpc_id}")
        else:
            print("  ⚠  Sin subnet por defecto — EMR usará la VPC predeterminada")
    except ClientError as e:
        print(f"  ⚠  No se pudo obtener subnet: {e}")

    # Crear security groups limpios (solo SSH) para pasar validación AWS Academy
    if not vpc_id:
        print("  ✗  No se pudo obtener VPC. Se necesita para crear SGs.")
        sys.exit(1)

    print("\n  Preparando security groups EMR (solo SSH)...")
    try:
        master_sg, slave_sg = preparar_security_groups_emr(ec2, vpc_id)
        CLUSTER_CONFIG["Instances"]["EmrManagedMasterSecurityGroup"] = master_sg
        CLUSTER_CONFIG["Instances"]["EmrManagedSlaveSecurityGroup"]  = slave_sg
    except ClientError as e:
        print(f"  ✗  Error creando SGs personalizados: {e}")
        sys.exit(1)

    # Crear clúster
    print("\n  Creando clúster EMR...")
    print("  (esto tarda ~8-12 minutos)")
    try:
        resp = emr.run_job_flow(**CLUSTER_CONFIG)
        cluster_id = resp["JobFlowId"]
        print(f"  ✓  Clúster creado: {cluster_id}")
    except ClientError as e:
        print(f"  ✗  Error creando clúster: {e}")
        sys.exit(1)

    # Guardar cluster ID
    cluster_id_file = BASE_DIR / "data" / "emr_cluster_id.txt"
    cluster_id_file.parent.mkdir(parents=True, exist_ok=True)
    cluster_id_file.write_text(cluster_id)
    print(f"  ✓  Cluster ID guardado en: data/emr_cluster_id.txt")

    # Esperar que esté listo
    listo = esperar_cluster(emr, cluster_id, timeout_min=20)

    if listo:
        dns = obtener_dns_master(emr, cluster_id)
        jupyterhub_url = f"https://{dns}:9443"

        print("\n" + "=" * 65)
        print("  CLÚSTER LISTO")
        print("=" * 65)
        print(f"  Cluster ID   : {cluster_id}")
        print(f"  Master DNS   : {dns}")
        print(f"  JupyterHub   : {jupyterhub_url}")
        print()
        print("  Acceso a JupyterHub:")
        print(f"    1. Abre: {jupyterhub_url}")
        print(     "    2. Usuario: jovyan  |  Contraseña: (cualquier texto)")
        print(     "    3. Sube el notebook: notebooks/agrosmart_pipeline.ipynb")
        print()
        print("  ⚠  Recuerda TERMINAR el clúster al finalizar la sesión:")
        print(f"    aws emr terminate-clusters --cluster-ids {cluster_id}")
        print("   (o desde EMR Console → Actions → Terminate)")
        print("=" * 65)

        # Guardar info completa
        info = {
            "cluster_id": cluster_id,
            "master_dns": dns,
            "jupyterhub_url": jupyterhub_url,
            "region": AWS_REGION,
            "bucket": BUCKET_NAME,
        }
        info_file = BASE_DIR / "data" / "emr_info.json"
        with open(info_file, "w") as f:
            json.dump(info, f, indent=2)
        print(f"\n  Info guardada en: data/emr_info.json")
    else:
        print("\n  ✗  El clúster no llegó a estado WAITING.")
        print(f"     Revisa en EMR Console → Cluster {cluster_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()
