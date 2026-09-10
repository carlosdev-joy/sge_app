---
name: orquestra-finalizacao-manual
description: Tela Finalizar Pipeline (/finalizacao) — encerramento manual de execuções penduradas em RUNNING; branch feat/finalizacao-forcada aguardando PR/deploy
metadata: 
  node_type: memory
  type: project
  originSessionId: 6be00b90-dd3a-4cf7-bd42-c91cbf215942
---

Tela **Finalizar Pipeline** do [[orquestra-sge-app]] (branch `feat/finalizacao-forcada`, commit 3dd70dd, criada em 2026-07-05): operador informa o pipeline e força o encerramento de execuções órfãs (terminaram no DataStage mas ficaram EXECUTANDO no Orquestra — worker morre antes do `log_end` e o `etl_ds_job_log` também fica RUNNING, então o reconciliador nunca fecha).

Uma transação toca 3 lugares: `etl_job_execution` (status final + end_time → sai do Executando/Gantt/KPIs/SLA), `etl_ds_job_log` (status/status_code terminal → monitor central para de pollar via SSH) e DELETE em `etl_pipeline_performance_snapshot` (some da tela Performance na hora). Auditoria em `etl_pipeline_audit` (field_name `finalizacao_manual`) + `add_notificacao`. Escrita exige `acao_executar`; menu por `tela_finalizacao` (migration 057 → admin/desenvolvedor/operador).

**Em produção desde 2026-07-05** (PR #163, merge `86045ab`). Confirmado funcionando após o usuário rodar o `migrate.py` manualmente — ver gotcha de deploy em [[orquestra-sge-app]]: o `deploy.sh` NÃO aplica migrations. De carona, o rótulo pendente de `tela_inventario` no Admin ([[orquestra-inventario-consumidores]]) foi corrigido nesta branch.
