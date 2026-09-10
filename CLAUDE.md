# ORQUESTRA — Gestão de Pipelines

Plataforma de orquestração de ETLs (DataStage) sobre Apache Airflow, com governança,
monitoramento e operação pela equipe. Backend **FastAPI + SQL Server (MSSQL)**, frontend
**React 19/Vite/Tailwind 3.4**, infraestrutura em **Docker Compose**. Idioma de trabalho:
**português do Brasil** (respostas, comentários, commits, PRs, docs).

## Estrutura do repositório
- `api/` — FastAPI. Working dir é `api/` (imports são `from db import…`, `from routers import…`).
  - `api/main.py` — cria o app e **registra cada router** (no import e na lista de include).
  - `api/routers/` — um arquivo por domínio (pipelines, jobs, execucoes, notificacoes,
    comunicados, admin, datastage, maestro…).
  - `api/services/` — helpers compartilhados (`notify.py`, `dag_reconcile.py`, `job_params.py`,
    `caixa_ia.py`, `maestro.py`…).
  - `api/deps.py` — auth/sessão: `get_current_user`, `require_perm`, `get_admin_user`, `PERM_*`.
    `api/db.py` — `get_db_conn()` (pyodbc/MSSQL, placeholders `?`).
- `ui-react/` — React + Vite + Tailwind. `src/` é o código; `ui-react/dist/` é o build **commitado**.
- `dags/` — DAGs do Airflow (pymssql, placeholders `%s`); operador em `dags/utils/datastage_operator.py`.
  ⚠️ O worker **cacheia `dags/utils/`**: mudança ali exige restart do worker no deploy.
- `sql/migrations/NNN_*.sql` — migrations numeradas e idempotentes; `sql/migrate.py` aplica
  (etapa 6c do `deploy.sh`, com confirmação `[s/N]`).
- `docs/` — specs (`docs/spec-<feature>.md`), release notes (`docs/release-notes/`), manual
  (`docs/MANUAL_USUARIO.md`), catálogo de funcionalidades. `scripts/` — `deploy.sh`, `deploy_prod.sh`.
- `tests/` — pytest na raiz (`pythonpath=api`, pyodbc stubbado); bancadas do front em `tests/js/`
  (sucrase + React mínimo da casa, sem runner JS).

## Convenções inegociáveis
- **Migrations**: próximo número sequencial. SEMPRE idempotente
  (`IF OBJECT_ID('dbo.x','U') IS NULL BEGIN … END`), blocos terminam com `GO`
  (`tests/test_migrations_idempotentes.py` prende). Backend e UI **degradam graciosamente**
  se a tabela não existir (503 nomeando a migration, ou vazio).
- **Router novo** → registrar em `api/main.py` (import + lista de include).
- **Cores da UI**: SEMPRE par claro + escuro. Nunca `bg-*-900` ou `text-*-300` como classe base.
  Use os tokens semânticos (`bg-panel`/`text-ink`/`text-dim`/`border-edge`/`bg-canvas`).
  Padrão completo em @docs/ui-temas-cores.md. **Não reordene objetos de tela sem pedido** claro.
- **Git**: uma branch por fase/feature a partir de `origin/main`; **nunca** push direto na `main`;
  commits convencionais em pt-BR (`feat:`, `fix:`, `docs:`, `chore:`) com o trailer
  `Co-Authored-By`. **O usuário SEMPRE autoriza o merge** — a PR fica aberta até ele dizer
  "merge autorizado" sobre aquela PR; nunca `gh pr merge` por conta própria.
- **Segredos**: nunca no Git (`.env*` está ignorado); chaves de API cifradas em `etl_app_config`
  com o Fernet de `ORQUESTRA_CONN_KEY`; valores Encrypted nunca em log, tela ou provedor de IA.

## Fluxo de trabalho (o processo do usuário — skills em `.claude/skills/`)
1. **Feature nova → spec antes de código**: skill `gerador-spec` → `docs/spec-<feature>.md`
   com fases F1..Fn mergeáveis, escopo OUT, riscos e smoke pós-deploy. O usuário aprova a spec
   ("aprovada") e só então a F1 começa. Bugfix pontual de 1 PR dispensa spec.
2. **Cada fase = 1 PR** (skill `organizacao`): branch, código + testes, validação (abaixo),
   **revisão adversarial obrigatória** pelo agent `qa-adversarial` (`.claude/agents/`) ANTES da PR,
   achados aplicados, PR com 3 blocos (**O que muda / Validação / Deploy**) e o rodapé do Claude
   Code. Depois, parar e pedir a autorização de merge.
3. **Validação antes de toda PR** (skill `testes-automatizados`): `python3 -m pytest tests -q` na
   raiz **comparado com a main** (há falhas pré-existentes — critério é zero falha NOVA);
   no front, `npx tsc -b` (⚠️ `tsc --noEmit` não checa nada neste template), `eslint` comparado
   com o baseline da main por (arquivo, regra, 1ª linha da mensagem) — zero achado novo —,
   `npm run build` e **`dist/` recompilada por último** e commitada; checagem de bytes NUL nos
   fontes. Smoke real no ambiente de DEV quando houver (ver `.claude/memory/vps-ambiente-dev-orquestra.md`).
4. **Ao fechar cada marco** (PR aberta/mergeada, deploy, decisão): atualizar a memória
   (`.claude/memory/` — ver README de lá) com estado, gotchas e pendências de deploy/smoke.
5. Segurança (skill `seguranca`, agent `auditor-seguranca`) quando a mudança toca auth, dados
   pessoais, segredos ou entrada de usuário. Performance: skill `performance`.

## Backend — padrões
- Endpoints usam `Depends(get_current_user | require_perm(PERM_*) | get_admin_user)`.
  Recurso RBAC novo (`tela_*`) entra em DOIS lugares (`RBAC_RECURSOS` + nav) e exige relogin.
- Banco via `get_db_conn()`; toda leitura degrada se a tabela não existir. Larguras `NVARCHAR(n)`
  contam UTF-16 — use `utf16_len`/`cortar_utf16` (`services/ssh_arquivos.py`).
- Id de INSERT: `OUTPUT INSERTED.id` (um `; SELECT SCOPE_IDENTITY()` no mesmo execute deixa o
  pyodbc sem resultado).
- Notificar usuário: `from services.notify import add_notificacao(...)` (best-effort).
- Trabalho que precisa sobreviver a restart NÃO usa BackgroundTask in-process: persista a
  intenção no banco e reconcilie num loop do `lifespan` (padrão `services/dag_reconcile.py`).
- Módulos espelhados entre `api/` e `dags/` (ex.: `services/job_params.py` ↔ `dags/utils/ds_params.py`)
  têm teste anti-drift — mudou num, muda no outro.

## Frontend — padrões
- Dados via `@tanstack/react-query` + `apiFetch` (`src/lib/api.ts`; o erro traz `status` e `detail`).
- Reutilize `src/components/ui/` (Button, Input, Select, Textarea, Modal, Badge, Tabs, Switch).
  Toasts: `toast.success | error | info`. Regex sempre literal `/…/` (string com `\\d` nunca casa).
- Lógica pura em `src/lib/*.ts` (testável na bancada `tests/js/`); componentes só orquestram.

## Deploy (produção Caixa, servidor air-gapped — "dev testa, produção manda")
- `scripts/deploy.sh` puxa a `main`, detecta mudanças e **aplica migrations pendentes via
  `sql/migrate.py`** (etapa 6c, confirmação `[s/N]`), depois atualiza UI/config/dags/api/nginx.
  `config/` → responder **n** (o nginx de produção está à frente do repo).
- pip é **offline**: dependência Python nova exige a `.whl` em `api/wheels/` commitada.
- Cada PR diz no bloco **Deploy** o que exige (migration, `dags/` + restart do worker, `dist/`,
  variáveis de ambiente). Roteiros completos em `docs/release-notes/`.

## Testes
- `pytest` (raiz). Baseline atual: ~5.000 testes, **8 falhas pré-existentes** (`test_api_v2_4` ×4,
  `test_kanban_rodape_card` ×3, `test_smoke` ×1) — não são regressão; compare sempre com a main.

## Orientações versionadas em `.claude/` (para qualquer sessão/máquina)
- `.claude/skills/` — as skills de processo do usuário (`organizacao`, `gerador-spec`,
  `testes-automatizados`, `seguranca`, `performance`, `entrevista-projeto`, `inovacao`,
  `design-impactante-corporativo`, `automacoes`) e as do projeto (`deploy`, `nova-migration`,
  `revisao-pr`, `backlog`).
- `.claude/agents/` — `qa-adversarial` (revisão adversarial antes de toda PR), `auditor-seguranca`,
  e os revisores do projeto (`orquestra-backend`, `-frontend`, `-datastage`, `-deploy`, `-reviewer`).
- `.claude/rules/` — regras por caminho (`api/**`, `ui-react/**`).
- `.claude/memory/` — a memória persistente do projeto (estado das specs, gotchas, pendências);
  índice em `.claude/memory/README.md`. Leia o arquivo do assunto antes de mexer nele.

## Mais contexto (sob demanda)
@docs/ui-temas-cores.md

Outros: `docs/AUDITORIA_TECNICA.md`, `docs/SEGURANCA-DIRETRIZES.md`, `docs/MANUAL_USUARIO.md`.
