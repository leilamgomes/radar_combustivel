# Lab Encontro 2: Pipeline Streaming MongoDB → Redis
## Caso de Uso: Radar Combustível

> **Database In-Memory | FIAP MBA em Tecnologia**
> Adaptação do projeto base `lab-streaming-mongo-redis-main` para o domínio de combustíveis.

---

## Objetivo

Construir um pipeline de streaming em tempo real que captura eventos e entidades do ecossistema Radar Combustível no MongoDB e os propaga para o Redis, mantendo métricas atualizadas de:

- **postos com menor preço por região**
- **combustíveis mais buscados**
- **UFs, cidades e bairros com maior volume de buscas**
- **postos mais bem avaliados**
- **postos com maior variação recente de preço**
- **evolução temporal dos preços**

O seed oficial do projeto continua sendo `init/mongo_seed.py` e **não deve ser alterado**.

---

## Arquitetura

```text
MongoDB (5 coleções) → Python Consumer → Redis Stack → Reader / Dashboard
```

Fluxo detalhado em [docs/streaming-mongo-redis.md](/C:/Users/leila/OneDrive/Documentos/MBA/radar-combustivel-fake-data-generator-main/docs/streaming-mongo-redis.md).

---

## Estrutura do repositório

```text
radar-combustivel-fake-data-generator-main/
├── docker-compose.yml
├── requirements.txt
├── docs/
│   └── streaming-mongo-redis.md
├── init/
│   ├── mongo_seed.py
│   └── redis_indexes.py
├── pipeline/
│   ├── event_transformer.py
│   └── mongodb_consumer.py
├── queries/
│   ├── data-view.py
│   └── redis_reader.py
└── README.md
```

---

## Coleções MongoDB

| Coleção | Papel no pipeline |
|--------|-------------------|
| `postos` | Cadastro base e metadados |
| `eventos_preco` | Atualização de preços e variação |
| `buscas_usuarios` | Popularidade de combustível e volume regional |
| `avaliacoes_interacoes` | Notas e interações dos usuários |
| `localizacoes_postos` | Geolocalização e recorte territorial |

---

## Estruturas Redis

### Hashes
- `posto:{posto_id}`: resumo do posto com identificação, endereço, localização, preço atual por combustível, avaliação média e contadores operacionais

### Sorted Sets
- `ranking:precos:{combustivel}:cidade:{regiao}`
- `ranking:precos:{combustivel}:bairro:{regiao}`
- `ranking:combustiveis:buscas`
- `ranking:bairros:buscas`
- `ranking:cidades:buscas`
- `ranking:postos:avaliacao`
- `ranking:postos:variacao_recente`

### GEO
- `geo:postos`

### Time Series
- `ts:preco:{posto_id}:{combustivel}`

### RediSearch
- `idx:postos`

---

## Configuração do ambiente

### 1. Pré-requisitos
- Docker + Docker Compose
- Python 3.10+

### 2. Variáveis de ambiente

O código aceita:

```env
MONGO_URI=mongodb://localhost:27017/?directConnection=true
DB_NAME=radar_combustivel
MONGO_DB=radar_combustivel
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
```

### 3. Subir a infraestrutura

```bash
docker-compose up -d
```

### 4. Instalar dependências

```bash
pip install -r requirements.txt
```

### 5. Popular MongoDB e preparar Redis

```bash
python init/mongo_seed.py
python init/redis_indexes.py
```

### 6. Iniciar o consumidor

```bash
python pipeline/mongodb_consumer.py
```

### 7. Abrir consultas em tempo real

```bash
python queries/redis_reader.py
```

### 8. Abrir o dashboard

```bash
python -m streamlit run queries/data-view.py
```

Depois abra:

```text
http://localhost:8501
```

---

## Dashboard

O painel foi organizado nas seguintes abas:

1. **Visão Geral**
2. **Top Avaliações**
3. **Ranking de Preço**
4. **Variação de Preço**
5. **Séries Temporais**
6. **Proximidade**

Na aba **Visão Geral** também ficam concentrados:
- **combustíveis mais buscados**
- **UFs mais buscadas**
- **cidades mais buscadas**
- **bairros mais buscados**

Cada aba responde diretamente às perguntas do trabalho usando estruturas reais do Redis Stack.

---

## Perguntas respondidas pelo sistema

1. Quais postos têm menor preço por região
2. Quais combustíveis estão em alta
3. Quais UFs, cidades e bairros têm maior volume de buscas
4. Quais são os postos mais bem avaliados
5. Quais postos tiveram maior variação recente de preço
6. Como os preços evoluem ao longo do tempo
7. Quais postos existem perto de um ponto de referência

---

## Consultas de demonstração

### Menor preço por cidade

```python
redis.zrange("ranking:precos:gasolina_comum:cidade:sp-almeida", 0, 9, withscores=True)
```

### Combustíveis em alta

```python
redis.zrevrange("ranking:combustiveis:buscas", 0, 4, withscores=True)
```

### Cidades com maior volume de buscas

```python
redis.zrevrange("ranking:cidades:buscas", 0, 9, withscores=True)
```

### Proximidade de postos

```python
redis.execute_command(
    "GEOSEARCH",
    "geo:postos",
    "FROMLONLAT",
    -46.6333,
    -23.5505,
    "BYRADIUS",
    10,
    "km",
    "ASC",
    "WITHDIST",
)
```

### Evolução temporal por combustível

```python
redis.execute_command(
    "TS.MRANGE",
    "-",
    "+",
    "AGGREGATION",
    "avg",
    "3600000",
    "FILTER",
    "metric=price",
    "combustivel=GASOLINA_COMUM",
)
```

---

## Checklist de validação

- [ ] `docker-compose up -d` sobe MongoDB + Redis Stack
- [ ] `python init/mongo_seed.py` popula as 5 coleções sem alterações no seed
- [ ] `python init/redis_indexes.py` cria hashes, GEO e `idx:postos`
- [ ] `python pipeline/mongodb_consumer.py` faz backfill e segue em Change Stream
- [ ] O Redis responde rankings por preço, avaliação e buscas
- [ ] A aba de proximidade usa `GEOSEARCH`
- [ ] A aba de séries temporais usa `TS.RANGE` e `TS.MRANGE`

---

## Referências

- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Redis Sorted Sets](https://redis.io/docs/data-types/sorted-sets/)
- [Redis GEO](https://redis.io/docs/data-types/geospatial/)
- [Redis TimeSeries](https://redis.io/docs/data-types/timeseries/)
- [Redis Query Engine / RediSearch](https://redis.io/docs/interact/search-and-query/)
