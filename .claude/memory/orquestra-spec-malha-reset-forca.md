---
name: orquestra-spec-malha-reset-forca
description: "Spec do botão Reset à força da malha (port de docs/forcar-reset-ciclo-malha.sql p/ produto) — docs/spec-malha-reset-forca.md, RASCUNHO na PR #301; 4 fases; construção após decisão de fila (§8d) vs spec de chamados #297"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5505a5f1-b450-4bac-a779-cc76b9496dca
  modified: 2026-08-11T11:27:56.222Z
---

**docs/spec-malha-reset-forca.md** (PR #301, 2026-08-11, RASCUNHO aguardando
aprovação) — port do script de reset (PRs #298/#299, ver
[[orquestra-malha-data-unica]]) para feature do [[orquestra-sge-app]]: botão
**Reset à força** na tela da malha.

**Desenho:** service `api/services/malha_reset.py` (transação pyodbc `?`,
paridade de predicado com o script; corte da virada REUSA `_inicio_do_ciclo`
— resolve o skew de relógio) → endpoint `POST /malhas/{m}/reset-forca`
(dry_run | preservar | limpar, motivo obrigatório, `PERM_ADMIN`) → modal
`ResetForcaModal.tsx` (pré-visualização = dry-run, confirmação digitando o
nome da malha) → evento `RESET_FORCA` com contadores → trava de DagRun em
voo via proxy airflow.py (bypass `ignorar_dagruns` auditado) → CTA
Republicar no resultado. **Sem migration** (evento é VARCHAR; permissão
reusa `acao_admin`).

**4 fases**: F1 service+dry-run · F2 execução+trava+auditoria · F3 modal ·
F4 encadeamento/polimento. Critérios de aceite reutilizam os cenários QA
desta sessão (colisão NULL×NULL, rastro rastejante, escopo não-membro,
idempotência).

**PENDÊNCIAS §8 (usuário):** (a) permissão `acao_admin` vs `acao_executar`
(recomendo admin); (b) manter bypass `ignorar_dagruns` (recomendo sim);
(c) matar DagRuns pelo botão fica p/ v2 (recomendo sim); (d) ordem de
construção vs spec de chamados #297.
