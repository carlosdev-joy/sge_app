---
name: regra-orquestra-pendencias-no-backlog
description: "⚠️ REGRA (24/09/2026): pendências do Orquestra vão para o Backlog de PRODUÇÃO (dbo.etl_backlog) via migration idempotente — não para a memória"
metadata:
  type: feedback
---

Toda pendência/melhoria identificada no Orquestra (escopo OUT de spec, achado de QA adiado, débito) é registrada no
**Admin › Backlog de produção**, por **migration idempotente** em `sql/migrations/` (`INSERT INTO dbo.etl_backlog …
WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'…')`), aplicada na etapa 6c do `deploy.sh`.

**Why:** o usuário quer liberar a memória — "ao invés de buscarmos em memória, colocamos dentro do backlog" (24/09/2026).
A tabela nasceu na migration 035 (colunas: titulo NVARCHAR(200), descricao, tipo feature|bug|debt|spike, area,
prioridade P0..P3, status ideia|refinado|em_andamento|concluido|descartado, tags, ref_pr).

**How to apply:** na PR que identifica a pendência (ou na de fechamento da spec), incluir a migration de backlog. A
memória guarda só o ponteiro/estado da spec, não a lista de pendências. Títulos ≤ 200 chars ([[gotcha-nvarchar-utf16]]);
migration roda 2× sem duplicar ([[orquestra-migrations-idempotentes]]). Origem: [[orquestra-spec-admin-reestruturacao]].
