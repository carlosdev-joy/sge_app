-- Migration 050: card estruturado por modelo (Fase C do nó de notificação Teams).
-- Estende dbo.etl_msg_template (criada na 049) com os campos que o TEMPLATE
-- passa a definir para montar um Adaptive Card estruturado:
--   • facts        — JSON array de {"label","value"} (values aceitam placeholders
--                    {pipeline} {job} {linhas} {status} {data}); vira FactSet.
--   • cor          — 'auto'|'info'|'success'|'warning'|'error'; vazio/'auto' usa o
--                    status agregado do pipeline na execução.
--   • botao_texto  — rótulo de um botão de link opcional (Action.OpenUrl).
--   • botao_url    — URL do botão (aceita placeholders); vazio = sem botão.
-- Idempotente (guard por COL_LENGTH em cada coluna); blocos terminam com GO.
-- Sem dados destrutivos. Tudo degrada se a coluna não existir (backend/runtime).

IF COL_LENGTH('dbo.etl_msg_template', 'facts') IS NULL
    ALTER TABLE dbo.etl_msg_template ADD facts NVARCHAR(MAX) NULL;
GO

IF COL_LENGTH('dbo.etl_msg_template', 'cor') IS NULL
    ALTER TABLE dbo.etl_msg_template ADD cor VARCHAR(20) NULL;
GO

IF COL_LENGTH('dbo.etl_msg_template', 'botao_texto') IS NULL
    ALTER TABLE dbo.etl_msg_template ADD botao_texto VARCHAR(120) NULL;
GO

IF COL_LENGTH('dbo.etl_msg_template', 'botao_url') IS NULL
    ALTER TABLE dbo.etl_msg_template ADD botao_url NVARCHAR(1000) NULL;
GO
