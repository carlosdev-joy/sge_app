---
name: orquestra-supervisao-ds-spec
description: "Spec da Supervisão de Jobs DataStage no Orquestra (docs/spec-supervisao-ds.md) — F1–F7 COMPLETAS e EM PRODUÇÃO, validadas pelo usuário em 2026-08-01; nada pendente"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2f861786-77b7-4a2e-b8b5-9f078cb50617
  modified: 2026-08-01T12:18:21.236Z
---

Spec **Supervisão de Jobs DataStage** no Orquestra (`/opt/orquestra-dev`),
salva em `docs/spec-supervisao-ds.md`. Criada em 2026-07-29.

✅ **SPEC ENCERRADA — F1–F7 EM PRODUÇÃO E FUNCIONANDO (confirmado pelo usuário
em 2026-08-01).** O deploy da F7 (migration 066 + `dags/` + front/API) foi feito
e validado; **nada pendente de deploy ou de smoke**. Melhorias sobre a
Supervisão ficam para o futuro, fora do backlog ativo.

**F7 (2026-07-30) — PR #216 MERGEADA na main (merge 66710da), deployada.**
Três pedidos do usuário num conjunto: (1) painel de Supervisão movido para
**abaixo dos KPIs e acima de "Rodando agora"/"Alertas de performance"**; (2)
**linha do tempo (Gantt) reordenada dinamicamente** — rodando no topo, foco
±15min, histórico descendo, divisor "antes disso", eixo de horas `sticky`,
rolagem vertical; (3) **diagrama da árvore de níveis** (`SupervisaoArvoreModal`,
@xyflow/react) com botão "Ver diagrama" SEMPRE visível na linha do job, e
**migration 066** (`inicio`/`fim` em `run_filho`) para horário/duração por job.
Smoke pós-deploy VALIDADO pelo usuário (2026-08-01). Nota que segue valendo:
horário nos nós só existe a partir da 1ª execução coletada DEPOIS da 066 — as
execuções anteriores mostram aviso, e isso é esperado.

⚠️ **CONCEITO QUE O USUÁRIO PRECISOU ESCLARECER (2026-07-30):** a
`etl_ds_supervisao_estrutura` (o "aprendendo N jobs" do log) **NÃO alimenta o
painel e NÃO tem hierarquia** — é lista chapada de nomes, usada só para
`FILHO_AUSENTE`. Quem decide "falhou" é o status da árvore do run
(`ds_estrutura.filhos_que_falharam`), não a estrutura aprendida. O detalhe da
tela vem de `etl_ds_supervisao_run_filho` (nivel/job_pai), gravado pela
**expansão daquele run** — que só roda com run TERMINADO
(`etl_ds_supervisao_monitor.py`: `if r.resultado == "running": continue`),
`expandido = 0` e orçamento no ciclo. Logo: **job em execução mostra só nível 1,
e isso é correto**; os níveis 2–4 aparecem no primeiro ciclo depois do término,
não "com o passar dos dias". A estrutura aprendida **não tem tela nenhuma** —
só SQL.
**Status: APROVADA. F1 (PR #208) e F2 (PR #209) MERGEADAS na main em 2026-07-29**
(merge commits db01818 e e9a3709). **AGUARDANDO DEPLOY** — nada em produção ainda.
**F3 (PR #210) e ajustes (PR #211) MERGEADAS na main em 2026-07-29** (merge
commits c1d10ca e ef44274). **F1–F3 + ajustes estão na main AGUARDANDO DEPLOY**
— nada em produção ainda. F4 (Teams) não começou.
**F4 (Teams) MERGEADA na PR #212 (merge ddfecd7) — SPEC COMPLETA, 4/4 fases.**
**TUDO na main, NADA em produção: o deploy nunca rodou com esse código.**
**1º DEPLOY FEITO em 2026-07-29 (migrations 062–064 aplicadas, DAG no ar).**
O 1º ciclo LEU tudo certo (SSH ok, parser segmentou 3 runs e identificou os 10
jobs filhos de BI_PRESTAMISTA.SeqSsdPrs_CargaDiaria) mas GRAVOU ZERO por bug de
placeholder — ver [[orquestra-placeholder-pyodbc-pymssql]]. **Fix mergeado na
PR #214 (merge 4b2bae5); AGUARDANDO NOVO DEPLOY** só de `dags/` (nenhuma
migration nova). Depois do deploy: conferir
`SELECT * FROM etl_ds_supervisao_run_filho` — se os 10 filhos aparecerem com
seus códigos, a análise de dependência está de pé.
Job de teste em produção: **BI_PRESTAMISTA.SeqSsdPrs_CargaDiaria** (janela
05:00–06:00, roda ~05:20 e termina ~13:43, 9 jobs filhos diretos).

**F6 — varredura de NÍVEIS MERGEADA (PR #215, merge 7e55921, migration 065);
AGUARDANDO DEPLOY (migration 065 + dags/ + front).** O
painel com dado real provou que o sucesso falso é RECURSIVO: CargaDiaria "ok" →
Dim "concluído" → DimSocios "Concluído" → **DimSocios_01_ext ABORTED** (nível 3).
Cada sequence intermediária esconde o nível de baixo. **A varredura tem de ser em
LARGURA** — nenhum job do nível 1 aparecia falhado, então descer só pela cadeia
de aborts (o "Causa-raiz" do console) não acha nada. 4 níveis por padrão;
expansão 1x por run (coluna `expandido`) com orçamento de chamadas SSH E de
tempo por ciclo; run do filho escolhido pelo que começou dentro da execução do
pai; proteção contra laço. A 065 ZERA o aprendizado (estrutura de 1 nível é
incompleta por construção; mantê-la faria todo job de nível 2+ virar
FILHO_AUSENTE) → a amostra mínima de 3 execuções recomeça.

**F5 — análise de dependência MERGEADA (PR #213, merge d94b69c, migration 064).**
Resolve caso REAL de produção: sequence termina "Finished OK" com job filho
ABORTADO e o DataStage não propaga a falha p/ o pai — o abort passava
despercebido. Agora sucesso REAL = sequence OK **e** nenhum filho abortado.
Tipos novos: SUCESSO_FALSO e FILHO_AUSENTE. A estrutura de filhos é APRENDIDA
só de execuções com sucesso real (frequência mín. 80% + amostra mín. 3 execuções
evitam alarme com job condicional; coluna `aprendido` impede recontar o mesmo
run a cada 15 min). Só abort (3) alerta por decisão do usuário; crash (96),
parado (97) e validação (13) são gravados e exibidos sem card → ampliar é
mexer em CODIGOS_DE_FALHA. No painel, sucesso_falso fica acima de nao_executou
e o dia NÃO fica verde ("Falhou abaixo").

F4: `dags/utils/ds_teams.py` (montar_card puro + enviar_card) e a etapa de
notificação da DAG. REGRAS: `notificado_em` só após 2xx; a URL do webhook nunca
entra em log (erros citam o canal pelo nome); SITUACAO_INICIAL sai verde, não
vermelho. Contenções: janela de reenvio de 2 dias e lote de 50/ciclo com o corte
logado (Variables DS_SUPERVISAO_JANELA_NOTIFICACAO_DIAS e _LOTE_NOTIFICACAO).
✔ Ordem que funcionou para PR empilhada: mergear a base SEM `--delete-branch`,
depois `gh pr edit <filha> --base main`, mergear a filha e só então apagar a
branch base.

PR #211 (migration 063): projeto vira lista fechada, **mensagem por tipo de
alerta** com variáveis de contexto ({janela_inicio}, {tolerancia}, {limite}…),
descrição obrigatória, template_id removido. A mensagem é renderizada NA
DETECÇÃO e guardada em etl_ds_supervisao_evento.mensagem — a F4 só entrega.
**GOTCHA de UI (vale para todo o projeto): o `hint` do design system é popover
`absolute` e é CLIPADO dentro de qualquer contêiner com `overflow-y-auto`
(Modal, dock do FluxoEditor) — z-index não resolve. Use a prop `ajuda` (texto
visível abaixo do campo) em formulário dentro de modal.** Pendente fora do
escopo: PainelNotificacao/PainelSql/PainelDecisao ainda usam `hint` no dock.

F3 entregue: `GET /dashboard/supervisao?date_ref=` (get_current_user) +
`ui-react/src/components/dashboard/SupervisaoCard.tsx` no Dashboard + 24 testes.
DECISÃO: o estado do dia é **derivado dos eventos gravados pela DAG**, nunca
reclassificado na API — regra escrita em dois lugares divergiria. Precedência:
sem_verificacao > abortado > nao_executou > atrasado > executando > ok > sem_registro.

⚠️ GOTCHA de PR empilhada (erro cometido aqui): mergear a PR base com
`gh pr merge --delete-branch` **fecha** a PR filha (CLOSED, não retarget) e não
dá para reabrir enquanto a branch base não existir. Correção: recriar a branch
base com `git push origin <sha>:refs/heads/<branch>`, `gh pr reopen`,
`gh pr edit --base main`, mergear e só então apagar. Melhor ainda: mergear a base
SEM `--delete-branch` quando houver PR empilhada.

F1 entregue: migration 062 (3 tabelas), `api/routers/ds_supervisao.py` (CRUD sob
`require_ds_console`), `ui-react/src/components/console/SupervisaoTab.tsx` (aba
nova no Console DS) e 72 testes de validação.

F2 entregue: `dags/utils/ds_logsum.py` (parser, porte do TS),
`dags/utils/ds_supervisao_regras.py` (classificação pura) e
`dags/etl_ds_supervisao_monitor.py` (ciclo de 15 min, SSH única, upsert de runs,
eventos idempotentes, expurgo às 03h) + 79 testes. Total 759 passando.
GOTCHA de teste: `int(MagicMock())` devolve 1 — asserção sobre Variable stubada
passava por acidente; testar com valores reais injetados.
Baseline medido no HEAD por stash: os 6 erros de eslint de `DsConsole.tsx` e as
5 falhas de pytest JÁ EXISTEM na main — não são da PR.

Demanda do usuário (prioridade trazida fora do backlog de [[orquestra-fluxo-etapas]]):
cadastrar jobs DataStage supervisionados, coletar o resumo de runs a cada 15 min,
mostrar alerta no Dashboard e notificar canal do Teams.

Decisões fechadas na entrevista:
- Coleta por **DAG Airflow a cada 15 min** (SSH único reaproveitado), não SSH ao vivo no request.
- Gatilhos: ABORTOU, NAO_EXECUTOU, ATRASO (janela de início + tolerância) e
  ESTRUTURA (o próprio `dsjob` não lê o job). Warning ficou de fora.
- Cadastro fica **dentro do Console DataStage** (aba nova), não no Admin.
- Painel visível a **todos** no Dashboard, reusando o seletor de data que já existe.
- Teams **1x por ocorrência**, reusando `etl_msg_grupo` + `etl_msg_template`.
- Grava início E término de cada run por dia → base para sugerir SLA **depois**
  (sugestão de SLA está no Escopo OUT desta entrega).
- 10–30 jobs supervisionados; retenção de 1 ano.
- **Vigência por job**: o usuário escolhe a data em que o monitoramento passa a
  valer; com vigência hoje, o primeiro ciclo já manda um **card de situação
  inicial** com o cenário do dia (mesmo sem problema) para ele validar a config.
- Lista de jobs é **dinâmica** (entra/sai pela tela, sem carga inicial) e a
  remoção é **lógica** — o histórico de SLA precisa sobreviver ao descadastro.
- `-max` do logsum é **por job** (`max_linhas`, default 200, teto 2000).
- Canal de homologação **já existe** no `etl_msg_grupo`; a migration não cria
  grupo. Fluxo do usuário: homologar no grupo de teste → trocar para o oficial.
- **O usuário decide quando subir cada fase.**

Fases: F1 modelo+cadastro · F2 parser Python + DAG · F3 painel no Dashboard · F4 Teams.

Achados do levantamento que valem além desta spec:
- O "Resumo dos runs" do Console DS (`DsConsole.tsx:827`) **não tem janela de 7 dias** —
  é `dsjob -logsum` ao vivo, limitado por `-max` (default 200, exibe 15 runs).
  Os "7 dias" são a retenção do log no DataStage.
- O parser que segmenta o logsum em **runs** só existe em TypeScript
  (`DsConsole.tsx:116`). O lado Python (`etl_ds_monitor_centralizado.py:101`) só
  tem `_current_run_lines`/`_parse_child_jobs`, que não separam múltiplos runs —
  por isso a F2 precisa de parser novo com fixtures reais.
- `require_ds_console` (`api/deps.py:215`) libera admin **ou** o recurso
  `tela_ds_console` — não precisa criar permissão nova.
- Padrão de dedup já existente: índice único de `etl_sla_alert`
  (`sql/migrations/013_operacao_fase2.sql:28`), reaproveitado no desenho.
- GOTCHA de deploy: `dags/` só é sincronizado **com confirmação** (etapa 5 do
  `scripts/deploy.sh`) — DAG nova pode não subir e a feature fica muda em produção.

Pendências registradas na §8 da spec: canal de homologação do Teams, lista real de
jobs e janelas, `-max` por job ou global, e se o cadastro nasce ativo ou inativo.
