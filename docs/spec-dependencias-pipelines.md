# Spec: Dependências entre pipelines (modelo Control-M) — Orquestra
Data: 2026-07-31 · Status: ✅ **Retomada F2–F6 COMPLETA NO CÓDIGO (PRs #243–#248, 2026-08-02) — pendente o deploy de produção (ordem no preâmbulo; dívidas §10).**

> **Por que esta spec foi revertida.** As seis fases foram implementadas e
> reprovadas em DUAS revisões adversariais independentes. A primeira encontrou
> 21 defeitos; as cinco correções fecharam 14 deles e **introduziram ~15 novos**,
> um dos quais fazia **todo pipeline que falha aparecer VERDE no Airflow** —
> afetando 100% dos pipelines, com ou sem dependência.
>
> A causa não foi descuido pontual: comportamento distribuído (trigger rules do
> Airflow, corridas entre tasks, estado compartilhado em banco) **não é
> verificável por leitura de código**, e não havia ambiente onde executá-lo. Os
> 1053 testes passavam em todas as rodadas.
>
> **O que sobrevive (F1):** migration 067, detecção de ciclo por BFS, FK de
> existência do predecessor e `dags/utils/data_referencia.py`. Isso fecha os
> defeitos 3 e 4 do QA original sem tocar em execução nenhuma.
>
> **O que voltou:** o `ExternalTaskSensor`, com os defeitos 1, 2 e 5 do QA —
> conhecidos, documentados no §3, e contornáveis pelo modo Dataset.
>
> **Para retomar:** a parte de execução (F2–F6) precisa de um ambiente com
> Airflow e SQL Server onde os cenários possam ser EXECUTADOS, não deduzidos. O
> `docker-compose.dev.yaml` do repo é o ponto de partida. Os 21 + 15 defeitos
> estão descritos nos relatórios das duas revisões e valem como suíte de
> aceitação do que for refeito.
>
> ✅ **Ambiente montado (2026-08-02):** o stack dev está DE PÉ na VPS — SQL
> Server 2019 (`orquestra_dev`, schema de produção + migrations 002–069),
> Airflow completo (webserver :8082, scheduler, worker, triggerer) e API :8000 /
> UI :8090. Runbook, credenciais e armadilhas do bootstrap em
> `docs/ambiente-dev.md`. A pré-condição da retomada está satisfeita.
>
> ✅ **RETOMADA F2–F6 COMPLETA NO CÓDIGO (2026-08-02):** PRs **#243** (F2 —
> registro de execução por data de referência), **#244** (fix do kwarg
> reservado `params` no StoredProcOperator), **#245** (F3 — liberação por
> condição e disparo push), **#246** (F4 — guardiã, janela e alertas),
> **#247** (F5 — cadastro e visão de dependências) e **#248** (F6 — este
> fecho: manual, smoke §7, factory zerando a pendência de publicação), todas
> mergeadas em 2026-08-02, com os cenários **EXECUTADOS** no ambiente dev
> (suíte `docs/retomada-aceitacao.md`; harness `docs/retomada-harness-dev.md`).
>
> ✅ **COMPONENTES DE MALHA COMPLETOS (2026-08-03):** as fases F10–F15
> (`docs/malha-componentes-desenho.md`, PRs **#250–#255**) entregaram os quatro
> componentes — Início, Aguarde, Notificação e Fim — como **açúcar de
> compilação sobre este motor**: nenhum executor, sensor ou DAG-mestre novo. A
> **aceitação final** (matriz E1–E15 do §14 + smoke integrado com malha criada
> do zero + validação do roteiro de produção) passou **inteira** no ambiente
> dev em 2026-08-03. Migrations novas: **075** (nós e arestas do desenho) e
> **076** (derruba a `FK_dep_evento_pipeline` — sem isso o marcador `#no:{id}`
> dos eventos de Notificação/Fim não cabe na tabela).
>
> ✅ **OPERAÇÃO NO NÍVEL DE ETAPA — F1–F4 TAMBÉM ENTRAM NESTE MESMO DEPLOY**
> (`docs/spec-operacao-nivel-etapa.md`, PRs até a **#265**): realce de
> dependências no canvas (F1), ponte `run_id ↔ ts_nodash` (F2), modo Execução
> do canvas (F3) e **rerun a partir de uma etapa com tentativas acumuladas**
> (F4). A F4 traz a migration **078**, que nenhum documento mencionava até aqui:
> tabela `dbo.etl_job_execution_tentativa` (histórico das tentativas
> superadas), colunas `substituida_em`/`substituida_por` em
> `etl_pipeline_execucao` (reabertura de corrida do dependente) e a
> **`sp_etl_job_execution_log` v3** (arquiva a tentativa superada e incrementa
> `attempt`; assinatura idêntica à v2 — por isso não exige regerar DAG).
>
> ✅ **OPERAÇÃO NO NÍVEL DE ETAPA — A F5 (ETAPA EM ESPERA) TAMBÉM ENTRA NESTE
> DEPLOY** (PRs até a **#268**): pausa em runtime de uma etapa que ainda não
> começou, liberação/cancelamento com auditoria, teto com alerta. Ela traz a
> migration **079** — tabela `dbo.etl_etapa_pausa`, índice único filtrado
> `ux_etapa_pausa_pendente` (uma pausa PENDENTE por etapa/corrida) e a chave
> `espera_teto_minutos` em `etl_app_config`.
>
> ⚠️ **A F5 é a única fase deste trem que EXIGE `force_all`** — ver o passo 6.
> Sem regerar, o pipeline **não tem portão** e a pausa não segura nada.
>
> **Pendente: o deploy de produção do trem inteiro** (motor + malha +
> componentes + operação no nível de etapa vão JUNTOS).
>
> ---
>
> ### ⚠️ ORDEM: `dags/` ANTES das migrations
>
> Esta é a ordem do próprio `scripts/deploy.sh` (**dags na etapa 5, migrations
> na 6c**) e é a única segura. Uma versão anterior deste preâmbulo mandava o
> INVERSO — migrations primeiro — e o inverso **abre um defeito real**: com o
> **banco novo e o `dags/` velho**, o carimbo de corrida substituída
> (`substituida_em`, migration 078) já passa a ser gravado, mas o push antigo
> não sabe o que ele significa — e **nenhum dependente roda**.
>
> No sentido certo não existe janela ruim: **o código novo degrada em banco
> velho** (toda leitura nova é guardada por `COL_LENGTH`/`OBJECT_ID` e cai no
> comportamento antigo), **mas o banco novo não se protege de código velho**.
> Rodar o `deploy.sh` de ponta a ponta numa sessão só já entrega essa ordem —
> **não inverta na mão**.
>
> ---
>
> **Durante o `deploy.sh`** (na ordem em que o script pergunta):
>
> 1. **`config/` e `dags/`** (etapas 4 e 5, com confirmação): factory nova,
>    guardiã com os observadores de malha, utils. A `api/` e o front são
>    automáticos (etapas 3 e 7).
> 2. **`docker-compose.yaml`** (etapa 6, pergunta se divergir): responder **s**
>    para levar o `TZ: America/Sao_Paulo` da API — pré-requisito da F9, que vai
>    no MESMO deploy. Depois conferir `docker exec orquestra-api date` → `-03`
>    (sem isso, o ODATE default da visão de execução nasce no dia seguinte entre
>    21h e meia-noite de Brasília — achado da revisão da F9).
> ✅ **REPUBLICAÇÃO DA MALHA TAMBÉM ENTRA NESTE DEPLOY**: o botão *Republicar
> pipelines* da tela Malha (regerar as DAGs de todos os membros para que os
> vínculos desenhados passem a valer no Airflow) toca as TRÊS árvores —
> `dags/etl_dag_factory.py` (a factory passou a aceitar uma LISTA de alvos em
> `conf["pipelines"]`), `api/` (endpoint + fila de verificação) e o front. Traz
> a migration **080** (coluna `modo_verificacao` em `etl_dag_pendente`): sem
> ela o gesto funciona, mas a conferência pós-publicação não é registrada e um
> erro de importação da DAG nova passa despercebido.
>
> 3. **Migrations `067` e `070–080`** (etapa 6c) — o prompt é padrão-**NÃO**,
>    **responder `s`**. Se responder não, a feature sobe **muda** e o smoke
>    ainda assim "passa" nos primeiros passos.
>
>    ⚠️ **A etapa 6c vai avisar que há muitas pendentes — isto é ESPERADO neste
>    deploy** (são **12**: 067 + 070…080). Versões antigas do `deploy.sh`
>    recomendavam ali `migrate.py --baseline`: **NÃO SIGA**. `--baseline`
>    **registra sem executar** — usá-lo aqui marcaria como aplicadas onze
>    migrations que nunca rodaram, e o banco ficaria permanentemente atrás do
>    código, sem erro nenhum para avisar. O caso aqui é "acabei de atualizar o
>    código, migrations novas vêm junto": aplicar.
>
>    ⚠️ **ANTES de responder `s`, dimensionar o backfill da 078** — ela roda
>    `WHILE / UPDATE TOP (5000)` na `etl_job_execution`, tabela QUENTE (toda
>    etapa de todo pipeline escreve nela), e a etapa 6c roda **desassistida**:
>
>    ```sql
>    SELECT COUNT(*) AS total,
>           SUM(CASE WHEN attempt IS NULL THEN 1 ELSE 0 END) AS sem_attempt
>      FROM dbo.etl_job_execution;
>    ```
>
>    `sem_attempt = 0` → no-op. Até ~100 mil → segundos, basta fora do pico.
>    **Acima de ~1 milhão → exigir janela** (scheduler/monitor pausados), como
>    a migration 058 já exigiu para a mesma tabela. O loop é retomável
>    (`WHERE attempt IS NULL`).
>
> **Depois do `deploy.sh`:**
>
> 4. **Conferência pós-migration** — rodar no banco de produção logo após a 6c.
>    `sql/migrate.py` **descarta PRINT** (D40): o log do deploy não prova nada
>    sozinho.
>
>    ```sql
>    SELECT
>      (SELECT COUNT(*) FROM sys.tables WHERE name = 'etl_pipeline_execucao')          AS t067_pipe_exec,      -- 1
>      (SELECT COUNT(*) FROM sys.tables WHERE name = 'etl_malha')                      AS t070_malha,          -- 1
>      (SELECT COUNT(*) FROM sys.tables WHERE name = 'etl_malha_no')                   AS t075_malha_no,       -- 1
>      (SELECT COUNT(*) FROM sys.indexes WHERE name = 'ix_pipe_exec_ultima')           AS ix077_ultima,        -- 1
>      (SELECT COUNT(*) FROM sys.foreign_keys WHERE name = 'FK_dep_evento_pipeline')   AS fk076_TEM_DE_SER_0,  -- 0 !
>      (SELECT COUNT(*) FROM sys.tables WHERE name = 'etl_job_execution_tentativa')    AS t078_tentativa,      -- 1
>      COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em')                       AS c078_subst_em,       -- não-NULL
>      COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_por')                      AS c078_subst_por,      -- não-NULL
>      CASE WHEN EXISTS (SELECT 1 FROM sys.sql_modules
>                        WHERE object_id = OBJECT_ID('dbo.sp_etl_job_execution_log')
>                          AND definition LIKE '%etl_job_execution_tentativa%')
>           THEN 'v3' ELSE 'ANTIGA' END                                                AS sp078_versao,        -- 'v3'
>      (SELECT COUNT(*) FROM dbo.etl_job_execution WHERE attempt IS NULL)              AS backfill_pendente,   -- 0
>      (SELECT COUNT(*) FROM sys.tables WHERE name = 'etl_etapa_pausa')                AS t079_etapa_pausa,    -- 1
>      (SELECT COUNT(*) FROM sys.indexes WHERE name = 'ux_etapa_pausa_pendente')       AS ix079_pausa_unica,   -- 1
>      (SELECT COUNT(*) FROM dbo.etl_app_config
>        WHERE config_key = 'espera_teto_minutos')                                     AS cfg079_teto,         -- 1
>      COL_LENGTH('dbo.etl_dag_pendente', 'modo_verificacao')                          AS c080_verificacao,    -- não-NULL
>      (SELECT COUNT(*) FROM dbo.etl_schema_version
>        WHERE migration_name IN ('067_dependencias_pipeline','070_malha',
>              '071_normaliza_grafia_dependencias','072_execution_id_250',
>              '073_dag_config_pendente','074_malha_orientacao','075_malha_nos',
>              '076_dependencia_evento_no','077_pipe_exec_ultima_por_pipeline',
>              '078_tentativas_acumuladas','079_etapa_pausa',
>              '080_dag_pendente_verificacao'))                                        AS registradas;         -- 12
>    ```
>
>    **`fk076_TEM_DE_SER_0` é a linha que não mente** (achado da aceitação
>    final): enquanto a `FK_dep_evento_pipeline` existir, o marcador `#no:{id}`
>    dos eventos de Notificação/Fim não cabe na tabela e os componentes de malha
>    ficam mudos. `registradas = 12` prova que o migrate rodou de verdade — mas
>    **sozinho não basta**, porque `--baseline` também o deixaria em 12; é o
>    conjunto das outras colunas que prova que o schema existe.
>
>    As três linhas da **079** são a metade de BANCO da etapa em espera:
>    `t079_etapa_pausa` (onde a pausa vive), `ix079_pausa_unica` (o índice
>    único FILTRADO que impede duas pausas pendentes para a mesma
>    etapa/corrida — sem ele, dois cliques criam duas pausas e liberar uma não
>    solta nada) e `cfg079_teto` (o teto default que a TELA mostra antes de o
>    operador pausar). A metade de DAG é o passo 6.
> 5. **ANTES do `force_all`**, rodar a consulta de dimensionamento do CSV órfão
>    (pipelines ativos com `depends_on` preenchido, por `schedule_type`) e
>    tratar os órfãos — `sql/migrate.py` descarta PRINT (D40), o relatório não
>    chega sozinho.
> 6. **Regenerar as DAGs** (`force_all`) — **OBRIGATÓRIO neste deploy**, e por
>    DOIS motivos independentes: o **trem de dependências e a malha** não mudam
>    nada sem isso (o `deploy.sh` exclui `generated/`) **e a F5 (etapa em
>    espera) simplesmente não existe até a regeração**.
>
>    ⚠️ **A F5 EXIGE `force_all` — regerar NÃO é opcional.** O portão que
>    obedece a pausa não é uma migration nem um módulo importado em runtime:
>    ele é uma linha **emitida dentro do fonte gerado de cada DAG**, no
>    `log_start` de toda etapa (`dags/etl_dag_factory.py`):
>
>    ```python
>    if _espera is not None:
>        _espera.portao(hook, PIPELINE_NAME, job_name, execution_id)
>    ```
>
>    **DAG publicada antes da F5 não tem essas linhas.** Sem regerar, o banco
>    aceita a pausa, a tela mostra "pausa marcada" e **o pipeline passa
>    direto** — a etapa nunca pergunta se há pausa pendente. É por isso que a
>    API passou a **recusar** a criação de pausa em pipeline cuja DAG publicada
>    não tem portão (409 `dag_sem_portao`, com a frase do conserto) e a tela
>    desliga o botão: melhor recusar do que prometer.
>
>    ℹ️ **A F4 (rerun/tentativas acumuladas), essa sim, NÃO exige
>    `force_all`** — e isto nunca esteve escrito em lugar nenhum. A acumulação
>    de tentativas vive inteira na `sp_etl_job_execution_log` v3, cuja
>    **assinatura não mudou** (os 11 parâmetros que a factory já emite como
>    texto dentro das DAGs publicadas), e o módulo de dependências é
>    **importado em runtime** pelo código gerado. DAG antiga já publicada passa
>    a acumular tentativa sozinha, assim que a migration 078 entra. Não
>    confundir uma coisa com a outra: **a F4 dispensa, a F5 exige** — e o
>    `docs/spec-operacao-nivel-etapa.md` §9 já dizia isso da F5 ("Republicação
>    geral: F5 exige regerar as DAGs para o portão valer (`force_all`)").
>
>    **Conferência de UMA LINHA, depois do `force_all`** — a única prova de que
>    o portão foi mesmo publicado (o log da factory diz "N geradas", não diz o
>    que foi gerado):
>
>    ```bash
>    grep -rl "_espera.portao" <DAGS_FOLDER>/generated/ | wc -l
>    ```
>
>    O número **tem de bater com o total de pipelines ativos**:
>
>    ```sql
>    SELECT COUNT(*) FROM dbo.etl_pipeline WHERE active = 1;
>    ```
>
>    Menor que isso = há pipeline ativo publicado sem portão; a pausa nele será
>    recusada pela API (`dag_sem_portao`) até ser republicado individualmente.
> 7. Conferir `SELECT GETDATE()` no SQL Server (a data de referência nasce do
>    relógio DELE) e só então **despausar `etl_dependencia_guardia`**.
>
>    ℹ️ A guardiã deste deploy ganhou uma responsabilidade nova (§4.3): fechar
>    a corrida que **começou** e cujo DagRun morreu sem gravar nada. É a rede
>    contra o `dagrun_timeout` estourado — ele marca o DagRun FAILED e pula
>    `registrar_falha`/`flow_close`, deixando `etl_pipeline_execucao` em
>    EXECUTANDO para sempre e travando todos os dependentes (a classe "órfão em
>    RUNNING"). A F5 tornou essa rota alcançável por desenho: etapa parada no
>    portão consome o SLA sem consumir worker. Fecha FALHA só com DagRun
>    `failed`; DagRun `success` sem fecho vira **alerta** (`EXECUCAO_ORFA`) e
>    conserto pela Finalização Manual — a guardiã não inventa verde.
> 8. Smokes: **§7** desta spec em produção (o motor), começando por um PAR de
>    pipelines de teste; e **`docs/smoke-malha-componentes.md`** para os
>    componentes — roteiro executável sem contexto, validado passo a passo no
>    dev.
>
>    ⚠️ **NÃO EXISTE ROTEIRO DE SMOKE PARA AS F1–F5 DE
>    `docs/spec-operacao-nivel-etapa.md`** — manual e smoke são a entrega da
>    **F6** daquela spec, que **ainda não foi feita**. Quem deployar agora sobe
>    essas cinco fases (canvas em modo Execução, drill-down malha → etapa,
>    rerun com cascata, tentativas acumuladas e etapa em espera) **sem roteiro
>    de aceitação**. Ou se aceita validá-las na mão, ou se espera a F6.
>
>    Para a F5, a validação mínima na mão é: (a) a conferência de uma linha do
>    passo 6 (`grep -rl "_espera.portao"`), (b) pausar uma etapa que ainda não
>    começou num pipeline de teste e ver a execução PARAR ali, e (c) liberar e
>    ver seguir. Se (a) não bater, (b) vai passar direto — e é exatamente esse
>    o defeito que a recusa `dag_sem_portao` existe para tornar visível.
>
> ⚠️ No prompt do Airflow (rebuild da imagem), responder **N**: a factory e a
> guardiã são código montado por bind-mount, não exigem imagem nova.

## 1. Visão

Hoje a dependência entre pipelines existe, mas o mecanismo padrão só funciona
quando pai e filho têm **exatamente o mesmo horário de agendamento** e o pai dura
menos de 1 hora — e não existe nenhuma noção de **a que dia de processamento uma
execução pertence**. Com dezenas de processos migrando para o Orquestra, isso
quebra em produção de forma silenciosa.

Esta spec traz o modelo que o mercado usa (Control-M): cada execução carrega uma
**data de referência** (o `ODATE`), a liberação de um pipeline é uma **condição
sobre as dependências naquela data**, e o disparo é **imediato** quando a última
dependência conclui — não um sensor esperando um horário.

Quando estiver pronto: o operador cadastra "PIPE_C depende de PIPE_A e PIPE_B",
e o Orquestra garante que C só roda depois de A **e** B concluírem com sucesso
**na mesma data de referência**, disparando C em segundos, com alerta se a janela
estourar.

## 2. Escopo

**IN:**
- Data de referência (ODATE) por execução, com **hora de virada** configurável
  (global, com override por pipeline) e **herança** na cadeia de dependência.
- Tabela de execução no nível **pipeline** (hoje só existe no nível job).
- Dependência em tabela própria, com **validação de existência** do predecessor
  (FK) e **detecção de ciclo correta** (percorrendo todas as dependências).
- Liberação por condição: **todas** as dependências concluídas com sucesso na
  mesma data de referência (AND).
- **Disparo imediato (push)** pelo pipeline predecessor + **DAG guardiã** como
  rede de segurança e ordenadora do dia.
- Janela: `não iniciar antes de HH:MM` e `hora-limite` com alerta.
- Alerta de **data de referência divergente** e de **janela estourada**.
- Remoção do `ExternalTaskSensor` do gerador de DAGs.
- UI de cadastro de dependências com busca por projeto/nome e visão do estado.
- **Malha** (incluído em 2026-08-02): entidade que **agrupa pipelines de fato**
  — o análogo da *sequence mestre* do DataStage e da malha/SMART Folder do
  Control-M. A tela **Malha** é reaproveitada como o lugar onde as malhas são
  **montadas e exibidas em diagrama** (nó = pipeline, aresta = dependência),
  mantendo a linguagem visual atual. Ver §4b e as fases F7–F9.

**OUT (explícito):**
- **Dependência job → job entre pipelines diferentes.** Fica no backlog da
  aplicação (§9); o modelo de dados desta spec **já nasce preparado** para ela
  (colunas `tipo`, `job_origem`, `job_destino` reservadas), para a feature futura
  não exigir migration destrutiva.
- Recursos quantitativos / pools de concorrência estilo Control-M (o Airflow já
  tem `pool_name`, fora de escopo aqui).
- Dependência entre pipelines de **ambientes diferentes** (PROD × DEV).
- Reprocessamento em massa por data de referência (a data é editável no disparo
  manual; orquestrar um backfill de N dias fica para depois).
- Condições OR / expressões booleanas entre dependências — nesta entrega é
  sempre AND, que é o default do Control-M e o que o usuário confirmou.

## 3. Arquitetura proposta

### O problema atual, em uma frase por defeito
| # | Defeito | Onde |
|---|---------|------|
| 1 | `ExternalTaskSensor` sem `execution_delta`/`execution_date_fn` → exige mesmo `logical_date` entre pai e filho | `dags/etl_dag_factory.py:1366` |
| 2 | `timeout=3600` fixo → pai que dura mais de 1h reprova o filho | `dags/etl_dag_factory.py:1370` |
| 3 | Detecção de ciclo segue **só a primeira** dependência (`split(",")[0]`) | `api/routers/pipelines.py:197` |
| 4 | `depends_on` não valida se o pipeline citado **existe** | `api/routers/pipelines.py:537-550` |
| 5 | Modo Dataset: pai pulado pelo `check_agenda` nunca publica → filho não roda e ninguém é avisado | `dags/etl_dag_factory.py:1332,1340` |

### Modelo alvo (Control-M traduzido para o Orquestra)

| Conceito Control-M | Equivalente nesta spec |
|---|---|
| `ODATE` (Order Date) | `data_referencia` em `etl_pipeline_execucao` |
| New Day Procedure | DAG guardiã "ordena" as execuções previstas do dia |
| Condição OUT (`JOB-A-OK ODATE`) | linha `SUCESSO` em `etl_pipeline_execucao` para (pipeline, data_ref) |
| Condição IN (AND) | todas as linhas de `etl_pipeline_dependencia` satisfeitas na mesma `data_referencia` |
| Time window FROM/UNTIL | `nao_iniciar_antes` / `hora_limite_dependencia` |
| Cyclic monitor | DAG guardiã a cada 5 min (rede de segurança, não caminho principal) |

### Cálculo da data de referência

```
virada = pipeline.hora_virada ?? config global 'dependencia_hora_virada' (default 00:00)

se virada == 00:00        → data_referencia = data do calendário
senão se hora >= virada   → data_referencia = data do calendário + 1 dia
senão                     → data_referencia = data do calendário
```

Exemplos (o caso que motivou a spec):

| Virada | Início real | data_referencia |
|---|---|---|
| 00:00 (default) | 31/07 23:30 | 31/07 |
| 00:00 | 01/08 00:40 | 01/08 |
| **20:00** | 31/07 23:30 | **01/08** |
| **20:00** | 01/08 00:40 | **01/08** |

**Herança:** quem é disparado por dependência **não recalcula** — recebe a
`data_referencia` do predecessor via `conf` do trigger. É isso que mantém a
corrida inteira coerente quando ela atravessa a meia-noite, e é exatamente como
o Control-M carimba condições com o ODATE do job que as gerou.

### Disparo (push) e liberação

Fim do pipeline A (sucesso) → task `t_disparar_dependentes`:
1. lê quem depende de A em `etl_pipeline_dependencia`;
2. para cada dependente C, verifica se **todas** as dependências de C têm
   execução `SUCESSO` com a **mesma** `data_referencia`;
3. se falta alguma → não faz nada (quem completar por último dispara);
4. se `nao_iniciar_antes` ainda não chegou → não dispara (a guardiã pega na hora);
5. senão → dispara C com `conf={"data_referencia": ...}` via
   `airflow.api.client.local_client.Client.trigger_dag` — padrão já usado em
   `dags/etl_sequence_import_approve.py:208`.

**Pipeline com dependência passa a ter `schedule=None`** e some o
`ExternalTaskSensor`. O agendamento dele deixa de ser cron e passa a ser
condição — que é a semântica correta e mata os defeitos 1, 2 e 5.

### DAG guardiã (`etl_dependencia_guardia`, a cada 5 min)

Quatro responsabilidades, nesta ordem:
1. **Ordenar o dia:** para cada pipeline ativo com dependência e previsto para
   hoje (reusa as regras de agenda que já existem: `dias_semana`, dias úteis,
   calendário, blackout), garante uma linha `AGUARDANDO_DEPENDENCIA` na
   `data_referencia` corrente. É o New Day Procedure — sem ele não há como
   afirmar "este pipeline deveria ter rodado e não rodou".
2. **Rede de segurança do push:** dependências satisfeitas mas nada disparado
   (pai morto entre o fim e o trigger, worker reiniciado) → dispara.
3. **Deadline:** passou de `hora_limite_dependencia` sem liberar → evento +
   alerta Teams, e o pipeline **fica pendente, não falha**.
4. **Divergência:** predecessor só tem execução com `data_referencia` diferente
   → evento + alerta com as duas datas explícitas.

### Componentes tocados
- **Dados:** migration `067_dependencias_pipeline.sql` (§4).
- **Back:** `api/routers/pipelines.py` (CRUD de dependência, ciclo por BFS,
  validação de existência), `api/routers/dashboard.py` (estado "aguardando").
- **Orquestração:** `dags/etl_dag_factory.py` (remove sensor, grava execução,
  adiciona `t_disparar_dependentes`), `dags/utils/data_referencia.py` (novo,
  puro), `dags/utils/dependencias.py` (novo, puro: avaliação da condição),
  `dags/etl_dependencia_guardia.py` (novo).
- **Front:** `ui-react/src/components/pipelines/PipelineFormModal.tsx` (modal de
  dependências), `ui-react/src/pages/Malha.tsx` (grafo + estado), dashboard.

### Alternativas descartadas
- **Corrigir o `ExternalTaskSensor`** com `execution_date_fn`: resolveria o
  defeito 1, mas mantém polling, mantém o timeout e não resolve a perda de
  janela (filho agendado 10:00 com pai terminando 09:00 espera 1h à toa).
- **Scheduler central puro** (varredura a cada minuto disparando tudo): modelo
  Control-M literal, porém adiciona latência de até 1 min e concentra o disparo
  num ponto único de falha. O push com guardiã dá latência ~0 e mantém a rede.
- **Manter `depends_on` como CSV**: sem FK não há como garantir existência, e não
  há onde acomodar job→job depois.

## 4. Modelo de dados

Migration **`sql/migrations/067_dependencias_pipeline.sql`** — idempotente
(`IF OBJECT_ID`/`IF COL_LENGTH`), aplicada na **etapa 6c do `deploy.sh`**.

```sql
-- (A) Execução no nível PIPELINE (hoje só existe etl_job_execution, nível job)
CREATE TABLE dbo.etl_pipeline_execucao (
    id               BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    pipeline_name    VARCHAR(200) NOT NULL,
    data_referencia  DATE         NOT NULL,   -- ODATE
    execution_id     VARCHAR(50)  NULL,       -- run_id do Airflow
    status           VARCHAR(30)  NOT NULL,   -- AGUARDANDO_DEPENDENCIA|EXECUTANDO|
                                              -- SUCESSO|FALHA|PULADO|NAO_LIBEROU
    inicio           DATETIME2    NULL,
    fim              DATETIME2    NULL,
    disparado_por    VARCHAR(200) NULL,       -- pipeline pai | agenda | manual | guardia
    motivo           VARCHAR(500) NULL,
    criado_em        DATETIME2    NOT NULL DEFAULT GETDATE(),
    atualizado_em    DATETIME2    NOT NULL DEFAULT GETDATE()
);
-- Pipeline com horários específicos roda N vezes no dia: a chave inclui o
-- execution_id. A avaliação da condição usa a execução MAIS RECENTE da data.
CREATE UNIQUE INDEX ux_pipe_exec ON dbo.etl_pipeline_execucao
    (pipeline_name, data_referencia, execution_id);
CREATE INDEX ix_pipe_exec_cond ON dbo.etl_pipeline_execucao
    (pipeline_name, data_referencia, status, inicio);

-- (B) Dependência em tabela (substitui o CSV etl_pipeline.depends_on)
CREATE TABLE dbo.etl_pipeline_dependencia (
    id            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    pipeline_name VARCHAR(200) NOT NULL,   -- o dependente
    depende_de    VARCHAR(200) NOT NULL,   -- o predecessor
    -- Reservado para a feature FUTURA de dependência job→job (backlog §9).
    -- Nasce aqui para não exigir migration destrutiva depois.
    tipo          VARCHAR(20)  NOT NULL DEFAULT 'PIPELINE',  -- PIPELINE | JOB
    job_origem    VARCHAR(200) NULL,
    job_destino   VARCHAR(200) NULL,
    criado_em     DATETIME2    NOT NULL DEFAULT GETDATE(),
    criado_por    VARCHAR(100) NULL,
    CONSTRAINT FK_dep_pipeline  FOREIGN KEY (pipeline_name)
        REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE,
    -- É esta FK que torna impossível depender de um pipeline inexistente.
    CONSTRAINT FK_dep_predecessor FOREIGN KEY (depende_de)
        REFERENCES dbo.etl_pipeline (pipeline_name),
    CONSTRAINT CK_dep_nao_self CHECK (pipeline_name <> depende_de)
);
CREATE UNIQUE INDEX ux_dep ON dbo.etl_pipeline_dependencia
    (pipeline_name, depende_de, tipo, job_origem, job_destino);

-- (C) Colunas novas em etl_pipeline
ALTER TABLE dbo.etl_pipeline ADD
    hora_virada              TIME NULL,  -- override da virada global
    nao_iniciar_antes        TIME NULL,  -- janela: não dispara antes disso
    hora_limite_dependencia  TIME NULL;  -- deadline → alerta

-- (D) Eventos de dependência (idempotentes, padrão da supervisão DataStage)
CREATE TABLE dbo.etl_dependencia_evento (
    id              BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    pipeline_name   VARCHAR(200) NOT NULL,
    data_referencia DATE         NOT NULL,
    tipo            VARCHAR(30)  NOT NULL,  -- JANELA_ESTOUROU | DATA_DIVERGENTE |
                                            -- PREDECESSOR_FALHOU
    detalhe         VARCHAR(1000) NULL,
    detectado_em    DATETIME2 NOT NULL DEFAULT GETDATE(),
    notificado_em   DATETIME2 NULL
);
CREATE UNIQUE INDEX ux_dep_evento ON dbo.etl_dependencia_evento
    (pipeline_name, data_referencia, tipo);

-- (E) Config global da virada, em etl_app_config (chave já existente no projeto)
--     'dependencia_hora_virada' = '00:00'
```

**Migração dos dados:** a 067 popula `etl_pipeline_dependencia` a partir do CSV
`etl_pipeline.depends_on` existente, **ignorando entradas órfãs** (predecessor
inexistente) e imprimindo cada uma no log da migration — são exatamente os casos
que hoje falham em silêncio. O CSV continua sendo escrito durante a transição
(F1–F4) para não quebrar `Malha.tsx` e o gerador; F6 o aposenta.

## 4b. Malha — o agrupador de pipelines (incluído em 2026-08-02)

### O conceito
Uma **malha** é uma entidade nomeada que agrupa pipelines — o análogo direto da
*sequence mestre* do DataStage (uma sequence que orquestra outras sequences,
com Waits entre ondas) e da malha/SMART Folder do Control-M. A malha **não é um
executor novo**: quem executa continua sendo o modelo desta spec (ODATE +
push + guardiã). A malha é o **agrupador e a lente de montagem** — desenhar uma
aresta entre dois pipelines na malha É cadastrar a dependência na tabela
`etl_pipeline_dependencia` (F1), com as mesmas validações de ciclo (BFS) e
existência (FK). Sem mecanismo paralelo, sem segunda fonte de verdade.

### A tela
A tela **Malha** (`/malha`) é reaproveitada: passa a **listar malhas** e, ao
abrir uma, mostra o **diagrama Control-M** — nó = pipeline (com criticidade,
agendamento e estado), aresta = dependência, ondas visíveis pelo layout
topológico. A linguagem visual atual se mantém: cards com `CritBadge` e dot
ativo/inativo, stats-pills, toolbar de filtros, export CSV. O que a tela mostra
hoje e NÃO é malha-agrupadora sai dela: o inventário completo de pipelines
(visões Cards/Diagrama) e o `JobChain` intra-pipeline (assunto do canvas de
Etapas). **Destino decidido (2026-08-02): Catálogo & Lineage** (`/governanca`,
permissão `tela_governanca`) — de propósito: quem NÃO tem acesso à construção
de malhas (`tela_malha`) continua sabendo o que existe, pela mesma via de
consulta que já usa para catálogo e lineage.

O diagrama de montagem (`MalhaEditor`) nasce como **componente irmão** do
`FluxoEditor` (React Flow), não parametrização dele — o FluxoEditor é acoplado
a etapas. Na retomada, o modal de dependências da F5 e o MalhaEditor da F8
**coexistem como duas portas de entrada da MESMA tabela** — o modal serve o
ajuste pontual no cadastro do pipeline; a malha serve a montagem de conjunto. Os módulos puros migram para uso comum: `liveLayout`/`autoLayout`
(layout em camadas), `criaCiclo` (validação client-side, espelho do BFS da F1).
O `DependencyGraph` SVG atual da tela morre no processo (tem cores dark
hardcoded, quebrado no tema claro — não herdar).

### Modelo de dados (migration 070, na F7)
- `etl_malha` — `malha_name` (PK), `descricao`, `ativo`, `criado_em/por`.
- `etl_malha_pipeline` — membros: `malha_name` FK cascade, `pipeline_name` FK,
  `layout_x/layout_y` (posição do nó no diagrama da malha). Um pipeline pode
  estar em N malhas.
- **As dependências NÃO ganham escopo por malha**: continuam globais em
  `etl_pipeline_dependencia`. Uma dependência é um fato da orquestração, não da
  visão — se dois pipelines aparecem em duas malhas, a aresta aparece nas duas,
  porque ela é real nas duas. Consequência honesta: excluir uma aresta na malha
  exclui a dependência DE VERDADE (o editor avisa).

### Visão de execução (F9, depende de F2+)
Com `etl_pipeline_execucao` alimentada, a malha aberta numa **data de
referência** colore cada nó pelo status daquela data (AGUARDANDO_DEPENDENCIA /
EXECUTANDO / SUCESSO / FALHA / PULADO) e mostra os eventos da guardiã
(JANELA_ESTOUROU, DATA_DIVERGENTE) — a leitura diária de malha que o operador
de Control-M conhece.

## 5. Fases

### F1 — Fundação: modelo, data de referência e validações do cadastro
- **Entregável:** migration 067 aplicada, dependências em tabela, cadastro que
  recusa pipeline inexistente e detecta ciclo de verdade. Nada muda na execução.
- **Inclui:**
  - migration 067 (§4) + carga a partir do `depends_on` atual, com relatório de
    órfãos no log;
  - `dags/utils/data_referencia.py` — função pura `calcular(momento, virada)`;
  - `api/routers/pipelines.py`: CRUD de dependência na tabela nova; troca de
    `_check_circular` por **BFS sobre todas as dependências**; validação de
    existência (422 com a lista de nomes desconhecidos); escrita-espelho no CSV.
- **Critérios de aceite:**
  - dado A depende de `X,B` e B depende de A, quando gravar, então 422 de ciclo
    (é o caso que **passa** hoje);
  - dado `depends_on` com nome inexistente, quando gravar, então 422 citando o
    nome — nunca grava;
  - dado virada 20:00 e início 31/07 23:30, então `data_referencia` = 01/08;
  - dado virada 00:00 e início 31/07 23:30, então `data_referencia` = 31/07;
  - migration roda duas vezes sem erro e sem duplicar linhas.
- **Validação:** pytest (novos testes de ciclo/BFS, data de referência e carga) +
  tsc + eslint (baseline HEAD) + build.
- Revisão adversarial antes da PR. PR: `feat: modelo de dependências com data de referência`.

### F2 — Registro de execução por data de referência
- **Entregável:** toda execução de pipeline grava início/fim/status **com** a data
  de referência; disparo manual aceita a data.
- **Inclui:** `etl_dag_factory` grava em `etl_pipeline_execucao` (início na
  primeira task, fim na última, `FALHA` no callback de erro); leitura de
  `conf['data_referencia']` com fallback para o cálculo; `PULADO` quando o
  `check_agenda` corta.
- **Critérios de aceite:** dado um pipeline qualquer executado, então existe
  exatamente uma linha por `execution_id` com `data_referencia` preenchida e
  status final coerente; dado `conf` com data, então ela prevalece sobre o cálculo.
- **Validação:** pytest sobre a DAG gerada (compila + contém as gravações) +
  baseline. PR: `feat: execução de pipeline registrada por data de referência`.

### F3 — Liberação por condição e disparo imediato
- **Entregável:** o `ExternalTaskSensor` sai; o pipeline dependente é disparado
  pelo predecessor em segundos.
- **Inclui:** `dags/utils/dependencias.py` (puro: `liberado(pipeline, data_ref)`
  = todas as dependências com `SUCESSO` naquela data); task
  `t_disparar_dependentes` no fim do pipeline; `schedule=None` para pipeline com
  dependência; remoção do bloco de sensores e do modo Dataset.
- **Critérios de aceite:**
  - dado C depende de A e B, quando A conclui e B não, então C **não** dispara;
  - quando B conclui, então C dispara em menos de 1 min, com a mesma data;
  - dado `nao_iniciar_antes` = 08:00 e liberação às 07:10, então C não dispara
    (fica aguardando; a guardiã dispara às 08:00);
  - a DAG gerada de um pipeline com dependência **não** contém `ExternalTaskSensor`.
- **Validação:** pytest com DAG gerada + avaliação da condição em todos os casos
  (todas ok / uma falha / uma em outra data / nenhuma execução). PR:
  `feat: disparo imediato do pipeline dependente`.

### F4 — Guardiã, janela e alertas
- **Entregável:** o dia é "ordenado", nada fica preso em silêncio e a janela vira
  alerta.
- **Inclui:** DAG `etl_dependencia_guardia` (5 min) com as 4 responsabilidades do
  §3; `etl_dependencia_evento` alimentado com idempotência; alerta no Teams
  reusando `etl_msg_grupo` (mesmo caminho da supervisão DataStage).
- **Critérios de aceite:** dado predecessor que não rodou até
  `hora_limite_dependencia`, então evento `JANELA_ESTOUROU` + card no Teams, e o
  pipeline continua **pendente, não falha**; dado predecessor concluído em outra
  `data_referencia`, então `DATA_DIVERGENTE` citando as duas datas; ciclo repetido
  não duplica evento nem reenvia card.
- **Validação:** pytest da guardiã com banco stubado + baseline. PR:
  `feat: guardiã de dependências com janela e alerta`.

### F5 — UX/UI: cadastrar e enxergar dependência
- **Entregável:** cadastrar dependência sem digitar nome, e ver o estado da malha.
- **Inclui:** modal dedicado de dependências (busca por projeto e por nome,
  seleção múltipla, chips do que já está escolhido, estado da última execução de
  cada predecessor, bloqueio de ciclo com mensagem clara); campos de
  `nao_iniciar_antes` / `hora_limite_dependencia` / `hora_virada`; estado
  "Aguardando dependência" no dashboard e em `Malha.tsx`, com o motivo
  ("esperando PIPE_B · data ref 01/08").
- **Critérios de aceite:** não é possível salvar dependência digitando nome livre;
  o modal mostra por que um pipeline não pode ser escolhido (ciclo/ele mesmo); o
  dashboard distingue "aguardando dependência" de "não executou".
- **Validação:** tsc + eslint (baseline) + build com `dist/` commitada; tokens
  `canvas/panel/edge/ink` nos dois temas. PR: `feat: cadastro e visão de dependências`.

### F6 — Aposentar o legado + smoke ✔ entregue
- **Entregável:** a tabela é a fonte da verdade também na geração das DAGs, e o
  manual explica data de referência.
- **Inclui:** `etl_dag_factory` e o preview da API passam a ler
  `etl_pipeline_dependencia` (com fallback ao CSV); `docs/MANUAL_USUARIO.md`
  §3.4 reescrito; smoke do §7.
- **AJUSTE DE ESCOPO (2026-07-31):** a spec previa *parar de escrever* o CSV
  `depends_on`. Isso NÃO foi feito, de propósito. O CSV continua sendo escrito
  em espelho porque é o **fallback** de que o factory depende num deploy que
  leve `dags/` sem a migration 067 — e nada disto está em produção ainda.
  Derrubar o espelho antes do primeiro deploy validado trocaria uma dívida
  barata por um risco caro. Ver §10.
- **Validação:** suíte completa + smoke manual. PR: `chore: dependência só pela tabela`.

### F7 — Malha: entidade, API e lista (INDEPENDE da retomada F2–F6)
- **Entregável:** malhas existem, têm membros e aparecem na tela Malha como
  cards (linguagem visual atual); o inventário antigo segue acessível até a F9.
- **Inclui:** migration 070 (`etl_malha`, `etl_malha_pipeline` com layout);
  CRUD na API (criar/renomear/inativar malha; adicionar/remover membros);
  permissão `tela_malha` reaproveitada; tela lista malhas (cards com contagem
  de pipelines, criticidade agregada = a mais alta dos membros, dot ativo);
  item "Malha de Pipelines" do menu migra de **Governança & Dados** para
  **Construção** (`nav.ts` — decisão do usuário, 2026-08-02: montagem mora com
  Pipelines/Etapas/Fluxos/Publicação).
- **Critérios de aceite:** membro só pode ser pipeline existente (422 senão);
  excluir pipeline que é membro não quebra a malha (membro some, malha avisa);
  duas malhas podem conter o mesmo pipeline.
- **Validação:** pytest + tsc/eslint baseline + build. PR: `feat: malha — entidade e lista`.

### F8 — Malha: diagrama de montagem (INDEPENDE da retomada F2–F6)
- **Entregável:** abrir a malha mostra o diagrama React Flow; montar a malha É
  cadastrar dependências.
- **Inclui:** `MalhaEditor` irmão do FluxoEditor (nó = pipeline, aresta =
  dependência); extração de `liveLayout`/`autoLayout`/`criaCiclo` para módulo
  comum; paleta = busca de pipelines por projeto/nome; desenhar aresta grava em
  `etl_pipeline_dependencia` via API da F1 (ciclo BFS + existência + 422s);
  excluir aresta remove a dependência com confirmação explícita ("isto apaga a
  dependência real"); layout persistido em `etl_malha_pipeline`.
- **Critérios de aceite:** aresta que criaria ciclo é recusada no cliente E no
  servidor com a mesma mensagem; a MESMA dependência aparece em toda malha que
  contenha os dois pipelines; salvar sem mudanças é no-op.
- **Validação:** pytest + tsc/eslint baseline + build + revisão adversarial.
  PR: `feat: malha — diagrama de montagem`.

### F9 — Malha: visão de execução por data de referência (DEPENDE de F2–F4)
- **Entregável:** a malha aberta numa data colore os nós pelo status da
  `etl_pipeline_execucao` e mostra eventos da guardiã; o inventário antigo da
  tela migra para **Catálogo & Lineage** (`/governanca` — decisão do usuário,
  2026-08-02: consulta continua acessível a quem não constrói malhas) e a tela
  Malha passa a exibir SÓ malhas.
- **Inclui:** seletor de data de referência (default: ODATE corrente); polling
  do status; legenda de estados; realocação do inventário + remoção do
  `DependencyGraph` SVG legado.
- **Critérios de aceite:** status na malha bate com `etl_pipeline_execucao` da
  data; pipeline fora de malha não aparece em malha nenhuma (e o catálogo
  realocado continua listando todos).
- **Validação:** smoke no ambiente dev com cascata real (§7). PR:
  `feat: malha — visão de execução`.

## 6. Riscos e mitigações

| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Pipelines existentes com `depends_on` órfão (nome inexistente) travam a carga da 067 | Migration falha no deploy, etapa 6c aborta | A carga **ignora e loga** órfãos em vez de falhar; a lista sai no log da migration para correção pelo cadastro |
| 2 | `schedule=None` aplicado a um pipeline cujo pai nunca dispara (ex.: pai inativado) | Pipeline deixa de rodar sem ninguém notar | A guardiã ordena o dia e o deadline gera alerta — é o cenário que a F4 existe para cobrir. Smoke (d) valida |
| 3 | Deploy parcial: `dags/` sem a migration 067 | DAG grava em tabela inexistente e o `except` engole tudo | Mesmo padrão já usado na supervisão DS: consulta `sys.columns`/`OBJECT_ID` uma vez por ciclo e degrada; F2 inclui esse teste |
| 4 | Virada de dia mal configurada faz duas corridas caírem em datas diferentes | Dependência nunca libera | Default 00:00 (comportamento atual); a tela mostra a data de referência **calculada** ao lado do campo, e a guardiã alerta `DATA_DIVERGENTE` |
| 5 | Push duplicado: pai e guardiã disparam o mesmo filho | Execução dupla | Índice único `(pipeline, data_referencia, execution_id)` + a linha `AGUARDANDO_DEPENDENCIA` é atualizada com `UPDATE ... WHERE status='AGUARDANDO_DEPENDENCIA'`; quem não afetar linha não dispara |
| 6 | Pipeline que roda N vezes ao dia (horários específicos) com dependência | Condição ambígua | A avaliação usa a execução **mais recente** da data; documentado na tela e no manual |

## 7. Smoke pós-deploy

a) Cadastrar `PIPE_C depende de PIPE_A, PIPE_B` pelo modal — confirmar que não
   aceita nome livre e que sugere por projeto.
b) Tentar criar ciclo (`PIPE_A depende de PIPE_C`) → recusa com mensagem clara.
c) Rodar A e B no mesmo dia; ao concluir o **segundo**, C deve iniciar em menos
   de 1 min. Conferir `SELECT * FROM etl_pipeline_execucao WHERE data_referencia = CAST(GETDATE() AS DATE)`.
d) Não rodar B; passar da `hora_limite_dependencia` → alerta no Teams e C
   **pendente**, não falhado.
e) Configurar `hora_virada = 20:00` num pipeline, disparar às 23:30 → conferir
   `data_referencia` = dia seguinte, e o filho herdando a mesma data.
f) Conferir que a DAG gerada de um pipeline dependente **não** tem
   `ExternalTaskSensor` e está com `schedule=None` na UI do Airflow.

## 8. Decisões fechadas (2026-07-31)
- **Virada global = `00:00`** — preserva exatamente o comportamento de hoje. O
  override por pipeline (`hora_virada`) é opt-in, só para quem atravessa a
  meia-noite. Consequência: nenhum pipeline existente muda de data de referência
  ao subir a F1.
- **Alerta de dependência reusa o canal da supervisão DataStage** em
  `etl_msg_grupo` — sem grupo novo na migration. A F4 lê o mesmo grupo que a
  supervisão já usa.
- **`hora_limite_dependencia` nasce em branco** (sem deadline). Sem valor, a
  guardiã não gera `JANELA_ESTOUROU` para aquele pipeline — o deadline é opt-in,
  configurado por quem conhece a janela de negócio. **Não** herda `sla_minutos`:
  são coisas diferentes (SLA é duração da execução; o limite é o horário até o
  qual a liberação faz sentido).

Decisões de 2026-08-02 (inclusão da Malha):
- **A tela Malha exibirá SÓ malhas** (agrupadoras de pipelines, formato
  Control-M); o inventário atual migra para **Catálogo & Lineage**
  (`/governanca`) na F9 — separação deliberada entre construir (`tela_malha`)
  e consultar (`tela_governanca`): quem não constrói continua vendo o que
  existe.
- **"Malha de Pipelines" muda de grupo no menu: Governança & Dados →
  Construção** (na F7, junto da tela nova) — montagem mora com Pipelines,
  Etapas, Fluxos e Publicação; em Governança fica a consulta.
- **Dependência é global, não por malha** — a malha agrupa e exibe; a aresta
  desenhada nela grava na tabela da F1. Uma fonte de verdade só.
- **F7 e F8 podem andar ANTES da retomada F2–F6** (montagem só precisa da F1,
  que está na main); a F9 espera a execução existir.
- **Ambiente dev criado nesta VPS** como pré-condição da retomada — runbook em
  `docs/ambiente-dev.md`.

## 10. Pendências desta spec (depois do deploy validado)

Atualizado em 2026-08-02 (F6): as dívidas 1–2 **continuam aguardando o deploy
validado** — a F6 manteve o espelho de propósito (ajuste de escopo do §5-F6);
os fios soltos 3–4 do ambiente dev foram tratados na retomada:

1. **Remover a escrita em espelho do CSV `etl_pipeline.depends_on`** e, depois,
   a própria coluna. Hoje ela é o fallback do `etl_dag_factory` e do preview
   quando a migration 067 não está aplicada. Só faz sentido remover quando a
   067 estiver aplicada em produção **e** as DAGs regeradas — antes disso, o
   fallback é o que impede um deploy parcial de gerar DAGs sem dependência
   nenhuma. **Segue de pé após a F6, de propósito.**
2. **`trigger_por_dependencia`** já saiu da tela (F5) e não decide mais nada
   (F3), mas a coluna segue no banco. Some junto com o CSV, na mesma migration.

3. ~~FIO SOLTO: a `sp_etl_pipelines_pendentes_criar` não devolve
   `depends_on`~~ — **FECHADO (F3/F6, D37):** o gerador não depende mais da SP
   para dependências. O supplement `_dependencias_da_tabela` lê
   `etl_pipeline_dependencia` (067) diretamente, com o contrato None×{} (D36),
   e o `depends_on` do CSV entrou no SELECT de colunas avançadas só como
   **denunciante**: sem a 067, dependência no CSV faz a geração recusar
   ruidosamente em vez de regredir a cron em silêncio. Confirmado por EXECUÇÃO
   no dev (smoke §7f da F6): DAG de dependente gerada com dependência gravada
   SÓ na tabela sai com `schedule=None` e sem `ExternalTaskSensor`.
4. **Bootstrap de banco virgem tem armadilhas conhecidas** (encontradas ao
   montar o dev): `deploy_full.sql` referencia colunas de migrations posteriores
   nas SPs da Seção 2 (converge na 2ª passada, mas deveria ser corrigido) e
   está defasado do schema real (migrate para na 012 por falta de
   `updated_at`); a migration 010 cria `etl_ds_job_log` (a TABELA real de
   produção) **sem guarda de idempotência** e o bloco de limpeza do
   `schema_prod_dev.sql` tenta `DROP VIEW` sem checar o tipo — a ordem dos
   passos importa; `sqlcmd` (tools18) aborta o deploy_full com "Invalid cursor
   state" — usar o runner pyodbc do runbook. Detalhes e a sequência que
   funciona em `docs/ambiente-dev.md`. **Resolvido na F6:** o drift
   `etl_pipeline.ssh_conn_id` (produção tem, o dump não tinha — quebrava o
   `GET /factory/preview` no dev, achado da validação da F5) entrou na
   definição de `sql/schema_prod_dev.sql`.

Sequência sugerida: deploy → smoke §7 → uma execução real de ponta a ponta →
migration de limpeza removendo as duas colunas.

## 9. Backlog garantido (feature futura)
**Dependência job → job entre pipelines diferentes.** Decisão do usuário em
2026-07-31: fora desta entrega, mas **garantida no roadmap**. Por isso
`etl_pipeline_dependencia` já nasce com `tipo` ('PIPELINE'|'JOB'), `job_origem` e
`job_destino`: quando a feature entrar, é preenchimento de coluna e UI — não
migration destrutiva nem retrabalho de modelo. A avaliação da condição em
`dags/utils/dependencias.py` deve ser escrita já recebendo o `tipo`, ignorando
'JOB' nesta entrega.
