# AgroSmart Andino 🌿
## Sistema Big Data de Monitoreo Inteligente y Riego Automatizado para Cultivos de Papa Nativa en Huangascar, Yauyos

---

## Información del Proyecto

| Campo | Detalle |
|-------|---------|
| **Universidad** | Universidad Nacional de Ingeniería — Escuela de Posgrado |
| **Maestría** | Inteligencia Artificial |
| **Curso** | Big Data |
| **Docente** | Rosa Virginia Encinas Quille |
| **Grupo** | Grupo 2 |
| **Modalidad** | Informe Técnico |

## Integrantes

| Nombre | Rol en el proyecto |
|--------|--------------------|
| Anahys Montes Chapilliquen | |
| Christian Fabrizzio Vizcardo Estupinán | |
| Cristhian Massa Medina | |
| Freddy Antonio Huali Veliz | |
| Wilmer Jelko Lazaro Guerra | |

---

## Descripción del Sistema

**AgroSmart Andino** es un pipeline Big Data end-to-end que integra datos climáticos históricos,
datos de producción agrícola y sensores IoT simulados para monitorear el estado de cultivos
de papa nativa en la zona alto andina de Huangascar, Yauyos (Lima, Perú).

El sistema proporciona:
- Alertas tempranas de helada, tizón tardío y estrés hídrico
- Recomendaciones automatizadas de riego basadas en datos reales
- Predicción de rendimiento de cosecha mediante Machine Learning
- Dashboard en tiempo real con visualización del estado del cultivo

---

## Arquitectura del Sistema

```
INGESTIÓN          ALMACENAMIENTO        PROCESAMIENTO         SERVING            APLICACIÓN
NASA POWER  ──→                     ──→  AWS EMR           ──→                ──→
SENAMHI     ──→   AWS S3 (Data Lake)     Apache Spark           Apache Cassandra    Streamlit
MIDAGRI     ──→                     ──→  Spark MLlib        ──→  (Cloud9+Docker)    Dashboard
IoT Simulado──→
```

---

## Estructura del Repositorio

```
agrosmart_andino/
├── data/
│   ├── raw/                        # Datos originales sin modificar
│   │   ├── nasa_power_yauyos.csv   # Clima histórico 2015-2024 (NASA POWER API)
│   │   ├── sensores_iot.csv        # Lecturas IoT simuladas horarias 2023-2024
│   │   └── produccion_papa.csv     # Producción papa Yauyos MIDAGRI histórico
│   └── processed/                  # Datasets limpios y transformados por Spark
│
├── notebooks/
│   └── agrosmart_pipeline.ipynb    # Notebook PySpark principal (ejecutar en EMR)
│
├── scripts/
│   ├── data_acquisition/
│   │   ├── 01_download_nasa_power.py   # Descarga datos climáticos NASA POWER API
│   │   └── 02_generate_iot_data.py     # Genera datos IoT simulados realistas
│   ├── aws/
│   │   └── 03_upload_to_s3.py          # Sube datasets al bucket S3
│   └── cassandra/
│       ├── 04_create_schema.cql        # Keyspace y tablas Cassandra
│       └── 05_load_data.py             # Carga resultados Spark → Cassandra
│
├── dashboard/
│   └── app.py                      # Aplicación Streamlit (dashboard tiempo real)
│
├── docs/                           # Informe técnico y presentación
│
├── README.md
├── requirements.txt
└── .gitignore
```

---

## Datasets Utilizados

| Dataset | Fuente | Período | Registros aprox. | Variables clave |
|---------|--------|---------|------------------|----------------|
| Clima histórico | NASA POWER API | 2015–2024 | ~18,250 filas | T°max, T°min, precipitación, radiación solar, humedad, ET₀ |
| Sensores IoT | Simulado (Python) | 2023–2024 | ~17,520 filas | T°suelo, humedad suelo, caudal riego |
| Producción papa | MIDAGRI/SIEA | 2000–2024 | ~300 filas | Producción (t), área (ha), rendimiento (t/ha) |

**Ubicación de referencia:** Huangascar, Yauyos, Lima — aprox. 3,200 m.s.n.m.
**Coordenadas:** Latitud -12.94°, Longitud -75.77°

---

## Stack Tecnológico

| Tecnología | Versión | Rol |
|-----------|---------|-----|
| Python | 3.10+ | Lenguaje principal |
| Apache Spark / PySpark | 3.3+ | Procesamiento distribuido |
| AWS S3 | — | Data Lake |
| AWS EMR | 6.x | Cluster Spark |
| Apache Cassandra | 4.x | Base de datos NoSQL (serving layer) |
| Docker | — | Contenedor Cassandra en Cloud9 |
| Streamlit | 1.x | Dashboard interactivo |
| Pandas / NumPy | — | Procesamiento local auxiliar |
| Matplotlib / Seaborn | — | Visualizaciones EDA |

---

## Instrucciones de Ejecución

### FASE A — Preparación local (antes de abrir AWS)

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Descargar datos climáticos NASA POWER
python scripts/data_acquisition/01_download_nasa_power.py

# 3. Generar datos IoT simulados
python scripts/data_acquisition/02_generate_iot_data.py

# Verificar que data/raw/ contiene los 3 archivos CSV
```

### FASE B — Sesión AWS Academy (3 horas)

```bash
# 1. Subir datos a S3 (configurar credenciales AWS primero)
python scripts/aws/03_upload_to_s3.py

# 2. Crear cluster EMR (ver guía en docs/)
# 3. Ejecutar notebooks/agrosmart_pipeline.ipynb en JupyterHub EMR
# 4. En Cloud9: ejecutar scripts/cassandra/04_create_schema.cql
# 5. Cargar resultados en Cassandra
python scripts/cassandra/05_load_data.py
```

### FASE C — Dashboard local

```bash
streamlit run dashboard/app.py
```

---

## Zona de Estudio

**Huangascar** es un distrito de la provincia de Yauyos, región Lima, ubicado en la
sierra centro-occidental del Perú a aproximadamente 3,200 m.s.n.m. Es una zona
agrícola andina donde el cultivo de papa nativa es la principal actividad económica.

SENAMHI mantiene la estación meteorológica **Huangascar (MET PE)** en esta zona,
confirmando la disponibilidad de datos climáticos históricos para la región.
