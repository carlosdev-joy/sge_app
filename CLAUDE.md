# ORQUESTRA — Gestão de Pipelines

Plataforma de orquestração de ETLs (DataStage) sobre Apache Airflow, com governança,
monitoramento e operação pela equipe. Backend **FastAPI + SQL Server (MSSQL)**, frontend
**React/Vite/Tailwind**, infraestrutura em **Docker Compose**.

## Estrutura do repositório
- `api/` — FastAPI. Working dir é `api/` (imports são `from db import…`, `from routers import…`).
  - `api/main.py` — cria o app e **registra cada router** (no import e na lista de include).
  - `api/routers/` — um arquivo por domínio (pipelines, jobs, execucoes, notificacoes,
    comunicados, admin, datastage…).
  - `api/services/` — helpers compartilhados (`notify.py`, `dag_reconcile.py`, `powerbi_client.py`).
  - `api/deps.py` — auth/sessão: `get_current_user`, `require_perm`, `get_admin_user`, `PERM_*`,
    `AIRFLOW_URL/USER/PASSWORD`. `api/db.py` — `get_db_conn()` (pyodbc/MSSQL).
- `ui-react/` — React + Vite + Tailwind. `src/` é o código; `dist/` é o build **commitado**.
- `dags/` — DAGs do Airflow; operador em `dags/utils/datastage_operator.py`.
- `sql/migrations/NNN_*.sql` — migrations numeradas e idempotentes; `sql/migrate.py` aplica.
- `docs/` — base de conhecimento. `scripts/` — `deploy.sh`, `deploy_prod.sh`.

## Convenções inegociáveis
- **Migrations**: próximo número sequencial. SEMPRE idempotente
  (`IF OBJECT_ID('dbo.x','U') IS NULL BEGIN … END`), blocos terminam com `GO`. Backend e UI
  **degradam graciosamente** se a tabela não existir (try/except → vazio).
- **Router novo** → registrar em `api/main.py` (import + lista de include).
- **Cores da UI**: SEMPRE par claro + escuro. Nunca `bg-*-900` ou `text-*-300` como classe base.
  Use os tokens semânticos (`bg-panel`/`text-ink`/`text-dim`/`border-edge`/`bg-canvas`).
  Padrão completo em @docs/ui-temas-cores.md.
- **Git**: desenvolva em branch de feature; **nunca** push direto na `main`; **nunca** abra PR
  sem o usuário pedir. Commits claros, no estilo do projeto.
- **Antes de commitar**: `python -m pytest tests -q` (raiz) e, no frontend,
  `npm run build` em `ui-react/` (recompila `dist/`, que é versionado).

## Backend — padrões
- Endpoints usam `Depends(get_current_user | require_perm(PERM_*) | get_admin_user)`.
- Banco via `get_db_conn()`; toda leitura degrada se a tabela não existir.
- Notificar usuário: `from services.notify import add_notificacao(...)` (best-effort).
- Trabalho que precisa sobreviver a restart NÃO usa BackgroundTask in-process: persista a
  intenção no banco e reconcilie num loop do `lifespan` (padrão `services/dag_reconcile.py`).

## Frontend — padrões
- Dados via `@tanstack/react-query` + `apiFetch` (`src/lib/api.ts`).
- Reutilize `src/components/ui/` (Button, Input, Select, Textarea, Modal, Badge, Tabs).
  Toasts: `toast.success | error | info`.

## Deploy
- `scripts/deploy_prod.sh` puxa a `main`, detecta mudanças e **aplica migrations pendentes via
  `sql/migrate.py`** (idempotentes/rastreadas), depois atualiza UI/config/dags/api/nginx.
- Cirúrgico: `--no-deps` em api/nginx; **não recria** postgres/scheduler/worker. Aplique
  migrations **antes** do restart; tudo degrada se a tabela vier depois.

## Testes
- `pytest` (raiz; `pythonpath=api`, pyodbc é stubbado). Baseline: ~84 passam; há 5 falhas
  pré-existentes de auth em leitura — não são regressão.

## Skills e subagents
- Skills em `.claude/skills/` (`/nova-migration`, `/deploy`, `/revisao-pr`).
- Subagents em `.claude/agents/` (`orquestra-backend`, `-frontend`, `-datastage`, `-deploy`, `-reviewer`).

## Mais contexto (sob demanda)
@docs/ui-temas-cores.md

Outros: `docs/AUDITORIA_TECNICA.md`, `docs/SEGURANCA-DIRETRIZES.md`, `docs/MANUAL_USUARIO.md`.
