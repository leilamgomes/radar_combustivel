import os
import sys
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from pymongo import MongoClient
from redis import Redis
from redis.commands.search.field import GeoField, NumericField, TagField, TextField
from redis.commands.search.index_definition import IndexDefinition, IndexType

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.event_transformer import (
    COMBUSTIVEIS,
    fuel_field_name,
    geo_key,
    index_key,
    station_key,
)

# Load .env.local first (for host development), fallback to .env (for Docker)
load_dotenv(".env.local")
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
DB_NAME = os.getenv("DB_NAME", os.getenv("MONGO_DB", "radar_combustivel"))
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def resolve_database_name(mongo: MongoClient) -> str:
    preferred_name = DB_NAME
    preferred_db = mongo[preferred_name]
    preferred_total = sum(preferred_db[name].estimated_document_count() for name in preferred_db.list_collection_names())
    if preferred_total > 0:
        print(f"[REDIS] Banco selecionado: {preferred_name} ({preferred_total} documentos detectados).")
        return preferred_name

    fallback_name = "radar_combustivel"
    fallback_db = mongo[fallback_name]
    fallback_total = sum(fallback_db[name].estimated_document_count() for name in fallback_db.list_collection_names())
    if fallback_total > 0 and fallback_name != preferred_name:
        print(
            f"[REDIS] Banco configurado '{preferred_name}' está vazio. "
            f"Usando fallback '{fallback_name}' com {fallback_total} documentos."
        )
        return fallback_name

    print(f"[REDIS] Banco selecionado: {preferred_name}. Nenhum documento encontrado.")
    return preferred_name


def build_station_snapshot() -> Dict[str, dict]:
    mongo = MongoClient(MONGO_URI)
    db = mongo[resolve_database_name(mongo)]

    postos = {
        str(doc["_id"]): doc
        for doc in db.postos.find(
            {},
            {
                "nome_fantasia": 1,
                "bandeira": 1,
                "cnpj": 1,
                "telefone": 1,
                "ativo": 1,
                "endereco": 1,
                "location": 1,
            },
        )
    }
    localizacoes = {
        str(doc["posto_id"]): doc
        for doc in db.localizacoes_postos.find(
            {},
            {
                "posto_id": 1,
                "municipio": 1,
                "bairro": 1,
                "uf": 1,
                "codigo_ibge": 1,
                "geo": 1,
            },
        )
    }

    snapshot: Dict[str, dict] = {}
    for posto_id, posto in postos.items():
        endereco = posto.get("endereco") or {}
        local = localizacoes.get(posto_id) or {}
        geo = local.get("geo") or posto.get("location") or {}
        coords = geo.get("coordinates") or [0.0, 0.0]
        lon = float(coords[0]) if len(coords) > 0 else 0.0
        lat = float(coords[1]) if len(coords) > 1 else 0.0

        snapshot[posto_id] = {
            "posto_id": posto_id,
            "nome_fantasia": posto.get("nome_fantasia", ""),
            "bandeira": posto.get("bandeira", ""),
            "cnpj": posto.get("cnpj", ""),
            "telefone": posto.get("telefone", ""),
            "ativo": int(bool(posto.get("ativo", True))),
            "cidade": local.get("municipio") or endereco.get("cidade", ""),
            "municipio": local.get("municipio") or endereco.get("cidade", ""),
            "bairro": local.get("bairro") or endereco.get("bairro", ""),
            "uf": local.get("uf") or endereco.get("estado", ""),
            "codigo_ibge": local.get("codigo_ibge", ""),
            "logradouro": endereco.get("logradouro", ""),
            "numero": endereco.get("numero", ""),
            "cep": endereco.get("cep", ""),
            "lat": lat,
            "lon": lon,
            "location": f"{lon},{lat}",
            "avg_rating": 0,
            "rating_count": 0,
            "search_hits": 0,
        }
        for combustivel in COMBUSTIVEIS:
            field = fuel_field_name(combustivel)
            snapshot[posto_id][f"preco_{field}"] = 0.0
            snapshot[posto_id][f"variacao_pct_{field}"] = 0.0
            snapshot[posto_id][f"direcao_{field}"] = "➡️"

    return snapshot


def main() -> None:
    redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    snapshot = build_station_snapshot()

    redis.delete(geo_key())

    for posto_id, item in snapshot.items():
        redis.hset(station_key(posto_id), mapping=item)
        if item["lat"] or item["lon"]:
            redis.geoadd(geo_key(), [item["lon"], item["lat"], posto_id])

    try:
        redis.execute_command("FT.DROPINDEX", index_key(), "DD")
    except Exception:
        pass

    price_fields = [
        NumericField(f"preco_{fuel_field_name(combustivel)}", sortable=True)
        for combustivel in COMBUSTIVEIS
    ]

    redis.ft(index_key()).create_index(
        fields=[
            TextField("nome_fantasia", weight=2.0),
            TagField("bandeira"),
            TagField("cidade"),
            TagField("bairro"),
            TagField("uf"),
            NumericField("avg_rating", sortable=True),
            NumericField("rating_count", sortable=True),
            NumericField("search_hits", sortable=True),
            GeoField("location"),
            *price_fields,
        ],
        definition=IndexDefinition(
            prefix=["posto:"],
            index_type=IndexType.HASH,
        ),
    )

    print(
        f"[REDIS] {index_key()} criado com {len(snapshot)} postos e GEO inicial carregado."
    )


if __name__ == "__main__":
    main()
