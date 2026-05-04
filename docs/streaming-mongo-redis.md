# Como funciona o streaming MongoDB → Redis neste projeto

Este projeto adapta o lab base de restaurantes para o domínio de combustíveis, preservando a mesma linha de arquitetura: um consumidor Python faz o backfill inicial, acompanha inserts via Change Stream no MongoDB e mantém estruturas otimizadas no Redis para serving em tempo real.

## Visão geral do fluxo

1. O seed oficial `init/mongo_seed.py` popula cinco coleções no MongoDB:
   - `postos`
   - `eventos_preco`
   - `buscas_usuarios`
   - `avaliacoes_interacoes`
   - `localizacoes_postos`
2. O script `init/redis_indexes.py` prepara os hashes iniciais, a estrutura GEO e o índice RediSearch `idx:postos`.
3. O consumidor `pipeline/mongodb_consumer.py` processa primeiro o histórico já existente.
4. Em seguida, ele abre um Change Stream no database e escuta novos inserts nas cinco coleções.
5. Cada documento passa por `pipeline/event_transformer.py`, que normaliza o formato antes de aplicar as atualizações no Redis.

## Pré-requisito: Replica Set no MongoDB

O Change Stream exige MongoDB em Replica Set (`rs0`).

No projeto:
- `docker-compose.yml` sobe o Mongo com `--replSet rs0`
- o serviço `mongo-init` inicializa o Replica Set automaticamente

## Papel de cada coleção no pipeline

### `postos`
- cria o snapshot principal do posto no hash `posto:{posto_id}`
- preenche dados cadastrais como nome, bandeira, CNPJ e endereço

### `localizacoes_postos`
- complementa o hash do posto com município, bairro, UF e código IBGE
- atualiza a estrutura `geo:postos` para consultas de proximidade

### `eventos_preco`
- atualiza o preço corrente do combustível no hash do posto
- mantém rankings de menor preço por combustível e por recorte regional
- grava a evolução dos preços em `RedisTimeSeries`
- atualiza o ranking de maior variação recente

### `buscas_usuarios`
- incrementa os rankings de combustíveis mais buscados
- incrementa os rankings de UFs, cidades e bairros com maior volume de buscas
- pode ser combinada na interface com os demais rankings territoriais na aba **Visão Geral**

### `avaliacoes_interacoes`
- calcula média de avaliações por posto
- mantém o ranking dos postos mais bem avaliados
- acumula favoritos, compartilhamentos, denúncias e check-ins no hash do posto

## Estruturas Redis utilizadas

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `posto:{posto_id}` | Hash | Resumo operacional do posto |
| `ranking:precos:{combustivel}:cidade:{regiao}` | Sorted Set | Menor preço por cidade |
| `ranking:precos:{combustivel}:bairro:{regiao}` | Sorted Set | Menor preço por bairro |
| `ranking:combustiveis:buscas` | Sorted Set | Combustíveis mais buscados |
| `ranking:bairros:buscas` | Sorted Set | Bairros com maior volume de buscas |
| `ranking:cidades:buscas` | Sorted Set | Cidades com maior volume de buscas |
| `ranking:postos:avaliacao` | Sorted Set | Postos mais bem avaliados |
| `ranking:postos:variacao_recente` | Sorted Set | Maior variação percentual recente |
| `geo:postos` | GEO | Busca de postos por proximidade |
| `ts:preco:{posto_id}:{combustivel}` | TimeSeries | Histórico de preços por posto e combustível |
| `idx:postos` | RediSearch Index | Busca textual e geoespacial sobre os hashes |

## Como a interface final foi organizada

O dashboard Streamlit ficou dividido em 6 abas:

1. **Visão Geral**
2. **Top Avaliações**
3. **Ranking de Preço**
4. **Variação de Preço**
5. **Séries Temporais**
6. **Proximidade**

Na aba **Visão Geral**, além dos KPIs principais, o painel reúne:
- combustíveis mais buscados
- UFs mais buscadas
- cidades mais buscadas
- bairros mais buscados

## Regras de modelagem importantes

- O seed em `init/mongo_seed.py` não é alterado.
- Todo mapeamento é feito no pipeline e no consumidor.
- Os preços usam `ZADD` em ordem natural crescente, então o menor preço sai com `ZRANGE`.
- A popularidade de combustível, bairros e cidades usa `ZINCRBY`.
- A proximidade usa `GEOADD` e `GEOSEARCH`.
- A evolução temporal usa `TS.ADD`, `TS.RANGE` e `TS.MRANGE`.

## Como executar

1. Suba a infraestrutura:
   - `docker-compose up -d`
2. Popule o MongoDB com o seed oficial:
   - `python init/mongo_seed.py`
3. Prepare o Redis:
   - `python init/redis_indexes.py`
4. Inicie o consumidor:
   - `python pipeline/mongodb_consumer.py`
5. Abra consultas em tempo real:
   - `python queries/redis_reader.py`
6. Abra o dashboard:
   - `python -m streamlit run queries/data-view.py`

## O que o dashboard responde

1. Quais postos têm menor preço por região
2. Quais combustíveis estão em alta
3. Quais UFs, cidades e bairros têm maior volume de buscas
4. Quais são os postos mais bem avaliados
5. Quais postos tiveram maior variação recente de preço
6. Como os preços evoluem ao longo do tempo
7. Quais postos existem perto de um ponto de referência

## Resiliência

O consumidor roda em loop contínuo:
- tenta reconectar se o stream cair
- faz backfill antes de entrar no modo streaming
- trata criação preguiçosa das séries temporais quando necessário
