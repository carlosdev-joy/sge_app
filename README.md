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
