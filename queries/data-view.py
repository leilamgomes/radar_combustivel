import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import plotly.io._json as plotly_json
import streamlit as st
from dotenv import load_dotenv
from redis import Redis

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.event_transformer import (
    COMBUSTIVEIS,
    city_region_name,
    fuel_field_name,
    neighborhood_region_name,
    parse_variation_member,
    region_price_key,
    station_key,
)

load_dotenv(".env.local")
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def force_plotly_json_engine() -> None:
    # Força o Plotly a usar o serializador padrão do Python para evitar conflitos com orjson.
    pio.json.config.default_engine = "json"
    original_to_json_plotly = plotly_json.to_json_plotly

    def safe_to_json_plotly(plotly_object, pretty: bool = False, engine=None):
        safe_engine = "json" if engine in (None, "auto", "orjson") else engine
        return original_to_json_plotly(plotly_object, pretty=pretty, engine=safe_engine)

    plotly_json.to_json_plotly = safe_to_json_plotly


force_plotly_json_engine()
warnings.filterwarnings(
    "ignore",
    message=r"When grouping with a length-1 list-like, you will need to pass a length-1 tuple to get_group in a future version of pandas\.",
    category=FutureWarning,
)

COLOR_PRIMARY = "#0F766E"
COLOR_PRIMARY_SOFT = "#14B8A6"
COLOR_ACCENT = "#5EEAD4"
COLOR_TEXT = "#16302B"
COLOR_MUTED = "#5C7C76"
CHART_SEQUENCE = ["#0F766E", "#14B8A6", "#2DD4BF", "#5EEAD4", "#99F6E4"]


def get_redis() -> Redis:
    # Conexão principal para leitura das estruturas no Redis.
    return Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def apply_chart_theme(fig, title: str | None = None):
    # Padroniza o visual dos gráficos para uma linguagem única e mais clean.
    layout_updates = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Trebuchet MS, Segoe UI, sans-serif", "color": COLOR_TEXT},
        "title_font": {"size": 18, "color": COLOR_TEXT},
        "margin": {"l": 12, "r": 12, "t": 56, "b": 12},
    }
    if title is not None:
        layout_updates["title"] = title
    fig.update_layout(**layout_updates)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(15,118,110,0.12)", zeroline=False)
    fig.update_yaxes(showgrid=False, zeroline=False)
    return fig


def inject_page_style() -> None:
    # Aplica um tema visual mais amigável e consistente na página.
    st.markdown(
        f"""
        <style>
            .stApp {{
                background:
                    radial-gradient(circle at top right, rgba(94,234,212,0.16), transparent 26%),
                    linear-gradient(180deg, #f9fffe 0%, #f2fbf9 100%);
            }}
            .block-container {{
                padding-top: 1.5rem;
                padding-bottom: 2rem;
                max-width: 1240px;
            }}
            div[data-testid="stMetric"] {{
                background: rgba(255,255,255,0.92);
                border: 1px solid rgba(15,118,110,0.12);
                border-radius: 18px;
                padding: 0.8rem 1rem;
                box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
            }}
            div[data-testid="stMetricLabel"] {{
                color: {COLOR_MUTED};
                font-weight: 600;
            }}
            div[data-testid="stMetricValue"] {{
                color: {COLOR_TEXT};
            }}
            div[data-baseweb="tab-list"] {{
                gap: 0.5rem;
            }}
            button[data-baseweb="tab"] {{
                border-radius: 999px;
                padding: 0.4rem 0.95rem;
                border: 1px solid rgba(15,118,110,0.10);
                background: rgba(255,255,255,0.75);
            }}
            button[data-baseweb="tab"][aria-selected="true"] {{
                background: linear-gradient(135deg, {COLOR_PRIMARY} 0%, {COLOR_PRIMARY_SOFT} 100%);
                color: white;
                border-color: transparent;
            }}
            .dashboard-hero {{
                padding: 1.2rem 1.35rem;
                border-radius: 24px;
                background: linear-gradient(135deg, rgba(15,118,110,0.96) 0%, rgba(20,184,166,0.92) 100%);
                color: white;
                box-shadow: 0 18px 40px rgba(15, 118, 110, 0.18);
                margin-bottom: 1rem;
            }}
            .dashboard-hero h1 {{
                margin: 0 0 0.2rem 0;
                font-size: 2rem;
                line-height: 1.1;
            }}
            .dashboard-hero p {{
                margin: 0;
                color: rgba(255,255,255,0.88);
                font-size: 1rem;
            }}
            .section-chip {{
                display: inline-block;
                margin-bottom: 0.45rem;
                padding: 0.28rem 0.7rem;
                border-radius: 999px;
                background: rgba(20,184,166,0.12);
                color: {COLOR_PRIMARY};
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.02em;
            }}
            .section-title {{
                margin: 0 0 0.15rem 0;
                color: {COLOR_TEXT};
                font-size: 1.35rem;
                font-weight: 700;
            }}
            .section-copy {{
                margin: 0 0 1rem 0;
                color: {COLOR_MUTED};
                font-size: 0.95rem;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(chip: str, title: str, copy: str) -> None:
    # Renderiza um cabeçalho padrão para as seções do dashboard.
    st.markdown(
        f"""
        <div class="section-chip">{chip}</div>
        <div class="section-title">{title}</div>
        <div class="section-copy">{copy}</div>
        """,
        unsafe_allow_html=True,
    )


def zset_to_df(rows: List[tuple[str, float]], columns: List[str]) -> pd.DataFrame:
    # Converte saídas de ZSET para DataFrame com nomes explícitos.
    return (
        pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)
    )


def extract_uf_from_composed_region(value: str) -> str:
    # Extrai a UF de rótulos compostos como "SP - Cidade" ou "SP - Cidade - Bairro".
    parts = [part.strip() for part in str(value or "").split(" - ") if part.strip()]
    return parts[0] if parts else "UF não informada"


def prettify_fuel_label(value: str) -> str:
    # Ajusta os rótulos de combustível para exibição amigável no dashboard.
    fuel_map = {
        "GASOLINA_COMUM": "GASOLINA COMUM",
        "GASOLINA_ADITIVADA": "GASOLINA ADITIVADA",
        "DIESEL_COMUM": "DIESEL COMUM",
        "DIESEL_S10": "DIESEL S10",
    }
    return fuel_map.get(str(value), str(value))


def fuel_display_options() -> List[str]:
    # Lista de combustíveis pronta para uso nos componentes visuais.
    return [prettify_fuel_label(item) for item in COMBUSTIVEIS]


def fuel_code_from_label(label: str) -> str:
    # Converte o rótulo exibido na tela para o valor original usado no Redis.
    reverse_map = {prettify_fuel_label(raw): raw for raw in COMBUSTIVEIS}
    return reverse_map.get(label, label)


def station_snapshot(redis: Redis, posto_id: str) -> Dict[str, str]:
    # Recupera o hash resumido de um posto.
    return redis.hgetall(station_key(posto_id))


def weighted_rating_score(
    rating_mean: float, rating_count: int, global_mean: float, minimum_votes: int = 5
) -> float:
    # Calcula um score ponderado para evitar que poucas avaliações dominem o ranking.
    votes = max(int(rating_count), 0)
    if votes == 0:
        return 0.0
    return round(
        ((votes / (votes + minimum_votes)) * float(rating_mean))
        + ((minimum_votes / (votes + minimum_votes)) * float(global_mean)),
        3,
    )


def enrich_station_rows(
    redis: Redis, df: pd.DataFrame, id_column: str = "posto_id"
) -> pd.DataFrame:
    # Complementa linhas com nome, cidade, bairro e bandeira a partir do hash do posto.
    if df.empty:
        return df

    snapshots = {
        posto_id: station_snapshot(redis, posto_id)
        for posto_id in df[id_column].tolist()
    }
    df = df.copy()
    df["nome_fantasia"] = df[id_column].map(
        lambda posto_id: snapshots.get(posto_id, {}).get("nome_fantasia", posto_id)
    )
    df["uf"] = df[id_column].map(
        lambda posto_id: snapshots.get(posto_id, {}).get("uf", "-")
    )
    df["cidade"] = df[id_column].map(
        lambda posto_id: snapshots.get(posto_id, {}).get("cidade", "-")
    )
    df["bairro"] = df[id_column].map(
        lambda posto_id: snapshots.get(posto_id, {}).get("bairro", "-")
    )
    df["bandeira"] = df[id_column].map(
        lambda posto_id: snapshots.get(posto_id, {}).get("bandeira", "-")
    )
    df["cnpj"] = df[id_column].map(
        lambda posto_id: snapshots.get(posto_id, {}).get("cnpj", "-")
    )
    df["search_hits"] = df[id_column].map(
        lambda posto_id: int(snapshots.get(posto_id, {}).get("search_hits", 0) or 0)
    )
    df["rating_count"] = df[id_column].map(
        lambda posto_id: int(snapshots.get(posto_id, {}).get("rating_count", 0) or 0)
    )
    return df


def get_total_station_count(redis: Redis) -> int:
    # Conta os hashes dos postos indexados no Redis.
    return len(redis.keys("posto:*"))


def geo_search(redis: Redis, lon: float, lat: float, radius_km: float, limit: int = 20):
    # Busca postos por proximidade usando GEOSEARCH.
    return redis.execute_command(
        "GEOSEARCH",
        "geo:postos",
        "FROMLONLAT",
        lon,
        lat,
        "BYRADIUS",
        radius_km,
        "km",
        "ASC",
        "COUNT",
        limit,
        "WITHDIST",
    )


def nearest_geo_search(
    redis: Redis, lon: float, lat: float, radius_km: float, limit: int = 20
):
    # Expande o raio progressivamente quando não há resultados imediatos.
    search_steps = [radius_km, 5, 10, 25, 50, 100, 250, 500, 1000]
    tried = []
    for step_radius in search_steps:
        normalized_radius = max(float(radius_km), float(step_radius))
        if normalized_radius in tried:
            continue
        tried.append(normalized_radius)
        rows = geo_search(redis, lon, lat, normalized_radius, limit=limit)
        if rows:
            return rows, normalized_radius
    return [], max(tried) if tried else float(radius_km)


def fuel_timeseries(redis: Redis, combustivel: str):
    # Recupera séries agregadas por combustível com média horária.
    return redis.execute_command(
        "TS.MRANGE",
        "-",
        "+",
        "AGGREGATION",
        "avg",
        "3600000",
        "FILTER",
        "metric=price",
        f"combustivel={combustivel.upper()}",
    )


def station_timeseries(redis: Redis, posto_id: str, combustivel: str):
    # Recupera a série histórica de um posto e combustível.
    return redis.execute_command(
        "TS.RANGE",
        f"ts:preco:{posto_id}:{fuel_field_name(combustivel)}",
        "-",
        "+",
        "AGGREGATION",
        "avg",
        "3600000",
    )


def build_fuel_series_df(series_data: Any) -> pd.DataFrame:
    # Transforma o retorno de TS.MRANGE em tabela pronta para gráfico.
    rows: List[Dict[str, Any]] = []
    for key, labels, points in series_data:
        label_map = dict(labels)
        combustivel = label_map.get("combustivel", "N/A")
        for ts, value in points:
            rows.append(
                {
                    "ts": int(ts),
                    "datetime": datetime.fromtimestamp(int(ts) / 1000.0),
                    "valor": float(value),
                    "combustivel": combustivel,
                    "serie": key,
                }
            )
    return pd.DataFrame(rows)


def build_station_options(redis: Redis, combustivel: str, limit: int = 300) -> List[str]:
    # Monta opções estáveis apenas com postos que têm histórico útil para o combustível selecionado.
    ts_pattern = f"ts:preco:*:{fuel_field_name(combustivel)}"
    series_keys = sorted(str(key) for key in redis.scan_iter(ts_pattern))
    options = []
    seen = set()
    for key in series_keys:
        parts = key.split(":")
        if len(parts) < 4:
            continue
        posto_id = parts[2]
        if posto_id in seen:
            continue
        seen.add(posto_id)
        try:
            point_count = len(redis.execute_command("TS.RANGE", key, "-", "+"))
        except Exception:
            point_count = 0
        if point_count < 2:
            continue
        snapshot = station_snapshot(redis, posto_id)
        nome_fantasia = snapshot.get("nome_fantasia", posto_id)
        cidade = snapshot.get("cidade", "-")
        options.append(f"{posto_id} | {nome_fantasia} | {cidade}")
        if len(options) >= limit:
            break
    return sorted(options, key=lambda value: value.split(" | ", 2)[1:])


def build_geo_catalog(redis: Redis, limit: int = 5000) -> pd.DataFrame:
    # Monta um catálogo geográfico para filtros por UF, cidade e bairro.
    rows: List[Dict[str, Any]] = []
    for idx, key in enumerate(redis.scan_iter("posto:*"), start=1):
        if idx > limit:
            break
        snapshot = redis.hgetall(key)
        lat = snapshot.get("lat")
        lon = snapshot.get("lon")
        uf = snapshot.get("uf")
        cidade = snapshot.get("cidade")
        bairro = snapshot.get("bairro")
        if not lat or not lon or not uf or not cidade or not bairro:
            continue
        rows.append(
            {
                "posto_id": key.split(":", 1)[1],
                "nome_fantasia": snapshot.get("nome_fantasia", "Sem nome"),
                "uf": uf,
                "cidade": cidade,
                "bairro": bairro,
                "lat": float(lat),
                "lon": float(lon),
            }
        )
    return pd.DataFrame(rows)


def build_geo_reference_options_from_catalog(catalog_df: pd.DataFrame) -> List[str]:
    # Monta opções de referência usando o catálogo geográfico já carregado.
    if catalog_df.empty:
        return []
    rows = (
        catalog_df.sort_values(["uf", "cidade", "bairro", "nome_fantasia"])
        .head(300)
        .to_dict("records")
    )
    return [
        f"{row['posto_id']} | {row['nome_fantasia']} | {row['cidade']} | {row['bairro']} | {row['lat']} | {row['lon']}"
        for row in rows
    ]


def parse_geo_reference(option: str) -> Dict[str, Any]:
    # Extrai coordenadas e contexto da opção escolhida no seletor de referência.
    posto_id, nome, cidade, bairro, lat, lon = option.split(" | ", 5)
    return {
        "posto_id": posto_id,
        "nome_fantasia": nome,
        "cidade": cidade,
        "bairro": bairro,
        "lat": float(lat),
        "lon": float(lon),
    }


def neighborhood_center(
    catalog_df: pd.DataFrame, uf: str, cidade: str, bairro: str
) -> Dict[str, Any] | None:
    # Calcula o centro aproximado do bairro a partir dos postos disponíveis nessa região.
    if catalog_df.empty:
        return None
    filtered = catalog_df[
        (catalog_df["uf"] == uf)
        & (catalog_df["cidade"] == cidade)
        & (catalog_df["bairro"] == bairro)
    ]
    if filtered.empty:
        return None
    return {
        "uf": uf,
        "cidade": cidade,
        "bairro": bairro,
        "lat": float(filtered["lat"].mean()),
        "lon": float(filtered["lon"].mean()),
        "postos_origem": int(len(filtered)),
    }


def available_price_cities(
    redis: Redis, catalog_df: pd.DataFrame, combustivel: str, uf: str
) -> List[str]:
    # Retorna apenas cidades que realmente possuem ranking de preço para o combustível informado.
    if catalog_df.empty or not uf:
        return []
    city_options = []
    city_df = catalog_df[catalog_df["uf"] == uf]
    for city in sorted(city_df["cidade"].dropna().unique().tolist()):
        key = region_price_key(combustivel, "cidade", city_region_name(uf, city))
        if redis.exists(key):
            city_options.append(city)
    return city_options


def available_price_neighborhoods(
    redis: Redis, catalog_df: pd.DataFrame, combustivel: str, uf: str, cidade: str
) -> List[str]:
    # Retorna apenas bairros que realmente possuem ranking de preço para o combustível informado.
    if catalog_df.empty or not uf or not cidade:
        return []
    neighborhoods = []
    neighborhood_df = catalog_df[
        (catalog_df["uf"] == uf) & (catalog_df["cidade"] == cidade)
    ]
    for bairro in sorted(neighborhood_df["bairro"].dropna().unique().tolist()):
        key = region_price_key(
            combustivel, "bairro", neighborhood_region_name(uf, cidade, bairro)
        )
        if redis.exists(key):
            neighborhoods.append(bairro)
    return neighborhoods


def state_price_ranking(
    redis: Redis, catalog_df: pd.DataFrame, combustivel: str, uf: str, limit: int = 10
) -> pd.DataFrame:
    # Monta um ranking estadual usando os preços atuais já materializados no hash dos postos.
    if catalog_df.empty or not uf:
        return pd.DataFrame(columns=["posto_id", "preco"])

    fuel_field = f"preco_{fuel_field_name(combustivel)}"
    candidates = catalog_df[catalog_df["uf"] == uf]["posto_id"].dropna().unique().tolist()
    rows = []
    for posto_id in candidates:
        snapshot = station_snapshot(redis, posto_id)
        price_value = snapshot.get(fuel_field)
        if price_value in (None, "", "0", 0):
            continue
        try:
            price_float = float(price_value)
        except (TypeError, ValueError):
            continue
        if price_float <= 0:
            continue
        rows.append({"posto_id": posto_id, "preco": price_float})

    if not rows:
        return pd.DataFrame(columns=["posto_id", "preco"])

    return pd.DataFrame(rows).sort_values("preco", ascending=True).head(limit)


def proximity_rows_from_geo(
    redis: Redis, geo_rows: List[List[Any]]
) -> List[Dict[str, Any]]:
    # Converte o retorno do GEOSEARCH em linhas amigáveis para tabela e mapa.
    rows = []
    for posto_id, distance in geo_rows:
        snapshot = station_snapshot(redis, posto_id)
        rows.append(
            {
                "posto_id": posto_id,
                "nome_fantasia": snapshot.get("nome_fantasia", posto_id),
                "bandeira": snapshot.get("bandeira", "-"),
                "cidade": snapshot.get("cidade", "-"),
                "bairro": snapshot.get("bairro", "-"),
                "distancia_km": round(float(distance), 2),
                "lat": float(snapshot.get("lat", 0) or 0),
                "lon": float(snapshot.get("lon", 0) or 0),
            }
        )
    return rows


def variation_direction_label(direction: str) -> str:
    # Traduz a direção da variação para um rótulo mais visual.
    normalized = str(direction or "").strip()
    if normalized in {"⬆️", "↑", "up"}:
        return "⬆️"
    if normalized in {"⬇️", "↓", "down"}:
        return "⬇️"
    return "➡️"


def variation_row_style(row: pd.Series) -> List[str]:
    # Destaca a linha inteira conforme a direção da variação de preço.
    direction = str(row.get("Tendência", row.get("direcao", "")))
    if "⬆️" in direction:
        color = "rgba(239, 68, 68, 0.14)"
    elif "⬇️" in direction:
        color = "rgba(34, 197, 94, 0.14)"
    else:
        color = "rgba(250, 204, 21, 0.16)"
    return [f"background-color: {color}"] * len(row)


st.set_page_config(page_title="Radar Combustível | Dashboard", layout="wide")
inject_page_style()
st.markdown(
    """
    <div class="dashboard-hero">
        <h1>⛽ Plataforma Radar Combustível</h1>
        <p>Visualização em tempo real das estruturas alimentadas pelo consumidor MongoDB -> Redis.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

auto_refresh = st.sidebar.toggle("Atualização automática", value=True)
refresh_seconds = st.sidebar.number_input(
    "Intervalo (segundos)", min_value=3, max_value=60, value=10, step=1
)

redis = get_redis()
geo_catalog = build_geo_catalog(redis)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Visão Geral",
        "Top Avaliações",
        "Ranking de Preço",
        "Variação de Preço",
        "Séries Temporais",
        "Proximidade",
    ]
)

with tab1:
    render_section_header(
        "📊 Visão geral",
        "Indicadores principais",
        "Um resumo rápido para entender volume, alcance e saúde da operação.",
    )
    c1, c2, c3, c4 = st.columns(4)
    total_postos = get_total_station_count(redis)
    fuel_rows = redis.zrevrange("ranking:combustiveis:buscas", 0, -1, withscores=True)
    total_search_volume = sum(int(score) for _, score in fuel_rows)
    avg_rating_rows = redis.zrevrange(
        "ranking:postos:avaliacao", 0, -1, withscores=True
    )
    avg_top_rating = (
        round(
            sum(score for _, score in avg_rating_rows[:10])
            / max(len(avg_rating_rows[:10]), 1),
            2,
        )
        if avg_rating_rows
        else 0.0
    )
    geo_count = redis.zcard("geo:postos")

    c1.metric("Postos indexados", f"{total_postos:,}".replace(",", "."))
    c2.metric("Volume de buscas", f"{total_search_volume:,}".replace(",", "."))
    c3.metric("Postos no GEO", f"{geo_count:,}".replace(",", "."))
    c4.metric("Média do top 10 em avaliações", f"{avg_top_rating:.2f}")

    render_section_header(
        "🔥 Tendências",
        "Combustíveis em alta",
        "Veja quais combustíveis têm maior volume de buscas no momento.",
    )
    df_fuels = zset_to_df(
        redis.zrevrange("ranking:combustiveis:buscas", 0, 5, withscores=True),
        ["combustivel", "buscas"],
    )
    if df_fuels.empty:
        st.info("Sem dados ainda em `ranking:combustiveis:buscas`.")
    else:
        df_fuels["combustivel"] = df_fuels["combustivel"].apply(prettify_fuel_label)
        df_fuels["buscas"] = df_fuels["buscas"].astype(int)
        fig = px.bar(
            df_fuels.sort_values("buscas", ascending=True),
            x="buscas",
            y="combustivel",
            orientation="h",
            color="buscas",
            color_continuous_scale="Tealgrn",
            title="Combustíveis mais buscados",
        )
        apply_chart_theme(fig)
        st.plotly_chart(fig, width="stretch")

    render_section_header(
        "🔎 Territórios",
        "Territórios com maior demanda",
        "Recortes regionais para entender o volume de buscas por UF, Cidade e Bairro",
    )
    col_uf, col_cidades = st.columns(2)

    with col_uf:
        df_ufs = zset_to_df(
            redis.zrevrange("ranking:cidades:buscas", 0, 499, withscores=True),
            ["cidade_composta", "buscas"],
        )
        if df_ufs.empty:
            st.info("Sem volume de buscas por UF.")
        else:
            df_ufs["uf"] = df_ufs["cidade_composta"].apply(
                extract_uf_from_composed_region
            )
            df_ufs["buscas"] = df_ufs["buscas"].astype(int)
            df_ufs = (
                df_ufs.groupby("uf", as_index=False)["buscas"]
                .sum()
                .sort_values("buscas", ascending=False)
                .head(10)
            )
            fig = px.bar(
                df_ufs.sort_values("buscas", ascending=True),
                x="buscas",
                y="uf",
                orientation="h",
                color="buscas",
                color_continuous_scale="Tealgrn",
                title="UFs mais buscadas",
            )
            apply_chart_theme(fig)
            st.plotly_chart(fig, width="stretch")

    with col_cidades:
        df_cidades = zset_to_df(
            redis.zrevrange("ranking:cidades:buscas", 0, 199, withscores=True),
            ["cidade", "buscas"],
        )
        if not df_cidades.empty:
            df_cidades = df_cidades.head(10)
        if df_cidades.empty:
            st.info("Sem volume de buscas por cidade.")
        else:
            df_cidades["buscas"] = df_cidades["buscas"].astype(int)
            fig = px.bar(
                df_cidades.sort_values("buscas", ascending=True),
                x="buscas",
                y="cidade",
                orientation="h",
                color="buscas",
                color_continuous_scale="Tealgrn",
                title="UF - Cidade",
            )
            apply_chart_theme(fig)
            st.plotly_chart(fig, width="stretch")

    st.divider()

    with st.container():
        df_bairros = zset_to_df(
            redis.zrevrange("ranking:bairros:buscas", 0, 999, withscores=True),
            ["bairro", "buscas"],
        )
        if not df_bairros.empty:
            df_bairros = df_bairros[
                ~df_bairros["bairro"].str.contains(
                    "Bairro nao informado|Bairro não informado", na=False
                )
            ].head(10)
        if df_bairros.empty:
            st.info("Sem volume de buscas por bairro.")
        else:
            df_bairros["buscas"] = df_bairros["buscas"].astype(int)
            fig = px.bar(
                df_bairros.sort_values("buscas", ascending=True),
                x="buscas",
                y="bairro",
                orientation="h",
                color="buscas",
                color_continuous_scale="Tealgrn",
                title="UF - Cidade - Bairro",
            )
            apply_chart_theme(fig)
            st.plotly_chart(fig, width="stretch")

with tab3:
    render_section_header(
        "🏷️ Preços",
        "Ranking de preço por região",
        "Compare os postos mais baratos por combustível dentro da região escolhida.",
    )

    price_cols = st.columns(4)
    with price_cols[0]:
        ranking_fuel_label = st.selectbox(
            "Combustível", fuel_display_options(), index=0, key="ranking_fuel"
        )
        ranking_fuel = fuel_code_from_label(ranking_fuel_label)
    with price_cols[1]:
        uf_options = []
        if not geo_catalog.empty:
            for uf in sorted(geo_catalog["uf"].dropna().unique().tolist()):
                if available_price_cities(redis, geo_catalog, ranking_fuel, uf):
                    uf_options.append(uf)
        selected_uf = st.selectbox(
            "UF", uf_options, index=0 if uf_options else None, key="ranking_uf"
        )
    with price_cols[2]:
        city_options = (
            available_price_cities(redis, geo_catalog, ranking_fuel, selected_uf)
            if selected_uf
            else []
        )
        selected_city = st.selectbox(
            "Cidade",
            [""] + city_options,
            index=0,
            key="ranking_city",
        )
    with price_cols[3]:
        neighborhood_options = (
            available_price_neighborhoods(
                redis, geo_catalog, ranking_fuel, selected_uf, selected_city
            )
            if selected_uf and selected_city
            else []
        )
        selected_neighborhood = st.selectbox(
            "Bairro (opcional)",
            [""] + neighborhood_options,
            index=0,
            key="ranking_neighborhood",
        )

    if not geo_catalog.empty and selected_uf:
        if not selected_city:
            region_label = f"{selected_uf}"
            df_price = state_price_ranking(redis, geo_catalog, ranking_fuel, selected_uf)
            df_price = enrich_station_rows(redis, df_price)
        else:
            region_type = "bairro" if selected_neighborhood else "cidade"
            region_name = (
                neighborhood_region_name(selected_uf, selected_city, selected_neighborhood)
                if selected_neighborhood
                else city_region_name(selected_uf, selected_city)
            )
            region_label = (
                f"{selected_neighborhood}, {selected_city} - {selected_uf}"
                if selected_neighborhood
                else f"{selected_city} - {selected_uf}"
            )
            df_price = zset_to_df(
                redis.zrange(
                    region_price_key(ranking_fuel, region_type, region_name),
                    0,
                    9,
                    withscores=True,
                ),
                ["posto_id", "preco"],
            )
            df_price = enrich_station_rows(redis, df_price)
            if not df_price.empty:
                df_price = df_price[df_price["uf"] == selected_uf]
                df_price = df_price[df_price["cidade"] == selected_city]
                if selected_neighborhood:
                    df_price = df_price[df_price["bairro"] == selected_neighborhood]

        if df_price.empty:
            st.info("Sem ranking de preço para os filtros atuais.")
        else:
            fuel_field = fuel_field_name(ranking_fuel)
            df_price["preco"] = df_price["preco"].astype(float)
            df_price["preco_atualizado_ts"] = df_price["posto_id"].map(
                lambda posto_id: int(
                    station_snapshot(redis, posto_id).get(
                        f"atualizado_preco_{fuel_field}", 0
                    )
                    or 0
                )
            )
            df_price["dedupe_key"] = df_price.apply(
                lambda row: row["cnpj"]
                if str(row.get("cnpj", "-")).strip() not in {"", "-"}
                else row["nome_fantasia"],
                axis=1,
            )
            df_price = (
                df_price.sort_values(
                    ["dedupe_key", "preco_atualizado_ts"], ascending=[True, False]
                )
                .drop_duplicates(subset=["dedupe_key"], keep="first")
                .sort_values("preco", ascending=True)
                .head(10)
            )
            fig = px.bar(
                df_price.sort_values("preco", ascending=False),
                x="preco",
                y="nome_fantasia",
                orientation="h",
                color="preco",
                color_continuous_scale="Tealgrn",
                title=f"Postos com menor preço em {region_label}",
            )
            apply_chart_theme(fig)
            fig.update_xaxes(tickprefix="R$ ")
            fig.update_xaxes(title="Preço")
            fig.update_yaxes(title="Posto")
            st.plotly_chart(fig, width="stretch")
            st.dataframe(
                df_price[
                    ["nome_fantasia", "bandeira", "uf", "cidade", "bairro", "preco"]
                ]
                .rename(
                    columns={
                        "nome_fantasia": "Posto",
                        "bandeira": "Bandeira",
                        "uf": "UF",
                        "cidade": "Cidade",
                        "bairro": "Bairro",
                        "preco": "Preço",
                    }
                )
                .style.format({"Preço": "R$ {:.3f}"}),
                width="stretch",
                hide_index=True,
            )
    else:
        st.info("Sem dados de ranking de preço suficientes para os filtros atuais.")

with tab2:
    render_section_header(
        "⭐ Avaliações",
        "Top avaliações",
        "Veja os postos mais bem avaliados com um score ponderado entre nota média e volume de avaliações.",
    )
    df_top_rated = zset_to_df(
        redis.zrevrange("ranking:postos:avaliacao", 0, -1, withscores=True),
        ["posto_id", "nota_media"],
    )
    df_top_rated = enrich_station_rows(redis, df_top_rated)
    if df_top_rated.empty:
        st.info("Sem avaliações no Redis.")
    else:
        df_top_rated["nota_media"] = df_top_rated["nota_media"].astype(float).round(2)
        df_top_rated["rating_count"] = df_top_rated["rating_count"].astype(int)
        df_top_rated = df_top_rated[df_top_rated["rating_count"] > 0]
        df_top_rated = df_top_rated[df_top_rated["nome_fantasia"] != df_top_rated["posto_id"]]
        df_top_rated = df_top_rated[df_top_rated["cnpj"] != "-"]
        global_mean = (
            round(df_top_rated["nota_media"].mean(), 2) if not df_top_rated.empty else 0.0
        )
        df_top_rated["score_ponderado"] = df_top_rated.apply(
            lambda row: weighted_rating_score(
                row["nota_media"], row["rating_count"], global_mean, minimum_votes=5
            ),
            axis=1,
        )
        df_top_rated = df_top_rated.sort_values(
            ["score_ponderado", "nota_media", "rating_count"], ascending=[False, False, False]
        ).head(10)
        if df_top_rated.empty:
            st.info(
                "Os registros atuais de avaliação no Redis não têm metadados completos de posto. "
                "Se necessário, reconstrua o Redis com a ordem de backfill atualizada."
            )
        else:
            df_top_rated["label_posto"] = (
                df_top_rated["nome_fantasia"] + " | " + df_top_rated["uf"]
            )
            fig = px.bar(
                df_top_rated.sort_values(
                    ["score_ponderado", "rating_count"], ascending=[True, True]
                ),
                x="score_ponderado",
                y="label_posto",
                orientation="h",
                color="nota_media",
                color_continuous_scale="Tealgrn",
                hover_name="nome_fantasia",
                hover_data={
                    "cidade": True,
                    "bairro": True,
                    "rating_count": True,
                    "nota_media": ":.2f",
                    "score_ponderado": ":.3f",
                    "uf": True,
                    "cnpj": True,
                    "label_posto": False,
                },
                title="Top postos por score ponderado de avaliação",
            )
            apply_chart_theme(fig)
            fig.update_xaxes(title="Score ponderado")
            fig.update_yaxes(title="Posto")
            st.plotly_chart(fig, width="stretch")
            st.caption(
                f"Score ponderado calculado com média global {global_mean:.2f} e mínimo de 5 avaliações para ganhar confiança."
            )
            display_top_rated = df_top_rated[
                ["cnpj", "nome_fantasia", "uf", "cidade", "bairro", "nota_media", "rating_count", "score_ponderado"]
            ].rename(
                columns={
                    "cnpj": "CNPJ",
                    "nome_fantasia": "Posto",
                    "uf": "UF",
                    "cidade": "Cidade",
                    "bairro": "Bairro",
                    "nota_media": "Nota média",
                    "rating_count": "Número de avaliações",
                    "score_ponderado": "Score ponderado",
                }
            )
            st.dataframe(
                display_top_rated.style.format(
                    {"Nota média": "{:.2f}", "Score ponderado": "{:.3f}"}
                ),
                width="stretch",
                hide_index=True,
            )

with tab4:
    render_section_header(
        "📈 Variação",
        "Maior variação recente de preço",
        "Acompanhe os postos com mudanças mais fortes de preço no período recente.",
    )
    variation_fuel_label = st.selectbox(
        "Combustível",
        ["Todos"] + fuel_display_options(),
        index=0,
        key="variation_fuel",
    )
    variation_fuel = (
        "Todos"
        if variation_fuel_label == "Todos"
        else fuel_code_from_label(variation_fuel_label)
    )
    variation_rows = redis.zrevrange(
        "ranking:postos:variacao_recente", 0, -1, withscores=True
    )
    rendered_rows = []
    for member, score in variation_rows:
        posto_id, combustivel = parse_variation_member(member)
        if variation_fuel != "Todos" and combustivel != variation_fuel:
            continue
        snapshot = station_snapshot(redis, posto_id)
        field = fuel_field_name(combustivel)
        rendered_rows.append(
            {
                "cnpj": snapshot.get("cnpj", "-"),
                "nome_fantasia": snapshot.get("nome_fantasia", posto_id),
                "uf": snapshot.get("uf", "-"),
                "cidade": snapshot.get("cidade", "-"),
                "bairro": snapshot.get("bairro", "-"),
                "combustivel": prettify_fuel_label(combustivel),
                "preco_antigo": float(snapshot.get(f"preco_anterior_{field}", 0) or 0),
                "preco_atual": float(snapshot.get(f"preco_{field}", 0) or 0),
                "variacao_pct": round(
                    float(snapshot.get(f"variacao_pct_{field}", 0) or 0), 2
                ),
                "direcao": snapshot.get(f"direcao_{field}", "->"),
            }
        )
    df_variation = pd.DataFrame(rendered_rows)
    if df_variation.empty:
        st.info("Sem dados de variação recente.")
    else:
        df_variation = df_variation[
            (df_variation["variacao_pct"] != 0)
            & ((df_variation["preco_antigo"] != 0) | (df_variation["preco_atual"] != 0))
        ]
        df_variation = df_variation[df_variation["cnpj"] != "-"]
        df_variation = df_variation[df_variation["nome_fantasia"] != df_variation["cnpj"]]
        if df_variation.empty:
            st.info(
                "Sem registros de variação com preços válidos no Redis atual. "
                "Se necessário, reconstrua o Redis com a ordem de backfill atualizada."
            )
        else:
            df_variation = df_variation.head(10)
            df_variation["direcao"] = df_variation["direcao"].apply(
                variation_direction_label
            )
            df_variation = df_variation[
                [
                    "cnpj",
                    "nome_fantasia",
                    "uf",
                    "cidade",
                    "bairro",
                    "combustivel",
                    "preco_antigo",
                    "preco_atual",
                    "variacao_pct",
                    "direcao",
                ]
            ]
            st.dataframe(
                df_variation.rename(
                    columns={
                        "cnpj": "CNPJ",
                        "nome_fantasia": "Posto",
                        "uf": "UF",
                        "cidade": "Cidade",
                        "bairro": "Bairro",
                        "combustivel": "Combustível",
                        "preco_antigo": "Preço Anterior",
                        "preco_atual": "Preço Atual",
                        "variacao_pct": "Percentual Diferença",
                        "direcao": "Tendência",
                    }
                ).style.format(
                    {
                        "Preço Anterior": "R$ {:.3f}",
                        "Preço Atual": "R$ {:.3f}",
                        "Percentual Diferença": "{:.2f}%",
                    }
                ).apply(variation_row_style, axis=1),
                width="stretch",
                hide_index=True,
            )

with tab6:
    render_section_header(
        "📍 Proximidade",
        "Busca por geolocalização",
        "Encontre postos de determinada região.",
    )
    st.caption(
        "Aqui você pode usar UF, cidade e bairro como origem da busca, ou trocar para um posto de referência."
    )

    if geo_catalog.empty:
        st.info("Não há dados geográficos suficientes no Redis para montar a busca.")
    else:
        search_mode = st.radio(
            "Origem da busca",
            [
                "Selecionar UF, Cidade e Bairro",
                "Usar um posto real como referência",
            ],
            horizontal=True,
        )

        default_row = geo_catalog.iloc[0]
        lat = float(default_row["lat"])
        lon = float(default_row["lon"])
        origin_label = "Origem selecionada"

        if search_mode == "Selecionar UF, Cidade e Bairro":
            col_uf, col_cidade, col_bairro = st.columns(3)
            uf_options = sorted(geo_catalog["uf"].dropna().unique().tolist())
            with col_uf:
                selected_uf = st.selectbox("UF", uf_options, index=0)

            city_df = geo_catalog[geo_catalog["uf"] == selected_uf]
            city_options = sorted(city_df["cidade"].dropna().unique().tolist())
            with col_cidade:
                selected_city = st.selectbox("Cidade", city_options, index=0)

            neighborhood_df = city_df[city_df["cidade"] == selected_city]
            neighborhood_options = sorted(
                neighborhood_df["bairro"].dropna().unique().tolist()
            )
            with col_bairro:
                selected_neighborhood = st.selectbox(
                    "Bairro", neighborhood_options, index=0
                )

            center = neighborhood_center(
                geo_catalog, selected_uf, selected_city, selected_neighborhood
            )
            if center:
                lat = center["lat"]
                lon = center["lon"]
                origin_label = (
                    f"{selected_neighborhood} / {selected_city} - {selected_uf}"
                )
                st.info(
                    f"Origem calculada pelo centro aproximado do bairro. "
                    f"Base usada: {center['postos_origem']} posto(s) dessa região."
                )

        else:
            reference_options = build_geo_reference_options_from_catalog(geo_catalog)
            selected_option = st.selectbox(
                "Ponto de referência", reference_options, index=0
            )
            selected_reference = parse_geo_reference(selected_option)
            lat = selected_reference["lat"]
            lon = selected_reference["lon"]
            origin_label = (
                f"{selected_reference['nome_fantasia']} | "
                f"{selected_reference['cidade']} / {selected_reference['bairro']}"
            )
            st.info(f"Referência atual: {origin_label}")

        radius_km = st.slider("Raio (km)", min_value=1, max_value=100, value=10)

        try:
            geo_rows = geo_search(redis, float(lon), float(lat), float(radius_km))
            proximity_rows = proximity_rows_from_geo(redis, geo_rows)
            df_geo = pd.DataFrame(proximity_rows)

            if df_geo.empty:
                fallback_rows, expanded_radius = nearest_geo_search(
                    redis, float(lon), float(lat), float(radius_km)
                )
                if not fallback_rows:
                    st.info("Nenhum posto foi encontrado para a origem escolhida.")
                else:
                    fallback_table = pd.DataFrame(
                        proximity_rows_from_geo(redis, fallback_rows)
                    )
                    st.warning(
                        f"Nenhum posto foi encontrado em {radius_km} km. "
                        f"Mostrando os mais próximos encontrados até {int(expanded_radius)} km."
                    )
                    map_df = pd.concat(
                        [
                            pd.DataFrame(
                                [
                                    {
                                        "latitude": float(lat),
                                        "longitude": float(lon),
                                        "nome_fantasia": origin_label,
                                    }
                                ]
                            ),
                            fallback_table[["lat", "lon", "nome_fantasia"]].rename(
                                columns={"lat": "latitude", "lon": "longitude"}
                            ),
                        ],
                        ignore_index=True,
                    )
                    st.map(map_df)
                    st.dataframe(
                        fallback_table[
                            [
                                "nome_fantasia",
                                "bandeira",
                                "cidade",
                                "bairro",
                                "distancia_km",
                            ]
                        ].rename(
                            columns={
                                "nome_fantasia": "Posto",
                                "bandeira": "Bandeira",
                                "cidade": "Cidade",
                                "bairro": "Bairro",
                                "distancia_km": "Distância em Km",
                            }
                        ),
                        width="stretch",
                        hide_index=True,
                    )
            else:
                map_df = pd.concat(
                    [
                        pd.DataFrame(
                            [
                                {
                                    "latitude": float(lat),
                                    "longitude": float(lon),
                                    "nome_fantasia": origin_label,
                                }
                            ]
                        ),
                        df_geo[["lat", "lon", "nome_fantasia"]].rename(
                            columns={"lat": "latitude", "lon": "longitude"}
                        ),
                    ],
                    ignore_index=True,
                )
                st.map(map_df)
                st.dataframe(
                    df_geo[
                        [
                            "nome_fantasia",
                            "bandeira",
                            "cidade",
                            "bairro",
                            "distancia_km",
                        ]
                    ].rename(
                        columns={
                            "nome_fantasia": "Posto",
                            "bandeira": "Bandeira",
                            "cidade": "Cidade",
                            "bairro": "Bairro",
                            "distancia_km": "Distância em Km",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                )
        except Exception as exc:
            st.error(f"Falha na consulta GEO: {exc}")

with tab5:
    render_section_header(
        "⏱️ Séries temporais",
        "Evolução de preço",
        "Leitura agregada do combustível ao longo do tempo.",
    )
    combustivel_series_label = st.selectbox(
        "Combustível para média agregada", fuel_display_options(), index=0
    )
    combustivel_series = fuel_code_from_label(combustivel_series_label)

    try:
        all_series = fuel_timeseries(redis, combustivel_series)
        df_series = build_fuel_series_df(all_series)
        if df_series.empty:
            st.info("Sem dados de séries temporais para o combustível selecionado.")
        else:
            grouped = (
                df_series.set_index("datetime")["valor"]
                .resample("D")
                .mean()
                .reset_index()
            )
            grouped["media_movel_7d"] = grouped["valor"].rolling(
                window=7, min_periods=1
            ).mean()
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=grouped["datetime"],
                    y=grouped["valor"],
                    mode="lines",
                    name="Média diária",
                    line={"color": "rgba(20, 184, 166, 0.45)", "width": 2},
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=grouped["datetime"],
                    y=grouped["media_movel_7d"],
                    mode="lines",
                    name="Tendência (7 dias)",
                    line={"color": COLOR_PRIMARY, "width": 3},
                )
            )
            fig.update_layout(
                title=f"Evolução média de {prettify_fuel_label(combustivel_series)}"
            )
            apply_chart_theme(fig)
            fig.update_yaxes(title="Preço médio (R$)")
            fig.update_xaxes(title="Data")
            st.plotly_chart(fig, width="stretch")

    except Exception as exc:
        st.error(f"Falha ao consolidar séries por combustível: {exc}")

    st.divider()
    st.subheader("Histórico detalhado por posto")
    station_options = build_station_options(redis, combustivel_series)
    if not station_options:
        st.info("Nenhum posto com histórico disponível para o combustível selecionado.")
    else:
        station_option = st.selectbox(
            "Posto para detalhe",
            station_options,
            index=0,
            key="station_detail_option",
        )
        posto_id = station_option.split(" | ", 1)[0]
        try:
            station_points = station_timeseries(redis, posto_id, combustivel_series)
            df_station_series = pd.DataFrame(station_points, columns=["ts", "valor"])
            if df_station_series.empty:
                st.info("Sem histórico para o posto selecionado.")
            else:
                df_station_series["datetime"] = df_station_series["ts"].apply(
                    lambda value: datetime.fromtimestamp(int(value) / 1000.0)
                )
                fig = go.Figure(
                    data=[
                        go.Scatter(
                            x=df_station_series["datetime"],
                            y=df_station_series["valor"],
                            mode="lines+markers",
                            name="Preço",
                            line={"color": COLOR_PRIMARY, "width": 3},
                            marker={"color": COLOR_PRIMARY_SOFT, "size": 7},
                        )
                    ]
                )
                fig.update_layout(
                    title=f"Histórico do posto {posto_id} - {prettify_fuel_label(combustivel_series)}"
                )
                apply_chart_theme(fig)
                st.plotly_chart(fig, width="stretch")
        except Exception as exc:
            if "TSDB: the key does not exist" in str(exc):
                st.info(
                    "Esse posto ainda não possui histórico para o combustível selecionado."
                )
            else:
                st.error(f"Falha ao ler série do posto: {exc}")

if auto_refresh:
    time.sleep(int(refresh_seconds))
    st.rerun()
