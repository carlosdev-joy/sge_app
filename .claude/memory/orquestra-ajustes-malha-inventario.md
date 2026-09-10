---
name: orquestra-ajustes-malha-inventario
description: "Ajustes pós-spec da malha (2026-08-09): 4 PRs #293–#296 — renomeios p/ ciclo, KPI de etapas, painel do Dashboard no formato Supervisão (INVERSÃO das D26/27), inventário de DAGs no Admin; ✅ EM PRODUÇÃO desde 2026-08-12"
metadata: 
  node_type: memory
  type: project
  originSessionId: afee62fa-1c2e-4d5f-ba52-084b20f5cf9e
  modified: 2026-08-13T02:39:58.545Z
---

Rodada de ajustes pedida pelo usuário em **2026-08-09**, motivada pela migração
do **primeiro processo DataStage para o Orquestra**. As 4 PRs foram
**MERGEADAS na main em 2026-08-09** (autorizadas pelo usuário, squash, ordem
#293 → #295 → #294 → #296; suíte final na main: 3157 passed, 5 pré-existentes).
✅ **EM PRODUÇÃO desde 2026-08-12**, junto com o trem da malha — ver
[[orquestra-deploy-trem-producao]] e [[orquestra-spec-corrida-malha]].
⚠️ Lição do merge: squash da PR base reescreve
SHAs → a empilhada e as paralelas conflitam na `dist/` (e na região comum do
fonte); resolve-se mergeando a main na branch, `checkout --ours` no fonte da
branch mais nova e **rebuild** da dist (nunca editar bundle).

- **PR #293** (`fix/malha-nomes-e-horario-card`) — painel do Dashboard vira
  **"Execução de Malha"**; sobras visíveis de "corrida" → "ciclo" (complemento
  da #290); horário do ciclo em **linha própria** no card da malha. 3 âncoras
  de teste atualizadas.
- **PR #294** (`feat/kpi-etapas-do-dia`) — KPI **"Etapas"** no Dashboard:
  `kpis.total_etapas`/`total_etapas_ok` (grandeza de uso), mesmo recorte do
  KPI de execuções; grid 7→8.
- **PR #295** (`feat/painel-malha-formato-supervisao`) — ⚠️ **EMPILHADA na
  #293** (mergear a #293 primeiro; NÃO usar `--delete-branch` nela antes). O
  painel de malha do Dashboard passa ao **formato da Supervisão DataStage**:
  sempre visível, TODAS as malhas ativas, badge "N de M com problema" (âmbares
  contam, CANCELADA não), fundo avermelhado pelo MESMO predicado do badge.
  **⚖️ INVERSÃO deliberada das Decisões 26/27 neste painel** (o "some quando
  vazio" morreu): confirmação positiva exigida pela migração DS→Orquestra.
  Cadência intacta (D73: visível ≠ pollando). Testes f11 reescritos com a
  inversão anotada.
- **PR #296** (`feat/inventario-dags-admin`) — Admin → Sistema → **"Inventário
  de DAGs"**: `GET /admin/dags/inventario`, catálogo curado das 27 DAGs de
  sistema (6 categorias) × estado ao vivo do Airflow (pausada/ausente/cron
  real). Teste **anti-drift**: DAG de sistema nova/apagada sem atualizar o
  `CATALOGO_DAGS` (routers/admin.py) quebra a suíte. `orquestra_teste.py` fica
  fora (é script de job_command, não DAG).

**Processo:** cada PR passou por revisão adversarial (qa-adversarial). A #293
e a #295 REPROVARAM na 1ª rodada (âncoras de teste + sobras; horário de ontem
sem rótulo na linha "não abriu", badge verde sobre âmbar, mentira na 070
pendente, dia atípico sem frase) — tudo corrigido e re-validado. Baseline da
suíte: 5 failed pré-existentes (test_api_v2_4 ×4, test_smoke ×1), 3153 passed.

**Deploy (feito em 2026-08-12):** #293/#295 = front; #294/#296 = api + front.
Nenhuma migration, nenhuma wheel. ⚠️ **Smokes visuais sem confirmação item a
item**: linha nova do horário no card (claro/escuro), painel novo com malha
verde e com problema, inventário com Airflow de pé e parado — perguntar antes de
dar como feitos.

Ver [[orquestra-sge-app]], [[orquestra-spec-corrida-malha]],
[[orquestra-deploy-trem-producao]].
