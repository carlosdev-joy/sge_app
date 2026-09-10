# Spec: Parâmetros de execução dos jobs DataStage — Orquestra
Data: 2026-09-09 · Status: concluída (F6 = a PR que fecha esta spec, 2026-09-10) · F1 = PR #376 · F2 = PR #377 · F3 = PR #378 · F4 = PR #379 · F5 = PR #380 · migrations 107–109 aplicadas no DEV em 2026-09-10

## 1. Visão
Hoje o Orquestra dispara todo job DataStage sem nenhum `-param`: o comando gerado é
`dsjob -run -mode NORMAL [-queue X] 'projeto' 'job'` e o job roda com os defaults do
design e do Parameter Set. O único gancho de parâmetro do operador
(`execution_date_param`) nunca é preenchido pela fábrica de DAGs, e a tabela/editor de
parâmetros que existe (`etl_pipeline_job_param`, migration 026) é exclusiva de etapas
`storedproc`. Quem precisa passar uma data de referência, um caminho ou uma flag ao
job não tem onde fazer isso — e a mensagem de erro do operador já admite:
*"o Orquestra NÃO envia nenhum -param nesta etapa"*.

Esta spec faz o `-param` chegar ao DataStage a partir das **mesmas telas e da mesma
tabela** que o storedproc já usa (Construção › Etapas e Construção › Fluxos, via
`JobTypeFields`), com as **quatro decisões** tomadas na análise de 2026-09-09:

1. **Valor fixo OU calculado** — origem `fixo`, `data_referencia` (ODATE da corrida),
   `data_logica` (ds do Airflow), `data_execucao` (relógio no disparo) ou `run_id`.
   Para datas, um **cálculo declarativo** em passos fixos: deslocamento em meses →
   âncora (início/fim de mês, trimestre, ano, semana) → deslocamento em dias →
   formato. Cobre o caso "carga mensal do mês anterior": `pDataIni` = referência
   −1 mês, início do mês; `pDataFim` = referência −1 mês, fim do mês. O valor é
   recalculado a cada execução e o **valor enviado fica registrado** no log da
   task, em `etl_ds_job_log` e na tela de detalhe da execução.
2. **Tipos do DataStage**, não de SQL — String, Integer, Float, Date, Time, Timestamp,
   Pathname, List e **Encrypted** (cifrado com a mesma chave Fernet de `etl_conexao`,
   nunca em claro no banco, nunca no log).
3. **Nível de pipeline + sobreposição por etapa** — defaults do pipeline valem para
   toda etapa DataStage que **declarar** o parâmetro; a etapa pode sobrepor.
4. **Sobreposição na reexecução** — o modal de rerun mostra o valor efetivo de cada
   parâmetro e deixa o operador trocar só naquela corrida, com rastro de uso.

Para quem: Desenvolvedor ETL (cadastra), Operador (reexecuta com outro valor),
Sustentação (lê no log exatamente o que foi enviado).

## 2. Escopo
**IN:**
- Parâmetros por etapa `datastage` na tabela `etl_pipeline_job_param` (colunas novas:
  origem, meses, âncora, dias, formato), com validação por tipo DataStage na API.
- Endpoint de **prévia** do cálculo (`POST /pipelines/jobs/params/preview`): a tela
  mostra "com a referência X o valor seria Y" e permite simular outra data (fim de
  mês, 29/02) sem salvar nem disparar nada.
- **Rastro do valor enviado**: linha `[DS] parâmetros:` no log da task com o valor e
  a descrição do cálculo; coluna `params_json` em `etl_ds_job_log`; bloco "Parâmetros
  enviados" no modal de detalhe da execução (`ExecucaoDetailModal.tsx`).
- Operador `DataStageOperator` lê os parâmetros **em runtime** (banco), resolve as
  origens dinâmicas, decifra Encrypted, valida contra `dsjob -lparams` e emite N
  `-param` no `dsjob -run`. Sem parâmetro configurado, o comando é **byte a byte o de
  hoje**.
- Editor de parâmetros DataStage nas telas Etapas e Fluxos (mesmo `JobParamsEditor`,
  em "modo DataStage").
- Tabela `etl_pipeline_param` (defaults do pipeline) + seção no wizard de Pipelines +
  merge no operador (aplica só o que o job declara).
- Tabela `etl_job_param_override` (sobreposição por `dag_run_id`) + prévia e modal de
  rerun + `POST /execucoes/rerun` gravando antes do clear + carimbo `consumido_em`.
- Pré-preenchimento do editor a partir dos parâmetros já extraídos pelo lineage ISX
  (`etl_ds_job_isx.parameters_json`), que hoje são gravados e nunca exibidos.
- Manual do usuário, release note com restart do worker, testes (pytest + front).

**OUT (explícito):**
- **Sobreposição na execução manual do pipeline inteiro** (botão Executar da tela
  Pipelines). Fica para spec seguinte — reaproveita `etl_job_param_override`, porque o
  endpoint já sabe o `dag_run_id` que cria (`api/routers/pipelines.py:1455`).
- **Sobrepor parâmetro Encrypted no rerun.** O modal mostra `***` e não edita.
- **`-paramfile`** (arquivo temporário no servidor do DataStage) para tirar o segredo
  da linha de comando. Registrado como hardening futuro (risco #1).
- **Migrar o storedproc para leitura em runtime.** Ele continua com `proc_params`
  embutido na DAG gerada; a assimetria é conhecida e documentada (§3, decisões).
- **Resolver `#PSet.X#` no lineage** (já fora de escopo em `docs/spec-lineage-isx.md`).
- **Fila do DataStage editável na etapa.** Continua derivada da criticidade.
- **Parâmetros para etapas shell/python/http.** Só DataStage nesta spec.
- **Cálculo por dias úteis / calendário** ("último dia útil do mês anterior"). O
  Orquestra já tem calendários e `somente_dias_uteis`; entra como âncora nova numa
  spec seguinte, sem mudar o modelo (§8).
- **Expressão livre de data** (mini-linguagem). O cálculo é declarativo em passos
  fixos; se um caso real não couber, vira âncora nova, não expressão.

## 3. Arquitetura proposta

### Front (`ui-react/src`)
- `components/etapas/JobTypeFields.tsx` — fonte única de campos por tipo. Ganha:
  `DS_PARAM_TYPES`, `DS_PARAM_SOURCES`, `DS_PARAM_ANCORAS`, tipo `JobParam`
  estendido (`param_source`, `param_offset_meses`, `param_ancora`,
  `param_offset_dias`, `param_formato`, `tem_valor`), `JobParamsEditor` com prop
  `modo: 'storedproc' | 'datastage'`, e o ramo `job_type === 'datastage'` passa a
  renderizar a seção "Parâmetros do job (opcional)" abaixo de "Log detalhado".
  Para origem de data a linha abre um sub-bloco "Cálculo": Meses | Âncora | Dias |
  Formato, e uma coluna "Prévia" alimentada pelo endpoint de preview (debounce),
  com o campo "Simular com a referência" (padrão: hoje). O front **não
  reimplementa** o cálculo em TypeScript.
  `jobTypeFieldsErrors` valida o modo DataStage (nome com um ponto opcional, tipo,
  origem × tipo, meses, âncora, dias, formato, Pathname absoluto).
- `components/execucao/ExecucaoDetailModal.tsx` — bloco "Parâmetros enviados" lendo
  `params_json` da execução: nome, valor enviado (Encrypted como `***`), fonte
  (etapa / pipeline / rerun) e a descrição do cálculo.
- `pages/Jobs.tsx` (modal `JobFormModal`) — envia `params` também para `datastage`
  (hoje `:278` só envia para storedproc) e hidrata os campos novos (`:186-202`).
- `components/etapas/FluxoEditor.tsx` + `paineis/PainelEtapa.tsx` + `EtapaNode.tsx` —
  hidratação dos campos novos (`FluxoEditor.tsx:201`) e badge de contagem no nó
  DataStage, igual ao do storedproc.
- `components/pipelines/PipelineFormModal.tsx` — passo 2 (bloco Execução, abaixo de
  "Fila de execução (pool)", `:1031`) ganha a seção "Parâmetros DataStage do pipeline"
  reusando `JobParamsEditor` em modo DataStage; passo 3 (Revisão) mostra a contagem.
- `components/etapas/ModalRerunEtapa.tsx` — seção "Parâmetros desta reexecução":
  por etapa DataStage do conjunto limpo, lista nome, origem, fonte (etapa/pipeline) e
  valor efetivo; campo editável (exceto Encrypted); envia só o que mudou.
- `pages/DsConsole.tsx` e `governanca/isx/*` — **sem mudança** (continuam leitura).

### Back (`api/`)
- `routers/jobs.py` — validação DataStage compartilhada entre `POST /pipelines/jobs/register`
  (`:1857`) e `POST /pipelines/{p}/fluxo` (`:2491`), em um helper único
  `_validar_params_ds()`; GET do job (`:2054`) e GET do fluxo (`:2280`) devolvem as
  colunas novas com Encrypted mascarado. A regra `params_present` do fluxo (`:2492`)
  passa a valer para os dois caminhos.
- `services/conn_crypto.py` — `encrypt_password`/`decrypt_password` reutilizados como
  estão para Encrypted (mesma `ORQUESTRA_CONN_KEY` que o worker já usa em
  `dags/utils/conn_resolver.py:74-80`).
- `services/job_params.py` (novo, puro, sem banco) — `calcular_data(base, meses,
  ancora, dias)`, `formatar(data, formato)`, `descrever(spec)` (texto humano do
  cálculo) e `validar_spec(...)`. Usado pela validação do save, pelo endpoint de
  preview e pela prévia do rerun. Espelho de `dags/utils/ds_params.py` com teste
  anti-drift desde a F2.
- `routers/jobs.py` — `POST /pipelines/jobs/params/preview` (qualquer usuário
  logado, `get_current_user`: é cálculo puro, sem banco e sem efeito): recebe
  `{referencia: 'YYYY-MM-DD', itens: [{param_name, param_type,
  param_source, param_offset_meses, param_ancora, param_offset_dias,
  param_formato}]}` e devolve `[{param_name, valor, descricao}]` ou os erros de
  validação por item. Não toca no banco.
- `routers/datastage.py` — `GET /datastage/log` (o que o modal de detalhe da
  execução consome) inclui `params_json` na projeção quando a coluna existe e o
  devolve já parseado. (Os SELECTs de `execucoes.py` sobre `etl_ds_job_log` são
  agregações de fila, não o detalhe — corrigido na F3.)
- `routers/pipelines.py` — `POST /pipelines/register` aceita `parametros` (semântica
  de presença da chave) e o GET que hidrata o `PipelineFormModal` devolve `parametros`.
  `CAMPOS_QUE_AFETAM_DAG` **não muda**: parâmetro é lido em runtime, não entra na DAG.
- `routers/execucoes.py` — `GET /pipelines/{p}/rerun/previa` (`:1080`) devolve
  `parametros` por etapa; `POST /execucoes/rerun` (`:1309`) aceita `parametros`, grava
  em `etl_job_param_override` **antes** do `clearTaskInstances` e apaga se o clear
  falhar.
- `routers/lineage_isx.py` — `GET /lineage/isx/job` (`:225`) já devolve
  `parameters`; F6 só o consome.

### Dados
- `dbo.etl_pipeline_job_param` (existente) + 3 colunas; `sp_etl_pipeline_job_param_insert`
  com 3 parâmetros opcionais (compatível com o chamador do storedproc).
- `dbo.etl_pipeline_param` (nova) — defaults por pipeline.
- `dbo.etl_job_param_override` (nova) — sobreposição por corrida.
- `dbo.etl_pipeline_execucao.data_referencia` (067) — fonte do ODATE em runtime.
- `dbo.etl_ds_job_isx.parameters_json` (106) — fonte do pré-preenchimento.
- Conexão: a mesma `mssql_conn_id` que o operador já usa em `_persist`
  (`dags/utils/datastage_operator.py:823`), placeholders `%s` (árvore `dags/`).

### Orquestração (`dags/`)
- `dags/utils/ds_params.py` (novo, puro, testável sem Airflow): carregar linhas do
  banco → mesclar (pipeline < etapa < override) → resolver origens → calcular
  (meses → âncora → dias) → decifrar → formatar → devolver
  `[{nome, valor, fonte, descricao, mascarar}]` e a lista de ignorados. Mesmas
  funções puras `calcular_data`/`formatar`/`descrever` de `api/services/job_params.py`.
- Rastro em `etl_ds_job_log.params_json`: gravado logo após o primeiro `_persist`
  (QUEUED) por um `UPDATE` próprio, no padrão de `_persist_queued_seconds`
  (`datastage_operator.py:793-809`), sem mexer na assinatura de
  `sp_etl_ds_job_log_upsert` nem na sua cadeia de fallbacks. Encrypted entra como
  `***`. Falha nesse UPDATE é warning (observabilidade), não derruba a carga —
  o valor já está no log da task.
- `dags/utils/datastage_operator.py` — `_trigger_run` ganha o passo de resolução e
  emite N `-param` com `shlex.quote(f"{nome}={valor}")`; `_lparams()` novo wrapper
  (mesma disciplina de `_logsum`/`_ljobs`); `_descreve_param` passa a listar os
  nomes enviados (valores de Encrypted como `***`); carimbo `consumido_em` no
  override após o disparo aceito.
- `dags/etl_dag_factory.py:295-306` — passa `pipeline_name=PIPELINE_NAME` ao
  operador (hoje ele cai no `dag_id`, que é igual; a linha explícita elimina a
  dependência do fallback). **Nada mais muda na fábrica**: nenhum parâmetro entra
  no código gerado.

### Decisões e alternativas descartadas
- **Leitura em runtime, não embutida na DAG.** Embutir (como o `proc_params` do
  storedproc) exigiria "Publicar nova versão" a cada troca de valor, e hoje editar
  uma etapa **não acende** `dag_config_pendente_em` (só o register do pipeline e o
  reconciliador acendem — `api/routers/pipelines.py:1346`,
  `api/services/dag_reconcile.py:200`). Valor velho rodando em silêncio é exatamente
  a classe de "falso verde" que o projeto cataloga. Custo: uma leitura no banco por
  disparo, no mesmo banco que `check_agenda` já exige antes de qualquer job.
- **Sem banco = falha alta.** Se a leitura dos parâmetros falhar, a etapa falha com
  mensagem clara. Nunca dispara "com os defaults" por conta própria.
- **`-lparams` antes do `-run`, só quando há candidato.** É o que permite (a) aplicar
  default de pipeline só a quem declara e (b) transformar "parâmetro inexistente"
  numa mensagem antes do disparo, em vez do erro genérico do dsjob. Zero parâmetros
  = zero chamadas extras.
- **Etapa não declarada = falha; pipeline não declarado = ignora e loga.** Na etapa
  o operador digitou o nome de propósito; no pipeline o default é compartilhado por
  natureza.
- **Encrypted como valor cifrado no banco (Fernet), não como nome de Variable do
  Airflow.** A chave e o helper já existem para `etl_conexao`; o worker já decifra
  com ela. Uma Variable seria uma segunda fonte de segredo fora do Orquestra.
- **ODATE lido de `etl_pipeline_execucao` pelo `run_id`**, não recalculado. É a
  Decisão 36 da malha: o run tem UM ODATE e ele nasce no `check_agenda`
  (`etl_dag_factory.py:2272-2281`), sempre a montante das etapas
  (`root_anchor = "t_check_agenda"`, `:2417`). Fallback único: `conf['data_referencia']`
  válido. Sem os dois, falha alta — nunca "a data de hoje".
- **Sobreposição por `dag_run_id` numa tabela, não no `conf`.** O `clearTaskInstances`
  reusa o mesmo dag_run e o Airflow não deixa editar `conf`. A tabela dá rastro
  (`criado_por`, `consumido_em`) e não vaza para a corrida agendada seguinte.
- **Duplicar as funções puras de cálculo em `api/` e `dags/` com teste anti-drift**,
  em vez de módulo compartilhado: as duas árvores rodam em containers diferentes e
  o repo nunca importou uma da outra. O front não tem terceira cópia: a prévia vem
  do endpoint.
- **Cálculo declarativo em passos fixos (meses → âncora → dias → formato), não
  expressão livre.** É o vocabulário do Control-M (`%%$ODATE` com `%%CALCDATE`), cabe
  em quatro colunas com CHECK, valida sem parser e se descreve sozinho no log
  ("referência −1 mês → fim do mês"). A ordem é a que faz "mês anterior" funcionar
  em qualquer dia: deslocar o mês primeiro (com dia truncado para o último dia
  válido), ancorar depois, ajustar dias por último.
- **`data_execucao` existe, mas a recomendação é `data_referencia`.** O relógio do
  disparo diverge do dia de negócio na virada (o incidente `Carga_Vida`); a tela
  explica isso no hint e a referência é o padrão pré-selecionado.

## 4. Modelo de dados
Todas idempotentes (rodam 2×), aplicadas pela etapa 6c do `deploy.sh`. Números 107–109
a confirmar na abertura de cada fase (a spec `lineage-isx-pasta-raiz` pode tomar a 107).

### `107_job_param_datastage.sql` (F1)
```sql
-- etl_pipeline_job_param: colunas novas (IF COL_LENGTH(...) IS NULL)
param_source       VARCHAR(30)  NOT NULL CONSTRAINT DF_etl_pipeline_job_param_source DEFAULT 'fixo'
                   -- 'fixo' | 'data_referencia' | 'data_logica' | 'data_execucao' | 'run_id'
param_offset_meses INT          NULL   -- passo 1: deslocamento em meses (dia truncado ao último válido). NULL = 0
param_ancora       VARCHAR(20)  NULL   -- passo 2: NULL | inicio_mes | fim_mes | inicio_trimestre | fim_trimestre
                                       --          | inicio_ano | fim_ano | inicio_semana | fim_semana (seg–dom)
param_offset_dias  INT          NULL   -- passo 3: deslocamento em dias. NULL = 0
param_formato      VARCHAR(40)  NULL   -- passo 4: strftime. NULL = '%Y-%m-%d'
-- CHECKs (IF NOT EXISTS em sys.check_constraints): source no vocabulário; ancora no vocabulário;
--   meses em -120..120; dias em -3660..3660; cálculo só com source de data.
-- sp_etl_pipeline_job_param_insert: CREATE OR ALTER com os 5 novos @params opcionais (defaults acima)
-- sp_etl_pipelines_pendentes_criar: NÃO muda (a SP é global; o operador lê direto da tabela)

-- etl_ds_job_log: rastro do que foi enviado (IF COL_LENGTH(...) IS NULL)
params_json        NVARCHAR(MAX) NULL  -- [{name, valor, fonte: 'etapa'|'pipeline'|'rerun', descricao, mascarado}]
```
`param_type` (VARCHAR(30)) continua: vocabulário por `job_type` — storedproc mantém
`VARCHAR|INT|DATE|DATETIME|DECIMAL|BIT`; datastage usa
`String|Integer|Float|Date|Time|Timestamp|Pathname|List|Encrypted`.
`param_name` (VARCHAR(128)) aceita um ponto: `PSet.Param` para membro de Parameter Set.
`param_value` (NVARCHAR(MAX)) guarda o token Fernet quando `param_type='Encrypted'`.

### `108_pipeline_param.sql` (F4)
```sql
CREATE TABLE dbo.etl_pipeline_param (
    id                INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_param PRIMARY KEY,
    pipeline_name     NVARCHAR(200) NOT NULL,
    param_name        VARCHAR(128)  NOT NULL,
    param_type        VARCHAR(30)   NOT NULL,       -- vocabulário DataStage
    param_value       NVARCHAR(MAX) NULL,
    param_source       VARCHAR(30)   NOT NULL CONSTRAINT DF_etl_pipeline_param_source DEFAULT 'fixo',
    param_offset_meses INT           NULL,
    param_ancora       VARCHAR(20)   NULL,
    param_offset_dias  INT           NULL,
    param_formato      VARCHAR(40)   NULL,
    param_order        INT           NOT NULL CONSTRAINT DF_etl_pipeline_param_order DEFAULT 0,
    created_at        DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_pipeline_param_em DEFAULT GETDATE(),
    CONSTRAINT UQ_etl_pipeline_param UNIQUE (pipeline_name, param_name),
    CONSTRAINT FK_etl_pipeline_param_pipeline FOREIGN KEY (pipeline_name)
        REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE   -- PK_etl_pipeline(pipeline_name)
);
```
(200 × 2 + 128 = 528 bytes de chave, dentro do teto.)

### `109_job_param_override.sql` (F5)
```sql
CREATE TABLE dbo.etl_job_param_override (
    id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_param_override PRIMARY KEY,
    pipeline_name NVARCHAR(200) NOT NULL,
    job_name      NVARCHAR(200) NOT NULL,
    dag_run_id    NVARCHAR(250) NOT NULL,   -- run_id do Airflow (manual__…, scheduled__…, dep__…)
    param_name    VARCHAR(128)  NOT NULL,
    param_value   NVARCHAR(MAX) NULL,
    criado_em     DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_job_param_override_em DEFAULT GETDATE(),
    criado_por    NVARCHAR(100) NULL,       -- matrícula (mesmo vocabulário de etl_pipeline_audit.changed_by)
    consumido_em  DATETIME2(0)  NULL,       -- carimbado pelo operador quando o valor foi enviado
    CONSTRAINT UQ_etl_job_param_override UNIQUE (pipeline_name, job_name, dag_run_id, param_name),
    CONSTRAINT FK_etl_job_param_override_job FOREIGN KEY (pipeline_name, job_name)
        REFERENCES dbo.etl_pipeline_job (pipeline_name, job_name) ON DELETE CASCADE
);
-- índice IX_etl_job_param_override_run (pipeline_name, dag_run_id, job_name) — a consulta do operador
```
Retenção: sem job de limpeza nesta spec (volume = nº de reruns com sobreposição);
`etl_log_cleanup` pode ganhar a tabela depois (§8).

### Regras de resolução (contrato, vale para API e operador)
1. Base = `etl_pipeline_param` do pipeline, **filtrada** pelos nomes que `dsjob -lparams`
   devolve para o job. Não declarado → ignorado e listado no log.
2. `etl_pipeline_job_param` da etapa sobrepõe por nome. Nome **não declarado** pelo
   job → a etapa falha **antes** do `-run`, com a lista do `-lparams` na mensagem
   (mesma disciplina de `_falhar_se_erro_dsjob`).
3. `etl_job_param_override` do `(pipeline, job, run_id)` sobrepõe o valor (origem
   passa a `fixo`). Nome fora de 1+2 e não declarado → falha antes do `-run`.
4. Origem: `fixo` → `param_value`; `data_referencia` → `etl_pipeline_execucao` do
   `run_id` (fallback `conf['data_referencia']` ISO válido; senão falha);
   `data_logica` → `context['ds']`; `data_execucao` → data do relógio no disparo
   (fuso do worker); `run_id` → `context['run_id']`.
   Datas passam pelo **cálculo em ordem fixa**, cada passo opcional:
   1. `+ offset_meses` (o dia é truncado ao último dia válido do mês de destino:
      31/03 −1 mês = 28/02 ou 29/02);
   2. `ancora` (`inicio_mes`, `fim_mes`, `inicio_trimestre`, `fim_trimestre`,
      `inicio_ano`, `fim_ano`, `inicio_semana` = segunda, `fim_semana` = domingo);
   3. `+ offset_dias`;
   4. `strftime(formato)`.
   A mesma função gera a **descrição** que vai para o log, a prévia e o modal de
   rerun: `referência 2026-09-09 → −1 mês → fim do mês → 2026-08-31`.

   Exemplos (referência 2026-09-09):

   | Caso | meses | âncora | dias | formato | Valor |
   |------|------:|--------|-----:|---------|-------|
   | `pDataIni` do mês anterior | −1 | inicio_mes | 0 | `%Y-%m-%d` | 2026-08-01 |
   | `pDataFim` do mês anterior | −1 | fim_mes | 0 | `%Y-%m-%d` | 2026-08-31 |
   | D−1 compacto | 0 | — | −1 | `%Y%m%d` | 20260908 |
   | Último dia do mês corrente | 0 | fim_mes | 0 | `%d/%m/%Y` | 30/09/2026 |
   | Início do trimestre anterior | −3 | inicio_trimestre | 0 | `%Y-%m-%d` | 2026-04-01 |
   | Ano-mês de referência | 0 | — | 0 | `%Y%m` | 202609 |
   | Semana passada, segunda | 0 | inicio_semana | −7 | `%Y-%m-%d` | 2026-08-31 |

   Borda testada no anti-drift: 31/01 −1 mês = 31/12; 31/03 −1 mês = 28/02 (29/02 em
   bissexto); 30/04 +1 mês = 30/05; fim_mes de fevereiro bissexto; virada de ano em
   `inicio_trimestre` com meses −3 a partir de janeiro.
5. `Encrypted` → decifra com `ORQUESTRA_CONN_KEY`; no log e no `_descreve_param`
   aparece `nome=***`; o comando com o valor real **nunca** é logado.
5b. **Rastro obrigatório** do que foi enviado, nos três lugares, sempre com a mesma
   lista `[{name, valor, fonte, descricao, mascarado}]`: (i) linha `[DS] parâmetros:`
   no log da task, uma entrada por nome com a descrição do cálculo; (ii)
   `etl_ds_job_log.params_json` da execução; (iii) modal de detalhe da execução.
   O que aparece ali é **o que foi para a linha de comando** (após merge, override
   e cálculo), não a configuração.
6. Comando: `dsjob -run -mode NORMAL [-queue Q] -param 'N1=V1' … 'proj' 'job'`, cada
   par por `shlex.quote`. Lista vazia após 1–3 → sem `-lparams` e comando idêntico
   ao atual.
7. Nomes comparados **com caixa exata** (DataStage é case-sensitive; ver
   `orquestra-nome-job-datastage`). Formato validado por allowlist de diretivas
   (`%Y %m %d %y %H %M %S` e os literais `- / . _ :`).

## 5. Fases

### F1 — Modelo + API da etapa DataStage
- Entregável: migration 107 + `jobs.py` aceitando/devolvendo parâmetros de etapas
  `datastage`; nenhuma tela muda (o front continua escondendo o editor para datastage).
- Inclui:
  - Migration 107 (colunas, CHECK, SP com defaults), teste "roda 2×" da suíte de
    migrations.
  - `api/services/job_params.py` puro: `calcular_data`, `formatar`, `descrever`,
    `validar_spec`; testes de borda de mês/ano (tabela do §4).
  - `_validar_params_ds(lista)` em `jobs.py`: nome `^[A-Za-z_]\w*(\.[A-Za-z_]\w*)?$`,
    sem duplicata por caixa exata; tipo em `DS_PARAM_TYPES`; origem em
    `DS_PARAM_SOURCES`; origem de data só com tipo String/Date/Timestamp; `run_id` só
    com String; meses/âncora/dias/formato só com origem de data (`validar_spec`);
    `param_formato` pela allowlist; meses em ±120, dias em ±3660; valor fixo por tipo
    (Integer `^-?\d+$`, Float `^-?\d+(\.\d+)?$`, Date `^\d{4}-\d{2}-\d{2}$`, Time
    `^\d{2}:\d{2}:\d{2}$`, Timestamp `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$`,
    Pathname `^/[^\s'"]+$`, String/List sem quebra de linha).
  - `POST /pipelines/jobs/params/preview`: valida cada item com o mesmo helper e
    devolve `valor` + `descricao` para a referência informada; 422 por item com
    a mensagem que a tela mostra.
  - Encrypted: valor `***` no payload = "manter o token gravado"; qualquer outro
    valor é cifrado com `encrypt_password`. GET devolve `param_value: "***"` e
    `tem_valor: true|false`. Nunca em log.
  - Register (`:1857`) e fluxo (`:2491`) usam o helper; a regra "só toca em params
    se a chave veio no payload" passa a valer também no register.
  - Storedproc: byte a byte o mesmo comportamento (teste de regressão).
- Critérios de aceite:
  - Dado um job `datastage`, quando o POST traz `params` válidos, então as linhas
    ficam em `etl_pipeline_job_param` com origem/formato/offset e o GET as devolve.
  - Dado `param_type='Encrypted'`, então o banco guarda token Fernet, o GET devolve
    `***` e um novo POST com `***` preserva o token.
  - Dado nome `pset.param` com caixa diferente de outro, então NÃO é duplicata
    (caixa exata).
  - Dado preview com referência 2026-09-09 e `pDataIni` (−1 mês, inicio_mes) e
    `pDataFim` (−1 mês, fim_mes), então devolve 2026-08-01 e 2026-08-31 com as
    descrições; dado referência 2026-03-31 e −1 mês sem âncora, então 2026-02-28.
  - Dado âncora sem origem de data, então 422 com mensagem.
  - Dado job `storedproc` com params, quando salvo pelo caminho de hoje, então
    nada muda na tabela nem na resposta.
  - Dado payload sem a chave `params`, então os parâmetros existentes permanecem.
- Validação: pytest com baseline HEAD (zero falhas novas) — `tests/test_jobs_params_datastage.py`
  novo; `tsc -b` + eslint + build sem mudança (front intocado).
- Revisão adversarial multi-agente antes da PR. PR: `feat(etapas): parâmetros DataStage no modelo e na API`.

### F2 — Runtime: o `-param` chega ao DataStage
- Entregável: etapa DataStage com parâmetros cadastrados (via API) dispara com
  `-param`; sem parâmetros, comando idêntico ao atual.
- Inclui:
  - `dags/utils/ds_params.py` puro: `carregar(hook, pipeline, job, run_id)`,
    `mesclar(...)`, `resolver(...)`, `calcular_data(...)`, `formatar(...)`,
    `descrever(...)` — cópia das funções puras de `api/services/job_params.py`.
  - `tests/test_job_params_antidrift.py`: importa as duas implementações e confere
    valor **e descrição** iguais na tabela de casos do §4 mais as bordas.
  - `DataStageOperator._trigger_run`: resolução → `_lparams()` (só com candidato)
    → validação → N `-param` com `shlex.quote` → disparo; log
    `[DS] parâmetros: pDataIni=2026-08-01 (etapa · referência 2026-09-09 → −1 mês →
    início do mês) · pSenha=*** (etapa · fixo) · ignorados do pipeline: pX`.
  - Após o `_persist` QUEUED: `UPDATE etl_ds_job_log SET params_json=%s …` com a
    mesma lista (Encrypted como `***`), best-effort com warning.
  - Leitura do ODATE em `etl_pipeline_execucao` por `(pipeline_name, execution_id=run_id)`
    com `%s`; falha alta quando ausente e sem `conf['data_referencia']`.
  - Decifra Encrypted com a mesma rotina de `conn_resolver.py:74-80` (extrair para
    função reutilizável no mesmo módulo).
  - `_descreve_param` atualizado (cita os enviados, Encrypted como `***`).
    Categoria nova em `_classifica_erro_dsjob` para "parâmetro inválido" foi
    descartada na execução da F2: o `-lparams` antes do `-run` já transforma o
    caso em falha explícita, e a regra do módulo é "só entra categoria com
    marcador textual confirmado em incidente".
  - Fábrica: `pipeline_name=PIPELINE_NAME` no bloco datastage (`etl_dag_factory.py:298`).
  - Sem parâmetro no banco: nenhuma chamada `-lparams`, nenhuma leitura extra além
    da consulta às duas tabelas.
- Critérios de aceite (testes com Airflow stubado, padrão de `tests/test_ds_operator.py`):
  - Dado zero parâmetros, então o comando é exatamente
    `…/dsjob -run -mode NORMAL [-queue Q] 'proj' 'job'` e `-lparams` não é chamado.
  - Dado `pData` origem `data_referencia`, formato `%Y%m%d`, dias −1 e ODATE
    2026-09-09, então o comando traz `-param 'pData=20260908'`.
  - Dado `pDataIni` (−1 mês, inicio_mes) e `pDataFim` (−1 mês, fim_mes) com ODATE
    2026-09-09, então o comando traz `-param 'pDataIni=2026-08-01' -param
    'pDataFim=2026-08-31'` e o log traz as duas descrições; `params_json` gravado
    tem os dois itens com `fonte='etapa'`.
  - Dado ODATE 2026-03-31 e `pDataFim` (−1 mês, fim_mes), então 2026-02-28.
  - Dado `pSenha` Encrypted, então o comando contém o valor decifrado, o log contém
    `pSenha=***` e nenhuma linha de log contém o valor.
  - Dado parâmetro da etapa ausente no `-lparams`, então a etapa falha ANTES do
    `-run` e a mensagem lista os parâmetros que o job declara.
  - Dado ODATE ausente na tabela e no conf, então falha com "data de referência
    indisponível", sem disparo.
  - Dado valor com espaço ou aspa, então o par vai quotado por `shlex` e o dsjob
    recebe o valor íntegro (teste do comando montado).
  - Dado DAG gerada, então contém `pipeline_name=PIPELINE_NAME` no operador,
    uma linha por bloco DataStage e nenhum parâmetro no fonte
    (`tests/test_dag_factory_datastage.py` por AST; a âncora
    `tests/test_dag_factory_espera.py` declara esse delta). `test_dag_compile.py`
    não cobre o gerado neste repo — `dags/generated/` não é versionado.
- Validação: pytest baseline; nada de front. **Release note: `dags/utils/` mudou →
  restart do worker** (gotcha `orquestra-worker-cacheia-dags-utils`).
- Revisão adversarial multi-agente antes da PR. PR: `feat(datastage): -param resolvido em runtime no DataStageOperator`.

### F3 — Tela da etapa (Etapas e Fluxos)
- Entregável: o editor de parâmetros aparece para etapas DataStage nas duas telas,
  com tipo DataStage, origem, formato/offset e Encrypted.
- Inclui:
  - `JobTypeFields.tsx`: `DS_PARAM_TYPES`, `DS_PARAM_SOURCES`, `JobParam` estendido,
    `JobParamsEditor` com `modo`; colunas em modo DataStage: Nome | Tipo | Origem |
    Valor (para origem de data: Formato + Offset no lugar do valor; para Encrypted:
    `type="password"` com placeholder "mantido" quando `tem_valor`). Hint: "Se o
    job não declarar o parâmetro, a etapa falha antes do disparo. Nome de Parameter
    Set: `PSet.Param`." O campo Encrypted explica que `***` significa "manter o
    valor gravado" (é o sentinela da API — achado 4 da revisão da F1): para trocar
    a senha, digite o valor novo; deixar vazio com valor gravado também mantém.
  - `jobTypeFieldsErrors` no modo DataStage (regex escritas como literal `/…/`,
    nunca string com `\\d` — gotcha `gotcha-regex-escape-duplo`).
  - `Jobs.tsx:278`: envia `params` para datastage; hidratação dos campos novos.
  - `FluxoEditor.tsx:201` / `PainelEtapa.tsx`: campos novos hidratados e enviados
    pela mesma conversão da lib. (A "badge de contagem no nó" prometida no
    rascunho foi descartada na execução: `EtapaNode.tsx` não tem badge de
    parâmetros para tipo nenhum — o storedproc nunca teve — e o painel já mostra a
    contagem na seção.)
  - Coluna "Prévia" por linha, vinda de `POST /pipelines/jobs/params/preview` com
    debounce, e o campo "Simular com a referência" no cabeçalho da seção (padrão:
    hoje). A prévia mostra valor e descrição ("−1 mês → fim do mês"). Nenhum
    cálculo de data em TypeScript.
  - `ExecucaoDetailModal.tsx`: bloco "Parâmetros enviados" (oculto quando
    `params_json` é nulo — execuções anteriores a esta spec), com nome, valor, fonte
    e descrição.
  - Tokens `canvas/panel/edge/ink` (claro + escuro); densidade `compact` no painel
    do Fluxo; sem `overflow-hidden` novo em ancestral de `sticky`; comentário CSS
    sem `*/` interno.
- Critérios de aceite:
  - Dado etapa DataStage na tela Etapas, quando adiciono `pData` origem Data de
    referência, formato `%Y%m%d`, offset −1 e salvo, então o GET devolve a linha e
    reabrir a etapa mostra os mesmos campos.
  - Dado o mesmo job aberto no painel do Fluxo, então mostra os mesmos parâmetros e
    salvar pelo canvas não os apaga.
  - Dado Encrypted salvo, então reabrir mostra campo vazio com "mantido" e salvar
    sem tocar preserva o token (`***` no payload).
  - Dado tipo Integer e valor `abc`, então a validação bloqueia com mensagem.
  - Dado `pDataFim` (−1 mês, fim_mes) e "Simular com" 2026-03-15, então a prévia
    mostra 2026-02-28 e a descrição; trocar para 2024-03-15 mostra 2024-02-29.
  - Dado execução que rodou com parâmetros, então o modal de detalhe mostra
    "Parâmetros enviados" com os valores do log; execução antiga não mostra o bloco.
  - Dado storedproc, então o editor continua idêntico (tipos SQL, sem coluna Origem).
- Validação: `tsc -b` (não `--noEmit`, gotcha `gotcha-tsc-noemit-nao-checa`) + eslint
  baseline + `npm run build` + `dist/` commitada + pytest inalterado.
- Revisão adversarial multi-agente antes da PR (UI: CSS/estado/contrato). PR: `feat(etapas): editor de parâmetros DataStage nas telas Etapas e Fluxos`.

### F4 — Parâmetros do pipeline (defaults) + merge
- Entregável: defaults cadastrados no pipeline chegam a toda etapa DataStage que
  declara o parâmetro; a etapa sobrepõe.
- Inclui:
  - Migration 108.
  - `pipelines.py`: `POST /pipelines/register` com `parametros` (presença da chave;
    mesmo helper de validação da F1); GET de hidratação devolve `parametros` com
    Encrypted mascarado; `sp_etl_pipeline_delete` não precisa mudar (cascade).
  - `PipelineFormModal.tsx` passo 2: seção "Parâmetros DataStage do pipeline" com
    `JobParamsEditor` modo DataStage; passo 3 mostra "N parâmetros"; texto: "Valem
    para toda etapa DataStage que declarar o parâmetro; a etapa pode sobrepor."
  - `ds_params.mesclar`: pipeline (filtrado pelo `-lparams`) < etapa; log dos
    ignorados; `_descreve_param` mostra a fonte de cada nome.
  - Painel da etapa (F3) ganha a linha informativa "herdado do pipeline: pData,
    pAmbiente" (somente leitura, vinda do GET da etapa com `herdados`).
- Critérios de aceite:
  - Dado pipeline com `pAmbiente=PRD` e dois jobs, um que declara e outro não,
    então o primeiro recebe `-param 'pAmbiente=PRD'` e o segundo dispara sem ele,
    com o nome listado como ignorado no log.
  - Dado a etapa com `pAmbiente=HML`, então vence a etapa.
  - Dado pipeline sem parâmetros e etapa sem parâmetros, então `-lparams` não é
    chamado.
  - Dado remoção do pipeline, então `etl_pipeline_param` some por cascade.
- Validação: pytest (`tests/test_pipelines_params.py`, `tests/test_ds_params_merge.py`)
  + `tsc -b` + eslint + build + `dist/`. Release note: restart do worker.
- Revisão adversarial multi-agente antes da PR. PR: `feat(pipelines): parâmetros DataStage no nível do pipeline com sobreposição por etapa`.

### F5 — Sobreposição na reexecução
- Entregável: o modal de rerun mostra o valor efetivo de cada parâmetro das etapas
  que serão reexecutadas e permite trocar só naquela corrida.
- Inclui:
  - Migration 109.
  - `GET /pipelines/{p}/rerun/previa`: `parametros: [{job_name, task_id, itens:
    [{param_name, param_type, param_source, fonte: 'etapa'|'pipeline', valor_efetivo,
    descricao, editavel}]}]`, calculado por `api/services/job_params.py` com o ODATE
    de `_resolve_alvo_rerun`; Encrypted → `***`, `editavel: false`.
  - `POST /execucoes/rerun`: `parametros: [{job_name, param_name, param_value}]`
    validado pelo tipo da linha original; grava em `etl_job_param_override` com
    `criado_por = matricula` **antes** do clear; se o clear falhar (502), apaga o que
    gravou; auditoria no mesmo `etl_pipeline_audit` do rerun (`:1422-1428`).
  - Operador: passo 3 da resolução + `UPDATE … SET consumido_em=GETDATE()` após o
    disparo aceito; retry do Airflow no mesmo run reusa a sobreposição.
    ⚠️ `ds_params.mesclar` (F2) mantém o `param_type` da linha original no
    override: com Encrypted, `resolver` tentaria decifrar o texto do override e
    falharia com "ilegível" (mensagem enganosa). A F5 tem de RECUSAR override de
    Encrypted em `mesclar` (ParamError claro) e na API (422), não só no modal.
  - `ModalRerunEtapa.tsx`: seção "Parâmetros desta reexecução" (oculta quando
    vazia), sem opção pré-marcada além do valor atual; envia só o que mudou; erro
    do servidor com `detail` objeto tratado como o modal já faz (`:567`).
- Critérios de aceite:
  - Dado rerun de `Job_A` com `pData` trocado para `20260901`, então a corrida
    reexecutada dispara com esse valor, `consumido_em` fica preenchido e a corrida
    agendada seguinte volta ao valor dinâmico.
  - Dado clear recusado (DAG pausada, 409), então nenhuma linha fica em
    `etl_job_param_override`.
  - Dado parâmetro Encrypted, então a prévia mostra `***` e o modal não oferece
    edição.
  - Dado valor `abc` para tipo Integer, então 422 antes de qualquer clear.
  - Dado rerun sem tocar em parâmetro, então o corpo não leva `parametros` e o
    comportamento é o de hoje.
- Validação: pytest (`tests/test_execucoes_rerun_params.py`; anti-drift da F2 segue
  verde) + `tsc -b` + eslint + build + `dist/`. Release note: restart do worker.
- Revisão adversarial multi-agente antes da PR. PR: `feat(execucoes): sobreposição de parâmetros DataStage na reexecução de etapa`.

### F6 — Pré-preenchimento pelo ISX, documentação e smoke
- Entregável: botão "Importar do DataStage" no editor; manual e release note; smoke
  §7 executado no DEV.
- Inclui:
  - `JobTypeFields.tsx` modo DataStage: botão que chama `GET /lineage/isx/job`
    (`api/routers/lineage_isx.py:225`) e adiciona **só os nomes ausentes** com nome,
    tipo (mapa `extendedType`/`typeCode` → tipo DataStage; `Stringlist` → List;
    desconhecido → String), default como valor fixo — Encrypted vem sem valor e o
    default `***` (mascarado pelo parser por nome/tipo sensível) vira valor vazio
    **mantendo o tipo** do ISX; um `Parameterset` é só avisado (cadastre
    `PSet.Param`); nome fora da régua (`$APT_…`) é ignorado com aviso; extração
    com `status='erro'` → aviso para reextrair, sem importar. Sem ISX extraído
    (404) → toast orientando a aba Governança › Job DataStage (§3.9 do manual).
  - `docs/MANUAL_USUARIO.md`: §3.2 (Etapas) e §3.1 (wizard) ganham os parâmetros;
    §2 (rerun) ganha a sobreposição; tabela de erros com "parâmetro não declarado".
  - `docs/ORQUESTRA_Funcionalidades_e_Beneficios.md:91`: a frase "parâmetros" passa
    a ser verdadeira para DataStage.
  - `docs/release-notes/parametros-datastage.md`: migrations 107–109 (6c → **s**),
    restart do worker, `ORQUESTRA_CONN_KEY` obrigatória no worker, nginx → **n**.
  - `/simplify` nas fases de UI; `_CATALOG.md`/`CHANGELOG.md`.
- Critérios de aceite:
  - Dado job com ISX extraído e 3 parâmetros declarados, quando clico Importar,
    então as 3 linhas aparecem com tipo e default e nada é salvo até eu salvar.
  - Dado job sem ISX, então o botão informa e não altera a lista.
  - Dado smoke §7 no DEV, então todos os itens com resultado esperado.
- Validação: `tsc -b` + eslint + build + `dist/` + pytest baseline.
- Revisão adversarial multi-agente antes da PR. PR: `feat(etapas): importar parâmetros do job a partir do lineage ISX + docs`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Valor Encrypted aparece na linha de comando do `dsjob` (visível em `ps` no servidor do DataStage por ~1 s) e poderia vazar no log do Airflow | Segredo exposto | Nunca logar o comando com valor real (hoje `:378-379` loga `cmd` em erro/verbose → passa a logar a versão mascarada); o DataStage mascara Encrypted no próprio log; `-paramfile` fica como hardening (§8) |
| 2 | Janela entre F1/F2 (backend) e F3 (front): a `dist/` antiga envia `params: []` para etapas datastage (`Jobs.tsx:278`), o que apaga parâmetros criados por API; e o Fluxo (`FluxoEditor.tsx:1712`) reenvia os parâmetros SEM `param_source` — como a origem é obrigatória (achado 1 da revisão da F1), o save do canvas inteiro leva 422 enquanto houver parâmetro DataStage no pipeline | Parâmetro some ao salvar a etapa; canvas não salva | Não cadastrar parâmetro DataStage em produção antes da F3 estar no ar; release note diz isso; deploy F1–F3 preferencialmente no mesmo dia. A alternativa (default `fixo`) rebaixaria um parâmetro de data em silêncio — recusada |
| 3 | Banco indisponível na hora do disparo | Etapa falha em vez de rodar "sem parâmetro" | Decisão explícita: falha alta com mensagem; mesma dependência que `check_agenda` já tem; nunca dispara com default em silêncio |
| 4 | ODATE ausente (pipeline gerado antes da 067, linha não nasceu, `conf` sem data) | Data errada no job | Sem fallback para "hoje": falha com "data de referência indisponível" e orientação de regenerar a DAG |
| 5 | `-lparams` extra por disparo; falha do `-lparams` (rc≠0) | +1–2 s por etapa; falha nova | Só com candidato a parâmetro; zero parâmetros = comando de hoje; falha do `-lparams` tratada pela mesma rotina de diagnóstico do disparo |
| 6 | Default de pipeline "some" num job que não o declara e ninguém percebe | Job roda com valor de design | Log lista aplicados/ignorados por nome; painel da etapa mostra "herdado do pipeline"; prévia do rerun mostra a `fonte` |
| 7 | Worker do Airflow cacheia `dags/utils/` | Task verde com código antigo, sem `-param` | Release note de F2/F4/F5 exige restart do worker; smoke (a) confere o log "[DS] parâmetros:" |
| 8 | Placeholder errado na árvore `dags/` (`?` em vez de `%s`) | Zero leitura, task verde | Testes de `ds_params` exercitam o SQL montado; regra em `orquestra-placeholder-pyodbc-pymssql` |
| 9 | Formato de data inválido ou perigoso (`%` livre) | Valor estranho no job | Allowlist de diretivas na API; prévia pelo servidor; teste anti-drift api × dags |
| 9b | Aritmética de mês nas bordas (31 → 30/28/29, bissexto, virada de ano, semana ISO) | Data errada uma vez por mês, difícil de perceber | Tabela de bordas no anti-drift; descrição do cálculo no log e no detalhe da execução; "Simular com" na tela para conferir fim de mês antes de salvar |
| 9c | Três lugares de rastro divergirem (log × `params_json` × modal) | Operador lê um valor e o job recebeu outro | Uma única lista montada pelo operador alimenta o log e o `params_json`; o modal só exibe o JSON |
| 10 | Nome com caixa diferente do DataStage (`pdata` × `pData`) | Dsjob recusa | Comparação exata contra `-lparams` antes do disparo; mensagem lista os nomes declarados |
| 11 | `shlex.quote` transforma `~` em literal (gotcha do lineage ISX) | Pathname não expande | Pathname exige caminho absoluto (validação F1/F3) |
| 12 | `ORQUESTRA_CONN_KEY` diferente entre api e worker | Encrypted ilegível no disparo | Mensagem específica na falha (mesma de `conn_crypto.py:50`); smoke (e) |
| 13 | NVARCHAR conta UTF-16 (`gotcha-nvarchar-utf16`) em `criado_por`/nomes | Truncamento silencioso | Colunas com folga; valores de parâmetro em NVARCHAR(MAX) |

## 7. Smoke pós-deploy (ambiente real, na ordem)

> **Estado em 2026-09-10 (F6):** o DEV desta VPS não tem DataStage — só o
> `istool`/API REST de amostra — então os itens que exigem `dsjob` (a, b, c,
> c2, d, e, f, g, h, i, j) só rodam em homologação/produção. O que foi
> executado no DEV: migrations 106–109 aplicadas pelo `migrate.py` e
> reexecutadas (idempotência real), colunas/CHECKs/colação conferidos, API
> reconstruída com o código da spec e os endpoints exercitados (prévia do
> cálculo, parâmetros da etapa e do pipeline, GET mascarado). O item (k) foi
> exercitado só nas metades "sem ISX → orientação", "extração falhou →
> aviso" e "conjunto / nome fora da régua → aviso": o único ISX `ok` do DEV é
> a amostra sintética (declara um Parameter Set e um `$APT_…`), então a
> inserção de linhas com tipo/default reais depende de um `.isx` de
> produção. Achado lateral, pré-existente e fora desta spec:
> `GET /pipelines/jobs/{p}/{j}` responde 500 no DEV porque o banco de lá não
> tem `etl_pipeline_job.active` (o SELECT vem da main; produção tem a coluna)
> — o modal de Etapas de uma etapa existente não carrega no DEV. O item (l)
> vale para o deploy de produção.
a) Etapa DataStage **sem** parâmetro, `verbose_log` ligado: rodar e conferir no log da task a linha `[DS] comando:` idêntica à de antes (sem `-param`, sem `-lparams` no log).
b) Cadastrar em uma etapa `pTeste` String fixo `orquestra` (job que declara `pTeste`): rodar; log mostra `[DS] parâmetros: pTeste=orquestra`; `dsjob -logsum` no Console DataStage mostra `pTeste = orquestra` na entrada "Starting Job".
c) Trocar `pTeste` para origem Data de referência, formato `%Y%m%d`, offset −1: rodar; valor no log = ODATE da corrida − 1 dia (conferir com a coluna `data_referencia` de `etl_pipeline_execucao` do run).
c2) Caso mensal: `pDataIni` (referência −1 mês, início do mês) e `pDataFim` (referência −1 mês, fim do mês) num job que declara os dois: na tela, "Simular com" 2026-03-15 mostra 2026-02-01 e 2026-02-28; rodar; o log da task mostra as duas linhas com descrição; `SELECT params_json FROM etl_ds_job_log` do run tem os dois itens; o modal de detalhe da execução mostra "Parâmetros enviados" com os mesmos valores; `dsjob -logsum` mostra os dois valores na entrada "Starting Job".
d) Cadastrar `pNaoExiste`: rodar; a etapa falha **antes** do disparo com a mensagem listando os parâmetros declarados; `dsjob -jobinfo` confirma que o job não rodou.
e) Cadastrar `pSenha` Encrypted: rodar; log mostra `pSenha=***`; nenhuma ocorrência do valor no log da task; DS log mostra asteriscos.
f) Pipeline com `pAmbiente=PRD` e dois jobs (um declara, outro não): rodar; o primeiro recebe o valor, o segundo tem `pAmbiente` em "ignorados" no log.
g) Etapa sobrepõe `pAmbiente=HML`: rodar; vence HML.
h) Rerun da etapa (c) trocando o valor para `20260901`: a corrida reexecutada usa o valor; `SELECT consumido_em FROM etl_job_param_override` preenchido; a corrida agendada seguinte volta ao dinâmico.
i) Rerun com DAG pausada: 409 e nenhuma linha em `etl_job_param_override`.
j) Etapa storedproc existente com parâmetros: salvar e rodar; comportamento inalterado.
k) Importar do DataStage numa etapa com ISX extraído: linhas aparecem com tipo e default; sem ISX, toast orientando.
l) Conferir que o worker foi reiniciado após o deploy de `dags/utils/` (`docker service ps` ou data do processo) e que `ORQUESTRA_CONN_KEY` existe no container do worker.

## 8. Pendências e decisões em aberto
- **Aprovação das quatro decisões** e da escolha "leitura em runtime" (§3). Se o
  usuário preferir parâmetro embutido na DAG como o storedproc, F2 muda: a fábrica
  emite a lista e o save da etapa precisa acender `dag_config_pendente_em`.
- Números das migrations (107–109) — confirmar na abertura de cada fase.
- Nome exato da rota GET que hidrata o `PipelineFormModal` (F4 confirma).
- `-paramfile` para Encrypted: entra como spec de hardening ou como F7 desta?
- Sobreposição na execução manual do pipeline inteiro: spec seguinte (reusa 109).
- Limpeza de `etl_job_param_override` em `etl_log_cleanup`: retenção de 90 dias?
- Âncoras por **dias úteis / calendário** (`ultimo_dia_util_mes`, `dia_util_anterior`)
  usando os calendários e blackouts que o Orquestra já tem: spec seguinte, entra como
  valor novo de `param_ancora` sem mudar o modelo.
- Fuso de `data_execucao`: relógio do worker (hoje America/Sao_Paulo no compose?) —
  confirmar antes da F2; a spec recomenda `data_referencia` justamente para não
  depender disso.
- Confirmar em produção que o `dsjob -lparams` do 11.7 lista membros de Parameter
  Set como `PSet.Param` (o parser do Console DataStage, `DsConsole.tsx:286`, já assume
  esse formato).
