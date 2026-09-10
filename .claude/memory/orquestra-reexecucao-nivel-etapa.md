---
name: orquestra-reexecucao-nivel-etapa
description: "Operação no nível de ETAPA (docs/spec-operacao-nivel-etapa.md, APROVADA) — drill-down malha→pipeline→etapas, rerun a partir de um job, etapa em espera, realce de dependências; ✅ F1–F5 EM PRODUÇÃO desde 2026-08-12; F6 (manual+smoke+aceitação) é o que resta"
metadata: 
  node_type: memory
  type: project
  originSessionId: f83b731c-0876-4438-b369-1dd4f50c0621
  modified: 2026-08-13T02:41:04.825Z
---

Pedido do usuário em 2026-08-03, depois de encerrada a
[[orquestra-malha-componentes]]: **descer a operação ao nível da ETAPA**.
Quatro necessidades declaradas:

1. **Drill-down**: a malha exibe os pais (pipelines); clicar num pipeline
   mostra os filhos (etapas/jobs) **no mesmo formato de diagrama**, com
   horário de início e fim de cada um.
2. **Reexecução a partir de um job** quando deu erro — sem reprocessamento
   total.
3. **Job em espera**: marcar um job daquela execução como pausa até o OK do
   usuário (validar algo); ao liberar, a malha continua de onde parou.
4. **Realce de dependências** ao clicar numa linha/nó — no canvas de Etapas
   (dentro do pipeline) e no de Malha — acendendo os nós vinculados, com
   botões "dependência para trás" e "para frente" (mapeamento de processo).

⚖️ **DECISÃO ARQUITETURAL DO USUÁRIO (2026-08-03): NÃO construir executor
próprio — seguir com o Airflow que já temos.** Ele levantou a dúvida ("teria
que sair do airflow?... como gerenciar a questão de DAGs toda hora com essas
alterações?") e decidiu ficar. Consequência de projeto: reexecução parcial usa
os primitivos do Airflow (clear de task com downstream) e a espera-por-
aprovação é **estado em tabela** consultado por uma task em poll — a DAG NÃO
é republicada por causa de uma pausa; só o **desenho** muda a DAG (o carimbo
`dag_config_pendente_em` já cuida disso).

⚠️ **Ponto que exige decisão do usuário no desenho**: reexecutar o meio de uma
malha — os pipelines DEPENDENTES rodam de novo em cascata ou não? Hoje o
disparo dos dependentes é por evento de sucesso (push). O Control-M responde
isso com "rerun com/sem cascata"; a spec precisa escolher explicitamente.

📄 **SPEC APROVADA E EM MAIN: `docs/spec-operacao-nivel-etapa.md`** (PR #260,
mergeada 2026-08-03). Fases F1–F6. **Decisões do usuário (§7)**: (1) cascata no
rerun = **SEMPRE PERGUNTAR** (modal com "só este pipeline" × "com os
dependentes", mostrando os afetados); (2) tentativas = **ACUMULAR** (coluna
`attempt` + migration + ajuste da SP); (3) pausa = **runtime primeiro**
(declarada no desenho vai p/ backlog); (4) realce = **destacar por padrão,
isolar sob demanda**.

⚙️ **PROCESSO ALTERADO PELO USUÁRIO (2026-08-03)**: **sem revisão adversarial
por fase nesta spec** — o QA roda UMA VEZ, ao final da spec completa. (O QA da
F1 foi interrompido no meio a pedido dele.) Mantidos por fase: suíte contra
baseline + prova viva no dev. Merges: **autorizados em bloco**, sinalizando
cada um. ⚠️ Consequência a vigiar: defeitos chegam empilhados na revisão final
— nesta base histórica a revisão por fase pegou GRAVE em quase toda fase.

✅ **F1 EM MAIN (PR #261, 2026-08-03, main ed9ecfa)** — realce de dependências:
clique em nó/aresta acende a cadeia, botões de sentido (trás/frente/ambos),
contador, botão isolar; vale nos 2 canvas e nos 2 modos da malha.
`layoutGrafo.ts` ganhou `adjacencia`/`alcance` (privados) +
`upstreamDe`/`downstreamDe`/`cadeiaRealce`; `criaCiclo` passou a usar a mesma
travessia — **equivalência provada em 4.000 grafos aleatórios** (esbuild+node,
main × branch). `liveLayout`/`autoLayout` NÃO unificados de propósito (a
semeadura deles é regra de LAYOUT — unificar mudaria posição salva).
GOTCHA de bancada: arrasto de handle no Chromium headless só funciona depois
de `fitView` (senão falso-negativo silencioso). Fixture `SMOKE_F1_REALCE`
(9 etapas com decisão) ficou no dev p/ F3/F4.

✅ **F2 EM MAIN (PR #262, 2026-08-03, main 5c37b4e)** — a ponte de identidade:
`api/services/execucao_identidade.py` (peça única nos 2 sentidos) +
`GET /pipelines/{name}/execucao?data_referencia=` (etapas com status/horários
+ vínculo do dag_run; aceita `?execution_id=` no inverso; **vazio honesto com
o desenho das etapas** quando não há execução na data, p/ o canvas abrir
neutro; `degradado` sem 067). Ambiguidade (>1 corrida no ODATE — rerun manual,
disparo da malha) devolve `ambiguo` + `candidatos[]` e desempata pela MESMA
função do painel da malha (`mais_recente_da_data`), com modo `estrito` que
recusa — é o que a F4 deve usar em gesto destrutivo. 82 testes; suíte 1649.
⚠️ **GOTCHA CONFIRMADO NO DEV — o `run_id` do Orquestra embute relógio LOCAL,
não a logical date** (`manual__2026-08-03__PIPE__20260803T094924` × logical
12:49:24Z): regex ingênua de `\d{8}T\d{6}` devolveria `ts_nodash` **3h
errado**. A tradução por string só aceita a forma ISO do Airflow; o resto
força leitura do dag_run (⇒ o caminho comum depende do Airflow, com
degradação declarada).
⚠️ **FUSOS DIVERGENTES entre as duas tabelas**: `etl_pipeline_execucao.inicio`
= `GETDATE()` do SQL Server (no dev = UTC) × `etl_job_execution.start_time` =
`pendulum.now("America/Sao_Paulo")` do factory → **3h de diferença no dev**;
em produção provavelmente coincidem (SQL local), NÃO verificado.
**DECISÃO tomada p/ a F3: horários da tela vêm de UMA FONTE SÓ (a das
etapas)**; intervalo do pipeline = min(início)/max(fim) das etapas. Status e
ODATE podem vir da 067; a regra vale p/ HORÁRIOS.
📌 Ponto p/ a F4 (registrado pelo implementador): `compor_etapas` usa
`setdefault` → com várias linhas por job fica a mais ANTIGA; ao acumular
`attempt` a F4 vai querer a mais RECENTE.

✅ **F3 EM MAIN (PR #263, 2026-08-03, main 135d925)** — modo Execução do canvas
de etapas + drill-down: botão "Ver etapas" no modo Execução da malha abre
`/fluxos?pipeline=X&modo=execucao&data=...&de=malha:NOME` (PÁGINA, não modal —
volta rápida, link compartilhável, cabe o grafo); status/início/fim/duração por
etapa, caminho percorrido em destaque, ramos não tomados apagados; ambiguidade
declarada com troca de corrida (`?run_id=` aditivo, reusando a F2); realce da
F1 funciona por cima. Módulo puro `execucaoEtapas.ts` com o contrato LITERAL
copiado da resposta real. Correção colateral: o `fitView` rodava antes de o
React Flow medir os nós (abria com zoom altíssimo).

✅ **FIX EM MAIN (PR #264, main 8295e05) — DUPLO CLIQUE ESTAVA MORTO EM TODO O
APP** (defeito pré-existente achado pela F3): React Flow liga
`zoomOnDoubleClick` por padrão → o `dblclicked` do d3-zoom faz
`preventDefault + stopImmediatePropagation` no `.react-flow__pane` → com a
delegação do React 19 o evento morria ali e `onNodeDoubleClick` NUNCA era
chamado. Os gestos anunciados na UI (duplo clique no Início abre agendamento —
F13; duplo clique abre modo focado no editor de etapas) não disparavam; ninguém
notou porque ambos têm botão equivalente. Fix: `zoomOnDoubleClick={false}` nos
2 canvas (zoom segue por roda/controles). Provado vivo + inspeção de listeners.

✅ **F4 EM MAIN (PR #265, 2026-08-03, main cbce3e2)** — rerun a partir da etapa:
modal por etapa no modo Execução (inclusive em etapa com SUCESSO), com as 2
opções de cascata e a LISTA dos dependentes afetados em cada uma; ambiguidade
recusada com confirmar desabilitado (modo estrito da F2); auditoria em
`etl_pipeline_audit`.
- **Cascata sem furar o claim**: as corridas dos dependentes no ODATE são
  carimbadas `substituida_em/_por` e `reservar_corrida`/`ordenar_corrida`
  passam a ignorá-las (como já ignoram PULADO) → a cadeia refaz pelo PUSH
  normal, nível a nível; corridas antigas ficam intactas. `dags/utils/
  dependencias.py` é importado em RUNTIME pelo código gerado ⇒ **vale sem
  regerar DAGs**.
- **DESVIO ACEITO na decisão 2 (acumular)**: `etl_job_execution` segue com UMA
  linha por etapa (a corrente, com `attempt` preenchido) e a tentativa
  superada é arquivada em **`dbo.etl_job_execution_tentativa`** (migration
  078). Motivo: **17 consultas** quebrariam com N linhas, várias CONGELADAS
  dentro de DAGs já publicadas (mentiriam até serem regeradas); e trocar a PK
  exige rebuild de PK clusterizado com janela (a 6c roda desassistida). SP
  mantém 11 parâmetros ⇒ acumulação vale sem regerar DAGs. Alternativa
  "dentro da mesma tabela" = outra fase (17 consultas + force_all + janela).
- ⚠️ **2 DEFEITOS ANTIGOS achados e corrigidos**: (1) **`only_failed` tem
  default `true` no Airflow e o rerun nunca o enviava** → reexecutar "a partir
  de" uma etapa em SUCESSO silenciosamente NÃO a reexecutava (invisível porque
  o botão só existia com FAILED); (2) **`log_start_<etapa>` é UPSTREAM da
  etapa**, então `include_downstream` não o alcançava → a etapa retomada
  mantinha o `start_time` antigo (10s viravam 89s). Fix: `task_ids_do_clear` +
  `only_failed: False`. ⚠️ Isso muda o blast radius do rerun de Logs/Dashboard
  em produção (ramo paralelo com dado velho agora também é refeito).
- Degradação PROVADA VIVA (sp_rename da coluna): sem a 078 o push segue
  disparando dependentes, com aviso no log e cascata declarada indisponível.
  Essa prova achou +1 defeito (resposta contava dependentes reabertos que não
  seriam) — corrigido.
📌 Backlog: `sql/dump_schema.py`, `dump_dados.py` e `deploy_full.sql` NÃO
conhecem `etl_job_execution_tentativa`; nem ela nem `etl_job_execution` têm
expurgo; rerun feito direto na UI do Airflow não conta tentativa.

✅ **F5 EM MAIN (PR #267, 2026-08-03, main 5507f48)** — etapa em espera:
portão em `dags/utils/espera.py` (fora do fonte gerado: a DAG ganha 12 linhas +
troca de operador), `LogStartOperator` com `reschedule` REAL (registrando
`ReadyToRescheduleDep` + `get_serialized_fields`), teto por linha de pausa com
alerta e falha, eventos no canal da guardiã (que NÃO mudou), auditoria por
gesto, migration 079, tela com pausar/liberar/cancelar. **Mitigação do §9
cumprida**: teste-âncora carrega o factory de `main` via `git show` e compara o
fonte gerado BYTE A BYTE descontando o delta (4 cenários).
⚠️ **8 defeitos que só a prova real revelou** — 4 na execução: `reschedule` não
valia (43 checagens/180s → 3), teto NUNCA estouraria (relógio do banco ×
worker), `retries` anulava o teto (etapa passava depois de expirar), índice
filtrado exigia `QUOTED_IDENTIFIER`; + 2 no cancelamento (corrida eterna em
EXECUTANDO — classe do órfão em RUNNING; pausa sem ODATE logo após o trigger);
e 4 que **só a TELA revelou** (a prova visual que exigi depois): limite honesto
INVISÍVEL (botão sumia sem explicar), os 2 relógios lado a lado na cara do
operador, pausa quebrando com 2 corridas no ODATE, e a recusa falando do gesto
ERRADO ("escolha qual reexecutar" para quem clicou em pausar).
📌 **LIÇÃO**: validar UI por tsc/build/endpoints NÃO substitui clicar — 4 dos 8
defeitos só apareceram na tela.
⚠️ Deploy da F5 EXIGE `force_all` (pipeline não regerado não tem portão: a
pausa aparece marcada e nada segura).

✅ **F1–F5 EM PRODUÇÃO desde 2026-08-12** (trem inteiro —
[[orquestra-deploy-trem-producao]]), com o `force_all` que a F5 exige. A **F6**
da spec (manual do usuário + roteiro de smoke + aceitação com cenários
executados) é o que resta do §8; e a revisão adversarial ÚNICA de fim de spec,
que o processo desta feature adiou, não consta como feita.

🔧 **REVISÃO PRÉ-DEPLOY (2026-08-03) — histórico: 1 BLOQUEANTE, já corrigido.**
✅ Já corrigido na PR **#266**: `deploy.sh` recomendava `--baseline` com >5
migrations pendentes (este deploy leva 10 → subiria MUDO com smoke "passando");
migration 078 não degradava (SQL estático valida coluna em COMPILE-TIME — a 058
já usava `EXEC()` pelo mesmo motivo); backfill em tabela quente sem aviso de
janela; **ordem documentada INVERTIDA** (o certo é `dags/` ANTES das migrations
— código novo degrada em banco velho, banco novo NÃO se protege de código
velho) + lista até a 078 + query de conferência pós-migration.
✅ **TUDO CORRIGIDO E EM MAIN (44ce8d4, 2026-08-03)** — PRs #268 (bloqueante da
cascata) e **#270** (os 4 achados da revisão FINAL sobre F5+#268):
1. runbook não conhecia a **079** nem o **`force_all` que a F5 EXIGE** (dizia
   "10 migrations", seriam 11; e destacava que a F4 dispensa, o que induzia ao
   erro oposto) → corrigido + conferência `grep -rl "_espera.portao"
   <DAGS_FOLDER>/generated/ | wc -l` contra pipelines ativos;
2. **pausa em pipeline SEM portão era aceita e nada segurava** (mesma classe da
   #268 do outro lado) → sonda POR PIPELINE do `.py` gerado no bind mount `:ro`;
   sem portão **recusa 409**; ilegível cria **com aviso forte** (divergência
   deliberada do rerun, registrada no código);
3. **reexecutar corrida APOSENTADA = SUCESSO INVISÍVEL para sempre** (concluía
   ainda carimbada → `liberado()`/`pipelines_todos_sucesso` não viam sucesso no
   dia; dependentes travados, só UPDATE manual desfazia) → `reviver_corrida()`
   limpa `substituida_em` **no MESMO UPDATE** que marca EXECUTANDO; modal de
   ambiguidade rotula a aposentada;
4. **corrida parada no portão morta pelo `dagrun_timeout` virava órfã em
   EXECUTANDO** (o scheduler pula as TIs não-finalizadas ⇒ ninguém grava FALHA;
   `_resgatar_orfas` só via `inicio IS NULL`) → guardiã ganhou
   `corridas_em_execucao`/`fechar_orfa_em_execucao` com 3 guardas; **só fecha
   FALHA com DagRun `failed`**; `success` sem fecho ou DagRun ausente vira
   alerta `EXECUCAO_ORFA` (não inventa verde).
📌 **Backlog**: `dagrun_timeout` é emitido sem consciência do teto de pausa — a
guardiã limpa o estrago, mas a corrida ainda morre (decidir: não emitir, somar
ao teto, ou recusar pausa > SLA = fase própria).
📌 GOTCHA dev: `DELETE` em `etl_etapa_pausa` exige `SET QUOTED_IDENTIFIER ON`
(índice filtrado da 079) — sqlcmd sem isso dá Msg 1934.

_(histórico)_ Achados originais: (1) **BLOQUEANTE** — a F4
ensinou 2 das 3 portas do modelo de corrida a ignorar corrida substituída;
**`liberado()` ficou de fora** → em cadeia A→B→C o rerun com cascata faz a
guardiã liberar **C com o dado VELHO de B** em ≤5 min, e depois C fica travado
no ODATE (sem volta); (2) probe da cascata olha o BANCO, não o `dags/`
deployado → deploy parcial faz a API dizer "2 dependentes reabertos" e nenhum
roda; (3) carimbo de EXECUTANDO sem conferir rowcount + DAG pausada deixa
corrida pendurada bloqueando dependentes.

_(histórico da F5 abaixo)_ ⚠️ **A FASE DE RISCO REAL**:
mexe no `log_start_<job>`, presente em TODA etapa de TODO pipeline. Mitigação
inegociável do §9: sem linha de pausa, fonte gerado **byte-idêntico** ao de
main (com teste). Portão espera em `reschedule` (não segura worker), teto com
alerta, liberar/cancelar pela tela com auditoria. Exige **regerar DAGs**.

**Fatos do levantamento que mudam o desenho** (não supor de novo):
- Cada etapa **JÁ é uma task** (`task_id` == `job_name`), envolta por
  `log_start_<job>` e `log_end_<job>` (etl_dag_factory.py:289-445). Um
  pipeline = UMA DAG.
- Horários por etapa já gravados em `etl_job_execution` (start_time/end_time/
  duration/status), pela própria DAG via `sp_etl_job_execution_log`.
- **O rerun a partir de uma task JÁ EXISTE**: `POST /execucoes/rerun`
  (execucoes.py:570-638) faz `clearTaskInstances` com `include_downstream` —
  mas só aparece no `LogDetailModal` (Logs/Dashboard) e **só com status
  FAILED**. Não existe mark success/failed na API.
- ⚠️ **CHAVES DIFERENTES**: `etl_job_execution.execution_id` = `ts_nodash`;
  `etl_pipeline_execucao.execution_id` = `run_id` do Airflow. Conversão já
  existe (`_iso_to_ts_nodash` na API, `toNodash` no front) — a spec manda
  transformar isso em peça ÚNICA (F2).
- ⚠️ O clear mantém o mesmo `ts_nodash` e a SP faz IF NOT EXISTS→INSERT ELSE
  UPDATE: **a reexecução SOBRESCREVE a linha da tentativa anterior**; a coluna
  `attempt` existe e NUNCA é preenchida.
- ⚠️ Rerun hoje é "sem cascata" **por efeito colateral**: o push tenta
  disparar os dependentes, mas o claim (`reservar_corrida`) barra a 2ª corrida
  no mesmo ODATE.
- **Aprovação humana em runtime NÃO EXISTE**: zero sensores (removidos em D01);
  `etl_sequence_import_approve` aprova CADASTRO (sem poll); Finalização Manual
  conserta registro órfão. É a única peça a construir do zero.
- `layoutGrafo.ts` já tem DFS de sucessores (`criaCiclo`) e mapa de
  predecessores (`liveLayout`) — base pronta do realce.
- Airflow **2.11.2**, API v1, basic auth; `MalhaEditor` não tem `onNodeClick`
  e nenhum canvas tem `onEdgeClick`.

**Desenho proposto para a pausa (Bloco C2)**: o portão já existe fisicamente
— o `log_start_<job>` de cada etapa passa a consultar uma tabela de pausas e
espera em **`reschedule`** (não segura worker) até a liberação. Zero task nova,
zero mudança no desenho, pausa ad hoc em qualquer etapa **que ainda não
iniciou**. Exige regerar DAGs (force_all) e teto de espera com alerta.
