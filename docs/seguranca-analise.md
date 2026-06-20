# Análise de Segurança — ORQUESTRA (FastAPI + React + Airflow)

> Revisão **somente leitura** do código (auth, RBAC, segredos, injeção, superfície
> da API). Achados por severidade, com `arquivo:linha`, impacto e correção.
> Datado de 2026-06. **Tratar como confidencial.**

## Resumo executivo
O modelo de auth é sólido na base (tokens opacos com hash, sem armazenar senha,
SQL 100% parametrizado, RBAC na maioria dos endpoints). Os problemas concentram-se
em: **1 segredo commitado**, **2 caminhos de bypass do RBAC para o Airflow**,
**2 vetores de injeção/RCE** via configuração de job e **endpoint de escrita sem
auth**. Resolver os CRÍTICOS antes de novas evoluções.

---

## 🔴 CRÍTICO

### C1. Senha de serviço do AD (LDAP) commitada no repositório
`config/webserver_config.py:98-103` (arquivo **versionado** no git)
Bind user `CN=sisairflow0p,...,DC=adcorp,DC=intranet` + senha em texto puro, com
`AUTH_LDAP_USE_TLS = False` (bind em cleartext). Quem tiver acesso ao repo obtém
uma conta de domínio.
**Correção (urgente):** (1) **rotacionar a senha do AD agora** — considere-a
comprometida; (2) mover para env/secret store (`os.getenv`); (3) **purgar do
histórico** do git (`git filter-repo`/BFG); (4) `AUTH_LDAP_USE_TLS = True`.

### C2. Injeção de comando shell no monitor centralizado
`dags/etl_ds_monitor_centralizado.py:169` (`_exec_ssh` em `:155`)
`f"{dshome}/bin/dsjob -jobinfo {project} {jname}"` roda como `source dsenv && <cmd>`
via SSH. `project`/`jname` vêm de `etl_ds_job_log`, originados da config de job que
o usuário define em `POST /pipelines/jobs/register` — **sem validação nem quoting**.
Um `job_name` malicioso executa comando no host do DataStage.
**Correção:** validar ambos contra `^[A-Za-z0-9_.]+$` (igual `_JOB_RE`/`_SAFE_JOB_RE`)
e single-quote, antes de montar o comando. Pular/logar nome inválido.

### C3. `job_name` não validado vira código Python na DAG gerada (RCE)
`dags/etl_dag_factory.py:192-195,312,319` + falta de validação em `api/routers/jobs.py:171,181`
A factory escreve `f'    job_name="{name}",'` etc. em `.py` que o Airflow importa.
`job_name` (de `etl_pipeline_job`, via register) **não é validado** — um nome com
`"` + quebra de linha sai do literal e injeta Python (RCE no worker). O `ast.parse`
final só barra sintaxe inválida, não payload válido.
**Correção:** allowlist regex em `job_name` no register; usar `repr()`/`json.dumps()`
(não `f'"{name}"'`) para TODA string vinda do banco na factory (vale também para
`project`, `domain`, `mod` do python job, `url` do http, `safe_sql`).

### C4. `POST /catalogo` sem autenticação (mutações anônimas)
`api/routers/catalogo.py:345`
Sem `Depends`. Expõe `save_job_type`/`delete_job_type`/`save_owner`/`save_tag`
(INSERT/UPDATE/DELETE/MERGE) **sem login**, e o autor do audit vem do **body**
(`body.get("user","admin")`).
**Correção:** `_auth = Depends(require_perm(PERM_EDITAR))` e derivar o usuário do
principal autenticado, não do body.

### C5. `/auth/airflow-header` entrega o Basic do service account a qualquer logado
`api/routers/auth.py:112-119`
Devolve `Basic base64(AIRFLOW_USER:AIRFLOW_PASSWORD)` para qualquer sessão (até
`consulta`). Com o nginx repassando `Authorization` direto pro Airflow
(`config/nginx.conf:23-31`), um usuário read-only chama a REST API do Airflow com
privilégio de serviço → **bypassa todo o RBAC**.
**Correção:** remover o endpoint; manter as chamadas ao Airflow no backend (proxy
que injeta a credencial server-side e aplica permissão por operação).

### C6. Proxies GET do Airflow sem autenticação
`api/routers/airflow.py:31,47,66,128,148`
`list_task_instances`, `get_task_log`, `list_dag_runs`, `list_ssh_connections`,
`list_mssql_connections` **sem `Depends`** — usam o service account. Sem login dá
pra ler **log de qualquer task** (contém connection strings/host/SQL) e enumerar
conexões SSH/MSSQL. (Os POST/PATCH estão protegidos — o buraco é nos GET.)
**Correção:** `Depends(get_current_user)` em todos; logs com `require_perm`.

---

## 🟠 ALTO

### A1. Credenciais default no compose + Fernet key vazia
`api/deps.py:21-22`, `docker-compose.yaml:70-71,103-105,152-153`
`AIRFLOW_USER/PASSWORD` e Postgres caem em `airflow/airflow`; `FERNET_KEY` default
**vazio** → secrets de Connection/Variable do Airflow sem criptografia em repouso.
**Correção:** `${VAR:?obrigatório}` (falhar sem a env); gerar `FERNET_KEY`
(`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key())"`).

### A2. PowerBI client secret e webhooks Teams em texto puro no banco
`sql/migrations/025_powerbi_config.sql`, `etl_app_config` (VARCHAR), `api/routers/admin.py:62-66`
`config_value` em claro; `config_list` (admin) devolve o valor cru. Leak de DB/backup
expõe um secret de app do Azure AD e o webhook (permite forjar alertas).
**Correção:** criptografar config sensível em repouso (Always Encrypted/Fernet) ou
secret manager; no mínimo **mascarar** no `config_list` (`••• + 4 últimos`).
*(Obs.: o `GET /config` público JÁ mascara esses — o problema é o at-rest e o admin.)*

### A3. Outras strings de config cruas na DAG gerada (python/http/sql)
`dags/etl_dag_factory.py:215-218 (python), 288-291 (http), 276 (sql)`
`job_command` (do usuário) entra sem escape: `importlib.import_module("{mod}")`,
`requests.get("{url}")`, SQL com escape ingênuo. O tipo **shell** está correto
(`shlex.quote`, linha 202) — replicar o rigor nos demais.
**Correção:** `repr()` nas interpolações; validar `job_command` por tipo (regex de
módulo p/ python, allowlist de esquema p/ url).

### A4. Path traversal em `POST /lineage/extract-dsx`
`api/routers/lineage.py:190-211` → `dags/utils/dsx_engine.py:128`
`project_name` do body vai direto pro `os.path.join` **sem** `_safe_project_name`
(que os endpoints irmãos usam). `../../...` lê arquivos `.dsx` fora do base dir.
**Correção:** `project_name = _safe_project_name(project_name)`; idealmente checar
containment com `os.path.realpath` dentro do `DSXEngine`.

### A5. CORS com default `*` + `allow_credentials=True`
`api/main.py:123,145-151`
Default inseguro (em prod o compose restringe — ok — mas o fallback é latente).
**Correção:** remover o fallback `*`; exigir allow-list explícita (falhar sem ela).

### A6. Sem rate-limit / lockout no login
`api/routers/auth.py:26`
Brute-force/credential-stuffing livre contra o AD via a API.
**Correção:** `limit_req` no nginx para `/orquestra/auth/login` e/ou `slowapi`,
+ backoff/lockout por conta.

### A7. Sem security headers no nginx
`config/nginx.conf`
Faltam CSP, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options`,
`Referrer-Policy`, HSTS. `server_tokens` ligado.
**Correção:** adicionar os headers no `server`; HSTS quando houver TLS; `server_tokens off`.

---

## 🟡 MÉDIO

- **M1. Vazamento de exceção crua** (`detail=str(e)`/`detail=f"...{e}"`) em ~60 pontos
  (ex.: `deps.py:153`, `execucoes.py:439,...`, `airflow.py:44,...` que ainda repassa
  `r.text` do Airflow). Enumeração de schema/infra. → mensagem genérica + `log.exception`.
- **M2. Operador interpola `job_name`/`project` cru** em trigger/jobinfo/logsum
  (`datastage_operator.py:274-280,318,325,333`). Mesmo risco do C2 (defense-in-depth).
  → passar por `_SAFE_JOB_RE`.
- **M3. Token em `localStorage`** (`ui-react/src/store/auth.ts`, `lib/api.ts`) →
  exfiltrável por XSS. → cookie `HttpOnly/Secure/SameSite` ou CSP estrita + TTL menor.
- **M4. Sessão longa (12h) sem idle timeout / binding** (`deps.py:24`). → idle timeout,
  cap de TTL, "revogar sessões do usuário".
- **M5. `order_by` repassado cru ao Airflow** (`airflow.py:66`) e `dag_id` dos GET sem
  `_DAG_ID_RE`. → whitelist de campos; validar `dag_id`.
- **M6. HTTP interno / LDAP sem TLS** (`nginx.conf:17`, `webserver_config.py:99`).
  O domínio externo já tem TLS no VIP, mas o tráfego interno e o LDAP seguem em claro.
- **M7. Airflow CORS `*`** (`docker-compose.yaml:65`). → restringir à origem da UI.

## ⚪ BAIXO
- **B1. `dangerouslySetInnerHTML`** no markdown de versões (`Admin.tsx:70`,
  `lib/markdown.ts`) — hoje mitigado (escapa antes), mas frágil. → DOMPurify
  ou restringir edição de versão a admin.
- **B2. `TOP {n}` / `DATEADD(-{fhb})`** interpolados (`catalogo.py:155,...`,
  `execucoes.py:262,1073`) — **não exploráveis** (são `int` validados/clamped),
  só anti-pattern. → usar `TOP (?)`/`-?` para consistência.

---

## ✅ Bem feito (preservar)
- **SQL 100% parametrizado** — nenhuma query com string + input; IN-clauses só com
  `?` dinâmico; WHERE dinâmico só com fragmentos `?` fixos.
- **Sem JWT/segredo de assinatura** — tokens opacos `secrets.token_urlsafe(32)`.
- **App não armazena senha** (auth delegada ao AD/Airflow); **sessão guardada só como
  SHA-256**; expira server-side; logout revoga.
- **RBAC consistente** (`require_perm`/`get_admin_user`) na grande maioria; **audit
  derivado do principal**; sem auto-exclusão/auto-wipe.
- **`/config` mascara segredos**; PowerBI token só no backend; status reporta `✓/✗`.
- **XML seguro a XXE** (`xml.etree`, sem entidades externas).
- **`_safe_project`** barra `../`; **`shlex.quote`** no shell job; **`_JOB_RE`** +
  single-quote no `etl_ds_malha_status` (modelo a copiar no C2).

---

## Ordem sugerida de correção
1. **C1** — rotacionar a senha do AD + remover do código/histórico (ação de infra, urgente).
2. **C4, C6, C5** — fechar os bypasses de auth (gate `/catalogo`, proteger GETs do Airflow, remover `airflow-header`).
3. **C2, C3, A3, M2** — validar `job_name`/`project`/`job_command` (regex no register) + `repr()` na factory + quoting no monitor.
4. **A4, A5, A6, A7** — `_safe_project_name`, CORS sem `*`, rate-limit, headers.
5. **A1, A2** — defaults e segredos em repouso.
6. **M1** — varrer `detail=str(e)`.
