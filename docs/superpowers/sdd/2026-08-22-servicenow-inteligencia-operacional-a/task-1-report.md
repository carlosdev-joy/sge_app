# Task 1 Report — Migrations 094–098

**Status:** DONE

## O que foi criado

5 arquivos SQL criados em `/opt/airflow/spec/sql/migrations/` (094 a 098) e aplicados com sucesso no banco DMDB41 via pymssql.

## Resultado da verificação no banco

9/9 tabelas criadas: `etl_chamado_nota`, `etl_chamado_anexo`, `etl_chamado_ciclo`, `etl_indicador_snapshot`, `etl_indicador_snapshot_analista`, `etl_indicador_snapshot_grupo`, `etl_indicador_meta`, `etl_servicenow_grupo`, `etl_servicenow_gatilho`. Coluna `tem_anexo TINYINT` confirmada em `etl_chamado`.

## Concerns

A coluna `sys_id` em `etl_chamado` é `VARCHAR(32)` (não `NVARCHAR`). As FKs nas migrations 094 e 095 foram ajustadas para `VARCHAR(32)` nos campos `sys_id_nota`, `sys_id_chamado`, `sys_id_anexo` para compatibilidade de tipo. A spec original usava `NVARCHAR(32)` — os arquivos SQL no disco refletem a correção aplicada.
