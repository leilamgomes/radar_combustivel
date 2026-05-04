import argparse
import os
import time
from collections import defaultdict
from typing import Any, Dict, List

from dotenv import load_dotenv
from pymongo import MongoClient
from redis import Redis
from redis.exceptions import ResponseError

from event_transformer import (
    COLECOES_SUPORTADAS,
    fuel_field_name,
    geo_key,
    iter_region_targets,
    normalize_document,
    price_fields,
    region_price_key,
    station_key,
    station_snapshot_mapping,
    ts_key,
    variation_member,
)

# Load .env.local first (for host development), fallback to .env (for Docker)
load_dotenv(".env.local")
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
DB_NAME = os.getenv("DB_NAME", os.getenv("MONGO_DB", "radar_combustivel"))
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

BACKFILL_ORDER = (
    "postos",
    "localizacoes_postos",
    "eventos_preco",
    "buscas_usuarios",
    "avaliacoes_interacoes",
)

TIME_FIELDS = {
    "postos": "updated_at",
    "localizacoes_postos": "atualizado_em",
    "eventos_preco": "ocorrido_em",
    "buscas_usuarios": "consultado_em",
    "avaliacoes_interacoes": "created_at",
}

BACKFILL_PROGRESS_EVERY = 5000


def resolve_database_name(mongo: MongoClient) -> str:
    preferred_name = DB_NAME
    preferred_db = mongo[preferred_name]

    preferred_total = sum(
        preferred_db[name].estimated_document_count() for name in BACKFILL_ORDER if name in preferred_db.list_collection_names()
    )
    if preferred_total > 0:
        print(f"[CONSUMER] Banco selecionado: {preferred_name} ({preferred_total} documentos detectados).")
        return preferred_name

    fallback_name = "radar_combustivel"
    fallback_db = mongo[fallback_name]
    fallback_total = sum(
        fallback_db[name].estimated_document_count() for name in BACKFILL_ORDER if name in fallback_db.list_collection_names()
    )
    if fallback_total > 0 and fallback_name != preferred_name:
        print(
            f"[CONSUMER] Banco configurado '{preferred_name}' está vazio. "
            f"Usando fallback '{fallback_name}' com {fallback_total} documentos."
        )
        return fallback_name

    print(
        f"[CONSUMER] Banco selecionado: {preferred_name}. "
        f"Nenhum documento encontrado nas coleções monitoradas."
    )
    return preferred_name


def ensure_ts_add(redis: Redis, key: str, ts: int, value: float, labels: Dict[str, str]) -> None:
    if not redis.exists(key):
        args: List[str] = []
        for label_key, label_value in labels.items():
            args.extend([label_key, label_value])
        try:
            redis.execute_command(
                "TS.CREATE",
                key,
                "RETENTION",
                7776000000,
                "DUPLICATE_POLICY",
                "LAST",
                "LABELS",
                *args,
            )
        except ResponseError as exc:
            if "already exists" not in str(exc).lower():
                raise
    else:
        try:
            info = redis.execute_command("TS.INFO", key)
            labels_idx = info.index("labels") if "labels" in info else -1
            current_labels = info[labels_idx + 1] if labels_idx >= 0 else []
            if not current_labels:
                args = []
                for label_key, label_value in labels.items():
                    args.extend([label_key, label_value])
                redis.execute_command("TS.ALTER", key, "LABELS", *args)
        except Exception:
            pass

    try:
        redis.execute_command("TS.ADD", key, ts, value, "ON_DUPLICATE", "LAST")
    except ResponseError as exc:
        msg = str(exc)
        if "key does not exist" not in msg and "TSDB: the key does not exist" not in msg:
            raise
        redis.execute_command("TS.ADD", key, ts, value, "ON_DUPLICATE", "LAST")


def cached_station(redis: Redis, posto_id: str) -> Dict[str, Any]:
    data = redis.hgetall(station_key(posto_id))
    if not data:
        return {}
    return data


def refresh_geo(redis: Redis, posto_id: str, mapping: Dict[str, Any]) -> None:
    lat = float(mapping.get("lat") or 0.0)
    lon = float(mapping.get("lon") or 0.0)
    if lat or lon:
        redis.geoadd(geo_key(), [lon, lat, posto_id])


def apply_station_snapshot(redis: Redis, event: Dict[str, Any], quiet: bool = False) -> None:
    key = station_key(event["posto_id"])
    mapping = station_snapshot_mapping(event)
    redis.hset(key, mapping=mapping)
    refresh_geo(redis, event["posto_id"], mapping)
    if not quiet:
        print(f"[REDIS] HSET {key} snapshot atualizado")


def apply_price_event(redis: Redis, event: Dict[str, Any], quiet: bool = False) -> None:
    key = station_key(event["posto_id"])
    station = cached_station(redis, event["posto_id"])
    redis.hset(key, mapping=price_fields(event))

    for region_type, region_name in iter_region_targets(station):
        rank_key = region_price_key(event["combustivel"], region_type, region_name)
        redis.zadd(rank_key, {event["posto_id"]: event["preco_novo"]})

    redis.zadd(
        "ranking:postos:variacao_recente",
        {variation_member(event["posto_id"], event["combustivel"]): abs(float(event["variacao_pct"]))},
    )

    ensure_ts_add(
        redis,
        ts_key(event["posto_id"], event["combustivel"]),
        event["ts"],
        event["preco_novo"],
        {
            "metric": "price",
            "posto_id": event["posto_id"],
            "combustivel": event["combustivel"],
            "cidade": str(station.get("cidade") or "indefinido"),
            "bairro": str(station.get("bairro") or "indefinido"),
            "uf": str(station.get("uf") or "indefinido"),
        },
    )

    if not quiet:
        print(
            f"[REDIS] ZADD ranking de preço | {event['combustivel']} | posto={event['posto_id']} | preço={event['preco_novo']:.3f}"
        )


def apply_search_event(redis: Redis, event: Dict[str, Any], quiet: bool = False) -> None:
    bairro = event["bairro"] or infer_nearest_neighborhood(redis, event["lon"], event["lat"])
    posto_id = infer_nearest_station_id(redis, event["lon"], event["lat"])
    uf = event["uf"] or "UF nao informada"
    cidade = event["cidade"] or "Cidade nao informada"
    bairro_nome = bairro or "Bairro nao informado"
    cidade_composta = f"{uf} - {cidade}"
    bairro_composto = f"{uf} - {cidade} - {bairro_nome}"
    regiao = bairro_composto
    redis.zincrby("ranking:combustiveis:buscas", 1, event["combustivel"])
    redis.zincrby("ranking:bairros:buscas", 1, bairro_composto)
    redis.zincrby("ranking:cidades:buscas", 1, cidade_composta)
    redis.zincrby("ranking:regioes:buscas", 1, regiao)
    if posto_id:
        redis.hincrby(station_key(posto_id), "search_hits", 1)
    if not quiet:
        print(f"[REDIS] ZINCRBY ranking:combustiveis:buscas 1 {event['combustivel']}")


def infer_nearest_neighborhood(redis: Redis, lon: float, lat: float) -> str:
    posto_id = infer_nearest_station_id(redis, lon, lat)
    if not posto_id:
        return ""
    return str(redis.hget(station_key(posto_id), "bairro") or "")


def infer_nearest_station_id(redis: Redis, lon: float, lat: float) -> str:
    if not lon and not lat:
        return ""
    try:
        nearby = redis.execute_command(
            "GEOSEARCH",
            "geo:postos",
            "FROMLONLAT",
            lon,
            lat,
            "BYRADIUS",
            25,
            "km",
            "ASC",
            "COUNT",
            1,
        )
    except Exception:
        return ""

    if not nearby:
        return ""

    return str(nearby[0] or "")


def apply_interaction_event(redis: Redis, event: Dict[str, Any], quiet: bool = False) -> None:
    key = station_key(event["posto_id"])

    if event["tipo"] == "avaliacao":
        redis.hincrbyfloat(key, "rating_sum", event["nota"])
        redis.hincrby(key, "rating_count", 1)
        redis.hincrby(key, "rating_util_total", event["util_count"])
        rating_sum = float(redis.hget(key, "rating_sum") or 0.0)
        rating_count = int(redis.hget(key, "rating_count") or 1)
        avg_rating = round(rating_sum / max(rating_count, 1), 2)
        redis.hset(key, mapping={"avg_rating": avg_rating, "last_rating_ts": event["ts"]})
        redis.zadd("ranking:postos:avaliacao", {event["posto_id"]: avg_rating})
        if not quiet:
            print(f"[REDIS] ZADD ranking:postos:avaliacao {avg_rating} {event['posto_id']}")
        return

    field_map = {
        "favorito": "favorite_count",
        "compartilhamento": "share_count",
        "denuncia": "report_count",
        "check_in": "checkin_count",
    }
    target_field = field_map.get(event["tipo"])
    if target_field:
        redis.hincrby(key, target_field, 1)
        if not quiet:
            print(f"[REDIS] HINCRBY {key} {target_field} 1")


def handle_event(redis: Redis, collection_name: str, raw_document: Dict[str, Any], quiet: bool = False) -> None:
    event = normalize_document(collection_name, raw_document)

    if event["entity"] == "posto":
        if not quiet:
            print(f"[EVENT] posto | {event['posto_id']} | {event['nome_fantasia']}")
        apply_station_snapshot(redis, event, quiet=quiet)
        return

    if event["entity"] == "localizacao":
        if not quiet:
            print(f"[EVENT] localizacao | {event['posto_id']} | {event['municipio']} | {event['bairro']}")
        apply_station_snapshot(redis, event, quiet=quiet)
        return

    if event["entity"] == "preco":
        if not quiet:
            print(
                f"[EVENT] preco | {event['posto_id']} | {event['combustivel']} | {event['preco_anterior']:.3f} -> {event['preco_novo']:.3f}"
            )
        apply_price_event(redis, event, quiet=quiet)
        return

    if event["entity"] == "busca":
        if not quiet:
            print(f"[EVENT] busca | {event['combustivel']} | {event['cidade']}")
        apply_search_event(redis, event, quiet=quiet)
        return

    if event["entity"] == "interacao":
        if not quiet:
            print(f"[EVENT] interacao | {event['posto_id']} | {event['tipo']}")
        apply_interaction_event(redis, event, quiet=quiet)


def sorted_cursor(collection, collection_name: str):
    time_field = TIME_FIELDS[collection_name]
    return collection.find({}).sort(time_field, 1)


def backfill_existing(db, redis: Redis) -> None:
    processed = defaultdict(int)
    for collection_name in BACKFILL_ORDER:
        collection = db[collection_name]
        print(f"[CONSUMER] Iniciando backfill de {collection_name}...")
        for document in sorted_cursor(collection, collection_name):
            handle_event(redis, collection_name, document, quiet=True)
            processed[collection_name] += 1
            if processed[collection_name] % BACKFILL_PROGRESS_EVERY == 0:
                print(
                    f"[CONSUMER] Progresso {collection_name}: "
                    f"{processed[collection_name]} documentos processados."
                )
        print(f"[CONSUMER] Backfill concluído em {collection_name}: {processed[collection_name]} documentos.")

    total = sum(processed.values())
    print(f"[CONSUMER] Backfill geral concluído: {total} documentos processados.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Consome eventos do MongoDB Change Stream e publica agregados no Redis.")
    parser.add_argument("--skip-backfill", action="store_true", help="Não processa documentos já existentes.")
    args = parser.parse_args()

    mongo = MongoClient(MONGO_URI)
    redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    db = mongo[resolve_database_name(mongo)]

    if not args.skip_backfill:
        backfill_existing(db, redis)

    print("[CONSUMER] Conectado ao MongoDB Change Stream")
    print("[CONSUMER] Aguardando inserts nas coleções monitoradas...")

    while True:
        try:
            pipeline = [
                {"$match": {"operationType": "insert", "ns.coll": {"$in": list(COLECOES_SUPORTADAS)}}}
            ]
            with db.watch(pipeline, full_document="updateLookup") as stream:
                for change in stream:
                    collection_name = change["ns"]["coll"]
                    handle_event(redis, collection_name, change["fullDocument"])
        except Exception as exc:
            print(f"[CONSUMER] Reconectando após erro: {exc}")
            time.sleep(2)


if __name__ == "__main__":
    main()
