#!/usr/bin/env bash
# =================================================================
#  AgroSmart Andino — Setup Cassandra en AWS Cloud9 (t2.micro)
#  Parte 5 — Infraestructura NoSQL
# =================================================================
#  Ejecutar en Cloud9:
#    chmod +x scripts/cassandra/09_setup_cassandra_cloud9.sh
#    bash scripts/cassandra/09_setup_cassandra_cloud9.sh
#
#  Este script:
#    1. Instala Docker si no está disponible
#    2. Levanta contenedor Cassandra 4.1
#    3. Espera que esté listo (nodetool status)
#    4. Crea el keyspace y las tablas (07_create_schema.cql)
#    5. Muestra instrucciones para cargar los datos
# =================================================================

set -e

KEYSPACE="agrosmart_andino"
CONTAINER="cassandra_agrosmart"
CQL_SCHEMA="scripts/cassandra/07_create_schema.cql"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo "================================================================="
echo "  AgroSmart Andino — Setup Cassandra en Cloud9"
echo "================================================================="

# ── 1. Verificar / instalar Docker ───────────────────────────────
if ! command -v docker &> /dev/null; then
    warn "Docker no encontrado. Instalando..."
    sudo yum update -y -q
    sudo yum install -y docker
    sudo service docker start
    sudo usermod -aG docker ec2-user
    info "Docker instalado. Reinicia la sesión Cloud9 y vuelve a ejecutar."
    exit 0
fi
info "Docker disponible: $(docker --version | cut -d' ' -f3)"

# ── 2. Detener contenedor anterior si existe ──────────────────────
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    warn "Contenedor '${CONTAINER}' ya existe. Eliminando..."
    docker stop "${CONTAINER}" 2>/dev/null || true
    docker rm   "${CONTAINER}" 2>/dev/null || true
fi

# ── 3. Ajustar límites del sistema para Cassandra ────────────────
warn "Ajustando ulimits para Cassandra..."
sudo sysctl -w vm.max_map_count=1048575 2>/dev/null || true

# ── 4. Levantar contenedor Cassandra 4.1 ─────────────────────────
info "Iniciando contenedor Cassandra 4.1 (modo single-node)..."
docker run -d \
    --name "${CONTAINER}" \
    -p 9042:9042 \
    -p 9160:9160 \
    -e CASSANDRA_CLUSTER_NAME="AgroSmartCluster" \
    -e CASSANDRA_DC="datacenter1" \
    -e CASSANDRA_RACK="rack1" \
    -e HEAP_NEWSIZE="128M" \
    -e MAX_HEAP_SIZE="512M" \
    --restart unless-stopped \
    cassandra:4.1

info "Contenedor iniciado: ${CONTAINER}"

# ── 5. Esperar que Cassandra esté listo ───────────────────────────
echo ""
info "Esperando que Cassandra esté listo (puede tardar ~60s)..."
MAX_WAIT=120
WAITED=0
while true; do
    STATUS=$(docker exec "${CONTAINER}" nodetool status 2>/dev/null | grep "^UN" | wc -l || echo "0")
    if [ "${STATUS}" -ge "1" ]; then
        info "Cassandra listo — nodo UP+NORMAL"
        break
    fi
    if [ "${WAITED}" -ge "${MAX_WAIT}" ]; then
        error "Timeout esperando Cassandra. Revisa: docker logs ${CONTAINER}"
    fi
    echo -n "."
    sleep 5
    WAITED=$((WAITED + 5))
done
echo ""

# ── 6. Copiar CQL al contenedor y ejecutar ───────────────────────
if [ ! -f "${CQL_SCHEMA}" ]; then
    error "No se encontró ${CQL_SCHEMA}. Ejecuta desde la raíz del proyecto."
fi

info "Copiando esquema CQL al contenedor..."
docker cp "${CQL_SCHEMA}" "${CONTAINER}:/tmp/create_schema.cql"

info "Creando keyspace y tablas..."
docker exec "${CONTAINER}" cqlsh -f /tmp/create_schema.cql
info "Esquema creado correctamente"

# ── 7. Verificar tablas creadas ───────────────────────────────────
echo ""
info "Verificando tablas en keyspace '${KEYSPACE}':"
docker exec "${CONTAINER}" cqlsh -e "
  USE ${KEYSPACE};
  DESCRIBE TABLES;
"

# ── 8. Mostrar estado del clúster ─────────────────────────────────
echo ""
info "Estado del nodo Cassandra:"
docker exec "${CONTAINER}" nodetool status

echo ""
echo "================================================================="
echo "  Cassandra listo en localhost:9042"
echo "================================================================="
echo ""
echo "  Para cargar los datos (desde tu entorno local o EMR):"
echo ""
echo "  1. Descarga los CSVs Gold desde S3:"
echo "     mkdir -p data/gold"
echo "     aws s3 sync s3://agrosmart-andino-demo/gold/csv/ data/gold/"
echo ""
echo "  2. Ejecuta el script de carga:"
echo "     pip install cassandra-driver python-dotenv"
echo "     python scripts/cassandra/08_load_data.py --host 127.0.0.1"
echo ""
echo "  3. Para acceder a cqlsh manualmente:"
echo "     docker exec -it ${CONTAINER} cqlsh"
echo "     USE ${KEYSPACE};"
echo "     SELECT * FROM estado_nodos;"
echo ""
echo "  Para detener Cassandra:"
echo "     docker stop ${CONTAINER}"
echo "================================================================="
