import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


COMBUSTIVEIS = (
    "GASOLINA_COMUM",
    "GASOLINA_ADITIVADA",
    "ETANOL",
    "DIESEL_S10",
    "DIESEL_COMUM",
    "GNV",
)

COLECOES_SUPORTADAS = (
    "postos",
    "eventos_preco",
    "buscas_usuarios",
    "avaliacoes_interacoes",
    "localizacoes_postos",
)


def slugify(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower())
    return clean.strip("_") or "indefinido"


def fuel_field_name(combustivel: str) -> str:
    return slugify(combustivel)


def to_timestamp_ms(value: Any) -> int:
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    raise ValueError(f"Timestamp inválido: {value!r}")


def get_coordinates(raw: Dict[str, Any]) -> tuple[float, float]:
    geo = raw.get("geo") or raw.get("location") or {}
    coords = geo.get("coordinates") or [0.0, 0.0]
    lon = float(coords[0]) if len(coords) > 0 else 0.0
    lat = float(coords[1]) if len(coords) > 1 else 0.0
    return lat, lon


def station_key(posto_id: str) -> str:
    return f"posto:{posto_id}"


def ts_key(posto_id: str, combustivel: str) -> str:
    return f"ts:preco:{posto_id}:{fuel_field_name(combustivel)}"


def geo_key() -> str:
    return "geo:postos"


def index_key() -> str:
    return "idx:postos"


def region_price_key(combustivel: str, region_type: str, region_name: str) -> str:
    return f"ranking:precos:{fuel_field_name(combustivel)}:{region_type}:{slugify(region_name)}"


def city_region_name(uf: str, cidade: str) -> str:
    return f"{safe_str(uf)}|{safe_str(cidade)}"


def neighborhood_region_name(uf: str, cidade: str, bairro: str) -> str:
    return f"{safe_str(uf)}|{safe_str(cidade)}|{safe_str(bairro)}"


def variation_member(posto_id: str, combustivel: str) -> str:
    return f"{posto_id}|{combustivel}"


def safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_posto(raw: Dict[str, Any]) -> Dict[str, Any]:
    lat, lon = get_coordinates(raw)
    endereco = raw.get("endereco") or {}
    return {
        "entity": "posto",
        "posto_id": safe_str(raw.get("_id")),
        "nome_fantasia": safe_str(raw.get("nome_fantasia")),
        "bandeira": safe_str(raw.get("bandeira")),
        "cnpj": safe_str(raw.get("cnpj")),
        "cidade": safe_str(endereco.get("cidade")),
        "bairro": safe_str(endereco.get("bairro")),
        "uf": safe_str(endereco.get("estado")),
        "logradouro": safe_str(endereco.get("logradouro")),
        "numero": safe_str(endereco.get("numero")),
        "cep": safe_str(endereco.get("cep")),
        "telefone": safe_str(raw.get("telefone")),
        "ativo": int(bool(raw.get("ativo", True))),
        "lat": lat,
        "lon": lon,
        "location": f"{lon},{lat}",
        "updated_ts": to_timestamp_ms(raw.get("updated_at") or raw.get("created_at")),
    }


def normalize_localizacao(raw: Dict[str, Any]) -> Dict[str, Any]:
    lat, lon = get_coordinates(raw)
    return {
        "entity": "localizacao",
        "posto_id": safe_str(raw.get("posto_id")),
        "municipio": safe_str(raw.get("municipio")),
        "bairro": safe_str(raw.get("bairro")),
        "uf": safe_str(raw.get("uf")),
        "codigo_ibge": safe_str(raw.get("codigo_ibge")),
        "lat": lat,
        "lon": lon,
        "location": f"{lon},{lat}",
        "updated_ts": to_timestamp_ms(raw.get("atualizado_em")),
    }


def normalize_evento_preco(raw: Dict[str, Any]) -> Dict[str, Any]:
    combustivel = safe_str(raw.get("combustivel")).upper()
    return {
        "entity": "preco",
        "posto_id": safe_str(raw.get("posto_id")),
        "combustivel": combustivel,
        "preco_anterior": round(float(raw.get("preco_anterior") or 0.0), 3),
        "preco_novo": round(float(raw.get("preco_novo") or 0.0), 3),
        "variacao_pct": round(float(raw.get("variacao_pct") or 0.0), 4),
        "fonte": safe_str(raw.get("fonte")),
        "revisado": int(bool(raw.get("revisado", False))),
        "ts": to_timestamp_ms(raw.get("ocorrido_em")),
    }


def normalize_busca(raw: Dict[str, Any]) -> Dict[str, Any]:
    lat, lon = get_coordinates({"geo": raw.get("geo_centro")})
    filtros = raw.get("filtros") or {}
    return {
        "entity": "busca",
        "usuario_id": safe_str(raw.get("usuario_id")),
        "session_id": safe_str(raw.get("session_id")),
        "combustivel": safe_str(raw.get("tipo_combustivel")).upper(),
        "cidade": safe_str(raw.get("cidade")),
        "bairro": safe_str(raw.get("bairro")),
        "uf": safe_str(raw.get("estado")),
        "raio_km": int(raw.get("raio_km") or 0),
        "apenas_abertos": int(bool(filtros.get("apenas_abertos", False))),
        "ordenacao": safe_str(filtros.get("ordenacao")),
        "resultado_count": int(raw.get("resultado_count") or 0),
        "latencia_ms": int(raw.get("latencia_ms") or 0),
        "lat": lat,
        "lon": lon,
        "ts": to_timestamp_ms(raw.get("consultado_em")),
    }


def normalize_avaliacao(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "entity": "interacao",
        "posto_id": safe_str(raw.get("posto_id")),
        "tipo": safe_str(raw.get("tipo")),
        "nota": float(raw.get("nota") or 0.0),
        "util_count": int(raw.get("util_count") or 0),
        "ts": to_timestamp_ms(raw.get("created_at")),
    }


def normalize_document(collection_name: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    if collection_name == "postos":
        return normalize_posto(raw)
    if collection_name == "eventos_preco":
        return normalize_evento_preco(raw)
    if collection_name == "buscas_usuarios":
        return normalize_busca(raw)
    if collection_name == "avaliacoes_interacoes":
        return normalize_avaliacao(raw)
    if collection_name == "localizacoes_postos":
        return normalize_localizacao(raw)
    raise ValueError(f"Coleção não suportada: {collection_name}")


def station_snapshot_mapping(event: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {
        "posto_id": event["posto_id"],
        "updated_ts": event.get("updated_ts", 0),
    }

    fields = (
        "nome_fantasia",
        "bandeira",
        "cnpj",
        "cidade",
        "bairro",
        "uf",
        "logradouro",
        "numero",
        "cep",
        "telefone",
        "codigo_ibge",
        "municipio",
        "location",
    )
    for field in fields:
        if field in event and event[field] != "":
            mapping[field] = event[field]

    if "ativo" in event:
        mapping["ativo"] = event["ativo"]
    if "lat" in event:
        mapping["lat"] = event["lat"]
    if "lon" in event:
        mapping["lon"] = event["lon"]
    return mapping


def price_fields(event: Dict[str, Any]) -> Dict[str, Any]:
    fuel_name = fuel_field_name(event["combustivel"])
    current = round(float(event["preco_novo"]), 3)
    previous = round(float(event["preco_anterior"]), 3)
    variation_pct = round(float(event["variacao_pct"]), 4)
    direction = "➡️"
    if current > previous:
        direction = "⬆️"
    elif current < previous:
        direction = "⬇️"

    return {
        f"preco_{fuel_name}": current,
        f"preco_anterior_{fuel_name}": previous,
        f"variacao_pct_{fuel_name}": variation_pct,
        f"direcao_{fuel_name}": direction,
        f"fonte_preco_{fuel_name}": event["fonte"],
        f"atualizado_preco_{fuel_name}": event["ts"],
        "ultimo_combustivel_atualizado": event["combustivel"],
        "ultimo_preco_atualizado_em": event["ts"],
    }


def iter_region_targets(station_data: Dict[str, Any]) -> Iterable[tuple[str, str]]:
    bairro = safe_str(station_data.get("bairro"))
    cidade = safe_str(station_data.get("cidade") or station_data.get("municipio"))
    uf = safe_str(station_data.get("uf"))
    if bairro:
        yield "bairro", neighborhood_region_name(uf, cidade, bairro)
    if cidade:
        yield "cidade", city_region_name(uf, cidade)


def parse_variation_member(member: str) -> tuple[str, str]:
    posto_id, combustivel = member.split("|", 1)
    return posto_id, combustivel


def fuel_series_filter(combustivel: str) -> str:
    return f"combustivel={combustivel.upper()}"


def station_series_filter(posto_id: Optional[str] = None) -> list[str]:
    filters = ["metric=price"]
    if posto_id:
        filters.append(f"posto_id={posto_id}")
    return filters
