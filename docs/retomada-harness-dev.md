# Runbook — Harness de execução real no ambiente dev (retomada F2–F6 das dependências)

> **Status: VALIDADO fim a fim em 2026-08-02.** Todos os comandos deste runbook foram
> executados de verdade no dev desta VPS: geração pela factory, run de SUCESSO,
> run de FALHA determinística e a limpeza completa. A validação encontrou 2 defeitos
> reais no caminho (ver §11) — prova de que o princípio da retomada está certo:
> **comportamento distribuído só se verifica executando.**
>
> Complementa `docs/ambiente-dev.md` (subir/derrubar, bootstrap do banco).

## 1. Pré-requisitos

Ambiente dev no ar (`docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --env-file .env.dev up -d`):

| Container | Papel |
|---|---|
| `orquestra-dev-airflow-webserver-1` | Airflow 2.11.2, REST em `:8082` (`/api/v1`, basic auth) |
| `orquestra-dev-airflow-scheduler-1` / `-worker-1` | scheduler + Celery worker |
| `orquestra-sqlserver-dev` | SQL Server 2019, banco `orquestra_dev` (loopback `:1433`) |
| `orquestra-api` | FastAPI `:8000` |

Variáveis de sessão (credenciais SEMPRE do `.env.dev`, nunca hardcoded):

```bash
cd /opt/orquestra-dev
set -a; source .env.dev; set +a
AUTH="$DEV_AIRFLOW_USER:$DEV_AIRFLOW_PASSWORD"
BASE="http://localhost:8082/api/v1"
SQLCMD='docker exec orquestra-sqlserver-dev /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -d orquestra_dev'
# uso: $SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "..." -b
```

Fatos do ambiente que o harness usa (todos verificados):
- `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION='true'` (compose base) — **toda DAG nova nasce PAUSADA**.
- `AIRFLOW__API__AUTH_BACKENDS` inclui `basic_auth` — REST funciona com o usuário admin do dev.
- `AIRFLOW_CONN_SQL14_DMDB41` (compose dev) aponta para `sqlserver-dev/orquestra_dev` — `MsSqlHook`
  e `utils.conn_resolver.abrir_conexao_mssql` (pymssql) funcionam no worker sem nenhum ajuste.
- `dags/` é o **repo git montado** em `/opt/airflow/dags` (rw nos containers do Airflow, ro na API);
  `logs/` é montado em `./logs` (gitignored).

## 2. O que executa DE VERDADE no worker do dev (sem DataStage e sem SSH)

Leitura de `dags/etl_dag_factory.py` + `dags/utils/job_operators.py`:

| `job_type` | Operador emitido | Executa no dev? | Por quê |
|---|---|---|---|
| `datastage` | `DataStageOperator` (SSH + `dsjob`) | ❌ | não há engine DS nem servidor SSH |
| `shell` | `ShellOperator(SSHOperator)` — o comando roda **via SSH** no `ssh_conn_id` | ❌ | não há servidor SSH de jobs no dev |
| `python` c/ `python_json` (v2 arquivo/código) | `PythonScriptOperator(SSHOperator)` | ❌ | idem — publica e roda via SSH |
| `python` legado (sem `python_json`) | `PythonModuleOperator` — `importlib` **no worker** | ⚠️ sim | exige módulo importável em `dags/` (2ª escolha; gera arquivo extra a isolar do git) |
| **`http`** | `HttpCallOperator` — `requests` **no worker** + `raise_for_status` | ✅ | alvo interno da rede compose; sem infra externa |
| **`storedproc`** | `StoredProcOperator` — pymssql via `conn_resolver` → `orquestra_dev` | ✅ | o SQL Server dev É a infra; permite **assert de efeito colateral** (linha gravada) |
| nó `sql` / `decisao` / `aguarde` | callables no worker (pymssql / branch / EmptyOperator) | ✅ | executam no worker |
| nó `notificacao` | callable no worker | ✅ (degrada) | sem `Variable TEAMS_WEBHOOK_URL_CVP` só imprime no log — não falha |

**Alvos HTTP verificados de dentro do worker:** `http://airflow-webserver:8080/health` → 200;
`http://orquestra-api:8000/docs` → 200; qualquer caminho inexistente → 404 (falha determinística).

⚠️ **Restrição descoberta na validação (bug latente de produção, §11-b):** job `storedproc`
com **parâmetros fixos** (`etl_pipeline_job_param`) gera DAG que **não importa**
(`TypeError: params must be a mapping` — `params` é kwarg reservado do `BaseOperator` e a
factory emite lista). Até a correção na retomada: **procs do harness sem parâmetros fixos**
(usar defaults na própria proc).

## 3. Fixtures dev-only (uma vez por ambiente; NÃO são migrations, NÃO vão para produção)

### 3.1 Tabelas e procs do harness

```bash
cat > /tmp/harness_fixtures.sql <<'EOF'
IF OBJECT_ID('dbo.harness_marca','U') IS NULL
  CREATE TABLE dbo.harness_marca (id INT IDENTITY PRIMARY KEY, origem VARCHAR(200) NOT NULL,
                                  criado_em DATETIME2 NOT NULL DEFAULT GETDATE());
IF OBJECT_ID('dbo.harness_controle','U') IS NULL
  CREATE TABLE dbo.harness_controle (chave VARCHAR(100) PRIMARY KEY, falhar BIT NOT NULL DEFAULT 0);
GO
CREATE OR ALTER PROCEDURE dbo.sp_harness_marca @origem VARCHAR(200) = 'sem-origem'
AS BEGIN SET NOCOUNT ON;
  INSERT INTO dbo.harness_marca (origem) VALUES (@origem);
  SELECT 'marcado' AS resultado, @origem AS origem;
END
GO
CREATE OR ALTER PROCEDURE dbo.sp_harness_falha
AS BEGIN SET NOCOUNT ON;
  THROW 50001, 'falha deterministica do harness (sp_harness_falha)', 1;
END
GO
CREATE OR ALTER PROCEDURE dbo.sp_harness_flaky @chave VARCHAR(100)
AS BEGIN SET NOCOUNT ON;
  IF EXISTS (SELECT 1 FROM dbo.harness_controle WHERE chave=@chave AND falhar=1)
    THROW 50002, 'falha comandada por harness_controle (zere o flag p/ reprocessar)', 1;
  INSERT INTO dbo.harness_marca (origem) VALUES ('flaky:' + @chave);
END
GO
EOF
docker cp /tmp/harness_fixtures.sql orquestra-sqlserver-dev:/tmp/
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -i /tmp/harness_fixtures.sql -b
```

- `sp_harness_marca` → **prova de execução** (linha em `harness_marca`), sucesso sempre.
- `sp_harness_falha` → falha SEMPRE (THROW) — falha estável mesmo com retry.
- `sp_harness_flaky` → falha **enquanto** `harness_controle.falhar=1`; zere o flag e
  reprocesse (Clear) para provar o caminho de reprocessamento.

### 3.2 Patch obrigatório do `sp_etl_pipeline_upsert` (defeito do ambiente, já APLICADO em 2026-08-02)

A versão do dev (vinda do `deploy_full.sql` defasado — pendência já registrada no §10 da spec)
**não tem `@scheduled_time`** (que a factory de produção passa) e referencia colunas
inexistentes (`atualizado_em`, `criado_por`). Sem o patch, a factory grava o arquivo da DAG
mas **falha ao marcar `dag_criada=1`** (run FAILED com
`@scheduled_time is not a parameter for procedure sp_etl_pipeline_upsert`).

O patch (`CREATE OR ALTER` com `@scheduled_time VARCHAR(8) = NULL` + colunas reais
`updated_at`/`DAG_CRIADA`/...) **já está aplicado neste dev**. Se o banco for recriado do zero,
reaplicar — o SQL completo fica em nota do bootstrap; a correção DEFINITIVA é consertar o
`deploy_full.sql` (mesma pendência §10). Verificação rápida:

```bash
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "SELECT COUNT(*) FROM sys.parameters
  WHERE object_id=OBJECT_ID('dbo.sp_etl_pipeline_upsert') AND name='@scheduled_time'" -b
# esperado: 1
```

## 4. Receita dos pipelines de teste

Regras inegociáveis (todas com motivo verificado):
- **Prefixo `HARNESS_`** em tudo (pipelines, jobs referenciáveis) — a limpeza deleta SÓ por esse prefixo (lição Royal Park).
- **`schedule_type='on_demand'`** → a DAG sai com `schedule=None` ("Never, external triggers only") — sem gatilho automático NUNCA.
- **`ambiente='DEV'`** → desliga os 3 cards do Teams na geração (`f_ini/f_fim/f_err` exigem PROD).
- **`retry_delay_seconds=1`** → ⚠️ GOTCHA da factory: `int(retries_count or 1)` transforma `0` em `1` — **toda task que falha roda 2 tentativas**; com delay de 1s o cenário de falha fecha em segundos em vez de +5 min.
- `envia_msg_* = 0`, `max_active_runs=1`.

### 4.1 `HARNESS_PIPE_OK` — sucesso fim a fim (http + storedproc, encadeados por ondas)

```bash
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -b -Q "SET NOCOUNT ON;
INSERT INTO dbo.etl_pipeline
  (pipeline_name, scheduled_time, active, ENVIA_MSG_INICIO, ENVIA_MSG_FIM, ENVIA_MSG_ERRO,
   DAG_CRIADA, project_name, domain, tags, schedule_type, ambiente,
   max_active_runs, retries_count, retry_delay_seconds)
VALUES ('HARNESS_PIPE_OK','06:00:00',1,0,0,0,0,'HARNESS','DEV','harness','on_demand','DEV',1,0,1);
INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command) VALUES
  ('HARNESS_PIPE_OK','http_saude',1,'http','http://airflow-webserver:8080/health');
INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command, mssql_conn_id) VALUES
  ('HARNESS_PIPE_OK','proc_marca',2,'storedproc','dbo.sp_harness_marca','SQL14_DMDB41');"
```

### 4.2 `HARNESS_PIPE_FALHA` — falha determinística com job a jusante que NÃO deve rodar

```bash
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -b -Q "SET NOCOUNT ON;
INSERT INTO dbo.etl_pipeline
  (pipeline_name, scheduled_time, active, ENVIA_MSG_INICIO, ENVIA_MSG_FIM, ENVIA_MSG_ERRO,
   DAG_CRIADA, project_name, domain, tags, schedule_type, ambiente,
   max_active_runs, retries_count, retry_delay_seconds)
VALUES ('HARNESS_PIPE_FALHA','06:00:00',1,0,0,0,0,'HARNESS','DEV','harness','on_demand','DEV',1,0,1);
INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command) VALUES
  ('HARNESS_PIPE_FALHA','http_saude',1,'http','http://airflow-webserver:8080/health'),
  ('HARNESS_PIPE_FALHA','http_404',  2,'http','http://airflow-webserver:8080/harness-404-de-proposito');
INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command, mssql_conn_id) VALUES
  ('HARNESS_PIPE_FALHA','proc_nao_deve_rodar',3,'storedproc','dbo.sp_harness_marca','SQL14_DMDB41');"
```

### 4.3 `HARNESS_PIPE_FLAKY` — reprocessamento (falha comandada → clear → sucesso)

Mesmo molde do 4.1, com um único job
`('HARNESS_PIPE_FLAKY','proc_flaky',1,'storedproc','dbo.sp_harness_flaky','SQL14_DMDB41')` —
**sem** parâmetro fixo (§2): controlar a chave direto na proc não dá; então para este cenário
crie uma variação dev-only `sp_harness_flaky_padrao` sem parâmetro (corpo idêntico com
`@chave='padrao'` embutido) OU aguarde a correção do bug `params` na retomada.
Armar/desarmar a falha:

```bash
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "MERGE dbo.harness_controle t USING (SELECT 'padrao' c) s ON t.chave=s.c
  WHEN MATCHED THEN UPDATE SET falhar=1 WHEN NOT MATCHED THEN INSERT (chave,falhar) VALUES ('padrao',1);" -b   # armar
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "UPDATE dbo.harness_controle SET falhar=0 WHERE chave='padrao';" -b     # desarmar
```

Para dependências entre pipelines (F3+): registrar 2+ pipelines do molde 4.1 e a linha em
`dbo.etl_pipeline_dependencia` (a tabela da F1 já existe no dev, com a FK de existência).

## 5. Gerar a DAG pela factory (via REST)

A `etl_dag_factory` está **PAUSADA** no dev (correto: `schedule=None`, run só sob demanda —
mas run disparado com ela pausada fica `queued` para sempre). Fluxo:

```bash
# 1) despausar a factory (sem risco: schedule=None => nunca roda sozinha)
curl -s -u "$AUTH" -X PATCH "$BASE/dags/etl_dag_factory" -H 'Content-Type: application/json' \
  -d '{"is_paused": false}'

# 2) disparar SEMPRE com escopo de 1 pipeline — NUNCA force_all (regeneraria tudo que existir no banco)
curl -s -u "$AUTH" -X POST "$BASE/dags/etl_dag_factory/dagRuns" -H 'Content-Type: application/json' \
  -d '{"conf": {"pipeline_name": "HARNESS_PIPE_OK"}}'
# guarde o dag_run_id da resposta

# 3) poll até success/failed (URL-encode o run_id: o + vira %2B)
ENC=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1],safe=''))" "$RUN")
curl -s -u "$AUTH" "$BASE/dags/etl_dag_factory/dagRuns/$ENC" | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])"

# 4) diagnóstico da geração (o que a tela do Admin mostraria)
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -y 1500 -Q "SELECT TOP 3 estado, geradas, erros,
  CAST(detalhes_json AS VARCHAR(1500)) FROM dbo.etl_factory_log ORDER BY iniciado_em DESC;"

# 5) arquivo gerado (no HOST, porque dags/ é o repo montado)
ls -la dags/generated/HARNESS/DEV/
```

**Acelerar a descoberta da DAG nova** (senão o scan de diretório demora até 5 min):

```bash
docker exec orquestra-dev-airflow-scheduler-1 airflow dags reserialize >/dev/null 2>&1
curl -s -u "$AUTH" "$BASE/importErrors"                # tem que devolver total_entries: 0
curl -s -u "$AUTH" "$BASE/dags/HARNESS_PIPE_OK"        # is_paused: true (nasce pausada) + "Never, external triggers only"
```

Se `importErrors` acusar o arquivo gerado: o defeito é DA GERAÇÃO (foi exatamente assim que o
bug do `params` apareceu) — anexar o stack trace ao achado antes de limpar.

## 6. Executar e fazer ASSERT

```bash
# despausar e disparar
curl -s -u "$AUTH" -X PATCH "$BASE/dags/HARNESS_PIPE_OK" -H 'Content-Type: application/json' -d '{"is_paused": false}'
curl -s -u "$AUTH" -X POST "$BASE/dags/HARNESS_PIPE_OK/dagRuns" -H 'Content-Type: application/json' \
  -d '{"conf": {}, "note": "harness: cenario sucesso"}'
# poll do estado como no §5 (48x5s de teto)
```

Mapeamento run → telemetria: **`execution_id` = `ts_nodash` do run em UTC** —
`manual__2026-08-02T12:57:51.857486+00:00` → `20260802T125751` (derive do `logical_date` da
resposta REST removendo `-`/`:` e truncando nos segundos).

Asserts (todos executados na validação):

```bash
# (a) estado das tasks
curl -s -u "$AUTH" "$BASE/dags/HARNESS_PIPE_OK/dagRuns/$ENC/taskInstances?limit=100"

# (b) telemetria por job (a tabela que o painel lê)
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "SELECT execution_id, job_name, status, duration_seconds, status_code
  FROM dbo.etl_job_execution WHERE pipeline='HARNESS_PIPE_OK' ORDER BY start_time;"

# (c) prova de execução real (efeito colateral do storedproc)
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "SELECT origem, criado_em FROM dbo.harness_marca;"

# (d) logs de task — arquivo no host (logs/ é montado) ou REST
tail -50 "logs/dag_id=HARNESS_PIPE_OK/run_id=<run_id>/task_id=proc_marca/attempt=1.log"
curl -s -u "$AUTH" "$BASE/dags/HARNESS_PIPE_OK/dagRuns/$ENC/taskInstances/proc_marca/logs/1"
```

**Resultado esperado (medido):** DagRun `success`; tasks
`check_agenda → log_start_/job/log_end_ (×2) → publish_dataset` todas `success`;
2 linhas `SUCCESS` em `etl_job_execution` com o `execution_id` do run; 1 linha em `harness_marca`.

**Cenário de falha (medido):** DagRun `failed`; `http_404` `failed` com **2 tentativas** (o
gotcha do retries≥1); `proc_nao_deve_rodar` `upstream_failed` com **0 tentativas** (fail-fast
preservado — sem verde mentiroso); em `etl_job_execution`: `http_saude=SUCCESS`,
`http_404=FAILED` e **NENHUMA linha** para o job não-rodado (semântica correta: upstream_failed
≠ SKIPPED); `publish_dataset` `upstream_failed` → o Dataset **não** é publicado em run que falha.
Nuance registrada: `log_end_proc_nao_deve_rodar` FALHA com `IntegrityError 515`
(`start_time` NULL — não houve `log_start`); o efeito líquido é o desejado (sem linha, run
vermelho), mas é ruído a observar (§11-c).

**Asserts da F2 (o que este harness passa a cobrar quando a F2 existir):**

```bash
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -Q "SELECT pipeline_name, data_referencia, execution_id, status,
  inicio, fim, disparado_por FROM dbo.etl_pipeline_execucao WHERE pipeline_name LIKE 'HARNESS[_]%';"
```

Hoje (pré-F2) devolve **0 linhas** — medido; a tabela da migration 067 existe, nada a escreve.
Pós-F2: exatamente 1 linha por `execution_id`, `data_referencia` preenchida (ODATE), status final
coerente (`SUCESSO`/`FALHA`), e `conf {"data_referencia": "YYYY-MM-DD"}` no trigger prevalecendo
sobre o cálculo.

**Reprocessamento (F-flaky):** armar o flag → run falha; desarmar → Clear via REST e o rerun
tem que fechar `success` **no mesmo `execution_id`**:

```bash
curl -s -u "$AUTH" -X POST "$BASE/dags/HARNESS_PIPE_FLAKY/clearTaskInstances" \
  -H 'Content-Type: application/json' \
  -d "{\"dag_run_id\": \"$RUN\", \"only_failed\": true, \"dry_run\": false}"
```

## 7. Limpeza entre cenários (ordem exata, validada — deixa o ambiente como estava)

```bash
# 1) pausar as DAGs do harness (impede run novo durante a limpeza)
for D in HARNESS_PIPE_OK HARNESS_PIPE_FALHA HARNESS_PIPE_FLAKY; do
  curl -s -u "$AUTH" -X PATCH "$BASE/dags/$D" -H 'Content-Type: application/json' -d '{"is_paused": true}'
done

# 2) remover os ARQUIVOS primeiro (senão o DELETE REST "ressuscita" a DAG no próximo parse)
rm -rf /opt/orquestra-dev/dags/generated/HARNESS

# 3) apagar metadados + histórico de runs no Airflow (204 = ok)
for D in HARNESS_PIPE_OK HARNESS_PIPE_FALHA HARNESS_PIPE_FLAKY; do
  curl -s -o /dev/null -w "DELETE $D: %{http_code}\n" -u "$AUTH" -X DELETE "$BASE/dags/$D"
done

# 4) repausar a factory (estado padrão do dev)
curl -s -u "$AUTH" -X PATCH "$BASE/dags/etl_dag_factory" -H 'Content-Type: application/json' -d '{"is_paused": true}'

# 5) SQL — deletar SÓ pelo prefixo do harness, na ordem das FKs
$SQLCMD -P "$DEV_MSSQL_SA_PASSWORD" -b -Q "SET NOCOUNT ON;
DELETE FROM dbo.etl_job_execution        WHERE pipeline      LIKE 'HARNESS[_]%';
DELETE FROM dbo.etl_factory_log          WHERE pipeline_name LIKE 'HARNESS[_]%';
DELETE FROM dbo.etl_pipeline_job_param   WHERE pipeline_name LIKE 'HARNESS[_]%';
DELETE FROM dbo.etl_pipeline_job         WHERE pipeline_name LIKE 'HARNESS[_]%';
DELETE FROM dbo.etl_pipeline_execucao    WHERE pipeline_name LIKE 'HARNESS[_]%';
DELETE FROM dbo.etl_dependencia_evento   WHERE pipeline_name LIKE 'HARNESS[_]%';  -- eventos da guardiã (F4+)
DELETE FROM dbo.etl_pipeline_dependencia WHERE pipeline_name LIKE 'HARNESS[_]%' OR depende_de LIKE 'HARNESS[_]%';
DELETE FROM dbo.etl_pipeline             WHERE pipeline_name LIKE 'HARNESS[_]%';
DELETE FROM dbo.harness_marca; UPDATE dbo.harness_controle SET falhar=0;"
```

As fixtures do §3 (tabelas/procs `harness_*` e o patch do upsert) **ficam** — são o aparelho do
ambiente, não sujeira de cenário.

## 8. Isolamento do git (dags/ é o REPO montado nos containers)

- `dags/generated/` **não existe no `.gitignore` hoje** → **a PR da F2 deve adicionar a linha
  `dags/generated/`** (vale também para produção: a factory de prod grava aí e esses arquivos
  nunca devem ser commitados). Até lá: nunca `git add -A` / `git add dags` com harness ativo.
- Os artefatos que o harness cria no working tree: `dags/generated/HARNESS/**` (removidos no §7)
  e nada mais. `logs/` já é gitignored.
- **Não trocar de branch com DagRun em andamento**: o checkout muda o código das DAGs debaixo
  do scheduler/worker no meio do run. Sequência segura: §7 completo → conferir
  `git status --porcelain` limpo → checkout.
- Arquivos criados pelos containers saem como `root` no host (AIRFLOW_UID=0 no dev) — o `rm`
  do §7 já cobre.

## 9. Riscos do harness e salvaguardas

| Risco | Salvaguarda (verificada) |
|---|---|
| Scheduler pegar DAG de teste com schedule ativo | tripla: `DAGS_ARE_PAUSED_AT_CREATION='true'` global + `schedule_type='on_demand'` (→ `schedule=None`) + `catchup=False` emitido sempre. **Proibido** cadastrar harness com `schedule_type` diário/custom |
| `force_all` na factory | zera `dag_criada` de TODOS os pipelines e regenera tudo (com dump de prod carregado seriam dezenas de DAGs). Trigger SEMPRE com `conf {"pipeline_name": ...}` |
| Task que falha roda 2× | gotcha `retries_count 0→1` da factory; `retry_delay_seconds=1` torna isso barato; asserts contam `try_number=2` como esperado |
| Dataset publicado dispara consumidor | o `publish_dataset` só roda em run de sucesso, e no dev não há consumidores; se o cenário F3+ criar um (`trigger_por_dependencia`), esse disparo passa a ser o PRÓPRIO objeto de teste |
| Cards Teams vazando | `ambiente='DEV'` corta na geração; `Variable TEAMS_WEBHOOK_URL_CVP` não existe no dev (degrada com print). Não cadastrar webhook real em `etl_msg_grupo` no dev |
| Derrubar processo errado na VPS | **nunca `pkill` por nome** (incidente registrado) — sempre compose/ID de container |
| Placeholder SQL errado | tudo que roda em `dags/` usa `%s` (pymssql); `?` é só da API (pyodbc) |
| Pipeline órfão `DEV_FILHO` (dag_criada=0, sem etapas) | vira `aviso` em todo run escopado da factory — inofensivo, mas não confundir com erro do harness |

## 10. Custo medido (referência de planejamento)

Ciclo completo de um cenário (registrar → gerar → reserialize → despausar → rodar → asserts):
**~2 min**; cenário de falha: **~1 min de run** (com `retry_delay_seconds=1`). Limpeza: ~15 s.

## 11. Achados REAIS desta validação (entram no radar da F2)

1. **`sp_etl_pipeline_upsert` do dev estava defasado** (sem `@scheduled_time`, colunas
   fantasmas) — factory gravava o arquivo e falhava ao marcar `dag_criada=1`. Patch dev-only
   aplicado (§3.2). Causa-raiz: `deploy_full.sql` defasado — mesma pendência do §10 da spec;
   corrigir lá.
2. **BUG latente de produção na factory/StoredProcOperator:** job `storedproc` com parâmetros
   fixos emite `StoredProcOperator(params=[...])`; `params` é kwarg **reservado** do
   `BaseOperator` (exige mapping) → **a DAG gerada não importa**
   (`TypeError: params must be a mapping`). Nunca disparou em produção porque nenhum job de
   lá usa parâmetro fixo. Correção (renomear o kwarg do operador, ex.: `proc_params`, e a
   emissão na factory) deve entrar na retomada ANTES de qualquer cenário com params.
3. **Job não-executado por falha a montante:** `log_end_*` (ALL_DONE) tenta gravar FAILED sem
   `start_time` e morre com `IntegrityError 515`. Efeito líquido correto (sem linha na
   telemetria, run vermelho), mas é falha ruidosa de task de log — conferir se a
   `sp_etl_job_execution_log` de produção tolera isso ou se o comportamento é o mesmo lá.
4. `etl_pipeline_execucao`, `etl_pipeline_dependencia` e `etl_dependencia_evento` (migration
   067/F1) **existem no dev e estão vazias** — o harness já tem os asserts prontos para o dia
   em que a F2 as alimentar (§6).
