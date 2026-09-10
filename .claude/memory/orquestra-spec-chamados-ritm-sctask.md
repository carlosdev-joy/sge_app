---
name: orquestra-spec-chamados-ritm-sctask
description: "Spec RASCUNHO 'um card por trabalho' (RITM × SCTASK) do Orquestra — o parentesco está no banco desde a #312 e nada acima do banco usa; 3 fases, aguardando aprovação e 3 decisões do usuário"
metadata: 
  node_type: memory
  type: project
  originSessionId: d72d0d73-1cb6-41fb-a79f-c44793f12b3e
  modified: 2026-08-21T14:15:59.669Z
---

Spec em `docs/spec-chamados-ritm-sctask.md` — **APROVADA pelo usuário em
2026-08-21**. Três PRs ABERTAS, nenhuma mergeada:
- **#325** — a spec.
- **#327 (F1)** — um card por trabalho (API + tela). pytest 3484 (+11), tsc 0,
  eslint no baseline, `dist/` commitada. Branch `feat/chamados-card-por-trabalho`.
- **#328 (F2)** — os indicadores contam trabalhos. **Empilhada na F1** (base é
  a branch da F1). pytest 3499 (+15). Branch `feat/chamados-indicadores-trabalho`.

⚠️ **F1 e F2 vão ao ar JUNTAS.** `total_ativos` é o denominador de todo "x de
y" da aba Indicadores; com a F1 sozinha, a aba diz 113 enquanto a Fila diz 60.

⚠️ **A revisão adversarial NÃO rodou nestas duas.** O `/code-review` local leu
`/opt/orquestra-dev` (branch da malha, trabalho não commitado) em vez do
worktree — **rodar por NÚMERO de PR** (`/code-review high 327`) é o contorno.

Nasce do documento `spec_089_ritm_sctask.html` que o usuário deixou em `/root`.

⚠️ **O documento de origem foi escrito contra um snapshot ANTIGO do repo.** A
§0 da spec faz o confronto — vale como método, porque quase tudo que ele
propunha já existia com outro nome:
- a migration seria a **089**; a 089 é o proxy, e o parentesco entrou na **090**
  (PR #312) como **`pai_sys_id` + `pai_numero` + `estado_cru`**;
- ele criava índice **FILTRADO**, que é exatamente o defeito já pago em
  [[orquestra-indice-filtrado-quoted-identifier]] — a 090 documenta a medição
  (Msg 1934, migration parando no meio, DML posterior quebrando);
- a normalização mudou de `dags/etl_servicenow_sync.py` para
  **`dags/utils/servicenow_sync.py`**, e o MERGE é **gerado** de `CAMPOS_UPSERT`
  (uma fonte só), então o "alinhe as duas listas" dele deixou de existir;
- o endpoint `/chamados/{sys_id}/tasks` foi descartado: a fila inteira já vem
  numa resposta só, e o agrupamento sai do mesmo SELECT.

**O buraco real:** o parentesco está gravado e **nada acima do banco o usa** —
API não devolve as colunas, a fila desenha 2 cards para o mesmo trabalho
(**113 registros para ~60 trabalhos**, medido; 49 de 49 tasks ativas com o pai
na fila) e os indicadores contam os dois.

**Insumo:** a branch preservada **`feat/chamados-card-unico` (`c665335`)**, da
**PR #315 fechada a pedido** — tem `_agrupar_por_pai`, `_so_trabalhos`, o
`POST /chamados/sincronizar` (3 recusas: desligado, sem credencial, **DAG
pausada** — o Airflow aceita a run e ela fica parada para sempre) e a janela de
histórico do sync. Escrita contra a tela ANTES das derivações (091/092) e da
triagem (093); é insumo, não merge (ver [[orquestra-chamados-triagem-ia]]).

**Fases (2):** F1 um card por trabalho (API + tela) · F2 indicadores/histórico
com o mesmo recorte em SQL + **teste de paridade e anti-drift**. A spec inteira
ficou **sem migration e sem `dags/`** — não depende da janela de restart do
worker.

**Decisões do usuário em 2026-08-21 (fechadas):**
1. **Carga por responsável** segue o trabalho, sem SQL especial — na instância
   deles o responsável da task e o do RITM são **sempre o mesmo**, e todos os
   indicadores passam ao nível de trabalho. A premissa fica dita no código.
2. **Task órfã não existe** (regra da instância garante o pai na mesma fila) →
   sem marca visual. Mas o código **não a esconde**: órfã que aparece é sintoma
   de filtro de grupo, e sumir com ela seria falso verde.
3. **"Sincronizar agora" saiu do escopo** — voltou ao backlog para não empilhar
   `dags/` + migration na janela que já deve a #324 e a F0 da #303.

⚠️ Fora do escopo, mas medido e real: o `sysparm_query` só-por-grupo traz
**~3.376 registros por ciclo** para uma fila ativa de 113 — vira spec própria.
