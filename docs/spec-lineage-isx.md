# Spec: Lineage automático via ISX (DataStage) — Orquestra
Data: 2026-09-07 · Status: **concluída** — F1 = PR #369, F2 = PR #370, F3 = PR #371, F4 = PR #373 mergeadas (2026-09-08); F5 (manual, release note, smoke, backlog) na PR de fecho

Consolida, no formato da casa, o documento técnico "Spec — Lineage Automático via ISX"
(Equipe BI CVP, 2026-09-07), levantado com acesso ao DataStage de produção. **Nenhuma
credencial entra neste arquivo nem no repositório**: só nomes de variáveis de ambiente.
Aquele documento continha senhas em claro e foi retirado do servidor de DEV.

## 1. Visão

O lineage dos jobs DataStage depende hoje de um `.dsx` exportado à mão e copiado para
`dsx/`: fica meses defasado do job em produção e é pobre (só nomes de tabela, colunas
raras, nenhuma transformação). Em 2026-09-07 o banco tinha 183 registros manuais, 92 por
DSX e 27 sem método.

Quando estiver pronto, o Orquestra **exporta o job por conta própria** com o `istool` do
IBM Information Server (formato ISX), via SSH no servidor do DataStage, lê o XML de
definição e grava por stage o **SQL completo**, o DSN, o path do arquivo, as **colunas
com tipo e tamanho**, as **expressões coluna a coluna**, o **APT code** do Transformer e
o **fluxo** entre stages. Só reextrai quando o `lastModified` do job mudou na API REST do
DataStage. Regra do usuário: **só para job que já está num pipeline do Orquestra**. A
Governança ganha a aba **Job DataStage**, com grafo e painel por stage. O banco fica
pronto para uma IA consultar — a IA em si é spec própria.

## 2. Escopo

**IN:**
- **Engine ISX** (`dags/utils/isx_engine.py`, transportes injetáveis): localizar o job na
  árvore de pastas do DataStage pela API REST; conferir `lastModified`; montar e rodar o
  `istool export` por SSH (JAR do launcher, `-authfile`, arquivo temporário único, `sftp
  get` + `rm`); abrir o ZIP; **parser puro** do `DSJobDefSDO` (`.pjb` parallel, `.sjb`
  sequence): parâmetros (`has_ParameterDef`), stages (`contains_JobObject … StageSDO`)
  com direção (Context → topologia), classe (via `etl_stage_type_map`), `XMLProperties`
  (DSN, SQL), path de DataSet/SequentialFile, colunas de saída e de entrada
  (`has_OutputPin`/`has_InputPin` → `has_DSMetaBag`), APT code (`TrxGenCode` →
  `mainloop`), expressões (`hasValue_Derivation`), fluxo (`lazyLoadInfo`); sequence →
  lista de jobs filhos (`CJobActivity`).
- **Chave e regra**: `(pipeline_name, job_name)` de `etl_pipeline_job`; o projeto vem de
  `etl_pipeline.project_name`. Job fora de pipeline → 422 nomeando a regra. Sem mudança
  em `pipeline_name` nem na FK de `etl_job_lineage`.
- **Cache**: cabeçalho por job em `etl_ds_job_isx` com `ds_last_modified`; a extração
  compara com a API REST (~0,4 s) e só roda o `istool` se mudou; `force` reextrai.
- **Endpoints** (F2): localizar, extrair (síncrono, executor dedicado de 4 threads, teto
  de 60 s, `acao_editar`), consultar por job e por pipeline, `GET /lineage` preferindo
  `isx_auto` quando existe e **passando a exigir autenticação** (hoje é aberto).
- **Lote** (F3): DAG `etl_lineage_extract_isx` que itera os jobs dos pipelines
  cadastrados (um pipeline ou todos), chama a API por job com 4 threads, timeout por job,
  erro individual não aborta; disparo pela API só para admin, com estado consultável.
- **Tela** (F4): aba **Job DataStage** em Catálogo & Lineage (`/governanca`, bloco de
  abas `lineage/catalogo/…`): pipeline → jobs com estado ISX → Extrair/Atualizar → grafo
  (`@xyflow/react`, já no projeto) + tabela de stages + painel lateral (SQL, colunas,
  expressões, APT colapsável), badge para `#PSet.X#`, indicador de cache; sequence mostra
  os filhos com Extrair em cada um.
- **Harness de DEV** (F1): `istool` de mentira dentro do `sshd-amostra` (mesma árvore
  `/opt/IBM/InformationServer/...`, `java` de shell que devolve um `.isx` de
  `/dados/bi/isx/<job>.isx`) e `ds-api-amostra` (HTTP com os JSONs da API REST). Os `.isx`
  reais (um parallel, um sequence, sem dado sensível) o usuário sobe pelo **Enviar
  arquivo** para `/dados/bi/isx/`.
- Coexistência: linhas `manual` e `dsx_auto` ficam; reextrair apaga só as `isx_auto` do
  job e reinsere numa transação.

**OUT (explícito):**
- Assistente de IA, prompt, consultas geradas por LLM, embeddings (§9 do documento
  original) — spec própria, com custo de modelo avaliado; esta deixa o banco pronto e um
  endpoint de consulta por job. Backlog: "Lineage ISX: contexto para IA".
- Export pela API REST do DataStage (`/export`, `/stages`, `/image` respondem 400 nessa
  instalação) e `dsjob -export` (não existe na versão).
- Resolver valores de Parameter Set (`#PSet.X#` fica como está, com badge).
- Substituir o extrator DSX ou o preview "Comparar XML × Atual": continuam; a consulta
  prefere ISX.
- Lineage de job que não está num pipeline do Orquestra; editar lineage ISX à mão.
- Extração recursiva automática dos filhos de um sequence (cada filho é extraído por
  demanda ou no lote). Backlog: "Lineage ISX: extrair filhos do sequence em cadeia".
- Dependência Python nova: `paramiko` e `httpx` já estão na API; `paramiko`, `requests`
  e `httpx` já estão na imagem do Airflow (worker).

## 3. Arquitetura proposta

### Back (`api/`)
- `api/routers/lineage.py` (existente: `GET /lineage`, `PUT /lineage/job`,
  `POST /lineage/extract-dsx`, …) ganha:
  - `GET /lineage/isx/localizar?pipeline_name&job_name` — `get_current_user`; resolve
    `ds_project` em `etl_pipeline`; se `etl_ds_job_isx.ds_folder_path` já existe, confere
    direto o `jobdesigns/{id}`; senão percorre `folders/…/contents` em largura (teto de
    5.000 nós e 30 s) → `{encontrado, ds_project, folder_path, job_type, last_modified,
    api_id}`.
  - `POST /lineage/isx/extrair` `{pipeline_name, job_name, force}` —
    `require_perm(PERM_EDITAR)`; 422 se o job não está em `etl_pipeline_job`; cache pelo
    `ds_last_modified` × API; extração em `_EXECUTOR_ISX` (`ThreadPoolExecutor(2)` POR
    worker do uvicorn — produção roda 2 workers → 4 JVMs do istool no total;
    `asyncio.wait_for` 60 s → 504 e a fila é cancelada, mesmo desenho de
    `routers/utilitarios.py`); grava cabeçalho + linhas numa transação com
    `sp_getapplock` por job (duas extrações do mesmo job: a segunda recebe 409);
    devolve o lineage completo e `cache_hit`. Nomes de pipeline/job saem do banco na
    grafia cadastrada (colação CI × DataStage case-sensitive).
  - `GET /lineage/isx/job?pipeline_name&job_name` — `get_current_user`; só banco.
  - `GET /lineage/isx/pipeline?pipeline_name` — `get_current_user`; um item por job de
    `etl_pipeline_job` com o estado ISX (extraído em, `ds_last_modified`, status, erro).
  - `POST /lineage/isx/lote` `{pipeline_name?, force}` — `get_admin_user`; dispara a DAG
    pela REST do Airflow (mesmo helper de `routers/admin.py`, `AIRFLOW_URL/USER/PASSWORD`
    de `deps.py`); `GET /lineage/isx/lote/{run_id}` lê o estado da run.
  - `GET /lineage` passa a exigir `get_current_user` (achado: hoje sem `Depends`) e a
    preferir `isx_auto` por job quando existe (`NOT EXISTS` na cláusula).
- Importa o engine do pacote das DAGs como o DSX faz (`_import_dsx_engine`: `DAGS_FOLDER`
  no `sys.path`; o container da API monta `dags/` só leitura).
- Transportes na API: SSH por `paramiko` com as variáveis `DS_SSH_*` que o Console e os
  Utilitários já usam (canal aberto à mão com timeout, como `services/ssh_arquivos.py`);
  REST por `httpx` com `DS_API_URL`, `DS_API_USER`, `DS_API_PASSWORD`, `DS_API_VERIFY_SSL`
  (`false` = aviso no log a cada arranque; `true` ou caminho de CA = recomendado).
- Shape de erro para o front: `detail` string em pt-BR; 422 regra do pipeline; 404 job não
  achado no DataStage; 502 istool/SSH falhou (`interno` só no log); 503 servidor não
  configurado; 504 teto; 409 só quando outra extração do MESMO job está em andamento.

### Engine (`dags/utils/isx_engine.py` — novo)
- `ConfigISX` lido do ambiente: `DS_ENGINE` (FQDN do engine, ex. no `.env.example`),
  `DS_API_URL`, `DS_ISTOOL_HOME` (padrão `/opt/IBM/InformationServer`),
  `DS_ISTOOL_LAUNCHER` (relativo ao home; padrão o JAR
  `Clients/istools/cli/plugins/org.eclipse.equinox.launcher_*.jar`), `DS_ISTOOL_DOMAIN`
  (`host:porta` dos serviços), `DS_ISTOOL_AUTHFILE` (caminho **no servidor**),
  `DS_ISTOOL_TMP` (padrão `~/.orquestra/tmp` — pasta PRIVADA do usuário SSH, com
  `umask 077`: o `.isx` traz credenciais de conexão e não pode nascer legível por todos
  num `/tmp` compartilhado), `DS_ISTOOL_CFG` (padrão `~/.orquestra/istool_cfg`).
- Funções puras (testáveis sem rede): `validar_nome(projeto|job)` (`^[A-Za-z0-9_.-]+$`,
  o mesmo espírito de `_SAFE_JOB_RE` do operador), `validar_pasta` (componentes
  `^[A-Za-z0-9_. -]+$`), `caminho_istool(engine, projeto, folder_path, job, tipo)`
  (`\\Jobs\\A\\B` → `Jobs/A/B`; PARALLEL → `.pjb`; SEQUENCE → `.qjb` e, se o istool
  disser "not found", `.sjb` — `caminhos_istool` + `exportar_job`; espaço no caminho vai
  como `\ ` dentro das aspas, porque o istool quebra no espaço mesmo entre aspas;
  componentes de pasta aceitam acento/parênteses), `comando_istool(cfg, caminho, archive)`
  (tudo por `shlex.quote`, `~/` vira `"$HOME"/`; `-authfile`, **nunca** `-password`;
  `umask 077` e pasta temporária privada), `parse_isx(bytes, mapa, job=)` (ZIP → XML →
  dict da §5 do documento original; `mapa` = linhas de `etl_stage_type_map`; raiz que
  não é `DSJobDefSDO`, job sem stage, DOCTYPE/ENTITY em qualquer codificação e membro
  acima do teto → 422/413; parâmetros `Encrypted`/senha mascarados); em
  `ds_stage_types.py`: `classe_do_tipo(stage_type, mapa)` e `direcao(classe, context,
  tem_entrada, tem_saida)`; o parse devolve `children` (só atividades com `JobName`) e
  `nao_reconhecidos`.
- Transportes injetáveis: `rest(caminho) -> dict | None` (caminho relativo à
  `DS_API_URL`, só `folders/…`/`jobdesigns/…` validados pelo engine — nunca `urljoin`)
  e `ssh() -> (executar, sftp)` (`contextmanager`). Na API: `paramiko` + `httpx`; na DAG
  não se usa (a DAG chama a API). Nos testes: fakes em memória — a mesma técnica do
  `FakeSftp` dos Utilitários.
- `exportar(ssh, cfg, caminho, job=) -> bytes`: `mkdir -p` do `DS_ISTOOL_CFG` + `cp -rn`
  da `configuration/` (uma vez por usuário, sem corrida entre chamadas), `istool export`
  com `-archive <tmp>/orq_<job>_<uuid8>.isx`, leitura por `sftp.open` com teto, `sftp.remove` em
  `finally`, teto de 60 s no canal; `stderr` do istool vai ao log, nunca à resposta.

### Dados
- Migration `106_lineage_isx.sql` (§4), etapa 6c do `deploy.sh`.
- `etl_stage_type_map` (já existe, semeada) é a fonte da classificação; a migration
  acrescenta (MERGE idempotente) os tipos PX que faltarem (`CTransformerStage`, `PxLookup`,
  `PxJoin`, `PxSort`, `PxFunnel`, `PxRemDup`, `PxAggregator`, `PxCopy`, `CJobActivity`…).
- Gravação: `DELETE … WHERE pipeline_name=? AND job_name=? AND extraction_method='isx_auto'`
  + `INSERT` por stage (a `sp_etl_job_lineage_upsert` faz `COALESCE` por
  `(direction, object_name)` e não serve a "substituir tudo").
- `etl_lineage_normalize.py` (quebra `sql_expression` em tabelas) continua valendo para as
  linhas ISX.

### Orquestração
- DAG `dags/etl_lineage_extract_isx.py` (F3): `dag_run.conf = {pipeline_name?: str,
  force: bool}`; task `listar_jobs` (SQL Server via `%s` — gotcha dos placeholders —
  `etl_pipeline_job ⋈ etl_pipeline.project_name`); task `extrair_em_lote`
  (`ThreadPoolExecutor(4)`, `requests.post(ORQUESTRA_API_URL + '/lineage/isx/extrair')`
  com a Connection `orquestra_api` do Airflow — login/senha de um usuário de serviço com
  `acao_editar` —, timeout 90 s por job, resumo `{extraídos, cache, erros[]}` no XCom e no
  log). **Decisão**: a DAG orquestra e a API extrai — uma credencial de DataStage, uma
  fila SSH, um só código de gravação (`?` da API), sem duplicar o upsert em `%s`.

### Front (`ui-react/src`)
- `pages/Governanca.tsx`: aba nova `isx` ("Job DataStage") no bloco de abas de lineage;
  o conteúdo vive em `components/governanca/isx/` (a página já tem 1.300 linhas):
  `PainelJobIsx` (seletor de pipeline reutilizando a busca da aba Lineage, lista de jobs
  com estado, botões Extrair/Atualizar só com `pode_editar`), `GrafoIsx` (`@xyflow/react`,
  nós por stage com par claro/escuro por direção — origem `emerald`, transformação
  `blue`, destino `amber` —, arestas com o nome do link, leiaute em camadas calculado em
  `lib/lineageIsx.ts` a partir de `flow_json`), `TabelaStagesIsx`, `PainelStageIsx`
  (SQL em `<pre>` mono com fundo fixo escuro — exceção documentada em
  `docs/ui-temas-cores.md` —, colunas, expressões `saída ← expressão (origem)`, APT code
  colapsado, badge `[PARÂMETRO: PSet.X]`), `CabecalhoJobIsx` (nome, projeto, tipo,
  descrição, última modificação, badge cache/extraído agora).
- `lib/lineageIsx.ts` (puro): tipos do contrato, `erroIsx` via `erroDaApi`, `leiaute`
  (camadas por profundidade no fluxo), `resumoStage`, `ehParametro`.
- Tokens da casa; `dist/` rebuildada e commitada na F4.

### Decisões e alternativas descartadas
- **Job só com pipeline** (decisão do usuário): descartadas `pipeline_name NULL` + FK
  relaxada (documento original), tabela separada e pipeline sintético.
- **Cabeçalho por job em tabela própria** em vez de repetir descrição/fluxo/parâmetros em
  cada linha de stage (documento original): menos duplicação, cache num lugar só.
- **DAG chama a API** em vez de rodar o engine no worker com `SSHHook`: evita segunda
  credencial REST no Airflow e um segundo upsert em `%s`.
- **`-authfile`** em vez de `-password` na linha de comando: a senha aparecia no `ps` do
  servidor e nos logs.
- **Grafo com `@xyflow/react`** (já no projeto, usado no editor de fluxo) em vez de lib
  nova.
- **`GET /lineage` autenticado**: hoje qualquer um na rede lê o lineage; a correção entra
  na F2 e é dita na PR.

## 4. Modelo de dados

Migration `sql/migrations/106_lineage_isx.sql`, idempotente (`IF OBJECT_ID … IS NULL`,
`IF COL_LENGTH … IS NULL`, MERGE no mapa), blocos com `GO`, aplicada na etapa 6c.

**`dbo.etl_ds_job_isx`** (cabeçalho por job, um por `(pipeline_name, job_name)`):

| coluna | tipo | notas |
|---|---|---|
| `id` | `INT IDENTITY(1,1) NOT NULL` | PK |
| `pipeline_name` | `NVARCHAR(200) NOT NULL` | FK `(pipeline_name, job_name)` → `etl_pipeline_job` |
| `job_name` | `NVARCHAR(200) NOT NULL` | |
| `ds_project` | `NVARCHAR(50) NOT NULL` | de `etl_pipeline.project_name` |
| `ds_folder_path` | `NVARCHAR(500) NULL` | `\Jobs\SsdVida\_Dime` (como a API devolve) |
| `ds_job_type` | `VARCHAR(20) NULL` | `PARALLEL` / `SEQUENCE` |
| `ds_last_modified` | `VARCHAR(40) NULL` | texto ISO da API REST; comparação textual |
| `job_description` | `NVARCHAR(2000) NULL` | `shortDescription` |
| `job_long_description` | `NVARCHAR(MAX) NULL` | `longDescription` |
| `parameters_json` | `NVARCHAR(MAX) NULL` | `[{name, type, default, description}]` |
| `flow_json` | `NVARCHAR(MAX) NULL` | `[{from, from_type, link, to, to_type}]` |
| `children_json` | `NVARCHAR(MAX) NULL` | sequence: `[{job_name, activity}]` |
| `nao_reconhecidos_json` | `NVARCHAR(MAX) NULL` | tipos de stage/elementos que o parser não classificou |
| `isx_sha256` | `CHAR(64) NULL` | do arquivo `.isx` |
| `isx_bytes` | `INT NULL` | |
| `status` | `VARCHAR(20) NOT NULL` | `ok` / `erro` |
| `erro` | `NVARCHAR(500) NULL` | frase pública do último erro |
| `extracted_at` | `DATETIME2(0) NOT NULL` | |
| `extracted_by` | `NVARCHAR(100) NULL` | matrícula ou `dag:etl_lineage_extract_isx` |
| `duracao_ms` | `INT NULL` | |

UNIQUE `UQ_etl_ds_job_isx (pipeline_name, job_name)` (400×2 = 800 bytes, dentro do teto
de 1.700). Larguras: `ds_project` segue os 50 de `etl_pipeline.project_name`;
`ds_folder_path` 500 cobre a maior pasta observada; `erro` cortado por `cortar_utf16`.

**`dbo.etl_job_lineage`** — colunas novas (as existentes não mudam):

| coluna | tipo | notas |
|---|---|---|
| `input_columns_json` | `NVARCHAR(MAX) NULL` | colunas de entrada do stage |
| `apt_code` | `NVARCHAR(MAX) NULL` | bloco `mainloop` |
| `expressions_json` | `NVARCHAR(MAX) NULL` | `[{output_col, expression, source_col}]` |
| `stage_internal_id` | `VARCHAR(20) NULL` | `V0S185` (liga ao fluxo) |

`extraction_method = 'isx_auto'` cabe no `VARCHAR(20)`. Índice
`IX_etl_job_lineage_job_metodo (pipeline_name, job_name, extraction_method)`.
`sql_expression`, `file_path` (`VARCHAR(500)`), `stage_name` (`VARCHAR(200)`),
`database_name` (`VARCHAR(200)`) já existem — o parser corta em UTF-16 antes de gravar
(`VARCHAR` não aceita acento fora da collation: `file_path` com `ç` vira `?`; registrar
o caso no `nao_reconhecidos_json` e no manual).

**`dbo.etl_stage_type_map`** — MERGE dos tipos PX ausentes, com `type_category`
(`banco`/`arquivo`/`transformacao`/`sequence`) e `role_hint`.

## 5. Fases

### F1 — Fundação: migration, engine ISX, parser provado, harness de DEV
- Entregável: `sql/migrations/106_lineage_isx.sql`; `dags/utils/isx_engine.py` com
  parser, classificação, comando do istool e transportes injetáveis; harness de DEV
  (`istool` de mentira no `sshd-amostra`, `ds-api-amostra`, variáveis no `.env.dev`);
  testes. Nenhum endpoint ainda; a main continua sã.
- Inclui:
  - Migration idempotente (2× no DEV), com o MERGE do mapa de tipos.
  - `isx_engine.py`: `ConfigISX`, validações, `caminho_istool`, `comando_istool`
    (`-authfile`, `shlex.quote`), `parse_isx` (parâmetros, stages, `XMLProperties` com
    `html.unescape`, DataSet/SequentialFile, colunas de saída e entrada, `TrxGenCode` →
    `mainloop`, `hasValue_Derivation`, `lazyLoadInfo`, filhos do sequence,
    `nao_reconhecidos`), `classificar` pelo mapa, `localizar_job` (BFS com teto),
    `checar_modificado`, `exportar` (com `sftp.remove` em `finally`).
  - `dev/sshd-amostra/10-amostra.sh` cria `/opt/IBM/InformationServer/{ASBNode/bin/
    setupEnv.sh, jdk/bin/java, Clients/istools/cli/{plugins/org.eclipse.equinox.launcher_
    dev.jar, configuration/}}`; o `java` de shell lê `-archive` e `-datastage` e copia
    `/dados/bi/isx/<job>.isx` (404 se não existe; `-preview` lista a pasta).
    `dev/ds-api-amostra/servidor.py` (stdlib `http.server`, container `python:3.12-alpine`
    no `docker-compose.dev.yaml`) serve `engines`, `projects`, `folders/…/contents`,
    `jobdesigns/…` a partir de `dev/ds-api-amostra/rotas.json` (os exemplos do
    documento original, sem credencial). `.env.dev` ganha `DS_API_*`, `DS_ENGINE`,
    `DS_ISTOOL_*`. `.env.dev.example` e `docker-compose.yaml` ganham as variáveis.
  - Testes `tests/test_lineage_isx_engine.py`: puras (validações, caminho, comando com
    quote e **sem** `-password`, classificação pelo mapa e fallback), parser sobre `.pjb`
    sintéticos montados dos fragmentos do documento (parallel com ODBC → Transformer →
    DataSet; sequence com dois filhos; stage de tipo desconhecido; `XMLProperties` com
    `TableName` em vez de `SelectStatement`; coluna sem `extendedType`; `TrxGenCode`
    sem `mainloop`), `exportar` com SSH falso (comando executado, `remove` mesmo em
    falha, teto), `localizar_job` com REST falso (achado no 2º nível, teto de nós,
    não achado). Anti-drift: nenhum literal de senha/host no engine (`grep` por
    `password=`, `-password`, `.intranet`).
  - Quando os `.isx` reais chegarem: teste de parse sobre eles marcado `skip` se o
    arquivo não existir em `tests/fixtures/isx/` (fixtures ficam FORA do git se contiverem
    nome de tabela sensível — decidir no §8).
- Critérios de aceite:
  - Dado o `.pjb` sintético parallel, `parse_isx` devolve 3 stages com direções
    `origem/transformacao/destino`, SQL completo do ODBC, `file_path` com `#PSet…#`,
    colunas `CPF_CNPJ:string[20]`, expressão `IND_PESSOA_NLIST ← trim(...)`, `mainloop` e
    fluxo `A → link → B → link → C`.
  - Dado o `.sjb`/`.qjb`, devolve `job_type='SEQUENCE'` e `children=[…]` sem SQL — o job
    chamado vem do atributo `jobname` do stage `CJobActivity` (fallback: `has_ParameterVal
    JobName`); atividade sem nome de job vai para `nao_reconhecidos`, nunca é chute. O
    `lazyLoadInfo` de sequence vem sem espaço entre blocos e com IDs `V22S<n>`.
  - `comando_istool` nunca contém `-password`; um nome com `;` ou espaço vira 422 antes
    de qualquer SSH.
  - Migration 106 aplicada 2× no DEV sem erro; `etl_stage_type_map` ganha os tipos PX uma
    vez só.
  - No DEV, `istool` de mentira + `ds-api-amostra` respondem a um `python -c` que chama
    `localizar_job` + `exportar` + `parse_isx` de ponta a ponta (prova viva, comando no
    `docs/ambiente-dev.md`).
- Validação: pytest (baseline `origin/main`, zero falhas novas) + `tsc -b` + eslint +
  build (front intocado).
- Revisão adversarial multi-agente (`qa-adversarial` + `/code-review` +
  `security-review`, foco em injeção de shell, segredo em log, ZIP bomb/XML bomb —
  `defusedxml` não está nas wheels: limitar tamanho do ISX a 20 MB e recusar entidades —
  e parser tolerante) antes da PR. PR: `feat(lineage): F1 — migration 106, engine ISX
  (parser, istool por SSH, cache pela API REST) e harness de DEV`. A spec entra nesta PR.

### F2 — Endpoints: localizar, extrair com cache, consultar; `GET /lineage` autenticado
- Entregável: os quatro endpoints ISX + `GET /lineage/isx/pipeline` + `GET /lineage`
  com auth e preferência por ISX; smoke por API contra o harness de DEV.
- Inclui: executor dedicado `_EXECUTOR_ISX` (4 threads, 60 s), transação de gravação
  (DELETE `isx_auto` + INSERT + MERGE do cabeçalho), `extracted_by` = matrícula, `status`
  `erro` com a frase pública quando o istool falha (o cabeçalho registra a tentativa),
  `interno` só no log; variáveis `DS_API_*` lidas no arranque com aviso se `VERIFY_SSL`
  desligado; `scripts/smoke_lineage_isx.sh` (itens c–i do §7 por `curl`).
- Critérios de aceite:
  - Dado um job em pipeline, `POST /lineage/isx/extrair` cria o cabeçalho e N linhas
    `isx_auto`; a segunda chamada responde `cache_hit: true` sem tocar o SSH (fake conta
    `exec`); `force` reextrai.
  - Dado job fora de pipeline, 422 com a regra; job que a API REST não acha, 404
    nomeando projeto e job; istool que falha, 502 com frase pública e cabeçalho `erro`.
  - `GET /lineage?pipeline_name=X` sem token → 401; com token, para um job com ISX,
    devolve só as linhas `isx_auto`; para um job sem ISX, as linhas de sempre.
  - Linhas `manual`/`dsx_auto` do mesmo job continuam no banco após reextrair.
- Validação: pytest + `tsc -b` + eslint + build (front intocado).
- Revisão adversarial (foco: transação parcial, executor e vaga, 401 do `GET /lineage`
  não quebrar a Governança — ela já manda token —, timeouts) antes da PR. PR:
  `feat(lineage): F2 — endpoints ISX (localizar, extrair com cache, consultar) e GET
  /lineage autenticado preferindo ISX`.

### F3 — Lote: DAG `etl_lineage_extract_isx` e disparo para admin
- Entregável: DAG que percorre os jobs dos pipelines e chama a API; `POST
  /lineage/isx/lote` + estado da run.
- Inclui: Connection `orquestra_api` do Airflow (login/senha de usuário de serviço —
  §8), Variable `ORQUESTRA_API_URL` (já usada pela factory), 4 threads, timeout 90 s por
  job, resumo no XCom, log por job, `extracted_by = dag:etl_lineage_extract_isx`; filtro
  por pipeline; `force`; sem tocar o banco diretamente (só a API grava).
- Critérios de aceite:
  - Dado um pipeline com 3 jobs no DEV (2 com `.isx` na amostra, 1 sem), a run termina
    com `{extraídos: 2, cache: 0, erros: [job3]}` e a DAG fica verde (erro individual não
    aborta).
  - Segunda run sem `force`: `{cache: 2}`.
  - `POST /lineage/isx/lote` com desenvolvedor → 403; com admin → `run_id`; `GET
    …/lote/{run_id}` reflete o estado.
- Validação: pytest (DAG importável sem Airflow real, como as outras DAGs testadas) +
  `tsc -b` + eslint + build.
- Revisão adversarial (foco: credencial de serviço, `NO_PROXY` do worker para a API,
  worker cacheia `dags/utils` — restart no deploy) antes da PR. PR: `feat(lineage): F3 —
  DAG de extração ISX em lote e disparo pela API para admin`.

### F4 — Aba "Job DataStage" na Governança
- Entregável: a aba com seletor de pipeline, lista de jobs com estado, Extrair/Atualizar,
  grafo, tabela, painel por stage, sequence com filhos.
- Inclui: `components/governanca/isx/*`, `lib/lineageIsx.ts` (leiaute em camadas,
  tipos, `erroIsx`), bancada `tests/js/lineage_isx_harness.cjs` +
  `tests/test_lineage_isx_front.py` (puras: leiaute, resumo, parâmetro; painel: SQL,
  colunas, expressões, APT colapsado; lista: botão Extrair só com `pode_editar`, estado
  `erro` com a frase; sequence: filhos com Extrair; anti-drift: aba nos dois lugares,
  pares claro/escuro, `type="button"` onde há form). `dist/` rebuildada.
- Critérios de aceite:
  - Dado um pipeline com job extraído, a aba mostra o grafo com 3 nós coloridos por
    direção e o painel abre com o SQL completo ao clicar no nó de origem.
  - Job sem ISX mostra "não extraído" e o botão Extrair (com `acao_editar`); ao clicar,
    spinner "Extraindo do DataStage…" e o resultado em até 60 s; erro vira frase.
  - `#PSetSsdVida.ParmDirDst#` aparece como badge com tooltip.
  - Tema claro e escuro sem classe base `*-900`/`*-300`; `git status ui-react/dist` vazio
    após rebuild; DEV em :8090 reflete.
- Validação: `tsc -b` 0 + eslint (zero novos) + `npm run build` + pytest.
- Revisão adversarial (foco: `Governanca.tsx` gigante — a aba nova não pode regredir as
  outras —, z-index de painel lateral × Modal, grafo com 50+ stages, resposta atrasada
  de extração) antes da PR. PR: `feat(lineage): F4 — aba Job DataStage na Governança
  com grafo e painel por stage`.

### F5 — Fecho: manual, release note, smoke, backlog
- Entregável: `docs/MANUAL_USUARIO.md` (Governança › Job DataStage; Admin: variáveis,
  authfile, lote), `docs/release-notes/lineage-isx.md`, `scripts/smoke_lineage_isx.sh`
  fechado, `sql/backlog/lineage_isx.sql` (contexto para IA, filhos em cadeia,
  reconhecimento de mais tipos de stage, expurgo de cabeçalhos de jobs removidos,
  extração recursiva), spec concluída.
- Critérios de aceite: smoke no DEV 0 falhas; backlog aplicado 2× sem duplicar.
- Validação: pytest + `tsc -b` + eslint + build (prova o baseline).
- Revisão de fecho antes da PR. PR: `docs(lineage): F5 — manual, release note, smoke e
  backlog do lineage ISX`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | O `istool` só funciona pelo JAR do launcher com `configuration/` copiada; o wrapper `.sh` falha por permissão. Uma atualização do IS pode mudar o nome do JAR | Extração quebra em produção | `DS_ISTOOL_LAUNCHER` configurável; `-preview` no smoke; 502 nomeando o passo (setupEnv, launcher, export) |
| 2 | Senha do istool na linha de comando (`ps`, logs) — como no documento original | Vazamento da credencial de serviço do DataStage | `-authfile` obrigatório no comando; teste anti-drift; `stderr` do istool só no log com o comando sem segredo |
| 3 | Nomes de projeto/pasta/job viram linha de shell | Injeção de comando no servidor do DataStage | Lista branca + `shlex.quote`; nomes vêm do banco (pipeline) e da API REST, nunca de texto livre; teste com `;`, espaço, `$(`; o operador já tem `_SAFE_JOB_RE` |
| 4 | Carga no servidor do DataStage (JVM por chamada, 3–5 s) num lote de milhares de jobs | Lentidão para os jobs de produção | Lote só por admin e por pipeline; 4 threads; cache pelo `lastModified`; extração unitária com executor de 4 e teto de 60 s |
| 5 | Variação do XML entre versões, parallel × sequence, tipos de stage fora do mapa | Parser cala ou classifica errado | Parser tolerante com `nao_reconhecidos_json`; mapa em tabela editável; amostras reais no harness; teste por tipo |
| 6 | `verify=False` na API REST (certificado autoassinado) | MITM na rede interna | `DS_API_VERIFY_SSL` aceita caminho de CA; `false` só com aviso no log; item do §8 |
| 7 | `GET /lineage` era aberto; passar a exigir token pode quebrar algum consumidor fora da tela | Erro 401 inesperado | A Governança já manda token; smoke confere; dito na PR e na release note |
| 8 | Proxy: a API alcança a porta 9443? O worker alcança a API? (`NO_PROXY`) | Sonda passa e DAG morre (gotcha conhecido) | Checklist de deploy testa da API (`curl` de dentro do container) e do worker; F3 documenta o `NO_PROXY` |
| 9 | Busca em largura na árvore de pastas do BI_CVP (3.398 jobs) custa dezenas de chamadas REST | Localizar lento na 1ª vez | `ds_folder_path` gravado no cabeçalho e reusado; teto de nós e de tempo com mensagem; lote lista os jobs do banco, não da árvore |
| 10 | `VARCHAR` em `file_path`/`stage_name` (sem N) perde acento | Caminho com `ç` gravado com `?` | Cortar e registrar em `nao_reconhecidos_json`; backlog: migrar para NVARCHAR quando a spec anterior do lineage permitir |
| 11 | ISX gigante ou XML malicioso (entidades) | Memória/CPU da API | Teto de 20 MB no `.isx`; `ET` com entidades recusadas; parse no executor com teto |
| 12 | Worker cacheia `dags/utils` | DAG verde com engine antigo depois do deploy | Checklist: restart do worker quando `dags/utils/isx_engine.py` mudar (gotcha registrado) |

## 7. Smoke pós-deploy

> **Script**: `scripts/smoke_lineage_isx.sh` (`ORQ_URL`, `ORQ_USER`, `ORQ_PASS`,
> `PIPELINE`, `JOB`, `JOB_SEQ`; `LOTE_TETO_S`, `SMOKE_LOTE=0`) cobre c–i e k pela API
> (k só com usuário admin — desenvolvedor recebe 403 e o item é pulado). a, b, j, l e m
> são manuais, com o roteiro impresso no fim. **Resultado no DEV (2026-09-08, F5): 14
> conferências ok, 0 falhas** — lote `success` com 3 jobs (2 em cache, 1 erro individual
> esperado: `JobRaiz` sem `.isx` → 404 não derruba a run); j provado pela tela com
> Chromium headless nos dois temas (scripts de prova ad hoc, não versionados);
> backlog aplicado 2× (12 linhas, 12 títulos).

a) Migration **106** aplicada na 6c (responder **s**); `SELECT COUNT(*) FROM
   dbo.etl_stage_type_map` cresceu; `etl_ds_job_isx` existe.
b) `.env` da API com `DS_API_URL`, `DS_API_USER`, `DS_API_PASSWORD`, `DS_ENGINE`,
   `DS_ISTOOL_DOMAIN`, `DS_ISTOOL_AUTHFILE` (arquivo criado no servidor do DataStage com
   permissão 600 do usuário SSH); de dentro do container da API, `curl -k
   $DS_API_URL/engines` responde 200 com Basic; `ssh` (Console) continua ok.
c) `GET /lineage/isx/localizar?pipeline_name=P&job_name=J` → `encontrado: true`, pasta,
   tipo e `last_modified`.
d) `POST /lineage/isx/extrair` (desenvolvedor) → 200 em até ~5 s, `cache_hit: false`,
   stages com SQL completo; `SELECT * FROM dbo.etl_ds_job_isx WHERE job_name='J'` mostra
   `status='ok'`, `isx_sha256`, `extracted_by` = matrícula.
e) Repetir d → `cache_hit: true` em < 1 s; `ps -ef | grep istool` no servidor do
   DataStage durante a chamada mostra **`-authfile`**, nunca a senha.
f) `force: true` → reextrai; `extracted_at` muda; linhas `manual`/`dsx_auto` do job
   continuam (`SELECT extraction_method, COUNT(*) … GROUP BY`).
g) Job que não está em pipeline → 422 com a regra; nome com `;` → 422 antes do SSH.
h) Sequence → `ds_job_type='SEQUENCE'`, `children_json` com os filhos; extrair um filho
   que está em pipeline funciona; um que não está → 422.
i) `GET /lineage?pipeline_name=P` sem token → 401; com token, o job J mostra só linhas
   `isx_auto`; a aba Lineage da Governança continua abrindo.
j) Governança › Job DataStage: pipeline P → lista com J "extraído em …"; grafo com nós
   por direção; clicar no nó de origem abre o SQL; `#PSet…#` com badge; tema escuro ok.
k) Lote: admin dispara `POST /lineage/isx/lote {pipeline_name: P}` → run; a DAG fica
   verde com o resumo; desenvolvedor recebe 403. Restart do worker feito se
   `dags/utils` mudou.
l) Proxy: `curl` de dentro do worker para `ORQUESTRA_API_URL/health` → 200 (NO_PROXY).
m) Log da API não contém senha nem `-password`; `nao_reconhecidos_json` dos jobs
   extraídos revisado (tipos para incluir no mapa).

## 8. Pendências e decisões em aberto

Resolvidas pelo usuário em 2026-09-07: job só com pipeline (sem mudar `pipeline_name`/FK);
aba nova na Governança; IA fora (banco pronto); parallel completo + sequence com filhos;
unitário `acao_editar` e lote admin; arquivo com senhas apagado do DEV; harness com
`.isx` reais subidos pelo Enviar arquivo; extração unitária síncrona na API.

1. **Usuário de serviço para a DAG** (Connection `orquestra_api` do Airflow): qual
   matrícula/perfil com `acao_editar`? Alternativa: a DAG usar `SSHHook` + engine
   diretamente (descartada nesta spec, ver §3).
2. **`-authfile` do istool**: ops cria o arquivo no servidor do DataStage (formato do
   istool: `user=` e `password=` em linhas próprias — confirmar na documentação da versão
   11.7.1) com permissão 600 do usuário SSH do Orquestra. Sem ele, a extração responde
   503 "authfile não configurado" — **não** há fallback para senha na linha de comando.
3. **Certificado da API REST**: há CA interna para `DS_API_VERIFY_SSL=<caminho>`? Se não,
   `false` com aviso, e o item entra no backlog de segurança.
4. **Amostras `.isx`**: subir um parallel e um sequence, sem dado sensível, para
   `/dados/bi/isx/` do DEV. Se os nomes de tabela forem sensíveis, as fixtures ficam fora
   do git (`tests/fixtures/isx/` no `.gitignore`) e os testes marcam `skip`.
5. **Tipos de stage do mapa**: revisar `nao_reconhecidos_json` dos primeiros jobs reais e
   completar `etl_stage_type_map` pela tela (sem migration).
6. **Timezone**: o XML traz `lastModificationTimestamp` local (-0300) e a API traz UTC; a
   chave de cache é o valor da **API**; o XML fica só informativo.
7. **`file_path`/`stage_name` em `VARCHAR`**: migrar para `NVARCHAR` numa spec de lineage
   futura (mexe no DSX e na `sp_etl_job_lineage_upsert`).
8. **`GET /lineage` autenticado**: confirmar que nenhum script externo (n8n, relatório)
   lê esse endpoint sem token antes do deploy da F2.
9. **Extração de filhos em cadeia** e **contexto para IA**: backlog na F5.
10. **`etl_stage_type_map` tem duas grafias no repo** (achado da F1): `sql/schema_prod_dev.sql`
    e `sql/deploy_full.sql` criam a tabela com a chave `stage_type` (é o que `/lineage` e
    `dags/etl_lineage_query.py` leem); `script/alteracoes/20260601_lineage_catalogo_fase2_v1`
    cria com `type_raw` + `description` (é o que `api/routers/catalogo.py` e
    `dags/etl_catalogo_query.py` leem). Qual existe depende de qual script rodou primeiro no
    ambiente — no DEV é `stage_type`, e por isso as consultas do catálogo falham lá com
    "Invalid column name 'type_raw'". A migration 106 descobre a coluna em tempo de execução;
    a F2 carrega o mapa do mesmo jeito. **Pendente do usuário**: rodar em produção
    `SELECT COL_LENGTH('dbo.etl_stage_type_map','type_raw'), COL_LENGTH('dbo.etl_stage_type_map','stage_type')`
    e dizer o resultado, para decidirmos se unificamos a grafia numa migration própria
    (fora desta spec).
11. **Segunda versão do documento de origem (lida em 2026-09-07, depois da F1)**: trouxe
    `.qjb` para sequences com filhos, `jobname` como atributo do stage, `lazyLoadInfo` de
    sequence sem espaço e com `V22S<n>`, espaço no `-datastage` escapado com `\ `, pastas
    com acento — tudo absorvido na F1. **Voltou a trazer senhas em claro** (SSH, Basic auth
    da API REST, `-password` do istool/dsjob): nada disso entra no repo; apagar do DEV.
12. **Para a F2 (transporte SSH)**: com senha, o paramiko precisa de `allow_agent=False` e
    `look_for_keys=False` (o documento mediu "Authentication failed" sem eles); server jobs
    (`jobType` fora de PARALLEL/SEQUENCE) respondem 422 — fora do escopo.
13. **Produção, antes do deploy da F2 (auditoria de segurança da F2)**: definir
    `DS_SSH_KNOWN_HOSTS` no `.env` da API — sem ele o SSH aceita qualquer host key
    (`AutoAddPolicy`, paridade com o Console) e o canal agora transporta o `.isx`, que traz
    credenciais de conexão (a API avisa no arranque); conferir que o host da API REST do
    DataStage NÃO passa pelo proxy corporativo (`rest_transport` usa `trust_env=False`, ou
    seja, chamada direta — se a rede exigir proxy para esse host, é decisão a tomar);
    `DS_API_URL` com `usuario:senha@` é recusada (503) — a credencial vai em
    `DS_API_USER/DS_API_PASSWORD`.
14. **Limitações registradas**: o mascaramento de parâmetros do job é por tipo `Encrypted`
    ou nome sugestivo (senha/password/pwd/secret); `apt_code`/`sql_expression`/`BeforeSQL`
    podem carregar literais sensíveis do próprio design do job e são lidos por qualquer
    usuário autenticado. A F4 renderiza tudo por escape do React (nunca `innerHTML`).
16. **Produção, antes do deploy da F3 (auditoria de segurança da F3)**: a credencial de
    serviço da DAG deve vir pelo AMBIENTE do worker, não pelo banco do Airflow —
    `AIRFLOW_CONN_ORQUESTRA_API=http://<usuario>:<senha>@orquestra-api:8000/http` no `.env`
    (o compose repassa; vazio = cai no banco). Motivos: um role Op do Airflow edita
    Connections/Variables pela UI e poderia apontar a URL para outro host e capturar o
    Basic; e sem `AIRFLOW__CORE__FERNET_KEY` a senha de uma Connection de banco fica em
    claro no Postgres. Com a Connection no ambiente, a DAG monta a URL a partir dela e
    ignora a Variable `ORQUESTRA_API_URL`. Conferir também se há usuários com role Op em
    produção e a que perfil do Orquestra mapeiam. O disparo genérico de DAG da API
    (`/airflow/dags/{dag_id}/dagRuns` e o PATCH) passa a exigir admin para esta DAG.
15. **Para a F3 (lote)**: excluir por padrão pastas `bkp/backup/bkup` e jobs `CopyOf*`;
    timeout por job 30 s; `max_workers=4`. O documento propõe descobrir a pasta de
    sub-sequences tentando uma lista fixa de pastas por projeto — descartado: a busca é
    pela API REST (`localizar_job`).
