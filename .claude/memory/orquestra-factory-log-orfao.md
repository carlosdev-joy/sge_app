---
name: orquestra-factory-log-orfao
description: "GOTCHA do Orquestra — geração de DAG que falha no meio deixava etl_factory_log em RUNNING para sempre, e o operador via só \"timeout\"; corrigido na PR #234 e ✅ EM PRODUÇÃO desde 2026-08-12"
metadata: 
  node_type: memory
  type: project
  originSessionId: e1e7afb3-0f73-4fb0-bc9c-ce947f1c789d
  modified: 2026-08-13T02:42:40.886Z
---

⚠️ **GOTCHA de diagnóstico do [[orquestra-sge-app]]:** quando a task
`gerar_dags` (`dags/etl_dag_factory.py`) morria por exceção **fora** dos
try/except por-pipeline, o registro em `dbo.etl_factory_log` ficava em
**RUNNING para sempre**.

**Como isso aparece para o usuário** (relatado em 2026-08-01): "não consigo mais
gerar DAG, dá timeout e não aparece no servidor". A tela de Publicação não mostra
causa nenhuma, o `.py` não é escrito, e 15 min depois o reconciliador
(`api/services/dag_reconcile.py`, `PENDENTE_TIMEOUT_S=900`) marca **TIMEOUT** —
que não explica nada. **O erro real fica só no log da task no Airflow.**

**Pontos que morriam assim**, todos entre `_log_upsert("RUNNING")` e o
fechamento: `hook.get_conn()`, o UPDATE de `dag_criada`, a
`EXEC sp_etl_pipelines_pendentes_criar`, os `fetchall`/`nextset`, as queries de
colunas avançadas e — o pior — o **`os.makedirs` dentro do loop e fora do try**,
que derrubava a execução inteira e levava junto os pipelines seguintes.

✅ **Corrigido na PR #234, MERGEADA em main em 2026-08-01** (independente das PRs
do [[orquestra-no-aguarde]] — as duas linhas tocam `dags/etl_dag_factory.py` e
auto-mergearam sem conflito; ✅ o **deploy de `dags/`** foi no trem de 2026-08-12
— [[orquestra-deploy-trem-producao]]): wrapper `gerar_dags_task` fecha o log como FAILED com
a causa e deixa o erro subir; `_ErrosPorPipeline` evita sobrescrever o detalhe
por pipeline; `os.makedirs` entrou no try; **pipeline sem nenhuma etapa deixou de
ser um `print` silencioso e virou erro de primeira classe** (era outro caminho
para "esperei um arquivo que nunca veio").

📋 **DIAGNÓSTICO quando isso acontecer de novo** (roda no SQL Server):
```sql
SELECT TOP 20 dag_run_id, estado, escopo, pipeline_name, geradas, erros,
       iniciado_em, finalizado_em, detalhes_json
FROM dbo.etl_factory_log ORDER BY iniciado_em DESC;
```
- `estado='RUNNING'` sem `finalizado_em` e antigo = a task morreu no meio → ver o
  log da task `gerar_dags` no Airflow (é onde está a causa real)
- `estado='TIMEOUT'` = o arquivo foi gerado mas a DAG não ficou ativa no Airflow
- `estado='ERRO'` + step `import_error` = a DAG foi gerada mas o Airflow não
  consegue importá-la (stack trace na tela de Publicação)

**A geração NÃO roda na API:** é um DagRun da DAG `etl_dag_factory` disparado por
REST (`POST /pipelines/{name}/gerar-dag`). Se a `etl_dag_factory` estiver
**pausada** ou o **scheduler parado**, o run fica em queued e nada acontece —
mesmo sintoma, causa fora do código.
