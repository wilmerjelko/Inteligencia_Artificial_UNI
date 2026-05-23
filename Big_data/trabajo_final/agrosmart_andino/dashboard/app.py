"""
AgroSmart Andino 🌱 Dashboard Streamlit
=======================================
Panel de monitoreo en tiempo real para el cultivo de papa nativa
en Huangascar, Yauyos, Lima.

Lee los CSVs Gold generados por el pipeline PySpark en EMR.

Uso:
    streamlit run dashboard/app.py

Datos esperados en data/gold/:
    lecturas_climaticas.csv
    alertas_activas.csv
    recomendaciones_riego.csv
    predicciones_rendimiento.csv
"""

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime, timedelta, date

# ═══════════════════════════════════════════════════════
# CONFIGURACIÓN DE PÁGINA
# ═══════════════════════════════════════════════════════

st.set_page_config(
    page_title="AgroSmart Andino 🌱 Dashboard",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent.parent
GOLD_DIR = BASE_DIR / "data" / "gold"

# Paleta de colores AgroSmart
COLORS = {
    "verde":    "#2D6A4F",
    "verde_cl": "#52B788",
    "amarillo": "#F4A261",
    "rojo":     "#D62828",
    "azul":     "#3A86FF",
    "gris":     "#6C757D",
    "bg":       "#F8F9FA",
}

NIVEL_COLOR = {0: "#28A745", 1: "#FFC107", 2: "#FF6B35", 3: "#DC3545"}
NIVEL_LABEL = {0: "NORMAL", 1: "ALERTA", 2: "CRÍTICO", 3: "EMERGENCIA"}
NIVEL_ICON  = {0: "✅", 1: "⚠️", 2: "🔴", 3: "🚨"}

NODO_INFO = {
    "NODO-001": {"parcela": "Parcela Baja",  "altitud": 3000, "icon": "🏔️"},
    "NODO-002": {"parcela": "Parcela Media", "altitud": 3200, "icon": "🏔️"},
    "NODO-003": {"parcela": "Parcela Alta",  "altitud": 3500, "icon": "🏔️"},
}

# ═══════════════════════════════════════════════════════
# CARGA DE DATOS
# ═══════════════════════════════════════════════════════

@st.cache_data(ttl=300)   # Refresca cada 5 minutos
def cargar_datos():
    """Carga todos los CSVs Gold con manejo de errores."""
    dfs = {}

    def leer(nombre):
        path = GOLD_DIR / f"{nombre}.csv"
        if path.exists():
            df = pd.read_csv(path)
            # Convertir columnas de fecha
            for col in df.columns:
                if "fecha" in col.lower() and df[col].dtype == object:
                    df[col] = pd.to_datetime(df[col], errors="coerce")
            return df
        return pd.DataFrame()

    dfs["clima"]   = leer("lecturas_climaticas")
    dfs["alertas"] = leer("alertas_activas")
    dfs["riego"]   = leer("recomendaciones_riego")
    dfs["pred"]    = leer("predicciones_rendimiento")

    return dfs


def estado_actual_nodo(df_alertas: pd.DataFrame, df_riego: pd.DataFrame, nodo_id: str) -> dict:
    """Extrae el estado más reciente de un nodo."""
    estado = {
        "nivel": 0,
        "tipo_alerta": "NORMAL",
        "recomendacion": "NORMAL",
        "humedad_suelo": 55.0,
        "temp_min": 8.0,
        "et0": 3.2,
        "deficit": 0.0,
        "horas_riego": 0,
    }
    # Última alerta
    if not df_alertas.empty and "nodo_id" in df_alertas.columns:
        nodo_a = df_alertas[df_alertas["nodo_id"] == nodo_id].sort_values("fecha", ascending=False)
        if not nodo_a.empty:
            row = nodo_a.iloc[0]
            estado["nivel"]      = int(row.get("nivel_alerta", 0) or 0)
            estado["tipo_alerta"] = str(row.get("tipo_alerta", "NORMAL"))
            estado["humedad_suelo"] = float(row.get("humedad_suelo_media", 55) or 55)
            estado["temp_min"]   = float(row.get("temp_min_c", 8) or 8)
    # Última recomendación
    if not df_riego.empty and "nodo_id" in df_riego.columns:
        nodo_r = df_riego[df_riego["nodo_id"] == nodo_id].sort_values("fecha", ascending=False)
        if not nodo_r.empty:
            row = nodo_r.iloc[0]
            estado["recomendacion"] = str(row.get("recomendacion", "NORMAL"))
            estado["et0"]    = float(row.get("et0_mm", 3.2) or 3.2)
            estado["deficit"] = float(row.get("deficit_hidrico_mm", 0) or 0)
            estado["horas_riego"] = int(row.get("horas_riego", 0) or 0)
    return estado


# ═══════════════════════════════════════════════════════
# COMPONENTES UI
# ═══════════════════════════════════════════════════════

def semaforo_html(nivel: int, label: str = "") -> str:
    """Genera un semáforo HTML de 3 luces."""
    colores = {
        0: ("#28A745", "#ccc",    "#ccc"),
        1: ("#ccc",    "#FFC107", "#ccc"),
        2: ("#ccc",    "#ccc",    "#DC3545"),
        3: ("#ccc",    "#ccc",    "#DC3545"),
    }
    c = colores.get(nivel, ("#ccc", "#ccc", "#ccc"))
    return f"""
    <div style="display:flex;flex-direction:column;align-items:center;gap:2px;">
        <div style="width:28px;height:28px;border-radius:50%;background:{c[0]};
                    box-shadow:{'0 0 10px ' + c[0] if c[0] != '#ccc' else 'none'};
                    border:1px solid #aaa;"></div>
        <div style="width:28px;height:28px;border-radius:50%;background:{c[1]};
                    box-shadow:{'0 0 10px ' + c[1] if c[1] != '#ccc' else 'none'};
                    border:1px solid #aaa;"></div>
        <div style="width:28px;height:28px;border-radius:50%;background:{c[2]};
                    box-shadow:{'0 0 10px ' + c[2] if c[2] != '#ccc' else 'none'};
                    border:1px solid #aaa;"></div>
        <div style="font-size:10px;color:#555;text-align:center;margin-top:4px;">{label}</div>
    </div>
    """


def metrica_card(titulo: str, valor: str, unidad: str = "",
                 color: str = COLORS["verde"], delta: str = "") -> None:
    """Muestra una métrica estilizada."""
    st.markdown(f"""
    <div style="background:white;padding:12px 16px;border-radius:10px;
                border-left:4px solid {color};box-shadow:0 1px 4px rgba(0,0,0,0.08);">
        <div style="font-size:11px;color:#888;font-weight:600;text-transform:uppercase;
                    letter-spacing:0.5px;">{titulo}</div>
        <div style="font-size:24px;font-weight:700;color:{color};">{valor}
            <span style="font-size:13px;font-weight:400;color:#666;">{unidad}</span>
        </div>
        {"<div style='font-size:11px;color:#888;'>"+delta+"</div>" if delta else ""}
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════
# GRÁFICOS
# ═══════════════════════════════════════════════════════

def grafico_temperatura_7dias(df_clima: pd.DataFrame) -> go.Figure:
    """Línea de temperatura máx/mín últimos 7 días."""
    if df_clima.empty:
        return go.Figure()

    df = df_clima.sort_values("fecha").tail(7).copy()
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["temp_max_c"],
        name="T. Máxima", mode="lines+markers",
        line=dict(color="#FF6B35", width=2),
        marker=dict(size=6),
    ))
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["temp_media_c"],
        name="T. Media", mode="lines+markers",
        line=dict(color="#F4A261", width=2, dash="dot"),
        marker=dict(size=5),
    ))
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["temp_min_c"],
        name="T. Mínima", mode="lines+markers",
        line=dict(color="#3A86FF", width=2),
        marker=dict(size=6),
    ))
    fig.add_hrect(y0=-10, y1=2, fillcolor="#3A86FF", opacity=0.08,
                  annotation_text="Zona helada (<2°C)",
                  annotation_position="bottom right",
                  annotation=dict(font_size=10, font_color="#3A86FF"))

    fig.update_layout(
        title="🌡️ Temperatura — Últimos 7 días (Huangascar)",
        xaxis_title="Fecha",
        yaxis_title="Temperatura (°C)",
        height=300,
        margin=dict(l=40, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.25),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0")
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


def grafico_precipitacion_30dias(df_clima: pd.DataFrame) -> go.Figure:
    """Barras de precipitación últimos 30 días."""
    if df_clima.empty:
        return go.Figure()

    df = df_clima.sort_values("fecha").tail(30).copy()
    colores = ["#3A86FF" if v > 5 else "#90CAF9" for v in df["precipitacion_mm"]]

    fig = go.Figure(go.Bar(
        x=df["fecha"], y=df["precipitacion_mm"],
        marker_color=colores,
        name="Precipitación",
        hovertemplate="<b>%{x}</b><br>Precip: %{y:.1f} mm<extra></extra>",
    ))
    fig.update_layout(
        title="🌧️ Precipitación — Últimos 30 días (Huangascar)",
        xaxis_title="Fecha",
        yaxis_title="Precipitación (mm)",
        height=280,
        margin=dict(l=40, r=20, t=40, b=40),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
    return fig


def grafico_humedad_suelo_nodo(df_riego: pd.DataFrame, nodo_id: str) -> go.Figure:
    """Serie temporal de humedad del suelo para un nodo."""
    if df_riego.empty or "nodo_id" not in df_riego.columns:
        return go.Figure()

    df = df_riego[df_riego["nodo_id"] == nodo_id].sort_values("fecha").tail(30).copy()
    if df.empty:
        return go.Figure()

    fig = go.Figure()
    fig.add_hrect(y0=0, y1=25, fillcolor="#FF6B35", opacity=0.1,
                  annotation_text="Estrés hídrico", annotation_position="top left",
                  annotation=dict(font_size=10))
    fig.add_hrect(y0=70, y1=100, fillcolor="#3A86FF", opacity=0.1,
                  annotation_text="Exceso de agua", annotation_position="bottom left",
                  annotation=dict(font_size=10))
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["humedad_suelo_pct"],
        mode="lines+markers",
        line=dict(color=COLORS["verde"], width=2),
        marker=dict(size=5),
        fill="tozeroy", fillcolor="rgba(45,106,79,0.1)",
        name="Humedad suelo (%)",
    ))
    fig.update_layout(
        title=f"💧 Humedad del suelo — {nodo_id}",
        yaxis_title="Humedad (%)", xaxis_title="Fecha",
        height=250,
        margin=dict(l=40, r=20, t=40, b=40),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False,
    )
    fig.update_yaxes(range=[0, 100], showgrid=True, gridcolor="#f0f0f0")
    return fig


def grafico_indices_tizon(df_alertas: pd.DataFrame) -> go.Figure:
    """Mapa de calor de riesgo de tizón tardío por nodo."""
    if df_alertas.empty or "nodo_id" not in df_alertas.columns:
        return go.Figure()

    df = df_alertas.copy()
    df["semana"] = pd.to_datetime(df["fecha"]).dt.to_period("W").dt.start_time
    pivot = (
        df.groupby(["nodo_id", "semana"])["itt"]
        .max().unstack(level=0).fillna(0)
    )
    if pivot.empty:
        return go.Figure()

    fig = go.Figure(go.Heatmap(
        z=pivot.values.T,
        x=pivot.index.astype(str),
        y=pivot.columns.tolist(),
        colorscale=[[0, "#28A745"], [0.33, "#FFC107"],
                    [0.66, "#FF6B35"], [1, "#DC3545"]],
        zmin=0, zmax=3,
        colorbar=dict(title="ITT", tickvals=[0,1,2,3],
                      ticktext=["Normal","Leve","Alto","Crítico"]),
        hovertemplate="Semana: %{x}<br>Nodo: %{y}<br>ITT: %{z}<extra></extra>",
    ))
    fig.update_layout(
        title="🍂 Riesgo Tizón Tardío por nodo (semanal)",
        height=200,
        margin=dict(l=40, r=80, t=40, b=60),
        paper_bgcolor="white",
    )
    return fig


def grafico_prediccion_rendimiento(df_pred: pd.DataFrame) -> go.Figure:
    """Gauge + barras de predicción de rendimiento 2025."""
    if df_pred.empty:
        return go.Figure()

    df = df_pred.copy()
    if "rendimiento_pred_tm_ha" not in df.columns:
        return go.Figure()

    # Promedio escenario normal
    pred_normal = df[df.get("evento_climatico", pd.Series(["normal"])) == "normal"][
        "rendimiento_pred_tm_ha"
    ].mean() if "evento_climatico" in df.columns else df["rendimiento_pred_tm_ha"].mean()

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.45, 0.55],
        specs=[[{"type": "indicator"}, {"type": "bar"}]],
    )

    # Gauge
    fig.add_trace(go.Indicator(
        mode="gauge+number+delta",
        value=round(float(pred_normal), 2),
        delta={"reference": 8.5, "valueformat": ".2f",
               "increasing": {"color": "#28A745"},
               "decreasing": {"color": "#DC3545"}},
        gauge={
            "axis": {"range": [0, 15]},
            "bar":  {"color": COLORS["verde"]},
            "steps": [
                {"range": [0, 5],   "color": "#FFEBEE"},
                {"range": [5, 8],   "color": "#FFF9C4"},
                {"range": [8, 12],  "color": "#E8F5E9"},
                {"range": [12, 15], "color": "#C8E6C9"},
            ],
            "threshold": {
                "line": {"color": COLORS["rojo"], "width": 3},
                "thickness": 0.8,
                "value": 6.5,
            },
        },
        title={"text": "Rendimiento Predicho 2025<br><span style='font-size:12px;color:gray'>t/ha (escenario normal)</span>"},
    ), row=1, col=1)

    # Barras por variedad
    if "variedad" in df.columns:
        df_v = df.groupby("variedad")["rendimiento_pred_tm_ha"].mean().reset_index()
        df_v = df_v.sort_values("rendimiento_pred_tm_ha", ascending=True)
        bar_colors = ["#D62828" if v < 7 else "#F4A261" if v < 9 else "#2D6A4F"
                      for v in df_v["rendimiento_pred_tm_ha"]]
        fig.add_trace(go.Bar(
            y=df_v["variedad"],
            x=df_v["rendimiento_pred_tm_ha"],
            orientation="h",
            marker_color=bar_colors,
            text=[f"{v:.2f} t/ha" for v in df_v["rendimiento_pred_tm_ha"]],
            textposition="outside",
            name="Rendimiento",
            hovertemplate="%{y}: <b>%{x:.2f} t/ha</b><extra></extra>",
        ), row=1, col=2)

    fig.update_layout(
        title="🤖 Predicción de Rendimiento de Papa Nativa — Campaña 2025",
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="white",
        showlegend=False,
    )
    fig.update_xaxes(title_text="Rendimiento (t/ha)", row=1, col=2,
                     range=[0, 16], showgrid=True, gridcolor="#f0f0f0")
    return fig


def grafico_tendencia_anual(df_clima: pd.DataFrame) -> go.Figure:
    """Temperatura media y precipitación anual histórica."""
    if df_clima.empty:
        return go.Figure()

    df = df_clima.copy()
    df["anio"] = pd.to_datetime(df["fecha"]).dt.year
    df_a = df.groupby("anio").agg(
        temp_media=("temp_media_c", "mean"),
        precip_total=("precipitacion_mm", "sum"),
        dias_helada=("riesgo_helada", "sum"),
    ).reset_index()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df_a["anio"], y=df_a["precip_total"],
        name="Precipitación anual (mm)",
        marker_color="#90CAF9", opacity=0.7,
        hovertemplate="<b>%{x}</b><br>Precip: %{y:.0f} mm<extra></extra>",
    ), secondary_y=True)
    fig.add_trace(go.Scatter(
        x=df_a["anio"], y=df_a["temp_media"],
        mode="lines+markers", name="T. Media (°C)",
        line=dict(color="#FF6B35", width=2.5),
        marker=dict(size=7),
        hovertemplate="<b>%{x}</b><br>T.media: %{y:.1f}°C<extra></extra>",
    ), secondary_y=False)

    fig.update_layout(
        title="📈 Tendencia Climática Histórica — Huangascar (2015-2024)",
        height=300,
        margin=dict(l=40, r=40, t=40, b=40),
        legend=dict(orientation="h", y=-0.25),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Temperatura (°C)", secondary_y=False,
                     showgrid=True, gridcolor="#f0f0f0")
    fig.update_yaxes(title_text="Precipitación (mm)", secondary_y=True, showgrid=False)
    return fig


# ═══════════════════════════════════════════════════════
# LAYOUT PRINCIPAL
# ═══════════════════════════════════════════════════════

def main():
    # ── Header ──────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1B4332,#2D6A4F);
                padding:20px 24px;border-radius:12px;margin-bottom:20px;">
        <h1 style="color:white;margin:0;font-size:26px;font-weight:700;">
            🌱 AgroSmart Andino
        </h1>
        <p style="color:#B7E4C7;margin:4px 0 0;font-size:14px;">
            Pipeline Big Data · Monitoreo de Papa Nativa · Huangascar, Yauyos, Lima
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ──────────────────────────────────────────────────────
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Flag_of_Peru.svg/240px-Flag_of_Peru.svg.png",
                 width=80)
        st.markdown("### ⚙️ Configuración")
        nodo_sel = st.selectbox(
            "Nodo seleccionado",
            options=list(NODO_INFO.keys()),
            format_func=lambda x: f"{x} — {NODO_INFO[x]['parcela']} ({NODO_INFO[x]['altitud']}m)",
        )
        dias_hist = st.slider("Días histórico", min_value=7, max_value=90, value=30, step=7)

        st.markdown("---")
        st.markdown("**Datos**")
        if st.button("🔄 Recargar datos"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown("**Proyecto**")
        st.markdown("""
        **Curso:** Big Data  
        **Maestría IA — UNI**  
        **Grupo 2**  
        Anahys Montes  
        Christian Vizcardo  
        Cristhian Massa  
        Freddy Huali  
        Wilmer Lazaro  
        """)

    # ── Cargar datos ─────────────────────────────────────────────────
    dfs = cargar_datos()
    df_clima   = dfs["clima"]
    df_alertas = dfs["alertas"]
    df_riego   = dfs["riego"]
    df_pred    = dfs["pred"]

    datos_ok = not df_clima.empty
    if not datos_ok:
        st.warning("⚠️ No se encontraron datos en `data/gold/`. Ejecuta primero el pipeline PySpark en EMR.")
        st.info("""
        **Pasos para generar los datos:**
        1. Sube los CSVs a S3: `python scripts/aws/05_upload_to_s3.py`
        2. Crea el clúster EMR: `python scripts/aws/06_create_emr_cluster.py`
        3. Ejecuta el notebook: `notebooks/agrosmart_pipeline.ipynb`
        4. Descarga los CSVs Gold a `data/gold/`
        """)
        st.stop()

    estado = estado_actual_nodo(df_alertas, df_riego, nodo_sel)

    # ── Fila 1: KPIs estado actual ───────────────────────────────────
    st.markdown("#### Estado Actual del Sistema")
    col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2])

    with col1:
        st.markdown(semaforo_html(estado["nivel"],
                    NIVEL_LABEL[estado["nivel"]]), unsafe_allow_html=True)

    with col2:
        color_nivel = NIVEL_COLOR[estado["nivel"]]
        metrica_card(
            "Nivel de Alerta",
            f"{NIVEL_ICON[estado['nivel']]} {NIVEL_LABEL[estado['nivel']]}",
            color=color_nivel,
        )

    with col3:
        info_nodo = NODO_INFO[nodo_sel]
        metrica_card(
            f"{nodo_sel} — {info_nodo['parcela']}",
            f"{info_nodo['icon']} {info_nodo['altitud']}",
            unidad="m.s.n.m.",
            color=COLORS["verde"],
        )

    with col4:
        hum_color = COLORS["rojo"] if estado["humedad_suelo"] < 25 else \
                    COLORS["azul"] if estado["humedad_suelo"] > 70 else COLORS["verde"]
        metrica_card("Humedad del Suelo",
                     f"{estado['humedad_suelo']:.1f}", unidad="%",
                     color=hum_color)

    with col5:
        riego_color = COLORS["rojo"] if "URGENTE" in estado["recomendacion"] else \
                      COLORS["amarillo"] if "RECOMENDADO" in estado["recomendacion"] else \
                      COLORS["azul"] if "SUSPENDER" in estado["recomendacion"] else COLORS["verde"]
        riego_icon = {"RIEGO_URGENTE": "🚿", "RIEGO_RECOMENDADO": "💧",
                      "SUSPENDER_RIEGO": "⛔", "NORMAL": "✅"}.get(estado["recomendacion"], "")
        metrica_card("Recomendación Riego",
                     f"{riego_icon} {estado['recomendacion'].replace('_', ' ')}",
                     color=riego_color)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Fila 2: Alertas activas + métricas climáticas ────────────────
    col_a, col_b = st.columns([1, 2])

    with col_a:
        st.markdown("#### 🚨 Alertas Activas")
        if df_alertas.empty:
            st.success("Sin alertas registradas")
        else:
            df_a_nodo = df_alertas[
                df_alertas["nodo_id"] == nodo_sel
            ].sort_values("fecha", ascending=False).head(10)

            if df_a_nodo.empty:
                st.success(f"✅ {nodo_sel} sin alertas recientes")
            else:
                for _, row in df_a_nodo.iterrows():
                    nivel = int(row.get("nivel_alerta", 0) or 0)
                    tipo  = str(row.get("tipo_alerta", "")).replace("_", " ")
                    fecha = str(row.get("fecha", ""))[:10]
                    color = NIVEL_COLOR[nivel]
                    icon  = NIVEL_ICON[nivel]
                    st.markdown(f"""
                    <div style="background:{color}15;border-left:3px solid {color};
                                padding:6px 10px;border-radius:4px;margin-bottom:4px;">
                        <span style="font-weight:600;font-size:12px;">{icon} {tipo}</span>
                        <span style="float:right;font-size:11px;color:#666;">{fecha}</span>
                        <br><span style="font-size:11px;color:#555;">
                        T.min: {row.get('temp_min_c','')}°C  |
                        HR: {row.get('humedad_relativa_pct','')}%
                        </span>
                    </div>
                    """, unsafe_allow_html=True)

    with col_b:
        st.markdown("#### 📊 Métricas Climáticas Recientes")
        if not df_clima.empty:
            df_c = df_clima.sort_values("fecha").tail(dias_hist)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                metrica_card("T. Media", f"{df_c['temp_media_c'].mean():.1f}", "°C",
                             color=COLORS["amarillo"])
            with c2:
                metrica_card("T. Mínima prom.", f"{df_c['temp_min_c'].mean():.1f}", "°C",
                             color=COLORS["azul"])
            with c3:
                metrica_card("Precip. total", f"{df_c['precipitacion_mm'].sum():.1f}", "mm",
                             color=COLORS["azul"])
            with c4:
                dias_helada = int(df_c["riesgo_helada"].sum()) if "riesgo_helada" in df_c.columns else 0
                metrica_card("Días helada", f"{dias_helada}", "días",
                             color=COLORS["rojo"] if dias_helada > 5 else COLORS["verde"])

            # ET y déficit
            c5, c6, c7, _ = st.columns(4)
            with c5:
                metrica_card("ET₀ actual", f"{estado['et0']:.2f}", "mm/día",
                             color=COLORS["verde_cl"])
            with c6:
                metrica_card("Déficit hídrico", f"{estado['deficit']:.2f}", "mm",
                             color=COLORS["rojo"] if estado["deficit"] > 3 else COLORS["verde"])
            with c7:
                metrica_card("Horas de riego hoy", f"{estado['horas_riego']}", "h",
                             color=COLORS["verde"])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Fila 3: Gráficos principales ─────────────────────────────────
    st.markdown("#### 📉 Series Temporales")
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        fig_temp = grafico_temperatura_7dias(df_clima)
        st.plotly_chart(fig_temp, width='stretch')

    with col_g2:
        fig_precip = grafico_precipitacion_30dias(df_clima.tail(dias_hist))
        st.plotly_chart(fig_precip, width='stretch')

    # ── Fila 4: Humedad suelo + Tizón tardío ─────────────────────────
    col_h1, col_h2 = st.columns(2)

    with col_h1:
        fig_hum = grafico_humedad_suelo_nodo(df_riego, nodo_sel)
        st.plotly_chart(fig_hum, width='stretch')

    with col_h2:
        fig_tizon = grafico_indices_tizon(df_alertas)
        if fig_tizon.data:
            st.plotly_chart(fig_tizon, width='stretch')
        else:
            st.info("Sin datos de índice de tizón tardío disponibles")

    # ── Fila 5: Predicciones + Tendencia histórica ───────────────────
    st.markdown("#### 🤖 Predicciones Machine Learning")
    fig_pred = grafico_prediccion_rendimiento(df_pred)
    st.plotly_chart(fig_pred, width='stretch')

    st.markdown("#### 🌡️ Tendencia Climática Histórica")
    fig_hist = grafico_tendencia_anual(df_clima)
    st.plotly_chart(fig_hist, width='stretch')

    # ── Fila 6: Tabla de recomendaciones ─────────────────────────────
    st.markdown("#### 💧 Recomendaciones de Riego (Últimos días)")
    if not df_riego.empty:
        df_r_show = (
            df_riego[df_riego["nodo_id"] == nodo_sel]
            .sort_values("fecha", ascending=False)
            .head(14)
            [["fecha", "nodo_id", "humedad_suelo_pct", "et0_mm",
              "precipitacion_mm", "deficit_hidrico_mm", "recomendacion", "horas_riego"]]
            .rename(columns={
                "fecha": "Fecha",
                "nodo_id": "Nodo",
                "humedad_suelo_pct": "Humedad suelo (%)",
                "et0_mm": "ET (mm)",
                "precipitacion_mm": "Precip. (mm)",
                "deficit_hidrico_mm": "Déficit (mm)",
                "recomendacion": "Recomendación",
                "horas_riego": "H. riego",
            })
        )

        def colorear_recomendacion(val):
            colors_map = {
                "RIEGO_URGENTE":     "background-color:#FFEBEE;color:#C62828;font-weight:600",
                "RIEGO_RECOMENDADO": "background-color:#FFF8E1;color:#F57F17;font-weight:600",
                "SUSPENDER_RIEGO":   "background-color:#E3F2FD;color:#1565C0;font-weight:600",
                "NORMAL":            "background-color:#E8F5E9;color:#2E7D32",
            }
            return colors_map.get(str(val), "")

        df_r_show["Fecha"] = df_r_show["Fecha"].astype(str).str[:10]
        st.dataframe(
            df_r_show.style.map(colorear_recomendacion, subset=["Recomendación"]),
            width='stretch',
            hide_index=True,
        )

    # ── Footer ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"""
    <div style="text-align:center;color:#888;font-size:12px;padding:8px;">
        AgroSmart Andino · Pipeline Big Data · Maestría en IA — UNI · Grupo 2 ·
        Datos actualizados: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
