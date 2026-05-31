# ORQUESTRA — Documentação da aplicação (UI + Airflow + SQL)

Este documento descreve como a aplicação **ORQUESTRA** se organiza no repositório, quais são as **DAGs**, as **procedures/tabelas** (SQL Server) e como a **UI** se relaciona com o Airflow via API.

---

## 1) Visão geral da arquitetura

**Componentes principais**

- **UI (SPA estática)**: `ui/index.html`
  - Faz login no Airflow via **Basic Auth**.
  - Dispara DAG Runs via **Airflow REST API** (`/api/v1/...`).
  - Para consultas (Read), lê o retorno via **XCom** (`xcomEntries/return_value`).

- **Airflow (DAGs Python)**: `dags/*.py`
  - Executa DAGs de **cadastro** (Create/Update) e de **consulta** (Read).
  - Integra com **SQL Server** via `MsSqlHook` usando o conn_id: `SQL14_DMDB41`.

- **SQL Server (DMDB41)**: `script/tabela/*.sql` + `script/proc/*.sql`
  - Modela as entidades (pipelines, jobs, lineage, execução).
  - Centraliza regras de upsert/reorder via stored procedures.

---

## 2) Estrutura do repositório

```
config/
  webserver_config.py            # config do Airflow webserver

dags/
  etl_dag_factory.py             # factory/geração/gestão de DAGs (ver seção 5)
  etl_pipeline_query.py          # consulta pipelines (Read)
  etl_pipeline_register.py       # upsert pipeline (Create/Update) + soft delete via active
  etl_pipeline_job_query.py      # consulta jobs (Read)
  etl_pipeline_job_register.py   # upsert job (Create/Update) + lineage obrigatório
  etl_pipeline_job_reorder.py    # reorder de jobs (Update somente execution_order)

script/
  tabela/
    etl_pipeline.sql
    etl_pipeline_job.sql
    etl_job_lineage.sql
    etl_job_execution.sql
  proc/
    sp_etl_pipeline_upsert.sql
    sp_etl_pipeline_job_upsert.sql
    sp_etl_pipeline_job_reorder.sql
    sp_etl_job_lineage_upsert.sql
    sp_etl_job_execution_log.sql
    sp_etl_pipelines_pendentes_criar.sql

ui/
  index.html
  ORQUESTRA_Spec_Login_v1.docx
  ORQUESTRA_Spec_Melhorias_Visuais_v1.docx

docker-compose.yaml
Dockerfile
README.md
```

---

## 3) Modelo de dados (SQL Server)

### 3.1 Tabela `dbo.etl_pipeline` (`script/tabela/etl_pipeline.sql`)

Chave primária: `pipeline_name`

Campos principais:
- `pipeline_name` (PK)
- `scheduled_time`
- `active` (soft delete do pipeline)
- `project_name`, `domain`, `tags`
- flags: `ENVIA_MSG_INICIO`, `ENVIA_MSG_FIM`, `ENVIA_MSG_ERRO`, `DAG_CRIADA`
- `last_execution`, `created_at`, `updated_at`

### 3.2 Tabela `dbo.etl_pipeline_job` (`script/tabela/etl_pipeline_job.sql`)

Chave primária composta: `(pipeline_name, job_name)`

Campos principais:
- `pipeline_name` (FK para `etl_pipeline.pipeline_name`)
- `job_name`
- `execution_order`
- `job_type` (ex.: datastage/shell/python/storedproc)
- `job_command`
- `created_at`, `updated_at`

> Observação: atualmente **não existe** coluna `active` para jobs. Portanto, “inativar job” ainda não está implementado no banco para jobs.

### 3.3 Tabela `dbo.etl_job_lineage` (`script/tabela/etl_job_lineage.sql`)

Relaciona o lineage de cada job, com FK para `(pipeline_name, job_name)` em `etl_pipeline_job`.

Campos principais:
- `direction` (`origem` | `destino`)
- `object_type` (ex.: Tabela, View, Arquivo, Proc, Query)
- `object_name` (ex.: `dbo.tabela`)

### 3.4 Tabela `dbo.etl_job_execution` (`script/tabela/etl_job_execution.sql`)

Tabela voltada para logging/rastreio de execução (usada por `sp_etl_job_execution_log.sql`).

---

## 4) Stored Procedures (regras de escrita)

### 4.1 `sp_etl_pipeline_upsert` (`script/proc/sp_etl_pipeline_upsert.sql`)

Upsert de pipeline.
- Se existe `pipeline_name`: faz `UPDATE`
- Se não existe: faz `INSERT`

Também grava:
- flags de envio de mensagem
- `DAG_CRIADA`
- `active` (usado pela UI para “Inativar pipeline” = `active=0`)

### 4.2 `sp_etl_pipeline_job_upsert` (`script/proc/sp_etl_pipeline_job_upsert.sql`)

Upsert de job dentro do pipeline (chave: pipeline+job_name).
- Atualiza `execution_order`, `job_type`, `job_command`, `updated_at`

### 4.3 `sp_etl_job_lineage_upsert` (`script/proc/sp_etl_job_lineage_upsert.sql`)

Upsert do lineage por:
`pipeline_name`, `job_name`, `direction`, `object_name` (e atualiza `object_type`).

### 4.4 `sp_etl_pipeline_job_reorder` (`script/proc/sp_etl_pipeline_job_reorder.sql`)

Atualiza **somente** `execution_order` e `updated_at` do job, sem mexer em `job_type`, `job_command` e sem tocar em lineage.

> Esse é o caminho usado pela UI para o “Salvar ordem” (edição inline).

### 4.5 Outras procs

- `sp_etl_job_execution_log.sql`: logging de execução.
- `sp_etl_pipelines_pendentes_criar.sql`: apoio ao processo de criação/pendências (dependente do fluxo interno).

---

## 5) DAGs do Airflow (Python)

Todas as DAGs usam `MsSqlHook(mssql_conn_id="SQL14_DMDB41")`.

### 5.1 `etl_pipeline_register` (`dags/etl_pipeline_register.py`)

Objetivo: **Create/Update** (e também soft delete via `active`) de `etl_pipeline`.

Conf esperado (principais):
```json
{
  "pipeline_name": "etl_cobranca_diaria",
  "scheduled_time": "08:00:00",
  "active": 1,
  "envia_msg_inicio": 1,
  "envia_msg_fim": 1,
  "envia_msg_erro": 1,
  "dag_criada": 0,
  "project_name": "BI_CVP",
  "domain": "Cobranca",
  "tags": "cobranca,diario"
}
```

Procedure chamada:
- `dbo.sp_etl_pipeline_upsert`

### 5.2 `etl_pipeline_query` (`dags/etl_pipeline_query.py`)

Objetivo: **Read (consulta paginada)** de pipelines, retornando JSON via XCom (`return_value`).

Conf esperado (principais):
```json
{
  "offset": 0,
  "limit": 20,
  "filter_name": "etl_",
  "filter_project": "BI_CVP",
  "filter_active": 1
}
```

Task que produz o XCom:
- `task_id = consultar_pipelines`

### 5.3 `etl_pipeline_job_register` (`dags/etl_pipeline_job_register.py`)

Objetivo: **Create/Update** de job + gravação obrigatória de lineage.

Conf esperado (batch):
```json
{
  "pipeline_name": "etl_cobranca_diaria",
  "jobs": [
    {
      "job_name": "job_extrai_pedidos",
      "execution_order": 1,
      "job_type": "datastage",
      "job_command": null,
      "origens": [{"object_type":"Tabela","object_name":"dbo.pedidos"}],
      "destinos":[{"object_type":"Tabela","object_name":"dbo.pedidos_stg"}]
    }
  ]
}
```

Procedures chamadas:
- `dbo.sp_etl_pipeline_job_upsert`
- `dbo.sp_etl_job_lineage_upsert` (para cada origem/destino)

### 5.4 `etl_pipeline_job_query` (`dags/etl_pipeline_job_query.py`)

Objetivo: **Read (consulta paginada)** de jobs.

Pontos importantes:
- Detecta automaticamente a tabela de jobs (por lista de candidatos).
- Mapeia colunas para um formato padrão.

Conf esperado (principais):
```json
{
  "offset": 0,
  "limit": 50,
  "filter_pipeline": "etl_cobranca_diaria",
  "filter_job_name": "job_",
  "filter_job_type": "datastage"
}
```

Task que produz o XCom:
- `task_id = consultar_jobs`

### 5.5 `etl_pipeline_job_reorder` (`dags/etl_pipeline_job_reorder.py`)

Objetivo: **Update somente da ordem** (`execution_order`) em lote, sem tocar em lineage.

Conf esperado (batch):
```json
{
  "pipeline_name": "etl_cobranca_diaria",
  "jobs": [
    {"job_name":"job_a", "execution_order": 1},
    {"job_name":"job_b", "execution_order": 2}
  ]
}
```

Procedure chamada:
- `dbo.sp_etl_pipeline_job_reorder`

### 5.6 `etl_dag_factory` (`dags/etl_dag_factory.py`)

Arquivo “factory” para suportar a camada de geração/gestão de DAGs baseada no cadastro.

> Observação: esse arquivo é maior e costuma concentrar lógica de automação (ex.: criar DAGs a partir dos pipelines pendentes, atualizar flags como `DAG_CRIADA`, etc.). Quando formos evoluir o produto (ex.: dashboard/logs), vale documentar esse módulo com mais profundidade.

---

## 6) UI (ui/index.html) — como se relaciona com o Airflow

### 6.1 Autenticação

- A tela de login gera o header:
  - `Authorization: Basic base64(usuario:senha)`
- Faz uma chamada simples para validar:
  - `GET /api/v1/dags?limit=1`

### 6.2 Endpoints do Airflow usados pela UI

> A UI assume que existe um proxy para o Airflow em `/api/` (mesma origem), para evitar CORS.

Disparar uma DAG:
- `POST /api/v1/dags/{dag_id}/dagRuns`

Consultar status do DAG Run:
- `GET /api/v1/dags/{dag_id}/dagRuns/{run_id}`

Ler XCom (consultas):
- `GET /api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/xcomEntries/return_value`

### 6.3 Fluxos principais na UI

**Pipelines**
- Buscar: dispara `etl_pipeline_query` e depois lê XCom `consultar_pipelines`.
- Criar/editar/inativar: dispara `etl_pipeline_register`.

**Jobs**
- Buscar: dispara `etl_pipeline_job_query` e depois lê XCom `consultar_jobs`.
- Criar/editar: dispara `etl_pipeline_job_register` (com lineage).
- Reordenar: dispara `etl_pipeline_job_reorder` (somente job_name + execution_order).

---

## 7) docker-compose / execução local (visão rápida)

`docker-compose.yaml` sobe um cluster Airflow (CeleryExecutor) com Redis e Postgres, e monta volumes:
- `./dags` → `/opt/airflow/dags`
- `./config` → `/opt/airflow/config`
- `./config/ui` → `/opt/airflow/www` (pasta para servir a UI, caso o ambiente esteja configurado assim)

---

## 8) Pendências conhecidas / próximos passos típicos

- Implementar **inativação de job**: requer alteração de schema (`etl_pipeline_job.active`) + proc + DAG + UI.
- Reduzir inline styles remanescentes na UI (uso progressivo das classes utilitárias).
- Documentar o `etl_dag_factory.py` com fluxo completo (como cria DAGs e como marca `DAG_CRIADA`).

