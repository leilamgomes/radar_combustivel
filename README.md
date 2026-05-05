# Trabalho Final — Pipeline MongoDB → Redis
## Plataforma Radar Combustível

Projeto da disciplina **Database In-Memory** com foco em modelagem orientada a acesso, pipeline MongoDB → Redis e camada de serving rápida para consultas analíticas do caso **Radar Combustível**.

---

## Objetivo

Transformar dados de postos, preços, localização, buscas e avaliações em uma camada de consulta rápida no Redis, capaz de responder perguntas como:

- quais postos têm menor preço por região;
- quais combustíveis estão em alta;
- quais UFs, cidades e bairros têm maior volume de buscas;
- quais postos são mais bem avaliados com critério justo de ranqueamento;
- quais postos tiveram maior variação recente de preço;
- como os preços evoluem ao longo do tempo;
- quais postos estão próximos a um ponto de referência.

---

## Arquitetura

```text
MongoDB (5 coleções) → Python Consumer → Redis Stack → Dashboard / Queries
```

Fluxo detalhado em [docs/streaming-mongo-redis.md](/C:/Users/leila/OneDrive/Documentos/MBA/radar-combustivel-fake-data-generator-main/docs/streaming-mongo-redis.md).

---

## Estrutura do repositório

```text
radar-combustivel-fake-data-generator-main/
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .env.local
├── PDF_TRABALHO_FINAL.md
├── README.md
├── docs/
│   └── streaming-mongo-redis.md
├── init/
│   ├── mongo_seed.py
│   └── redis_indexes.py
├── pipeline/
│   ├── event_transformer.py
│   └── mongodb_consumer.py
└── queries/
    ├── data-view.py
    └── redis_reader.py
```

---

## Base MongoDB

O projeto usa as 5 coleções exigidas pelo trabalho:

| Coleção | Função |
|---|---|
| `postos` | cadastro base dos postos |
| `localizacoes_postos` | UF, cidade, bairro e geo dos postos |
| `eventos_preco` | histórico e atualização de preços |
| `buscas_usuarios` | volume de buscas por combustível e território |
| `avaliacoes_interacoes` | avaliações e demais interações |

Importante: `init/mongo_seed.py` foi preservado como fonte oficial de dados.

---

## Estruturas Redis utilizadas

### Hashes
- `posto:{posto_id}` para snapshot resumido do posto

### Sorted Sets
- `ranking:precos:{combustivel}:cidade:{regiao}`
- `ranking:precos:{combustivel}:bairro:{regiao}`
- `ranking:combustiveis:buscas`
- `ranking:cidades:buscas`
- `ranking:bairros:buscas`
- `ranking:postos:avaliacao`
- `ranking:postos:variacao_recente`

### GEO
- `geo:postos`

### Time Series
- `ts:preco:{posto_id}:{combustivel}`

### RediSearch
- `idx:postos`

---

## Pipeline MongoDB → Redis

O consumer implementa:

- backfill inicial;
- roteamento por coleção;
- atualização incremental no Redis;
- escuta em tempo quase real via Change Stream;
- reconexão automática em caso de falha.

### Ordem de backfill

```python
BACKFILL_ORDER = (
    "postos",
    "localizacoes_postos",
    "eventos_preco",
    "buscas_usuarios",
    "avaliacoes_interacoes",
)
```

### Observação importante

No estado atual, o Change Stream em tempo real está configurado para escutar eventos de `insert`. Isso atende bem ao cenário do seed e da demonstração, mas o projeto não foi modelado como sincronização completa de `update` em documentos já existentes.

---

## Dashboard

O dashboard Streamlit foi organizado nas seguintes abas:

1. **Visão Geral**
2. **Top Avaliações**
3. **Ranking de Preço**
4. **Variação de Preço**
5. **Séries Temporais**
6. **Proximidade**

### O que cada aba entrega

**Visão Geral**
- KPIs principais
- combustíveis mais buscados
- UFs mais buscadas
- cidades mais buscadas
- bairros mais buscados

**Top Avaliações**
- ranking por **score ponderado**
- combina nota média e número de avaliações
- evita favorecer postos com apenas 1 avaliação

**Ranking de Preço**
- filtro por combustível
- filtro por UF obrigatório
- cidade opcional
- bairro opcional
- ranking por preço atual mais recente

**Variação de Preço**
- mostra apenas registros com variação real
- tabela colorida por tendência:
  - vermelho para alta
  - verde para queda
  - amarelo para manutenção

**Séries Temporais**
- evolução média diária do combustível
- tendência móvel de 7 dias
- histórico detalhado por posto com pelo menos 2 pontos

**Proximidade**
- busca por UF, cidade e bairro
- ou por posto de referência
- expansão de raio quando necessário

---

## Como executar

### 1. Subir a infraestrutura

```bash
docker-compose up -d
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Popular o MongoDB

```bash
python init/mongo_seed.py
```

Para teste rápido:

```bash
$env:N=200; python init/mongo_seed.py
```

### 4. Preparar o Redis

```bash
python init/redis_indexes.py
```

### 5. Iniciar o consumer

```bash
python pipeline/mongodb_consumer.py
```

### 6. Abrir reader textual

```bash
python queries/redis_reader.py
```

### 7. Abrir dashboard

```bash
python -m streamlit run queries/data-view.py
```

---

## Checklist de validação

- [ ] MongoDB e Redis sobem corretamente com Docker
- [ ] O seed popula as 5 coleções
- [ ] O Redis recebe hashes, rankings, GEO, Time Series e índice RediSearch
- [ ] O consumer executa backfill completo
- [ ] O dashboard lê exclusivamente do Redis
- [ ] A aba de proximidade usa `GEOSEARCH`
- [ ] A aba de séries temporais usa `TS.RANGE` e `TS.MRANGE`
- [ ] O ranking de avaliações usa score ponderado

---

## Referências

- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Redis Sorted Sets](https://redis.io/docs/data-types/sorted-sets/)
- [Redis GEO](https://redis.io/docs/data-types/geospatial/)
- [Redis TimeSeries](https://redis.io/docs/data-types/timeseries/)
- [Redis Query Engine / RediSearch](https://redis.io/docs/interact/search-and-query/)
