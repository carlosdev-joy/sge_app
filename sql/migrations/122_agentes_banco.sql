-- sql/migrations/122_agentes_banco.sql
-- C1 da spec docs/spec-agentes-ferramenta-banco.md: consulta a banco dos
-- agentes criados pela tela.
--
--   1. dbo.etl_agente.bancos_json — os pares liberados, ex.:
--      '[{"conexao":"dw_prod","banco":"DW"}]'. NULL = nenhum (o agente sem
--      as ferramentas de banco). As conexões são as de dbo.etl_conexao; a
--      API confere cada par novo ao gravar.
--   2. dbo.etl_agente.mascarar_dados — C2: mascarar CPF/CNPJ/e-mail/telefone
--      no que volta das consultas. Padrão LIGADO.
--
-- Idempotente (roda 2×): IF COL_LENGTH. Aplicada pela etapa 6c do deploy.sh.

IF COL_LENGTH('dbo.etl_agente', 'bancos_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_agente ADD bancos_json NVARCHAR(MAX) NULL;
    PRINT '[OK] Coluna etl_agente.bancos_json criada';
END
ELSE
    PRINT '[SKIP] Coluna etl_agente.bancos_json ja existe';
GO

IF COL_LENGTH('dbo.etl_agente', 'mascarar_dados') IS NULL
BEGIN
    ALTER TABLE dbo.etl_agente ADD mascarar_dados BIT NOT NULL
        CONSTRAINT DF_etl_agente_mascarar DEFAULT 1;
    PRINT '[OK] Coluna etl_agente.mascarar_dados criada';
END
ELSE
    PRINT '[SKIP] Coluna etl_agente.mascarar_dados ja existe';
GO
