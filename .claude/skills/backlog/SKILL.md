---
description: >
  Registra itens de backlog do ORQUESTRA e gera o script SQL idempotente automaticamente.
  Use para "anotar no backlog", "registrar ideia", "criar tarefa", "gerar script de backlog".
argument-hint: "registrar|listar|gerar-script <texto>"
---

# Backlog — ORQUESTRA

O backlog vive em `dbo.etl_backlog` (banco MSSQL do ORQUESTRA). Se a tabela ainda não
existir, a primeira execução gera a migration de criação no padrão do projeto.

## registrar
1. Extraia do pedido: `titulo`, `descricao`, `tipo` (feature|bug|debt|spike), `area`
   (backend|frontend|datastage|deploy|infra), `prioridade` (P0..P3).
2. Se `dbo.etl_backlog` não existir, crie a próxima migration `sql/migrations/NNN_backlog.sql`
   idempotente (`IF OBJECT_ID('dbo.etl_backlog','U') IS NULL ... GO`).
3. Gere o `INSERT` do item (script versionável; ou via endpoint `/admin` se existir).
4. Confirme o registro (id/título).

## listar
- Leia `dbo.etl_backlog` por status/prioridade (degrada para vazio se a tabela faltar).

## gerar-script
- A partir de um item `refinado`, crie o esqueleto da entrega no padrão do projeto:
  migration idempotente + router/serviço + teste, já preenchido com título/descrição.

Convenções: ver `CLAUDE.md` (migrations idempotentes, numeração sequencial, degradação
graciosa). Campos sugeridos: id, titulo, descricao, tipo, area, prioridade,
status (ideia|refinado|em_andamento|concluido|descartado), origem, ref_pr, criado_em.
