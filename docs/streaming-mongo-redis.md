# Streaming MongoDB → Redis neste projeto

Este documento descreve a arquitetura real implementada no projeto **Plataforma Radar Combustível**, com foco na passagem dos dados do MongoDB para o Redis e na forma como o dashboard consome a camada de serving.

---

## Visão geral do fluxo

1. `init/mongo_seed.py` popula 5 coleções no MongoDB.
2. `init/redis_indexes.py` cria o snapshot inicial dos postos no Redis.
3. `pipeline/mongodb_consumer.py` executa o backfill completo.
4. Depois do backfill, o consumer mantém o Redis atualizado com Change Stream.
5. `queries/data-view.py` e `queries/redis_reader.py` consultam somente o Redis.

---

## Coleções da origem

| Coleção | Papel |
|---|---|
| `postos` | dados cadastrais do posto |
| `localizacoes_postos` | localização e recorte territorial |
| `eventos_preco` | evolução e atualização de preços |
| `buscas_usuarios` | comportamento de busca |
| `avaliacoes_interacoes` | avaliações e interações |

---

## Backfill e ordem de processamento

A ordem do backfill foi organizada para garantir integridade no Redis:

```python
BACKFILL_ORDER = (
    "postos",
    "localizacoes_postos",
    "eventos_preco",
    "buscas_usuarios",
    "avaliacoes_interacoes",
)
```

### Motivo da ordem

- `postos`: cria a base do hash
- `localizacoes_postos`: completa UF, cidade, bairro e geo
- `eventos_preco`: atualiza preço já com posto existente
- `buscas_usuarios`: incrementa popularidade e demanda territorial
- `avaliacoes_interacoes`: compõe score e ranking de avaliação

---

## Change Stream

O projeto usa Change Stream para ingestão incremental.

### Comportamento atual

- escuta eventos de `insert`
- aplica a transformação por coleção
- atualiza as estruturas de serving no Redis

---

## Estruturas Redis e uso analítico

| Estrutura | Exemplo | Uso |
|---|---|---|
| Hash | `posto:{posto_id}` | snapshot resumido do posto |
| Sorted Set | `ranking:precos:*` | menor preço por região |
| Sorted Set | `ranking:combustiveis:buscas` | combustíveis em alta |
| Sorted Set | `ranking:cidades:buscas` | cidades mais buscadas |
| Sorted Set | `ranking:bairros:buscas` | bairros mais buscados |
| Sorted Set | `ranking:postos:avaliacao` | base do ranking de avaliação |
| Sorted Set | `ranking:postos:variacao_recente` | maior variação recente |
| GEO | `geo:postos` | proximidade |
| Time Series | `ts:preco:{posto_id}:{combustivel}` | histórico de preços |
| RediSearch | `idx:postos` | busca textual e geoespacial |

---

## Transformações relevantes

### Preço

- grava preço atual e preço anterior no hash
- guarda timestamp de atualização do combustível
- atualiza rankings por cidade e bairro
- alimenta Time Series
- alimenta ranking de maior variação recente

### Buscas

- incrementa ranking de combustíveis
- incrementa ranking de cidades e bairros
- permite derivar UFs mais buscadas na interface

### Avaliações

- acumula `rating_sum`
- acumula `rating_count`
- calcula `avg_rating`
- grava o ranking base de avaliação

Na interface, o ranking final de avaliações não usa só média simples. Ele usa **score ponderado**, combinando:
- nota média;
- número de avaliações;
- média global;
- mínimo de confiança.

---

## Dashboard e consultas

### Visão Geral

- KPIs principais
- combustíveis mais buscados
- UFs, cidades e bairros com maior demanda

### Top Avaliações

- ranking por score ponderado
- gráfico horizontal por número de avaliações e força da nota

### Ranking de Preço

- combustível obrigatório
- UF obrigatória
- cidade opcional
- bairro opcional

### Variação de Preço

- apenas registros com variação diferente de zero
- destaque visual por cor de linha

### Séries Temporais

- média diária do combustível
- tendência móvel de 7 dias
- histórico detalhado apenas para postos com pelo menos 2 pontos

### Proximidade

- busca por território ou posto de referência
- expansão automática de raio quando necessário

---

## Resiliência

O consumer implementa:

- reconexão automática;
- fallback de banco quando a configuração aponta para base vazia;
- criação preguiçosa de séries temporais;
- backfill completo antes de escuta contínua.

---

## Resumo arquitetural

O projeto atende o núcleo exigido pela disciplina:

- modelagem orientada a consulta;
- Redis como camada de serving;
- pipeline MongoDB → Redis funcional;
- uso adequado de Hash, Sorted Set, GEO e Time Series;
- visualização prática e demonstrável.

---