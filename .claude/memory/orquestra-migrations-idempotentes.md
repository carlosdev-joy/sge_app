---
name: orquestra-migrations-idempotentes
description: "Toda migration do sge_app tem de rodar duas vezes sem quebrar; teste trava a regra desde 2026-08-28"
metadata:
  type: project
---

**Regra:** toda migration em `sql/migrations/` precisa poder **rodar duas
vezes**. Travada por `tests/test_migrations_idempotentes.py` (analisa as 100,
com consciência de `BEGIN/END`, ignorando corpo de procedure).

Verificado em 2026-08-28: **99 de 100 já eram**. A exceção era a
`010_datastage_job_log.sql` (CREATE TABLE + 2 índices sem guarda) — corrigida.

**Por que não basta o `etl_schema_version`.** O runner pula o que já foi
aplicado, mas essa é proteção de FORA e não cobre: banco de backup parcial,
migration aplicada à mão sem registrar, deploy interrompido entre o objeto e o
registro, ambiente novo de dump antigo. Nesses casos ela roda de novo e **para
o deploy no meio da sequência**.

**Formas de guarda aceitas** (qualquer condicional serve): `IF OBJECT_ID(...)
IS NULL`, `IF NOT EXISTS (SELECT 1 FROM sys.indexes ...)`, `IF COL_LENGTH(...)
IS NULL`, `IF @var < N`, `CREATE OR ALTER`, `WHERE NOT EXISTS`, `MERGE`.
Índices pedem guarda **própria**: um banco com a tabela mas sem os índices
(deploy morto no meio) ficaria sem eles para sempre.

⚠️ **Limite declarado:** o teste não julga se a condição está CERTA (`IF 1=1`
passaria) — ele prende a ausência de condicional nenhuma.

Ver [[orquestra-chamados-tabela-copiar-notas]] e
[[orquestra-porte-chamados-producao]].
