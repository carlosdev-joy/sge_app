# SGE — Cadastro de Pipeline (UI + DAG Query)

Aplicação web estática (single page) servida via Nginx e que consome o Airflow via proxy `/api/` (mesma origem).

## Estrutura (padrão do repositório)

- `config/` — arquivos de configuração (ex.: nginx, variáveis, etc.)
- `dags/` — DAGs do Airflow
- `script/`
  - `tabela/` — scripts SQL de tabelas
  - `proc/` — scripts SQL de procedures
- `ui/` — frontend (colocar o `index.html` aqui)

## Como funciona a consulta

1. UI dispara um `dagRun` no Airflow para `etl_pipeline_query`
2. UI aguarda o `state` do `dagRun`
3. UI lê o XCom do task `consultar_pipelines` na key `return_value`
4. O retorno é renderizado em formato de grid

Para jobs, o fluxo é equivalente usando:
- DAG: `etl_pipeline_job_query`
- task: `consultar_jobs`

## Reordenar jobs (sem mexer em lineage)

Para permitir edição rápida de ordem na UI sem risco de sobrescrever lineage, o projeto inclui:

- PROC: `script/proc/sp_etl_pipeline_job_reorder.sql`
- DAG: `dags/etl_pipeline_job_reorder.py` (dag_id `etl_pipeline_job_reorder`)

A UI envia somente `{ job_name, execution_order }` para essa DAG.

## Nginx (exemplo)

O proxy recomendado para evitar CORS:

- UI: `/`
- Airflow API: `/api/` → `http://airflow-webserver:8080/api/`

---

## Performance Monitor v1 (snapshot histórico de alertas)

Objetivo: registrar histórico de pipelines que ultrapassaram **3h / 6h / 12h** em execução (status `RUNNING`) para análise de tendência ao longo do tempo.

### SQL

- Tabela (DDL para novos ambientes): `script/tabela/etl_pipeline_performance_snapshot.sql`
- Script de implantação (ambiente existente): `script/alteracoes/20260601_perf_snapshot_v1/001_create_table_etl_pipeline_performance_snapshot.sql`

### Airflow

- DAG: `dags/etl_performance_monitor.py`
  - `dag_id`: `etl_performance_monitor`
  - `schedule`: `0 * * * *` (minuto 0 de cada hora)
  - Task: `monitorar_performance`
  - Anti-duplicata: não insere novamente o mesmo `(execution_id, alerta_horas)` no mesmo dia.

---

## Schema Lineage v2 (enriquecimento de etl_job_lineage)

Objetivo: enriquecer `dbo.etl_job_lineage` com metadados de extração do DataStage/DSXEngine (grão por objeto), mantendo retrocompatibilidade para lineage manual.

### SQL

- DDL atualizado (novos ambientes): `script/tabela/etl_job_lineage.sql`
  - Novas colunas (todas `NULL`):
    - `stage_name`, `stage_type_raw`, `database_name`, `sql_expression`, `dsx_source_file`, `extracted_at`, `extraction_method`
- Scripts de implantação (ambiente existente): `script/alteracoes/20260601_schema_lineage_v2/`
  - `001_alter_table_etl_job_lineage.sql`
  - `002_alter_proc_sp_etl_job_lineage_upsert.sql`

### Stored Procedure

- `dbo.sp_etl_job_lineage_upsert` foi atualizada com **7 parâmetros opcionais** (default `NULL`).
- Em `UPDATE`, usa `COALESCE` para não sobrescrever valores existentes com `NULL`.

> Nota: o design da futura tabela `etl_job_lineage_column` (fase 2) não é implementado nesta etapa.
