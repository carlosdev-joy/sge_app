# Ambiente de desenvolvimento — Airflow + SQL Server (VPS)

Montado em 2026-08-02 como pré-condição da retomada da spec de dependências
(`docs/spec-dependencias-pipelines.md`): os cenários de execução precisam ser
**executados**, não deduzidos. Fica na mesma VPS dos demais produtos — portas
escolhidas para não colidir com o Swarm de produção.

## Endereços

| Serviço | Endereço | Observação |
|---|---|---|
| UI (nginx) | `:8090` | ⚠️ o compose base usa `UI_PORT_VIP` (default 8090) — o `UI_PORT=8081` do example é ignorado |
| Airflow webserver | `:8082` | login no `.env.dev` (`DEV_AIRFLOW_*`) |
| API FastAPI | `:8000` | `/docs` para o Swagger |
| SQL Server 2019 | `127.0.0.1:1433` | **loopback de propósito**: Docker publica portas por FORA do UFW; um `sa` exposto na internet não acontece. Acesso externo: túnel SSH |

Credenciais: geradas no `.env.dev` (gitignored, `chmod 600`). Banco:
`orquestra_dev`, usuário `sa`.

## Subir / derrubar

```bash
cd /opt/orquestra-dev
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --env-file .env.dev up -d
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --env-file .env.dev down   # volumes preservados
```

⚠️ Nesta VPS, **nunca** derrubar por `pkill`/nome de processo — processos de
containers de produção aparecem no host (incidente registrado na memória do
ambiente). Sempre pelo compose ou por ID de container.

## Bootstrap do banco (sequência REAL executada na montagem — banco virgem)

⚠️ Esta sequência é para a **criação** do banco. Repeti-la sobre um banco
populado é destrutivo: o `schema_prod_dev.sql` dá DROP+CREATE nas tabelas de
dados.

1. `CREATE DATABASE orquestra_dev` (sqlcmd no container `orquestra-sqlserver-dev`).
2. **`deploy_full.sql` em DUAS passadas** com o runner pyodbc (batch a batch,
   split por `GO`, continua-em-erro): as SPs da Seção 2 referenciam colunas que
   as Seções 3 e 5 (migrações 002–008) criam — em banco virgem a 1ª passada
   falha nesses batches e a 2ª os fecha. ⚠️ Não usar `sqlcmd` (tools18) para o
   deploy_full: aborta com "Invalid cursor state".
3. **`sql/migrate.py`** (1ª rodada) — aplica 002–011 e **PARA na 012 com
   "Invalid column name 'updated_at'"**. Esperado: o deploy_full está defasado
   do schema real (falta `updated_at` em `etl_pipeline_job`, entre outros); as
   migrations até a 011 ficam registradas em `etl_schema_version`.
4. **`DROP TABLE dbo.etl_ds_job_log`** e depois **`schema_prod_dev.sql`**
   (schema EXATO de produção para as tabelas de dados). O drop manual é
   necessário porque a migration 010 (rodada no passo 3) cria
   `etl_ds_job_log` como TABELA **sem guarda de idempotência**, e o bloco de
   limpeza do `schema_prod_dev.sql` tenta `DROP VIEW` sem checar o tipo do
   objeto. (Papel real dos objetos: `etl_ds_job_log` é a **tabela** — nome real
   de produção; `etl_datastage_job_log` é a **view-alias** criada pelo script.)
5. **`sql/migrate.py`** (2ª rodada) — segue da 012 até a 069 (as registradas na
   1ª rodada são puladas). Resultado na montagem: **002–069 todas OK**.

O runner usado (executa dentro do container `orquestra-api`, que tem pyodbc +
ODBC Driver 18):

```bash
docker cp sql orquestra-api:/tmp/sql
docker cp <runner>.py orquestra-api:/tmp/run_sql.py
docker exec -e SA_PW="<senha>" -e SQL_FILE=/tmp/sql/<arquivo>.sql orquestra-api python /tmp/run_sql.py
docker exec orquestra-api python /tmp/sql/migrate.py --conn "DRIVER={ODBC Driver 18 for SQL Server};SERVER=sqlserver-dev,1433;DATABASE=orquestra_dev;UID=sa;PWD=<senha>;TrustServerCertificate=yes;"
```

## O que o `.env.dev.example` não cobria (corrigido no example)

A API lê `MSSQL_CONN_STR` **pronto** (não monta a partir de `MSSQL_SERVER/USER/...`)
e as credenciais do Airflow nos nomes `AIRFLOW_WWW_USER_USERNAME/PASSWORD`
(não `DEV_AIRFLOW_*` — estes valem para o INIT do Airflow). Também são
necessários `ORQUESTRA_CONN_KEY` (Fernet — mesma chave nos containers do
Airflow e da API) e `AIRFLOW_UI_URL` (IP público, para os botões "Ver no
Airflow").

## Pendências conhecidas do ambiente

- Corrigir a ordem do `deploy_full.sql` (SPs antes das colunas) e o tipo do
  `etl_ds_job_log` — registradas no §10 da spec de dependências.
- Confirmar no dev o FIO SOLTO da `sp_etl_pipelines_pendentes_criar` (não
  devolve `depends_on` na versão do repo) — §10 da spec.
- O banco está sem dados de negócio; para cenários com pipelines reais, usar
  `scripts/carregar-dados-dev.sh` com um dump de produção, ou criar pipelines
  de teste pela própria UI.

## Servidor de arquivos de amostra (`sshd-amostra`) — tela Utilitários

A VPS não tem servidor DataStage, e a tela Utilitários (spec
`docs/spec-utilitarios-arquivos.md`) lê arquivos dele por SFTP. O serviço
`sshd-amostra` do `docker-compose.dev.yaml` (`linuxserver/openssh-server`, porta
2222, só na rede do compose) faz esse papel. A API chega nele pelas **mesmas
variáveis do Console DataStage** — no `.env.dev`, `DS_SSH_HOST=sshd-amostra`,
`DS_SSH_PORT=2222` e `DS_SSH_USER/PASSWORD` iguais a `DEV_SSHD_USER/PASSWORD`
(ver `.env.dev.example`). O Console DataStage continua degradado no DEV: lá não
existe `dsjob`, e isso é esperado.

A árvore de amostra é gerada no arranque do container por
`dev/sshd-amostra/10-amostra.sh` (nada vai para o git): duas raízes para
cadastrar no Admin — `/dados/bi` e `/dados/param` — com texto UTF-8, texto
Latin-1 (`parametros_latin1.param`), log de ~5 MB acima do teto
(`logs/grande.log`), binário (`imagem.bin`), oculto (`.oculto.txt`), symlink para
fora da raiz (`link_fora → /fora`), pasta ilegível (`param/sem_acesso`) e um
arquivo fora de qualquer raiz (`/fora/segredo.txt`).

```bash
# subir só ele (primeira vez cria; depois stop/start preserva a árvore)
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --env-file .env.dev up -d sshd-amostra
# recriar a API para ela enxergar as DS_SSH_* novas do .env.dev
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --env-file .env.dev up -d --no-deps orquestra-api
# conferir a árvore
docker exec orquestra-dev-sshd-amostra ls -la /dados/bi /dados/param
# smoke da tela Utilitários (spec §7) pela API, comparando com o servidor
bash scripts/smoke_utilitarios.sh
```

`DEV_SSHD_PASTA_EXTRA=/caminho/na/vps` no `.env.dev` monta uma pasta real da VPS
dentro do `sshd-amostra` (**somente leitura**) para testar com arquivos de
verdade — cadastre-a como raiz no Admin. Gravar nela responde "o sistema de
arquivos está montado somente leitura", que é o esperado.

## Nota de operação (075+): DML manual em etl_pipeline_dependencia

Após a migration 075 (índice filtrado `ix_dep_origem_no`), qualquer
INSERT/UPDATE/DELETE **manual** nessa tabela via `sqlcmd` exige a flag `-I`
(QUOTED_IDENTIFIER ON) — sem ela, erro 1934. App e migrations não são
afetados (pyodbc/pymssql já setam a opção).

## Testes AO VIVO contra o SQL Server (F6+ da corrida de malha)

Parte da suíte só prova o que promete se conversar com o banco de verdade —
`tests/test_dependencias_f6_vivo.py` (16 testes) pergunta ao SQL Server se o
predicado de liberação resolve o degrau certo, com o SQL que a DAG manda em
produção. Sem a variável de ambiente eles **pulam em silêncio**, e a suíte fica
verde sem ter provado nada:

```bash
# do /opt/orquestra-dev, com o ambiente dev de pé
ORQ_TEST_MSSQL_PASSWORD='<senha do sa do dev>' python3 -m pytest tests/ -q
```

Sem a variável: `2622 passed, 17 skipped`.
Com a variável: `2638 passed, 1 skipped` — os 16 que importam.

⚠️ **Rode COM a variável antes de ligar `malha_corrida_ativa`** (§11.2 da
`spec-malha-execucao.md`). São os únicos testes que provam que o corte do modo
SEQUÊNCIA sai do `aberta_em` da corrida, e não da janela de 12h — e é
exatamente essa troca que o incidente `Carga_Vida` produziu. A senha nunca
entra no repositório; ela vem de `.env.dev` (`DEV_MSSQL_SA_PASSWORD`), que é
ignorado pelo git.

Os outros 17 pulados sem a variável são: os 16 acima + 1 de compilação de DAG
que já pulava antes.
