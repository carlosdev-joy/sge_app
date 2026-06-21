---
description: >
  Roteiro de deploy do ORQUESTRA em produção, incluindo migrations. Use quando o usuário pedir
  "deploy", "subir para produção", "roteiro de deploy", "aplicar migrations".
---

# Deploy — ORQUESTRA

> O deploy real roda no servidor. Esta skill é o roteiro/checklist a seguir e validar.

## Antes
- `docker compose ps` (tudo Up/healthy); `docker compose exec postgres pg_isready`.
- Evite janela com execução DataStage longa em voo (o operador re-anexa, mas evite risco).
- Backup do banco antes de migrations.

## Aplicar
1. **Migrations primeiro**: `deploy_prod.sh` detecta mudanças em `sql/migrations/` e aplica as
   pendentes via `sql/migrate.py` (idempotentes, rastreadas). Confira com `migrate.py --status`.
2. **App**: `bash scripts/deploy_prod.sh` (ou `deploy.sh`) — sincroniza `ui-react/dist`, config,
   dags, api; rebuild `orquestra-api` e recria `ui-nginx` com `--no-deps`.

## Riscos (importante)
- O deploy padrão é cirúrgico e **não recria** postgres/scheduler/worker — não reproduz a queda
  de "heartbeat / could not translate host name postgres" (isso é evento de rede/infra).
- **Não** rode `docker compose up -d` sem `--no-deps`, nem `down/restart` global, com jobs rodando.
- Se o `docker-compose.yaml` novo mudou o bloco `networks:`, o `up` pode recriar a rede e dar blip
  de DNS — confira antes.

## Validar pós-deploy
- `curl -s http://localhost/orquestra/health`; `docker compose ps`.
- `docker compose logs --tail=20 orquestra-api | grep DAG-RECONCILE` → "loop iniciado".
- Fumaça nas telas alteradas (sininho, comunicados, gerar-dag, etc.).
