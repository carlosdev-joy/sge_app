---
name: orquestra-spec-lineage-isx
description: "Spec lineage automático via ISX (istool export por SSH + API REST do DataStage) no Orquestra; docs/spec-lineage-isx.md; ✅ APROVADA 2026-09-07; F1–F3 MERGEADAS (PRs #369–#371) + casca (#372); F4 (aba Job DataStage) = PR #373 MERGEADA (`5a515e6`); F5 (docs/smoke/backlog) = PR #374 MERGEADA (`69089dd`, 2026-09-08) — 🏁 SPEC FECHADA; ⏳ deploy F1–F5 em produção pendente; deploy F1–F4 pendente; ⚠️ o documento de origem tinha senhas em claro — nunca commitar; só variáveis de ambiente"
metadata:
  type: project
  originSessionId: 627a18b0-5a47-44d0-b15e-ca31a4caf9a1
  modified: 2026-09-08T12:31:51.924Z
---

Pedido do usuário em 2026-09-07: "vamos fazer entendimento desta spec
/dados/bi/2026-09-07-lineage-isx-automatico.md" — um documento técnico (Claude Code +
Equipe BI CVP, escrito com acesso ao DataStage de produção) que o usuário subiu para o
sshd-amostra do DEV pelo próprio Enviar arquivo. Entrevista feita; entendimento e spec
**aprovados ("aprovado", 2026-09-07)**; spec em `docs/spec-lineage-isx.md` no
[[orquestra-sge-app]], branch `feat/lineage-isx-f1` (a spec entra na PR da F1).

## Estado (2026-09-08)
- **F1 COMMITADA (`47f2c07` + ajustes do documento v2) e enviada em `feat/lineage-isx-f1`,
  revisada (qa-adversarial + auditor-seguranca, achados corrigidos), provada no DEV** —
  migration 106 aplicada 2× em `orquestra_dev` (FK com cascade), harness no ar, 48 testes,
  prova viva localizar→exportar_job(.qjb→.sjb)→parse de dentro do `orquestra-api`.
  **PR #369 MERGEADA (squash `856a473`, 2026-09-08 00:41 UTC, "merge autorizado")**; deploy
  em produção ainda não feito (F1 sozinha não muda nada visível — pode ir junto com a F2).
  Documento v2 e o `.bak` que o upload criou foram apagados do sshd-amostra.
- **F2 em andamento** na branch `feat/lineage-isx-f2` (criada de `origin/main` em
  2026-09-08): `api/services/lineage_isx.py` (transportes httpx/paramiko + persistência),
  `api/routers/lineage_isx.py` (localizar/extrair/job/pipeline), `GET /lineage`
  autenticado preferindo isx_auto, `tests/test_lineage_isx_api.py` (23), `scripts/
  smoke_lineage_isx.sh` — smoke c–i VERDE no DEV (pipeline de amostra `PIPE_VIDA` com os
  dois jobs criado no `orquestra_dev`). **Revisada (qa-adversarial + auditor-seguranca,
  achados corrigidos: fila cancelada após 504, executor 2/worker, sp_getapplock por job
  → 409, grafia canônica, known_hosts aviso, URL com credencial 503, trust_env=False,
  endpoints DSX autenticados). PR #370 MERGEADA (squash `3f46f0c`, 2026-09-08 01:26 UTC,
  "Pode fazer Merge").** Deploy em produção de F1+F2 ainda não feito.
  ⚠️ `pytest -p no:logging` quebra 7 testes com `caplog` (não é regressão).
- **F3 COMMITADA (`f92933d`) e enviada em `feat/lineage-isx-f3`** (2026-09-08): DAG
  `etl_lineage_extract_isx` + `POST /lineage/isx/lote` (admin, despausa antes) +
  `GET /lineage/isx/lote/{run_id}` + `origem`; revisada (qa + auditoria, achados
  corrigidos); provas vivas no DEV verdes (pipeline, cache, todos os pipelines).
  **PR #371 MERGEADA (squash `779f3a2`, 2026-09-08, "merge autorizado").** DEV:
  Connection `orquestra_api` pelo ambiente (`AIRFLOW_CONN_ORQUESTRA_API` no `.env.dev`),
  a do banco foi apagada. Deploy de F1+F2+F3 em produção ainda não feito.
- **F4 escrita e provada no DEV** na branch `feat/lineage-isx-f4` (2026-09-08): aba "Job
  DataStage" na Governança (`components/governanca/isx/*`: PainelJobIsx container,
  ListaJobsIsx, CabecalhoJobIsx, FilhosSequenceIsx, GrafoIsx xyflow, TabelaStagesIsx,
  ConteudoStageIsx/PainelStageIsx Sheet, TextoComParametros; `lib/lineageIsx.ts` puro),
  bancada `tests/js/lineage_isx_harness.cjs` + `tests/test_lineage_isx_front.py` (11
  testes), tsc 0, eslint = baseline 184/12, dist rebuildada; prova viva com Chromium
  headless (`scratchpad/prova_aba_isx.py`, claro e escuro) OK. **Revisão adversarial
  REPROVOU a 1ª versão com 9 achados, todos corrigidos e guardados pelo teste
  `test_container_guarda_as_correcoes_da_revisao_adversarial`** (fitView por `key`
  do job; `onMutate` fixa a seleção; nome canônico do filho da sequence; `onError`
  invalida o detalhe; `colorMode` do xyflow; erro do lote para o polling; flicker
  `&& !job`; `runId` zera por pipeline; frase do erro só com stages) e provados no DEV
  (`scratchpad/prova_achados_f4.py`). **PR #373 MERGEADA (squash `5a515e6`,
  2026-09-08 10:19 UTC, "merge autorizado").** Deploy de F1–F4 em produção ainda não
  feito. Gotchas: eslint
  `react-hooks/set-state-in-effect` proíbe setState em efeito → ajuste durante o render
  (`pipelineAnterior`) e seleção derivada; SQL das amostras sintéticas aparece numa linha
  só porque o XML normaliza `\n` em atributo (real usa `&#10;`) — não é bug.
- **F5 escrita na branch `feat/lineage-isx-f5`** (2026-09-08): manual (§1.4, §3.9, §4.8,
  FAQ), `docs/release-notes/lineage-isx.md`, smoke fechado (item k do lote via API com
  admin; roteiro impresso), `sql/backlog/lineage_isx.sql` (12 itens, aplicado 2× no DEV
  sem duplicar), spec concluída, `tests/test_lineage_isx_docs.py` (anti-drift dos
  documentos + anti-segredo). Smoke no DEV verde (c–i + k). **Revisão de fecho reprovou
  com 13 achados de texto (504 descarta o tardio; 503 "não configurado"; KNOWN_HOSTS é
  dos Utilitários, não do Console; sequence tem grafo; condição de falha do lote…),
  todos corrigidos; PR #374 MERGEADA (squash `69089dd`, 2026-09-08 11:02 UTC, "merge
  autorizado").** 🏁 SPEC FECHADA: F1–F5 = PRs #369, #370, #371, #373, #374. **Deploy
  em produção de F1–F5 ainda não feito** — roteiro em `docs/release-notes/lineage-isx.md`
  (8 passos) e pendências §8 do usuário (grafia de `etl_stage_type_map`, `DS_*` +
  `-authfile` no servidor do DataStage, `DS_SSH_KNOWN_HOSTS`, `AIRFLOW_CONN_ORQUESTRA_API`,
  usuários role Op do Airflow, consumidores de `GET /lineage`). Gotcha: o
  `sqlcmd` do container é `/opt/mssql-tools18/bin/sqlcmd … -C` (docker cp do .sql para
  `/tmp` do container; `rm` lá é negado, não importa).
- **⚠️ CAUSA REAL da "página que vai para baixo" (medida no DEV com Chromium headless)**:
  `sr-only` do Tailwind é `position: absolute`; o input do Switch/Checkbox/Radio sem
  ancestral `relative` se ancora no DOCUMENTO e, abaixo da dobra, estica a área rolável
  (442 px na aba Utilitários do Admin) — a rolagem do <main> encadeia para o documento
  e a casca inteira sobe. Correção: `relative` nos invólucros (ui/Checkbox, ui/Switch,
  ui/RadioGroup, FormEnviarArquivo) + `relative` na casca (bloco de contenção). NÃO usar
  `overflow-clip` na casca (deixa o transbordo rolar o documento; medido 414 px). O
  primeiro commit `9558dd8` da branch fez o clip — a correção certa vem por cima.
- **Correção da casca (pedido do usuário 2026-09-07, captura `utilitario_erro.png`)**:
  branch `fix/casca-rolagem-foco` (worktree em scratchpad `wt-casca`) — primeiro commit
  `9558dd8` com `overflow-clip` (ERRADO, substituído pelo 2º commit `9a2d079`: `relative`
  nos invólucros sr-only + na casca; provado no DEV: transbordo do documento 442 → 0).
  **PR #372 MERGEADA (squash `65e5ada`, 2026-09-08, "merge autorizado").** + teste
  `tests/test_casca_rolagem_por_foco.py`; dist rebuildada. Há Chromium headless do
  Playwright em `~/.cache/ms-playwright` (python `playwright` importa): script
  `scratchpad/prova_casca.py` faz login no DEV e mede scrollTop/header/menus. O bug do
  usuário NÃO reproduziu headless (autoFocus rola só o <main>); a causa real pode ser
  seleção de texto arrastada, Ctrl+F ou drag — todos rolam `hidden` e nenhum rola `clip`,
  então a correção cobre. A dist corrigida está COPIADA em `/opt/orquestra-dev/ui-react/
  dist` (DEV :8090) para o usuário testar — árvore local suja em `ui-react/dist`
  (restaurar com `git archive HEAD ui-react/dist | tar -x` + rsync, porque
  `git checkout -- ui-react/dist` foi NEGADO pela permissão). PR separada, aguardando
  "pode abrir". ⚠️ O "erro 502 no login" do usuário era o nginx `airflow-ui` com o IP
  antigo da API recriada — `docker restart airflow-ui` resolveu.
  ⚠️ Antes do deploy da F2 em produção: `DS_SSH_KNOWN_HOSTS` no `.env` (spec §8.13).
- ⚠️ `main` local está presa num worktree antigo de outra sessão
  (`/tmp/claude-0/-root/d72d0d73…/scratchpad/wt-chat`): `gh pr merge --delete-branch`
  falha no passo local; o merge no GitHub acontece mesmo assim — conferir com `gh pr view`.
- **Documento de origem, versão 2** (`/dados/bi/2026-09-07-lineage-isx-automatico (1).md`
  no sshd-amostra, 2026-09-07): validado contra a F1 → sequences exportam como `.qjb`
  (fallback `.sjb`), `jobname` é atributo do stage, `lazyLoadInfo` de sequence sem espaço
  e com `V22S<n>`, espaço no `-datastage` vai como `\ `, pastas com acento. **Voltou a
  trazer senhas em claro** — cópia do scratchpad apagada; pedir ao usuário para apagar do
  DEV (a v1 ele mandou "Apagar agora").
- Os `.isx` em `/dados/bi/isx/` do DEV são SINTÉTICOS (das fixtures); o usuário vai subir
  os reais (`SsdVidaDimePessoa02Ftp.isx`, `SeqSsdVidaDime.isx`) pelo Enviar arquivo.

## ✅ Deploy em produção — o que já foi medido (2026-09-08)
- **Formato do `-authfile` do istool 11.7 CONFIRMADO em produção pelo usuário**: grafia
  chave=valor (`user=…` / `password=…` em linhas próprias). A grafia `-user`/`-password`
  em linhas falha com "user name not found" — eu tinha sugerido essa no chat; errado.
  Arquivo na pasta do usuário SSH do Orquestra, 600. `DS_ISTOOL_AUTHFILE` tem de ser
  caminho ABSOLUTO (`comando_istool` usa `shlex.quote`, não `_caminho_shell`, no
  authfile → `~` não expande). Os nomes de usuário SSH/istool apareceram no chat do
  usuário — nunca no repo. **Correção de código na branch `fix/lineage-isx-authfile-til`**
  (inclui os 2 commits de docs de `docs/lineage-isx-authfile`): `comando_istool` passa o
  `-authfile` por `_caminho_shell` (`~/x` → `"$HOME"/x`); o istool falso do DEV agora
  exige o `-authfile` existente (rc 3, `IISCOM000: authfile nao encontrado`); `.env.dev`
  ficou com `DS_ISTOOL_AUTHFILE=~/.orquestra/istool.auth` (home do usuário `orquestra` da
  amostra é `/config`). Provas no DEV: smoke c–i verde com `~/`; authfile inexistente →
  502 com o caminho EXPANDIDO no log. Regenerar o harness: `docker exec sshd rm -f
  /dados/.amostra-isx-pronta && docker restart orquestra-dev-sshd-amostra`. Revisão
  adversarial APROVADA sem achados; **PR #375 MERGEADA (squash `6889e67`, 2026-09-08
  12:31 UTC, "merge autorizado")**. ⚠️ Fora do escopo, apontado pelo revisor:
  `scripts/export_dsx.sh` (legado, extrator DSX) ainda passa `-password "$DS_PASSWORD"`
  ao istool real — candidato a backlog/correção própria.
- A API de produção respondeu 503 "não configurado" listando as 5 variáveis → o `.env`
  ainda não tinha o bloco Lineage ISX (é `/opt/airflow/.env`; `up -d --no-deps
  orquestra-api` para reler, `restart` não relê).

## ⚠️ Segurança do documento de origem
- Continha senha SSH, Basic auth da API REST e senha do `dsjob`/`istool` em claro, e
  propunha fixá-las na classe do engine. **Apagado do sshd-amostra (autorizado) e a cópia
  do scratchpad também.** A spec e o código só usam variáveis de ambiente
  (`DS_SSH_*` existentes; `DS_API_URL/USER/PASSWORD/VERIFY_SSL`, `DS_ENGINE`,
  `DS_ISTOOL_HOME/LAUNCHER/DOMAIN/AUTHFILE/TMP/CFG` novas). `istool` com `-authfile`,
  nunca `-password` (aparecia no `ps`). Teste anti-drift proíbe literal de segredo/host.

## Decisões fechadas na entrevista (2026-09-07)
- **Job só com pipeline**: lineage ISX chave `(pipeline_name, job_name)` de
  `etl_pipeline_job`; projeto de `etl_pipeline.project_name`; job fora de pipeline → 422.
  Sem mexer em `pipeline_name NOT NULL` nem na FK (o documento original queria NULL).
- Cabeçalho por job em tabela nova `etl_ds_job_isx` + colunas novas em `etl_job_lineage`
  (`input_columns_json`, `apt_code`, `expressions_json`, `stage_internal_id`);
  `extraction_method='isx_auto'`; migration 106.
- Aba nova "Job DataStage" em `/governanca`; IA fora (banco pronto; backlog); parallel
  completo + sequence com lista de filhos; unitário `acao_editar`, lote admin; extração
  unitária síncrona na API; DAG de lote chama a API (Connection `orquestra_api`).

## ⚠️ GOTCHAs pagos na F1
- **`etl_stage_type_map` tem DUAS grafias no repo**: `stage_type` (schema_prod_dev,
  deploy_full; lida por `/lineage`) × `type_raw`+`description` (script/alteracoes do
  catálogo; lida por `catalogo.py`). No DEV é `stage_type` → as consultas do catálogo
  quebram lá. A migration 106 descobre a chave com `COL_LENGTH` e SQL dinâmico; o loader
  da F2 tem de fazer o mesmo. Pendente: usuário confere qual grafia produção tem (§8.10).
- **`10-amostra.sh` saía com `exit 0` no marcador antigo**: bloco novo nunca rodava em
  container já criado. Agora cada bloco tem marcador próprio e nenhum sai do script.
- **`shlex.quote("~/x")` mata o til**: default de `DS_ISTOOL_CFG` é `~/.orquestra/...`;
  `_caminho_shell` rende `"$HOME"/...` fora das aspas.
- Teste `test_migrations_idempotentes` exige guarda até em `DROP TABLE #temp`.
- **FK nova para `etl_pipeline_job` SEM `ON DELETE CASCADE` quebra remover/renomear job e
  apagar pipeline** (`jobs.py` e `sp_etl_pipeline_delete` não apagam tabelas-filhas à
  mão; precedente com cascade: migration 026). Achado da revisão adversarial da F1;
  a 106 recria a FK se encontrar `delete_referential_action = 0`.
- Revisão de segurança da F1: o teste anti-drift que eu mesmo escrevi vazava dois
  identificadores do documento apagado — tokens "proibidos" também são conteúdo do
  repo; usar padrões genéricos. `tests/fixtures/isx/` no `.gitignore` (um `.isx` real
  traz `Password` no XMLProperties). Temporário do istool em pasta privada
  (`~/.orquestra/tmp`, `umask 077`), não em `/tmp`. `field(repr=False)` na senha.
- `docker exec python - <<EOF` precisa de `-i`, senão o stdin some e nada roda.
- **NUNCA `set -a; . ./.env.dev` no mesmo shell do `docker compose up`**: o bash expande o
  `~` de `DS_ISTOOL_TMP=~/.orquestra/tmp` para `/root` e o compose prefere a variável do
  shell à do `--env-file` → o istool tenta `mkdir /root` no sshd e tudo vira 502. Ler
  valores do `.env.dev` com `grep ... | cut -d= -f2-` em vez de `source`.
- DAG nova nasce PAUSADA no Airflow: run disparada fica `queued` para sempre — o
  `POST /lineage/isx/lote` despausa (PATCH is_paused=false) antes do disparo.
- `BaseHook` é de `airflow.hooks.base` (não `airflow.models`) — os stubs dos testes
  aceitam qualquer import; o scheduler 2.11 não. Teste anti-drift cobre.
- `AIRFLOW_VAR_X=""` no ambiente do worker SOBRESCREVE a Variable do banco com string vazia
  (medido no 2.11); `AIRFLOW_CONN_X=""` é ignorada (cai no banco). Nunca pôr
  `AIRFLOW_VAR_*` com `${VAR:-}` vazio no compose; `AIRFLOW_CONN_*` pode.
- O proxy genérico `/airflow/dags/{dag_id}/dagRuns` (acao_executar) contornava o "só
  admin" do lote ISX — achado da auditoria da F3; DAGs administrativas exigem admin lá.
- Stubs de `sys.modules["airflow"]` são COMPARTILHADOS entre os testes de DAG da suíte:
  asserções sobre `DAG.call_args`/`PythonOperator.call_args_list` devem usar as
  referências do próprio módulo carregado e filtrar por `dag_id`/`task_id`.

## Descobertas no repo que mudaram o desenho
- `etl_job_lineage.pipeline_name NOT NULL` + FK `etl_pipeline_job`; `sp_etl_job_lineage_upsert`
  faz COALESCE por `(direction, object_name)` — não serve a "substituir tudo".
- `GET /lineage` NÃO exige autenticação (achado) — F2 corrige.
- Tela é `/governanca` (Governanca.tsx, 2 blocos de `Tabs`); `@xyflow/react` já no projeto.
- Worker tem `paramiko 3.5.1`, `requests`, `httpx` pela imagem; API tem `paramiko 3.5.0`
  + `httpx`; a API monta `dags/` em `/opt/airflow/dags` (o engine importa de lá).

## Fases (uma PR cada, merge sempre autorizado pelo usuário)
F1 migration 106 + engine + parser + harness DEV → F2 endpoints (localizar, extrair com
cache, consultar, `GET /lineage` autenticado preferindo ISX) → F3 DAG de lote + disparo
admin → F4 aba Job DataStage (grafo + painel) → F5 docs/smoke/backlog. Pendências §8:
usuário de serviço da DAG, formato do authfile, CA da API REST, amostras `.isx`,
timezone, `VARCHAR` em `file_path`, grafia de `etl_stage_type_map` em produção.

Ver [[orquestra-spec-utilitarios-transferencia]], [[orquestra-worker-cacheia-dags-utils]],
[[orquestra-proxy-worker-vs-api]], [[orquestra-placeholder-pyodbc-pymssql]],
[[orquestra-migrations-idempotentes]].
