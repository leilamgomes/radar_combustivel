# Trabalho Final em Grupo — Pipeline MongoDB → Redis
## Plataforma Radar Combustível

Este arquivo serve como base do conteúdo do PDF final a ser diagramado e exportado.

---

# 1. Capa

**MBA em Tecnologia — Database In-Memory**  
**Disciplina:** Database In-Memory  
**Trabalho Final em Grupo**  
**Título:** Pipeline MongoDB → Redis aplicado à Plataforma Radar Combustível  
**Ano:** 2026

---

# 2. Integrantes

| Nome | RM | Contribuição principal |
|---|---|---|
| [Preencher] | [Preencher] | [Preencher] |
| [Preencher] | [Preencher] | [Preencher] |
| [Preencher] | [Preencher] | [Preencher] |

Grupo com até 6 integrantes.

---

# 3. Descrição do problema

## 3.1 Contexto

A plataforma Radar Combustível acompanha postos, preços, buscas, avaliações e localização geográfica. O desafio do trabalho foi transformar esse conjunto de dados em uma camada de consulta rápida, adequada para responder perguntas de negócio com baixa latência.

## 3.2 Perguntas de negócio atendidas

1. Quais postos têm menor preço por região?
2. Quais combustíveis estão em alta?
3. Quais UFs, cidades e bairros têm maior volume de buscas?
4. Quais postos são mais bem avaliados?
5. Quais postos tiveram maior variação recente de preço?
6. Como os preços evoluem ao longo do tempo?
7. Quais postos estão próximos a um ponto de referência?

## 3.3 Problema técnico

O projeto precisava:

- usar MongoDB como fonte transacional/documental;
- construir um pipeline MongoDB → Redis;
- modelar estruturas Redis coerentes com o padrão de acesso;
- entregar visualização objetiva e executável.

---

# 4. Arquitetura da solução

## 4.1 Diagrama da arquitetura

> Inserir aqui o diagrama final da arquitetura.

Sugestão de elementos:
- MongoDB com 5 coleções;
- consumer Python;
- Redis Stack com Hashes, Sorted Sets, GEO, Time Series e RediSearch;
- dashboard Streamlit.

## 4.2 Visão geral da arquitetura

```text
MongoDB (5 coleções) → Python Consumer → Redis Stack → Dashboard Streamlit
```

## 4.3 Fluxo de dados

1. O seed oficial popula as 5 coleções do MongoDB.
2. O Redis recebe um snapshot inicial dos postos.
3. O consumer executa o backfill completo.
4. O Change Stream passa a processar novos inserts.
5. O dashboard consulta somente o Redis.

---

# 5. Pipeline MongoDB → Redis

## 5.1 Coleções utilizadas

| Coleção | Finalidade |
|---|---|
| `postos` | cadastro base |
| `localizacoes_postos` | UF, cidade, bairro e geo |
| `eventos_preco` | preço atual, preço anterior e variação |
| `buscas_usuarios` | comportamento de busca |
| `avaliacoes_interacoes` | avaliações e interações |

## 5.2 Ordem de processamento do backfill

```python
BACKFILL_ORDER = (
    "postos",
    "localizacoes_postos",
    "eventos_preco",
    "buscas_usuarios",
    "avaliacoes_interacoes",
)
```

Essa ordem garante que preço, geo, avaliação e ranking sejam processados sobre postos já existentes no Redis.

## 5.3 Change Stream

O consumer mantém escuta em tempo quase real para novos inserts das coleções monitoradas.

Observação importante:
- a solução em tempo real foi modelada para `insert`;
- o projeto não implementa replicação completa de `update` em documentos já existentes.

Isso foi considerado suficiente para o escopo do trabalho, porque a demonstração se apoia em seed + backfill + novos eventos append-only.

## 5.4 Resiliência

O pipeline implementa:

- reconexão automática;
- fallback para a base correta quando a configuração aponta para banco vazio;
- criação de séries temporais sob demanda;
- logs de progresso durante o backfill.

> Inserir print do terminal com o consumer em execução.

---

# 6. Estruturas Redis utilizadas

## 6.1 Estruturas e justificativa

| Estrutura | Chave | Motivo |
|---|---|---|
| Hash | `posto:{posto_id}` | snapshot de leitura rápida por posto |
| Sorted Set | `ranking:precos:*` | ranking de menor preço por região |
| Sorted Set | `ranking:combustiveis:buscas` | combustíveis em alta |
| Sorted Set | `ranking:cidades:buscas` | cidades mais buscadas |
| Sorted Set | `ranking:bairros:buscas` | bairros mais buscados |
| Sorted Set | `ranking:postos:avaliacao` | base para ranking de avaliação |
| Sorted Set | `ranking:postos:variacao_recente` | maior variação recente |
| GEO | `geo:postos` | consultas por proximidade |
| Time Series | `ts:preco:{posto_id}:{combustivel}` | evolução de preços |
| RediSearch | `idx:postos` | busca textual e filtros |

## 6.2 Decisão de modelagem

As estruturas foram escolhidas com base no padrão de acesso:

- leitura rápida por posto → Hash;
- ranking ordenado → Sorted Set;
- proximidade geográfica → GEO;
- histórico temporal → Time Series;
- busca textual e filtros → RediSearch.

## 6.3 Consulta de exemplo

```redis
ZREVRANGE ranking:combustiveis:buscas 0 4 WITHSCORES
```

```redis
GEOSEARCH geo:postos FROMLONLAT -46.6333 -23.5505 BYRADIUS 10 km ASC COUNT 20 WITHDIST
```

```redis
TS.MRANGE - + AGGREGATION AVG 3600000 FILTER metric=price combustivel=GASOLINA_COMUM
```

> Inserir print do Redis Insight ou redis-cli.

---

# 7. Visualizações e resultados

## 7.1 Aba 1 — Visão Geral

Entrega:
- KPIs
- combustíveis mais buscados
- UFs mais buscadas
- cidades mais buscadas
- bairros mais buscados

> Inserir print da aba.

## 7.2 Aba 2 — Top Avaliações

Entrega:
- ranking por **score ponderado**
- combinação entre nota média e número de avaliações

Importante:
- o projeto não usa apenas média simples;
- isso evita que um posto com 1 avaliação nota 5 lidere injustamente sobre um posto com muitas avaliações e nota consistente.

> Inserir print da aba.

## 7.3 Aba 3 — Ranking de Preço

Entrega:
- combustível
- UF obrigatória
- cidade opcional
- bairro opcional

O ranking exibe o preço atual mais recente consolidado por posto.

> Inserir print da aba.

## 7.4 Aba 4 — Variação de Preço

Entrega:
- filtro por combustível
- apenas registros com variação real
- tabela com destaque visual por tendência

> Inserir print da aba.

## 7.5 Aba 5 — Séries Temporais

Entrega:
- média diária por combustível
- linha de tendência de 7 dias
- histórico detalhado por posto com pelo menos 2 pontos

> Inserir print da aba.

## 7.6 Aba 6 — Proximidade

Entrega:
- busca por UF, cidade e bairro
- ou posto de referência
- expansão de raio quando necessário

> Inserir print da aba.

## 7.7 Pipeline em execução

> Inserir print do terminal com:
- backfill em progresso;
- backfill concluído;
- consumer aguardando inserts.

---

# 8. Conclusão

## 8.1 Resultado

O projeto implementa uma solução completa MongoDB → Redis com:

- base de dados adequada ao caso;
- pipeline funcional;
- estruturas Redis coerentes;
- visualização útil e executável;
- documentação alinhada à arquitetura.

## 8.2 Diferenciais positivos

- consultas geográficas com `GEOSEARCH`;
- séries temporais com `TS.RANGE` e `TS.MRANGE`;
- score ponderado para ranking de avaliação;
- ranking territorial por UF, cidade e bairro;
- interface refinada em Streamlit;
- tratamento básico de falhas e reconexão.

## 8.3 Limitação conhecida

O Change Stream em tempo real foi implementado para `insert`, e não como replicação completa de `update`. Essa limitação deve ser apresentada com transparência, mas não compromete o escopo obrigatório do trabalho.

---

# 9. Link do GitHub

**Repositório:** [Preencher link final]

---

# Checklist para gerar o PDF final

- [ ] preencher nomes e RMs
- [ ] inserir diagrama da arquitetura
- [ ] inserir prints das 6 abas
- [ ] inserir print do consumer
- [ ] inserir print do Redis
- [ ] inserir link final do GitHub
- [ ] exportar para PDF
