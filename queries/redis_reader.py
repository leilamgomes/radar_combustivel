import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from redis import Redis

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.event_transformer import (
    COMBUSTIVEIS,
    fuel_field_name,
    parse_variation_member,
    region_price_key,
    station_key,
)

# Load .env.local first (for host development), fallback to .env (for Docker)
load_dotenv(".env.local")
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def get_redis() -> Redis:
    return Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def station_summary(redis: Redis, posto_id: str) -> Dict[str, str]:
    return redis.hgetall(station_key(posto_id))


def lowest_price_by_region(redis: Redis, combustivel: str, region_type: str, region_name: str, n: int = 5):
    key = region_price_key(combustivel, region_type, region_name)
    return redis.zrange(key, 0, n - 1, withscores=True)


def top_fuels(redis: Redis, n: int = 5):
    return redis.zrevrange("ranking:combustiveis:buscas", 0, n - 1, withscores=True)


def top_neighborhoods(redis: Redis, n: int = 5):
    return redis.zrevrange("ranking:bairros:buscas", 0, n - 1, withscores=True)


def top_cities(redis: Redis, n: int = 5):
    return redis.zrevrange("ranking:cidades:buscas", 0, n - 1, withscores=True)


def top_rated(redis: Redis, n: int = 5):
    return redis.zrevrange("ranking:postos:avaliacao", 0, n - 1, withscores=True)


def top_price_variations(redis: Redis, n: int = 5):
    return redis.zrevrange("ranking:postos:variacao_recente", 0, n - 1, withscores=True)


def fuel_price_series(redis: Redis, combustivel: str):
    series = redis.execute_command(
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
    if series:
        return series

    fallback = []
    pattern = f"ts:preco:*:{fuel_field_name(combustivel)}"
    for key in redis.keys(pattern)[:50]:
        points = redis.execute_command("TS.RANGE", key, "-", "+", "AGGREGATION", "avg", "3600000")
        fallback.append((key, [], points))
    return fallback


def sample_region_name(redis: Redis, combustivel: str, region_type: str) -> str:
    pattern = f"ranking:precos:{fuel_field_name(combustivel)}:{region_type}:*"
    keys = redis.keys(pattern)
    if not keys:
        return ""
    region_slug = keys[0].split(f"{region_type}:", 1)[1]
    return region_slug.replace("_", " ")


def print_block(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def print_station_lines(redis: Redis, rows: List[Tuple[str, float]], fuel: str | None = None) -> None:
    for idx, (member, score) in enumerate(rows, start=1):
        posto_id = member
        member_fuel = fuel
        if member_fuel is None and "|" in member:
            posto_id, member_fuel = parse_variation_member(member)
        summary = station_summary(redis, posto_id)
        nome = summary.get("nome_fantasia", posto_id)
        cidade = summary.get("cidade", "-")
        bairro = summary.get("bairro", "-")
        if member_fuel:
            field = fuel_field_name(member_fuel)
            atual = float(summary.get(f"preco_{field}", 0) or 0)
            anterior = float(summary.get(f"preco_anterior_{field}", 0) or 0)
            variacao = float(summary.get(f"variacao_pct_{field}", 0) or 0)
            direcao = summary.get(f"direcao_{field}", "➡️")
            print(
                f"{idx:02d}. {nome} | {cidade}/{bairro} | {member_fuel} | R$ {atual:.3f} "
                f"(antes R$ {anterior:.3f}) | {direcao} {variacao:.2f}%"
            )
        else:
            print(f"{idx:02d}. {nome} | {cidade}/{bairro} | score={score:.2f}")


def main() -> None:
    redis = get_redis()
    print("[READER] Consultas em tempo real iniciadas.")

    while True:
        print_block("1) Menor preço por região")
        for combustivel in COMBUSTIVEIS[:2]:
            region_name = sample_region_name(redis, combustivel, "cidade")
            if not region_name:
                continue
            rows = lowest_price_by_region(redis, combustivel, "cidade", region_name, 3)
            if rows:
                print(f"\nTop 3 menores preços em {region_name.title()} para {combustivel}:")
                print_station_lines(redis, rows, combustivel)

        print_block("2) Combustíveis mais buscados")
        for idx, (member, score) in enumerate(top_fuels(redis), start=1):
            print(f"{idx:02d}. {member} -> {int(score)} buscas")

        print_block("3) Bairros com maior volume de buscas")
        for idx, (member, score) in enumerate(top_neighborhoods(redis), start=1):
            print(f"{idx:02d}. {member} -> {int(score)} buscas")

        print_block("4) Cidades com maior volume de buscas")
        for idx, (member, score) in enumerate(top_cities(redis), start=1):
            print(f"{idx:02d}. {member} -> {int(score)} buscas")

        print_block("5) Postos mais bem avaliados")
        print_station_lines(redis, top_rated(redis))

        print_block("6) Maior variação recente de preço")
        print_station_lines(redis, top_price_variations(redis))

        print_block("7) Evolução de preços por combustível (média horária)")
        for combustivel in COMBUSTIVEIS[:2]:
            try:
                series = fuel_price_series(redis, combustivel)
                total_points = sum(len(item[2]) for item in series)
                print(f"{combustivel}: {len(series)} séries encontradas, {total_points} pontos agregados.")
            except Exception as exc:
                print(f"Falha ao ler série temporal de {combustivel}: {exc}")

        time.sleep(5)


if __name__ == "__main__":
    main()
