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
1. **App**: `bash /opt/git/deploy.sh` (fluxo real de produção) — clona a main, sincroniza
   `ui-react/dist`, api (rebuild `orquestra-api`), recria `ui-nginx` com `--no-deps`;
   config/dags/compose só com confirmação.
2. **Migrations**: a etapa 6c do `deploy.sh` detecta pendências e PERGUNTA antes de aplicar
   (roda `sql/migrate.py` dentro do container `orquestra-api` — idempotentes, rastreadas em
   `dbo.etl_schema_version`). Responda **s** quando o PR incluir `sql/migrations/`; sem tela,
   a pergunta assume NÃO e o deploy avisa como aplicar manualmente. Confira com
   `migrate.py --status`. Sintoma de migration esquecida: tela nova não aparece no menu
   (permissão `tela_*` inexistente no banco).
3. **Drift do etl_schema_version**: dezenas de "pendentes" num banco que já funciona =
   schema aplicado por fora do migrate.py (deploy_full/manual). NÃO reaplique — registre
   com `migrate.py --baseline` (pede confirmação; `--ate NNN` limita; `--yes` pula o
   prompt). Caso real 2026-07-05: 37 pendentes em prod e a 025 estourou sintaxe ao
   reaplicar (literais adjacentes, corrigida).

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
