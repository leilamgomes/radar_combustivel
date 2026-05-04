# Trabalho Final em Grupo — Pipeline MongoDB → Redis
## Plataforma Radar Combustível

---

# 1. CAPA

**MBA em Tecnologia - Database In-Memory**

**Disciplina:** Database In-Memory

**Trabalho Final em Grupo**

**Título:** Pipeline de Dados em Tempo Real: MongoDB → Redis para Plataforma Radar Combustível

**Data:** 2026

---

# 2. INTEGRANTES

| Nome | RM | Contribuição Principal |
|------|-----|------------------------|
| [Nome do Integrante 1] | [RM] | [Descrever contribuição] |
| [Nome do Integrante 2] | [RM] | [Descrever contribuição] |
| [Nome do Integrante 3] | [RM] | [Descrever contribuição] |
| [Adicionar mais integrantes se necessário] | | |

**Grupo com até 6 integrantes**

---

# 3. DESCRIÇÃO DO PROBLEMA

## 3.1 Contexto do Caso Radar Combustível

A plataforma **Radar Combustível** acompanha informações de postos de gasolina, preços de combustíveis, localização geográfica, buscas e interações dos usuários em todo o território brasileiro. O objetivo do projeto é transformar esses dados transacionais em uma **camada de consulta rápida** capaz de responder perguntas de negócio em tempo real.

## 3.2 Problemas de Negócio a Resolver

O trabalho foi desenvolvido para responder às seguintes perguntas críticas:

1. **Quais postos estão com menor preço por região?**
   - Permitir que usuários encontrem o combustível mais barato próximo a eles

2. **Quais combustíveis estão em alta?**
   - Identificar tendências de busca e demanda por tipo de combustível

3. **Quais bairros e cidades apresentam maior volume de buscas?**
   - Mapear o comportamento geográfico dos usuários

4. **Quais postos tiveram maior variação recente de preço?**
   - Alertar sobre oscilações de preço no mercado

5. **Como os preços evoluem ao longo do tempo?**
   - Análise histórica e temporal de preços por posto e combustível

6. **Quais postos existem próximos a um ponto de referência?**
   - Busca geográfica por proximidade

## 3.3 Desafio Técnico

O desafio principal consiste em construir um **pipeline de dados em tempo quase real** que:
- Capture eventos e entidades do MongoDB (camada transacional/documental)
- Processe e transforme esses dados
- Disponibilize em Redis (camada de serving) para consultas de baixa latência

---

# 4. ARQUITETURA DA SOLUÇÃO

## 4.1 Diagrama da Arquitetura

> **[INSERIR IMAGEM DO DIAGRAMA DE ARQUITETURA AQUI]**
> 
> *Sugestão: Criar um diagrama mostrando:*
> - *MongoDB com as 5 coleções*
> - *Seta para "Python Consumer (Change Stream)"*
> - *Seta para "Redis Stack" com as estruturas de dados*
> - *Seta para "Dashboard / Queries"*
> 
> *Ferramentas sugeridas: draw.io, Lucidchart, ou diagrama ASCII no README*

## 4.2 Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MONGODB (Fonte)                             │
│  ┌──────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐  │
│  │  postos  │ │eventos_preco│ │buscas_user  │ │avaliacoes_inter  │  │
│  └──────────┘ └─────────────┘ └─────────────┘ └──────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              localizacoes_postos                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Change Stream
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PIPELINE PYTHON CONSUMER                         │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Backfill   │  │   Event      │  │    Time      │             │
│  │   (batch)    │→ │   Router     │→ │   Series     │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│                           ↓                                        │
│                    ┌──────────────┐                              │
│                    │  Transform   │                              │
│                    └──────────────┘                              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      REDIS (Camada de Serving)                      │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  HASHES        │  SORTED SETS      │  GEO      │  TS       │  │
│  │  ─────────     │  ───────────      │  ────     │  ───      │  │
│  │  posto:{id}    │  ranking:precos   │ geo:postos│ ts:preco  │  │
│  │                │  ranking:buscas   │           │           │  │
│  │                │  ranking:avaliacao│           │           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                         ↓                                          │
│              ┌───────────────────┐                                 │
│              │  idx:postos       │  (RediSearch)                  │
│              └───────────────────┘                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    VISUALIZAÇÃO (Streamlit)                         │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Visão    │ │ Top      │ │ Ranking  │ │ Variação │ │ Séries   │ │
│  │ Geral    │ │ Avalia   │ │ Preço    │ │ Preço    │ │ Temporais│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐                                                      │
│  │ Proximi  │                                                      │
│  │ dade     │                                                      │
│  └──────────┘                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 4.3 Fluxo de Dados

1. **Ingestão Inicial:** `mongo_seed.py` popula 5 coleções no MongoDB (100k documentos cada)
2. **Indexação Redis:** `redis_indexes.py` cria snapshot inicial dos postos no Redis
3. **Pipeline Backfill:** `mongodb_consumer.py` processa documentos existentes na ordem correta
4. **Processamento em Tempo Real:** Change Stream captura novos inserts e atualiza Redis
5. **Consultas:** Dashboard Streamlit lê exclusivamente do Redis

---

# 5. PIPELINE MONGODB → REDIS

## 5.1 Componentes do Pipeline

### 5.1.1 MongoDB (Fonte de Eventos)

O MongoDB armazena 5 coleções principais conforme escopo obrigatório:

| Coleção | Propósito | Campos-chave |
|---------|-----------|--------------|
| `postos` | Cadastro de postos | cnpj, nome_fantasia, bandeira, endereco, location (GeoJSON) |
| `eventos_preco` | Atualizações de preço | posto_id, combustivel, preco_anterior, preco_novo, variacao_pct, ocorrido_em |
| `buscas_usuarios` | Buscas realizadas | usuario_id, tipo_combustivel, cidade, estado, geo_centro, consultado_em |
| `avaliacoes_interacoes` | Interações dos usuários | posto_id, tipo, nota, util_count, created_at |
| `localizacoes_postos` | Localização detalhada | posto_id, municipio, bairro, uf, codigo_ibge, geo |

> **[INSERIR PRINT DO MONGO COMPASS OU MONGOSH MOSTRANDO AS COLEÇÕES]**
>
> ```bash
> > use radar_combustivel
> > show collections
> > db.postos.countDocuments()
> > db.eventos_preco.countDocuments()
> ```

### 5.1.2 Change Stream

O MongoDB Change Stream captura eventos de insert em tempo real:

```python
pipeline = [
    {"$match": {"operationType": "insert", "ns.coll": {"$in": list(COLECOES_SUPORTADAS)}}}
]
with db.watch(pipeline, full_document="updateLookup") as stream:
    for change in stream:
        collection_name = change["ns"]["coll"]
        handle_event(redis, collection_name, change["fullDocument"])
```

> **[INSERIR PRINT DO TERMINAL MOSTRANDO O CONSUMER RODANDO]**
> 
> *Exemplo de saída esperada:*
> ```
> [CONSUMER] Banco selecionado: radar_combustivel (500000 documentos detectados).
> [CONSUMER] Iniciando backfill de postos...
> [CONSUMER] Progresso postos: 5000 documentos processados.
> [CONSUMER] Backfill concluído em postos: 100000 documentos.
> [CONSUMER] Conectado ao MongoDB Change Stream
> [CONSUMER] Aguardando inserts nas coleções monitoradas...
> [EVENT] preco | 664b8... | GASOLINA_COMUM | 5.234 -> 5.189
> [REDIS] ZADD ranking de preço | GASOLINA_COMUM | posto=664b8... | preço=5.189
> ```

### 5.1.3 Ordem de Processamento (Backfill)

A ordem correta de processamento é crítica para integridade:

```
1. postos              → Cria hashes base no Redis
2. localizacoes_postos → Atualiza dados geográficos
3. eventos_preco       → Atualiza preços (postos já existem)
4. buscas_usuarios     → Incrementa contadores de busca
5. avaliacoes_interacoes → Atualiza ratings e interações
```

## 5.2 Lógica de Transformação

Cada coleção passa por uma função de normalização específica:

| Entidade | Função | Saída |
|----------|--------|-------|
| `postos` | `normalize_posto()` | `entity: "posto"` com dados cadastrais |
| `localizacoes_postos` | `normalize_localizacao()` | `entity: "localizacao"` com geo enriquecido |
| `eventos_preco` | `normalize_evento_preco()` | `entity: "preco"` com variação calculada |
| `buscas_usuarios` | `normalize_busca()` | `entity: "busca"` com filtros e localização |
| `avaliacoes_interacoes` | `normalize_avaliacao()` | `entity: "interacao"` com tipo e nota |

> **[INSERIR PRINT DE CÓDIGO OU TERMINAL MOSTRANDO A TRANSFORMAÇÃO]**

## 5.3 Tratamento de Falhas

O pipeline implementa:

- **Reconexão automática:** `try/except` com `time.sleep(2)` no Change Stream
- **Fallback de banco:** `resolve_database_name()` detecta banco com dados automaticamente
- **Progress reporting:** Log a cada 5000 documentos no backfill
- **Duplicate handling:** `ON_DUPLICATE LAST` no Time Series

---

# 6. ESTRUTURAS REDIS UTILIZADAS

## 6.1 Tabela de Estruturas e Justificativas

| Estrutura | Chave (exemplo) | Dados Armazenados | Por Que Foi Escolhida |
|-----------|-----------------|-------------------|----------------------|
| **Hash** | `posto:{posto_id}` | Dados completos do posto (nome, bandeira, endereço, preços atuais por combustível, avaliação média, contadores) | Acesso O(1) a todos os atributos de um posto. Estrutura ideal para armazenar objetos complexos com múltiplos campos. |
| **Sorted Set** | `ranking:precos:{combustivel}:cidade:{uf\|cidade}` | Posto ID → Preço (score) | Permite consulta "menor preço em uma cidade" com `ZRANGE` em O(log N). Mantém ordenação automática por preço. |
| **Sorted Set** | `ranking:precos:{combustivel}:bairro:{uf\|cidade\|bairro}` | Posto ID → Preço (score) | Mesma lógica acima, granularidade de bairro para buscas mais precisas. |
| **Sorted Set** | `ranking:combustiveis:buscas` | Combustível → Número de buscas | Contador ordenado. Permite identificar "combustíveis em alta" com `ZREVRANGE`. |
| **Sorted Set** | `ranking:bairros:buscas` | Bairro composto → Número de buscas | Mapeia volume de buscas por território. |
| **Sorted Set** | `ranking:cidades:buscas` | Cidade composta → Número de buscas | Mapeia volume de buscas por cidade. |
| **Sorted Set** | `ranking:postos:avaliacao` | Posto ID → Nota média | Ranking de postos mais bem avaliados. |
| **Sorted Set** | `ranking:postos:variacao_recente` | `{posto_id}\|{combustivel}` → Variação % absoluta | Identifica postos com maior oscilação de preço. |
| **GEO** | `geo:postos` | Longitude, Latitude, Posto ID | Permite busca por proximidade com `GEOSEARCH` em raio de km. Essencial para "postos perto de mim". |
| **Time Series** | `ts:preco:{posto_id}:{combustivel}` | Timestamp → Preço | Série temporal com labels (cidade, bairro, uf). Suporta agregações (`TS.MRANGE`) e análise de evolução de preços. |
| **RediSearch** | `idx:postos` | Índice full-text sobre hashes | Busca por texto em nome de posto, filtros por tag (bandeira, cidade, bairro, uf), busca geoespacial combinada. |

## 6.2 Diagrama das Estruturas

> **[INSERIR DIAGRAMA OU ESQUEMA DAS ESTRUTURAS REDIS]**

```
┌─────────────────────────────────────────────────────────────────┐
│                      ESTRUTURAS REDIS                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  HASHES                    SORTED SETS                         │
│  ┌────────────────┐        ┌─────────────────────────────┐    │
│  │ posto:abc123   │        │ ranking:precos:gasolina:... │    │
│  │ ─────────────  │        │ posto:abc123 → 5.19         │    │
│  │ nome: Posto X  │        │ posto:def456 → 5.25         │    │
│  │ cidade: SP     │        └─────────────────────────────┘    │
│  │ preco_gasolina │                                           │
│  │   _comum: 5.19 │        ┌─────────────────────────────┐    │
│  │ ...            │        │ ranking:combustiveis:buscas │    │
│  └────────────────┘        │ GASOLINA_COMUM → 15234      │    │
│                            │ ETANOL → 8934                 │    │
│  GEO                       └─────────────────────────────┘    │
│  ┌────────────────┐                                           │
│  │ geo:postos     │        TIME SERIES                         │
│  │ ─────────────  │        ┌─────────────────────────────┐    │
│  │ -46.63 -23.55  │        │ ts:preco:abc123:gasolina_   │    │
│  │   posto:abc123 │        │   comum                     │    │
│  │ -46.64 -23.56  │        │ ─────────────────────────── │    │
│  │   posto:def456 │        │ 1717353600000 → 5.19        │    │
│  └────────────────┘        │ 1717357200000 → 5.21        │    │
│                            │ labels: cidade=SP, ...      │    │
│  REDISEARCH                └─────────────────────────────┘    │
│  ┌────────────────┐                                           │
│  │ idx:postos     │                                           │
│  │ ─────────────  │                                           │
│  │ nome (text)    │                                           │
│  │ bandeira (tag) │                                           │
│  │ cidade (tag)   │                                           │
│  │ location (geo) │                                           │
│  └────────────────┘                                           │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

## 6.3 Exemplos de Consultas

### Menor preço por cidade
```redis
ZRANGE ranking:precos:gasolina_comum:cidade:sp|sao_paulo 0 9 WITHSCORES
```

### Combustíveis mais buscados
```redis
ZREVRANGE ranking:combustiveis:buscas 0 4 WITHSCORES
```

### Postos próximos (raio de 10km)
```redis
GEOSEARCH geo:postos FROMLONLAT -46.6333 -23.5505 BYRADIUS 10 km ASC COUNT 20 WITHDIST
```

### Evolução de preço (série temporal)
```redis
TS.RANGE ts:preco:abc123:gasolina_comum - + AGGREGATION AVG 3600000
```

### Média de preços por combustível (agregação)
```redis
TS.MRANGE - + AGGREGATION AVG 3600000 FILTER metric=price combustivel=GASOLINA_COMUM
```

> **[INSERIR PRINT DO REDIS-CLI OU REDIS INSIGHT MOSTRANDO AS CONSULTAS]**

---

# 7. VISUALIZAÇÕES E RESULTADOS

## 7.1 Dashboard Streamlit

O dashboard foi desenvolvido em Streamlit com 6 abas principais:

### Aba 1: Visão Geral
Mostra KPIs principais e tendências de busca.

> **[INSERIR PRINT DA ABA "VISÃO GERAL"]**
>
> *Elementos a capturar:*
> - Cards com métricas (Postos indexados, Volume de buscas, Postos no GEO, Média de avaliações)
> - Gráfico de barras "Combustíveis mais buscados"
> - Gráficos de UFs, Cidades e Bairros mais buscados

### Aba 2: Top Avaliações
Relação entre nota média e número de avaliações.

> **[INSERIR PRINT DA ABA "TOP AVALIAÇÕES"]**
>
> *Elementos a capturar:*
> - Scatter plot: nota média vs número de avaliações
> - Tabela com top 10 postos

### Aba 3: Ranking de Preço
Filtros por combustível, UF, cidade e bairro.

> **[INSERIR PRINT DA ABA "RANKING DE PREÇO"]**
>
> *Elementos a capturar:*
> - Filtros dropdown (combustível, UF, cidade, bairro)
> - Gráfico de barras com postos mais baratos
> - Tabela com detalhes

### Aba 4: Variação de Preço
Postos com maiores variações recentes.

> **[INSERIR PRINT DA ABA "VARIAÇÃO DE PREÇO"]**
>
> *Elementos a capturar:*
> - Filtro de combustível
> - Tabela com preço antigo, atual, variação % e direção (⬆️ ⬇️ ➡️)

### Aba 5: Séries Temporais
Evolução de preços ao longo do tempo.

> **[INSERIR PRINT DA ABA "SÉRIES TEMPORAIS"]**
>
> *Elementos a capturar:*
> - Gráfico de linha: evolução média do combustível
> - Gráfico de linha: histórico de um posto específico

### Aba 6: Proximidade
Busca geográfica com mapa.

> **[INSERIR PRINT DA ABA "PROXIMIDADE"]**
>
> *Elementos a capturar:*
> - Seletor de UF/cidade/bairro ou posto de referência
> - Slider de raio (km)
> - Mapa com marcadores
> - Tabela de postos próximos com distância

## 7.2 Pipeline em Execução

> **[INSERIR PRINT DO TERMINAL MOSTRANDO O CONSUMER PROCESSANDO]**
>
> ```
> [CONSUMER] Banco selecionado: radar_combustivel (500000 documentos detectados).
> [CONSUMER] Iniciando backfill de postos...
> [CONSUMER] Progresso postos: 5000 documentos processados.
> ...
> [CONSUMER] Backfill concluído: 500000 documentos processados.
> [CONSUMER] Conectado ao MongoDB Change Stream
> [CONSUMER] Aguardando inserts nas coleções monitoradas...
> [EVENT] preco | 664b8f12... | GASOLINA_COMUM | 5.234 -> 5.189
> [REDIS] ZADD ranking de preço | GASOLINA_COMUM | posto=664b8f12... | preço=5.189
> [EVENT] busca | ETANOL | São Paulo
> [REDIS] ZINCRBY ranking:combustiveis:buscas 1 ETANOL
> ```

## 7.3 Redis com Dados Populados

> **[INSERIR PRINT DO REDIS INSIGHT OU REDIS-CLI MOSTRANDO]**
>
> - Keys existentes: `KEYS *`
> - Hash de um posto: `HGETALL posto:{id}`
> - Sorted Set de ranking: `ZRANGE ranking:precos:... 0 9 WITHSCORES`
> - Geo: `GEOPOS geo:postos {posto_id}`
> - Time Series: `TS.INFO ts:preco:...`

---

# 8. CONCLUSÃO

## 8.1 Resumo da Solução

Este trabalho demonstrou a implementação completa de um **pipeline de dados em tempo quase real** usando MongoDB como fonte de eventos e Redis como camada de serving, aplicado ao caso da Plataforma Radar Combustível.

Os principais entregáveis foram:

1. ✅ **Base de dados no MongoDB** com 5 coleções conforme escopo obrigatório
2. ✅ **Pipeline MongoDB → Redis** funcional com Change Stream e backfill
3. ✅ **Estruturas Redis adequadas:** Hashes, Sorted Sets, Geo, Time Series e RediSearch
4. ✅ **Camada de visualização** em Streamlit com 6 abas cobrindo todas as perguntas de negócio
5. ✅ **Documentação completa** do repositório

## 8.2 Diferenciais Implementados

- ✅ Consultas geográficas com `GEOSEARCH`
- ✅ Séries temporais de preço com `TS.MRANGE` e agregações
- ✅ Rankings hierárquicos (cidade + bairro)
- ✅ RediSearch para busca full-text e filtros combinados
- ✅ Interface refinada com tema visual customizado
- ✅ Auto-refresh do dashboard
- ✅ Tratamento de falhas e reconexão automática

## 8.3 Aprendizados

O projeto consolidou os conceitos trabalhados na disciplina:
- Modelagem orientada a acesso
- Redis como camada de leitura rápida
- Pipeline de atualização orientado a eventos
- Decisão adequada de estruturas de dados
- Visualização de resultados em interface simples

---

# 9. LINK DO GITHUB

**Repositório:** [https://github.com/{usuario}/{repositorio}](https://github.com/{usuario}/{repositorio})

**Estrutura do Repositório:**
```
radar-combustivel-fake-data-generator-main/
├── docker-compose.yml
├── requirements.txt
├── .env.example
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

## CHECKLIST DE ENTREGA

- [ ] PDF gerado com todas as seções
- [ ] Diagrama da arquitetura inserido
- [ ] Prints das 6 abas do Streamlit
- [ ] Print do pipeline/consumer em execução
- [ ] Print do Redis com dados
- [ ] Link do GitHub funcional
- [ ] Nomes e RMs dos integrantes preenchidos

---

*Documento gerado para Trabalho Final - Database In-Memory*
*MBA em Tecnologia - 2026*
