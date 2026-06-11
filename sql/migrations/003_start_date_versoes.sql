-- =============================================================================
-- Migration 003 — dag_start_date em etl_pipeline + Tabela de Versões
-- Banco: DMDB41  Schema: dbo
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Coluna dag_start_date em etl_pipeline
-- -----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline')
      AND name = 'dag_start_date'
)
BEGIN
    ALTER TABLE dbo.etl_pipeline
        ADD dag_start_date DATE NULL;
    PRINT 'Coluna dag_start_date adicionada em dbo.etl_pipeline';
END
ELSE
    PRINT 'Coluna dag_start_date ja existe em dbo.etl_pipeline — ignorado';
GO


-- -----------------------------------------------------------------------------
-- 2. Tabela dbo.etl_versao_ferramenta
--    Registra o histórico de versões / changelog da ferramenta ORQUESTRA.
-- -----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE object_id = OBJECT_ID('dbo.etl_versao_ferramenta')
)
BEGIN
    CREATE TABLE dbo.etl_versao_ferramenta (
        id           INT IDENTITY(1,1) NOT NULL,
        versao       NVARCHAR(20)  NOT NULL,
        titulo       NVARCHAR(200) NOT NULL,
        descricao_md NVARCHAR(MAX) NULL,
        criado_em    DATETIME2     NOT NULL DEFAULT GETDATE(),
        criado_por   NVARCHAR(100) NOT NULL DEFAULT 'admin',

        CONSTRAINT PK_etl_versao_ferramenta PRIMARY KEY CLUSTERED (id ASC)
    );

    CREATE NONCLUSTERED INDEX IX_etl_versao_ferramenta_criado
        ON dbo.etl_versao_ferramenta (criado_em DESC);

    PRINT 'Tabela dbo.etl_versao_ferramenta criada com sucesso';
END
ELSE
    PRINT 'Tabela dbo.etl_versao_ferramenta ja existe — ignorado';
GO


-- -----------------------------------------------------------------------------
-- Verificação final
-- -----------------------------------------------------------------------------
SELECT
    'etl_pipeline'          AS tabela,
    COUNT(*)                AS total_registros,
    SUM(CASE WHEN dag_start_date IS NOT NULL THEN 1 ELSE 0 END) AS com_start_date
FROM dbo.etl_pipeline
UNION ALL
SELECT
    'etl_versao_ferramenta' AS tabela,
    COUNT(*)                AS total_registros,
    NULL
FROM dbo.etl_versao_ferramenta;
GO
