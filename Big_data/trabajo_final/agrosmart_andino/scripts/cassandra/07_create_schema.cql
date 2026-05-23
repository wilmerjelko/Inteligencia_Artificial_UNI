-- =================================================================
--  AgroSmart Andino — Esquema Apache Cassandra
--  Parte 5 — Capa de Servicio NoSQL
-- =================================================================
--  Keyspace : agrosmart_andino
--  Ejecutar : cqlsh -f scripts/cassandra/07_create_schema.cql
--             (dentro del contenedor Docker en Cloud9)
--  Replication: SimpleStrategy factor=1 (demo single-node)
-- =================================================================

-- ── Crear keyspace ──────────────────────────────────────────────
CREATE KEYSPACE IF NOT EXISTS agrosmart_andino
WITH replication = {
    'class'              : 'SimpleStrategy',
    'replication_factor' : 1
}
AND durable_writes = true;

USE agrosmart_andino;

-- =================================================================
-- TABLA 1: lecturas_climaticas_por_dia
-- Propósito : Almacena el historial climático diario por estación.
-- Partición  : estacion (distribución por estación meteorológica)
-- Clustering : fecha DESC (últimas lecturas primero)
-- =================================================================
DROP TABLE IF EXISTS lecturas_climaticas_por_dia;

CREATE TABLE lecturas_climaticas_por_dia (
    estacion              TEXT,
    fecha                 DATE,
    temp_max_c            DOUBLE,
    temp_min_c            DOUBLE,
    temp_media_c          DOUBLE,
    precipitacion_mm      DOUBLE,
    humedad_relativa_pct  DOUBLE,
    radiacion_solar_mj    DOUBLE,
    viento_ms             DOUBLE,
    riesgo_helada         INT,
    anio                  INT,
    mes                   INT,
    PRIMARY KEY (estacion, fecha)
) WITH CLUSTERING ORDER BY (fecha DESC)
  AND comment = 'Lecturas climáticas diarias por estación — NASA POWER'
  AND default_time_to_live = 0;

-- Índice secundario para consultas por año
CREATE INDEX IF NOT EXISTS idx_climat_anio
ON lecturas_climaticas_por_dia (anio);

-- Índice para filtrar por riesgo de helada
CREATE INDEX IF NOT EXISTS idx_climat_helada
ON lecturas_climaticas_por_dia (riesgo_helada);


-- =================================================================
-- TABLA 2: alertas_activas
-- Propósito : Alertas agroclimáticas generadas por el pipeline.
-- Partición  : nodo_id (cada nodo IoT como partición)
-- Clustering : fecha DESC, tipo_alerta
-- =================================================================
DROP TABLE IF EXISTS alertas_activas;

CREATE TABLE alertas_activas (
    nodo_id               TEXT,
    fecha                 DATE,
    tipo_alerta           TEXT,
    parcela               TEXT,
    ihb                   INT,
    itt                   INT,
    ieh                   INT,
    nivel_alerta          INT,
    alerta_critica        INT,
    temp_min_c            DOUBLE,
    humedad_relativa_pct  DOUBLE,
    humedad_suelo_media   DOUBLE,
    PRIMARY KEY (nodo_id, fecha, tipo_alerta)
) WITH CLUSTERING ORDER BY (fecha DESC, tipo_alerta ASC)
  AND comment = 'Alertas agroclimáticas activas por nodo IoT'
  AND default_time_to_live = 7776000;  -- TTL 90 días

-- Índice para filtrar por nivel de alerta
CREATE INDEX IF NOT EXISTS idx_alertas_nivel
ON alertas_activas (nivel_alerta);

-- Índice para filtrar alertas críticas
CREATE INDEX IF NOT EXISTS idx_alertas_critica
ON alertas_activas (alerta_critica);


-- =================================================================
-- TABLA 3: recomendaciones_riego
-- Propósito : Recomendaciones diarias de irrigación por parcela.
-- Partición  : nodo_id
-- Clustering : fecha DESC
-- =================================================================
DROP TABLE IF EXISTS recomendaciones_riego;

CREATE TABLE recomendaciones_riego (
    nodo_id               TEXT,
    fecha                 DATE,
    parcela               TEXT,
    altitud_m             INT,
    et0_mm                DOUBLE,
    precipitacion_mm      DOUBLE,
    humedad_suelo_pct     DOUBLE,
    vol_riego_aplicado_l  DOUBLE,
    deficit_hidrico_mm    DOUBLE,
    recomendacion         TEXT,
    horas_riego           INT,
    PRIMARY KEY (nodo_id, fecha)
) WITH CLUSTERING ORDER BY (fecha DESC)
  AND comment = 'Recomendaciones diarias de riego por nodo'
  AND default_time_to_live = 7776000;  -- TTL 90 días

-- Índice para filtrar por tipo de recomendación
CREATE INDEX IF NOT EXISTS idx_riego_recomendacion
ON recomendaciones_riego (recomendacion);


-- =================================================================
-- TABLA 4: predicciones_rendimiento
-- Propósito : Predicciones ML de rendimiento de papa por campaña.
-- Partición  : anio, distrito
-- Clustering : variedad
-- =================================================================
DROP TABLE IF EXISTS predicciones_rendimiento;

CREATE TABLE predicciones_rendimiento (
    anio                    INT,
    distrito                TEXT,
    variedad                TEXT,
    evento_climatico        TEXT,
    sup_sembrada_ha         DOUBLE,
    rendimiento_pred_tm_ha  DOUBLE,
    produccion_estimada_tm  DOUBLE,
    fecha_prediccion        TIMESTAMP,
    PRIMARY KEY ((anio, distrito), variedad)
) WITH CLUSTERING ORDER BY (variedad ASC)
  AND comment = 'Predicciones GBT de rendimiento de papa nativa';


-- =================================================================
-- TABLA 5: estado_nodos (tabla de control en tiempo real)
-- Propósito : Estado actual de cada nodo IoT (última lectura).
-- Partición  : nodo_id (lookup por nodo)
-- =================================================================
DROP TABLE IF EXISTS estado_nodos;

CREATE TABLE estado_nodos (
    nodo_id               TEXT PRIMARY KEY,
    parcela               TEXT,
    altitud_m             INT,
    ultima_lectura        TIMESTAMP,
    temp_suelo_c          DOUBLE,
    humedad_suelo_pct     DOUBLE,
    bateria_pct           DOUBLE,
    estado_bateria        TEXT,   -- 'OK', 'BAJO', 'CRITICO'
    alerta_activa         BOOLEAN,
    tipo_alerta_actual    TEXT,
    nivel_alerta_actual   INT,
    recomendacion_riego   TEXT,
    actualizado_en        TIMESTAMP
) WITH comment = 'Estado en tiempo real de nodos IoT';


-- =================================================================
-- Verificar creación de tablas
-- =================================================================
DESCRIBE TABLES;
