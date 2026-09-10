---
name: orquestra-sge-app
description: "Projeto Orquestra = repo GitHub carlosdev-joy/sge_app, clonado em /opt/orquestra-dev; runtime migrado para fora do LCServer"
metadata: 
  node_type: memory
  type: project
  originSessionId: 86cdfd90-5683-49f4-922b-f8ee389b57c6
---

O projeto **Orquestra** (gestão de pipelines ETL DataStage sobre Airflow) vive no repo GitHub **carlosdev-joy/sge_app**, clonado em `/opt/orquestra-dev`.

**Why:** Em 2026-06-29 o ambiente de runtime (Airflow, SQL Server, Postgres, Redis, orquestra-api, nginx) foi **removido completamente do LCServer** (migrado para outro ambiente) — só o código-fonte é trabalhado aqui. O clone anterior foi apagado junto; foi re-clonado em 2026-07-01 para melhorias.

**How to apply:** Para trabalhar no Orquestra, usar `/opt/orquestra-dev` (branch `main`). Stack: FastAPI + MSSQL (`api/`), React/Vite/Tailwind (`ui-react/`, `dist/` commitado), DAGs Airflow (`dags/`), migrations idempotentes em `sql/migrations/`. O repo tem CLAUDE.md próprio com convenções (nunca push direto na main; pytest + npm run build antes de commitar) e skills/subagents em `.claude/`. Não há ambiente de execução local — testes rodam com pyodbc stubbado. Relacionado: [[infra-lcseguranca]].

**Fluxo de deploy (confirmado 2026-07-05):** minha parte termina ao deixar tudo na `main` do GitHub com `npm run build` já commitado; o usuário puxa no servidor rodando `deploy.sh` (clona a main em `/opt/git/checkout_tmp` e sincroniza dist/api/nginx; config/dags/compose só com confirmação). **GOTCHA (2026-07-05): drift do etl_schema_version em prod** — o schema foi aplicado por fora do migrate.py (registrado só até a 021); a etapa 6c acusou 37 "pendentes" e a 025 estourou sintaxe ao reaplicar (literais adjacentes estilo Python — corrigida). Solução: `migrate.py --baseline` (PR #166) registra pendentes sem executar. Roteiro no PR e na skill /deploy.

Desde o PR #164 (mergeado 2026-07-05), o `deploy.sh` tem a **etapa 6c de migrations**: detecta pendências (`migrate.py --dry-run` dentro do container orquestra-api) e PERGUNTA `[s/N]` antes de aplicar — quando o PR incluir `sql/migrations/`, lembrar o usuário de responder **s** (deploy sem terminal nunca aplica sozinho; sintoma de migration esquecida: tela nova não aparece no menu porque a permissão `tela_*` não existe no banco). O script se auto-atualiza a partir do repo no próximo deploy.
