---
name: orquestra-no-aguarde
description: "Nó \"Aguarde\" do Orquestra (junção de pernas paralelas) — spec docs/spec-no-aguarde.md, F1–F4 EM PRODUÇÃO (PRs #231–#235; deploy do trem em 2026-08-12); smoke §8.1 sem confirmação item a item"
metadata: 
  node_type: memory
  type: project
  originSessionId: e1e7afb3-0f73-4fb0-bc9c-ce947f1c789d
  modified: 2026-08-13T02:40:13.635Z
---

Nó **Aguarde** do [[orquestra-sge-app]] — ponto de encontro entre pernas
paralelas. Spec em `docs/spec-no-aguarde.md`, aprovada e implementada em
2026-08-01. ✅ **PRs #231 (F1) → #232 (F2) → #233 (F3) → #235 (F4) MERGEADAS em
main em 2026-08-01** (junto da #234), na ordem de baixo para cima, reapontando a
base de cada empilhada para `main` antes do merge da anterior e SEM
`--delete-branch` (gotcha já registrado em [[orquestra-supervisao-ds-spec]]).
Suíte na main pós-merge: 1007 passando, 5 falhas — as MESMAS 5 do baseline
(`test_api_v2_4.py` ×4 + `test_smoke.py::test_pipelines_unauthenticated`), ou
seja pré-existentes, zero novas.

**Caso de uso:** duas pernas paralelas usam os mesmos arquivos de trabalho; a
remoção só é segura quando as duas terminarem.

**Decisões do usuário (AskUserQuestion):** espera só as arestas ligadas (sem
barreira global); política configurável por nó com default conservador; sem
espera por tempo/arquivo; spec antes de código.

**Desenho:** 4º nó especial (junto de decisao/notificacao/sql), `t_wait_<n>` =
EmptyOperator sem t_start/t_end. Migration **068** = `aguarde_json`
`{"politica": "todas_sucesso"|"todas_terminarem"}`. Trigger rule:
todas_sucesso → ALL_SUCCESS; todas_sucesso + abaixo de decisão →
NONE_FAILED_MIN_ONE_SUCCESS (ramo pulado chega SKIPPED e travaria);
todas_terminarem → ALL_DONE.

⛔ **INVARIANTE (teste-âncora `test_ancora_end_tasks_intactas_em_todas_terminarem`):**
todo `t_end_*` continua em `end_tasks` e ligado DIRETO ao `publish_dataset`, sem
o Aguarde no meio. É isso que faz a limpeza rodar SEM esconder a falha —
`t_end` é ALL_DONE mas o `log_end` faz **raise** quando o status é FAILED
(`etl_dag_factory.py:1210`). Esse padrão "roda para registrar, mas propaga a
falha" é o antídoto do ALL_DONE-em-task-terminal que derrubou
[[orquestra-dependencias-pipelines]].

**Descoberta do levantamento:** a junção JÁ era topologicamente possível via
`depends_on_jobs` com várias origens. O que não existia era a semântica no
canvas e o controle de falha — o valor da feature está aí, não no grafo.

✅ **DEPLOY FEITO** (trem inteiro em 2026-08-12 — [[orquestra-deploy-trem-producao]]).
Roteiro executado, guardado como referência: migration 068 → subir API+front →
**REGERAR as DAGs** (sem isso NADA muda) → validar em 1 pipeline de teste.

⚠️ **O smoke §8.1 (9 passos) NÃO teve confirmação item a item** — o **passo 8** é
o que importa: política tolerante + perna falhando = limpeza roda **E** pipeline
vermelho; se aparecer verde, é falso verde e o deploy tem de parar. Só o usuário
pode rodá-lo; perguntar antes de dá-lo como feito. Migration 068 aplicada;
feature em uso real desde 2026-08-02 (SEQSSDVIDA4BILHETE, Aguarda_carga_fatos
com 5 pernas).

📌 **BACKLOG (episódio real de 2026-08-02):** usuário desenhou 5 pernas mas
prendeu só 2 no Aguarde; publicou sem aviso e as 3 pontas soltas foram direto
ao publish_dataset — a limpeza pós-Aguarde poderia rodar com pernas ainda
executando. O painel só avisa quando o nó está SELECIONADO. Melhoria: aviso na
PUBLICAÇÃO ("N etapas não passam pelo Aguarde — é intencional?"). Nota
correlata: o layout do grafo do Airflow puxa pontas soltas p/ baixo (âncora no
publish_dataset) — parece "outro nível de paralelo" mas é só cartografia; o
Gantt é a prova de paralelismo real.
