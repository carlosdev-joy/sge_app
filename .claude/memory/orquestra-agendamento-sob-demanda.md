---
name: orquestra-agendamento-sob-demanda
description: "GOTCHA do Orquestra: schedule_type novo precisa ser tratado em 3 lugares (front, api, gerador) — 'on_demand' existia só na tela e virava cron diário 06:00"
metadata: 
  node_type: memory
  type: project
  originSessionId: f530f050-81b0-4c91-a6cc-98cdb214290e
  modified: 2026-07-31T20:26:59.342Z
---

⚠️ **GOTCHA: um `schedule_type` novo precisa ser tratado em TRÊS lugares no
[[orquestra-sge-app]], senão vira agendamento diário silenciosamente.**

Descoberto em 2026-07-31 (PR #230): o tipo **"Sob demanda" (`on_demand`)**
existia só no front (`pipelineUtils.ts` → `SCHEDULE_TYPES`/`SCHEDULE_LABELS`).
Nem `api/routers/pipelines.py::_build_cron`, nem
`api/routers/sequence.py::_build_cron`, nem `dags/etl_dag_factory.py::_build_cron`
o conheciam — e as três funções terminam com o **mesmo fallback**
`return f"{m} {h} * * *"`. Resultado: o pipeline que o usuário pedia manual
nascia agendado para **todo dia às 06:00**.

Agravante que escondeu o problema: o formulário **mantém `schedule_hour` ao
trocar de tipo** e sob demanda esconde o campo de horário — o 06:00 default
ficava invisível e continuava sendo enviado.

**Como ficou:** cron `None` → `schedule=None` na DAG. No Airflow isso é uma DAG
**ATIVA e visível, disparável só pelo botão Executar** — a moldura toda
(check_agenda, jobs, telemetria, notificações) continua igual; some só o
gatilho. Front mostra "sob demanda" na Malha e "—" no campo Horário do detalhe.

**Checklist para o próximo `schedule_type`:**
1. `ui-react/src/components/pipelines/pipelineUtils.ts` — SCHEDULE_TYPES + LABELS
   + `describeSchedule` + `computeNextRuns`
2. `api/routers/pipelines.py::_build_cron`
3. `api/routers/sequence.py::_build_cron` (importação de .dsx)
4. `dags/etl_dag_factory.py::_build_cron` — **é o que decide o `schedule=` da DAG**
5. exibição: `Malha.tsx` (2 pontos) e `PipelineModals.tsx`

⚠️ **Pipelines `on_demand` cadastrados ANTES desta correção seguem com a DAG
antiga (agendada) até serem REGERADOS** — o `deploy.sh` exclui `generated/`.
Conferir com:
`SELECT pipeline_name, schedule_type, scheduled_time FROM dbo.etl_pipeline
WHERE schedule_type = 'on_demand' AND active = 1;`
Cada um estava rodando diariamente sem ninguém ter pedido — vale olhar o
histórico de execuções deles por carga indevida.
