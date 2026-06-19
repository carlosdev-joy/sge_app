# Backlog — Fase 2: tempo, histórico e alerta de performance por job na malha

> Continuação da frente de observabilidade da Malha DS. A **coleta de tempo** já
> começou (o `dsjob -jobinfo` na varredura captura `wave`, `start` e `elapsed`);
> falta **persistir histórico de todos os jobs**, **calcular baseline**, **exibir
> na malha** e **alertar por desvio**.

## Onde estamos (já entregue)
- Varredura `etl_ds_malha_status` captura por job: `status`, `wave_number`,
  `Job Start Time` e `Elapsed` (quando o `dsjob` informa) — `dags/etl_ds_malha_status.py`.
- `etl_ds_malha_falha` guarda `started_at` e `elapsed_seconds`, **mas só para os
  jobs ABORTED** (registro de falha). Não há histórico de tempo dos jobs OK/WARNING.
- Já existe baseline **por pipeline/job de execução** (`/execucoes/duracao-media`,
  P50/P90) sobre `etl_job_execution` — referência de padrão a reusar.

## Fase 2.1 — Histórico de tempo por job (base de tudo)
- [ ] **Migration**: tabela `etl_ds_malha_run_hist` (append-only) —
      `project, job_name, wave_number, status_code/label, started_at, ended_at,
      elapsed_seconds, captured_at`. Índice único de dedup por
      `(project, job_name, wave_number)` (não regravar o mesmo run a cada scan).
- [ ] **DAG**: na `scan_project`, gravar 1 linha por job com `wave/elapsed/started`
      (todos os status, não só abort), com dedup por wave. Reaproveita o parsing
      que já existe (`fields_by_job`).
- [ ] **Cuidado**: `Job Elapsed Time` nem sempre vem no `-jobinfo` (varia por
      versão); quando faltar, derivar de `Last Run Time − Job Start Time` ou deixar
      `elapsed_seconds = NULL`. Validar o formato num projeto real.

## Fase 2.2 — Baseline por job
- [ ] **API** `GET /malha-ds/{project}/baseline` (ou `?job=`): média, **P50, P95,
      máx, n** das últimas N execuções por `job_name` a partir de `etl_ds_malha_run_hist`.
      Espelhar a lógica de janela do `/execucoes/duracao-media`.
- [ ] Decidir N (ex.: últimas 30) e janela de tempo (ex.: 60 dias).

## Fase 2.3 — Exibir na malha (UI)
- [ ] No `MalhaTreeView` (`ui-react/src/components/MalhaTreeModal.tsx`), ao lado do
      status de cada nó: **tempo do último run + baseline + desvio** —
      ex.: `12m · p95 9m (+33%)`. Cores: verde dentro do p95, âmbar acima, vermelho
      muito acima (reusar a régua de `devBadge` do `ExecucaoDetailModal`).
- [ ] Mini-histórico ao expandir o nó (sparkline ou últimas N durações).
- [ ] Reaproveita os contadores/filtros já existentes no cabeçalho da malha.

## Fase 2.4 — Alerta de desvio de performance (Fase 3 original)
- [ ] Sentinela (DAG ou estender `etl_ds_malha_status`) que compara o `elapsed`
      atual com o baseline (p95 ou média×fator configurável) e dispara **Teams**.
- [ ] Reusar o card Teams + padrão de **dedup** (`etl_sla_alert`/`etl_ds_malha_falha`).
- [ ] Gatilhos: (a) job **estourado** vs baseline; (b) job **preso em RUNNING**
      acima do histórico. Thresholds por Variable e/ou por job.
- [ ] **Espelhar o DataStage** (mesma régua dos aborts): só alertar desvio onde
      faz sentido (job que efetivamente rodou), evitando ruído.

## Decisões em aberto
- Granularidade do histórico: por `wave` (run) parece suficiente; confirmar se há
  re-execuções com mesmo wave.
- Onde mora o baseline: calcular on-the-fly na API (simples) vs materializar.
- Default do alerta de desvio: fator sobre p95 (ex.: > p95 × 1.5) — calibrar com
  dados reais antes de ligar o Teams.

## Dependências
- Migration 030 (`etl_ds_malha_falha`) já criada; a 2.1 cria a `*_run_hist`.
- Varredura `etl_ds_malha_status(_auto)` precisa estar rodando para acumular histórico.
